"""
Request size limits applied to every GraphQL operation (sessions and API tokens).

Measured on the web app's operations: largest depth 6, no aliases, ~130 tokens (with the `__typename` fields the
client adds). The standard introspection query used by GraphiQL and codegen (graphql-js / graphql-core
`getIntrospectionQuery` with all options) has ~210 tokens, introspection depth 14 and 1 introspection list level
(`fields`).

The extensions are classes without arguments: strawberry instantiates them per operation (a shared instance would
have its `execution_context` overwritten by concurrent operations).
"""

import typing

from graphql import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    GraphQLError,
    GraphQLSyntaxError,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionSetNode,
    get_operation_ast,
    parse,
)
from graphql.validation import ValidationContext, ValidationRule
from strawberry.extensions import AddValidationRules, SchemaExtension

MAX_QUERY_DEPTH = 12
MAX_ALIASES = 15
MAX_TOKENS = 500
MAX_INTROSPECTION_DEPTH = 16
"""Depth of a `__schema` / `__type` selection, introspection fields included."""
MAX_INTROSPECTION_LISTS = 2
"""Nested `fields` / `interfaces` / `possibleTypes` / `inputFields` in an introspection selection (as graphql-js
`MaxIntrospectionDepthRule`). These lists branch, so each extra level multiplies the response size."""

INTROSPECTION_ROOTS = frozenset({"__schema", "__type"})
INTROSPECTION_LISTS = frozenset({"fields", "interfaces", "possibleTypes", "inputFields"})

LIMIT_EXCEEDED = "limit_exceeded"


def limit_error(message: str, limit: str, nodes=None) -> GraphQLError:
    return GraphQLError(message, nodes, extensions={"code": LIMIT_EXCEEDED, "limit": limit})


class SelectionStats(typing.NamedTuple):
    depth: int
    """A field with a selection counts 1 + the depth of its selection; leaf fields count 0. Introspection fields
    (and their selections) are not counted here."""
    aliases: int
    """Aliased fields, with every fragment spread expanded."""
    all_depth: int
    """Like `depth`, introspection fields included."""
    lists: int
    """Most nested INTROSPECTION_LISTS fields on one path."""
    introspection_depth: int
    """Largest `all_depth` of a `__schema` / `__type` field in the selection."""
    introspection_lists: int
    """Largest `lists` inside a `__schema` / `__type` field in the selection."""


EMPTY_STATS = SelectionStats(0, 0, 0, 0, 0, 0)


def merge_stats(stats: typing.Iterable[SelectionStats]) -> SelectionStats:
    stats = list(stats)
    if not stats:
        return EMPTY_STATS
    return SelectionStats(
        depth=max(item.depth for item in stats),
        aliases=sum(item.aliases for item in stats),
        all_depth=max(item.all_depth for item in stats),
        lists=max(item.lists for item in stats),
        introspection_depth=max(item.introspection_depth for item in stats),
        introspection_lists=max(item.introspection_lists for item in stats),
    )


class DocumentStats:
    """
    Size of each operation in a document. Each fragment is measured once and reused for every spread, so the cost
    is linear in the document size. Unknown and cyclic fragment spreads count as empty; graphql-core's own
    validation rules reject such documents.
    """

    def __init__(self, fragments: dict[str, FragmentDefinitionNode]) -> None:
        self.fragments = fragments
        self.fragment_stats: dict[str, SelectionStats] = {}
        self.in_progress: set[str] = set()

    def of_fragment(self, name: str) -> SelectionStats:
        if name in self.fragment_stats:
            return self.fragment_stats[name]
        fragment = self.fragments.get(name)
        if fragment is None or name in self.in_progress:
            return EMPTY_STATS
        self.in_progress.add(name)
        stats = self.of_selection_set(fragment.selection_set)
        self.in_progress.discard(name)
        self.fragment_stats[name] = stats
        return stats

    def of_field(self, field: FieldNode) -> SelectionStats:
        child = self.of_selection_set(field.selection_set)
        name = field.name.value
        all_depth = 1 + child.all_depth if field.selection_set else 0
        lists = child.lists + (1 if name in INTROSPECTION_LISTS else 0)
        is_introspection = name.startswith("__")
        introspection_depth = child.introspection_depth
        introspection_lists = child.introspection_lists
        if name in INTROSPECTION_ROOTS:
            introspection_depth = max(introspection_depth, all_depth)
            introspection_lists = max(introspection_lists, lists)
        return SelectionStats(
            depth=1 + child.depth if field.selection_set and not is_introspection else 0,
            aliases=child.aliases + (1 if field.alias else 0),
            all_depth=all_depth,
            lists=lists,
            introspection_depth=introspection_depth,
            introspection_lists=introspection_lists,
        )

    def of_selection_set(self, selection_set: SelectionSetNode | None) -> SelectionStats:
        stats = []
        for selection in selection_set.selections if selection_set else ():
            if isinstance(selection, FieldNode):
                stats.append(self.of_field(selection))
            elif isinstance(selection, InlineFragmentNode):
                stats.append(self.of_selection_set(selection.selection_set))
            elif isinstance(selection, FragmentSpreadNode):
                stats.append(self.of_fragment(selection.name.value))
        return merge_stats(stats)


class DocumentLimitsValidator(ValidationRule):
    def __init__(self, validation_context: ValidationContext) -> None:
        super().__init__(validation_context)
        definitions = validation_context.document.definitions
        stats = DocumentStats(
            {
                definition.name.value: definition
                for definition in definitions
                if isinstance(definition, FragmentDefinitionNode)
            },
        )
        for operation in definitions:
            if not isinstance(operation, OperationDefinitionNode):
                continue
            operation_stats = stats.of_selection_set(operation.selection_set)
            name = operation.name.value if operation.name else "anonymous"
            if operation_stats.depth > MAX_QUERY_DEPTH:
                self.report_error(
                    limit_error(f"'{name}' exceeds maximum operation depth of {MAX_QUERY_DEPTH}", "depth", operation),
                )
            if operation_stats.aliases > MAX_ALIASES:
                self.report_error(
                    limit_error(f"{operation_stats.aliases} aliases found. Allowed: {MAX_ALIASES}", "aliases", operation),
                )
            if (
                operation_stats.introspection_depth > MAX_INTROSPECTION_DEPTH
                or operation_stats.introspection_lists > MAX_INTROSPECTION_LISTS
            ):
                self.report_error(limit_error("Maximum introspection depth exceeded", "introspection_depth", operation))


class DocumentLimits(AddValidationRules):
    """
    Rejects operations deeper than MAX_QUERY_DEPTH, with more than MAX_ALIASES aliased fields (fragment spreads
    expanded), or with introspection selections beyond MAX_INTROSPECTION_DEPTH / MAX_INTROSPECTION_LISTS.
    """

    def __init__(self, *, execution_context=None) -> None:
        super().__init__([DocumentLimitsValidator])


class MaxTokensLimiter(SchemaExtension):
    """
    Parses the document with graphql-core's `max_tokens` limit. strawberry's own MaxTokensLimiter only sets parse
    options, which its async execution path does not pass to the parser.
    """

    @typing.override
    def on_parse(self):
        execution_context = self.execution_context
        if execution_context.graphql_document is None and execution_context.query:
            try:
                execution_context.graphql_document = parse(execution_context.query, max_tokens=MAX_TOKENS)
            except GraphQLSyntaxError as error:
                if f"Document contains more than {MAX_TOKENS} tokens." in error.message:
                    raise limit_error(error.message, "tokens") from None
                raise
        yield


INVALID_OPERATION = "invalid_operation"


class OperationSelectionCheck(SchemaExtension):
    """
    Rejects a document in which the requested operation can't be found (unknown `operationName`, or no operation
    at all) with a request error. strawberry raises a RuntimeError for these otherwise. Without `operationName`,
    strawberry runs the first operation.
    """

    @typing.override
    def on_parse(self):
        yield
        execution_context = self.execution_context
        document = execution_context.graphql_document
        if document is None:
            return
        if get_operation_ast(document, execution_context.operation_name) is not None:
            return
        if execution_context.operation_name:
            message = f"Unknown operation named '{execution_context.operation_name}'."
        else:
            message = "Must provide an operation."
        raise GraphQLError(message, extensions={"code": INVALID_OPERATION})
