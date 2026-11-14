import types

import strawberry
from graphql import (
    GraphQLInterfaceType,
    GraphQLNamedType,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLUnionType,
    get_named_type,
)

from apps.api_token.scopes import (
    ApiTokenScope,
    ApiTokenScopeExtension,
    ScopeTag,
    field_scope,
    get_field_tag,
    get_type_tag,
    type_scope,
)
from main.graphql.schema import schema
from main.tests import TestCase


def find_untagged(graphql_schema: GraphQLSchema) -> list[str]:
    """
    Walk every type reachable from the root operation types and list what lacks a scope tag.
    """
    problems: list[str] = []
    roots = [t for t in (graphql_schema.query_type, graphql_schema.mutation_type) if t is not None]
    seen: set[str] = set()
    queue: list[GraphQLNamedType] = list(roots)
    while queue:
        graphql_type = queue.pop()
        if graphql_type.name in seen or graphql_type.name.startswith("__"):
            continue
        seen.add(graphql_type.name)
        if isinstance(graphql_type, GraphQLUnionType):
            # Unions use the tags of their members
            queue.extend(graphql_type.types)
            continue
        type_tag = get_type_tag(graphql_type)
        if type_tag is None:
            problems.append(f"type {graphql_type.name}")
        if isinstance(graphql_type, GraphQLInterfaceType):
            queue.extend(graphql_schema.get_possible_types(graphql_type))
        if isinstance(graphql_type, GraphQLObjectType | GraphQLInterfaceType):
            queue.extend(graphql_type.interfaces)
        if isinstance(graphql_type, GraphQLObjectType | GraphQLInterfaceType):
            for field_name, field in graphql_type.fields.items():
                if type_tag is ScopeTag.ROOT and get_field_tag(field) is None:
                    problems.append(f"field {graphql_type.name}.{field_name}")
                named = get_named_type(field.type)
                if isinstance(named, GraphQLObjectType | GraphQLInterfaceType | GraphQLUnionType):
                    queue.append(named)
    return sorted(problems)


class TestSchemaScopeTags(TestCase):
    def test_all_reachable_types_and_root_fields_are_tagged(self):
        assert find_untagged(schema._schema) == []

    def test_public_roots_and_me_are_root_types(self):
        """
        Every field on these types, scalars included, needs an explicit tag; new untagged fields are closed to tokens.
        """
        for type_name in [
            "Query",
            "Mutation",
            "PublicQuery",
            "PrivateQuery",
            "PublicMutation",
            "PrivateMutation",
            "UserMeType",
        ]:
            assert get_type_tag(schema._schema.type_map[type_name]) is ScopeTag.ROOT, type_name

    def test_walk_reports_untagged_scalars_on_root_types(self):
        @type_scope(ScopeTag.ROOT)
        @strawberry.type
        class Me:
            tagged: str = strawberry.field(default="x", metadata=field_scope(ScopeTag.NO_SCOPE))
            untagged_scalar: str = "secret"

        @type_scope(ScopeTag.ROOT)
        @strawberry.type
        class Query:
            @strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
            def me(self) -> Me:
                return Me()

        assert find_untagged(strawberry.Schema(query=Query)._schema) == ["field Me.untaggedScalar"]

    def test_walk_reports_untagged_types_and_root_fields(self):
        @strawberry.type
        class Untagged:
            value: str

        @type_scope(ScopeTag.ROOT)
        @strawberry.type
        class Query:
            @strawberry.field
            def untagged(self) -> Untagged:
                return Untagged(value="x")

        assert find_untagged(strawberry.Schema(query=Query)._schema) == [
            "field Query.untagged",
            "type Untagged",
        ]

    def test_walk_reports_untagged_implemented_interfaces(self):
        @strawberry.interface
        class UntaggedInterface:
            value: str

        @type_scope(ApiTokenScope.EVENT_READ)
        @strawberry.type
        class Tagged(UntaggedInterface): ...

        @type_scope(ScopeTag.ROOT)
        @strawberry.type
        class Query:
            @strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
            def tagged(self) -> Tagged:
                return Tagged(value="x")

        assert find_untagged(strawberry.Schema(query=Query)._schema) == ["type UntaggedInterface"]


class TestAbstractReturnTypes(TestCase):
    """
    A field returning an interface needs the scopes of the interface and of every type implementing it.
    """

    @staticmethod
    def _schema(untagged_implementation: bool):
        @type_scope(ScopeTag.NO_SCOPE)
        @strawberry.interface
        class Node:
            value: str

        @type_scope(ApiTokenScope.EVENT_READ)
        @strawberry.type
        class EventNode(Node): ...

        @type_scope(ApiTokenScope.PROJECT_READ)
        @strawberry.type
        class ProjectNode(Node): ...

        types_ = [EventNode, ProjectNode]
        if untagged_implementation:

            @strawberry.type
            class UntaggedNode(Node): ...

            types_.append(UntaggedNode)

        @type_scope(ScopeTag.ROOT)
        @strawberry.type
        class Query:
            @strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
            def node(self) -> Node | None:
                return EventNode(value="x")

        return strawberry.Schema(query=Query, types=types_, extensions=[ApiTokenScopeExtension])

    def test_needs_scopes_of_all_implementations(self):
        test_schema = self._schema(untagged_implementation=False)
        result = test_schema.execute_sync(
            "{ node { value } }",
            context_value=TestFailClosed._context([ApiTokenScope.EVENT_READ.value]),
        )
        assert result.errors is not None
        assert [error.message for error in result.errors] == ["missing scope: project:read"]

        result = test_schema.execute_sync(
            "{ node { value } }",
            context_value=TestFailClosed._context([ApiTokenScope.EVENT_READ.value, ApiTokenScope.PROJECT_READ.value]),
        )
        assert result.errors is None
        assert result.data == {"node": {"value": "x"}}

    def test_untagged_implementation_denied(self):
        test_schema = self._schema(untagged_implementation=True)
        result = test_schema.execute_sync(
            "{ node { value } }",
            context_value=TestFailClosed._context([scope.value for scope in ApiTokenScope]),
        )
        assert result.errors is not None
        assert [error.message for error in result.errors] == ["Query.node is not available to API tokens"]


class TestFailClosed(TestCase):
    """
    Untagged types and untagged root fields are denied to tokens.
    """

    @staticmethod
    def _schema():
        @strawberry.type
        class Untagged:
            value: str

        @type_scope(ApiTokenScope.EVENT_READ)
        @strawberry.type
        class Tagged:
            value: str
            untagged: Untagged | None

        @type_scope(ScopeTag.ROOT)
        @strawberry.type
        class Query:
            @strawberry.field(metadata=field_scope(ScopeTag.NO_SCOPE))
            def tagged(self) -> Tagged:
                return Tagged(value="ok", untagged=Untagged(value="secret"))

            @strawberry.field
            def untagged_root_scalar(self) -> str | None:
                return "secret"

        return strawberry.Schema(query=Query, extensions=[ApiTokenScopeExtension])

    @staticmethod
    def _context(scopes: list[str] | None):
        token = None if scopes is None else types.SimpleNamespace(scopes=scopes)
        return types.SimpleNamespace(request=types.SimpleNamespace(api_token=token))

    def test_untagged_denied_for_tokens(self):
        test_schema = self._schema()
        result = test_schema.execute_sync(
            "{ tagged { value untagged { value } } untaggedRootScalar }",
            context_value=self._context([ApiTokenScope.EVENT_READ.value]),
        )
        assert result.errors is not None
        assert sorted(error.message for error in result.errors) == [
            "Query.untaggedRootScalar is not available to API tokens",
            "Tagged.untagged is not available to API tokens",
        ]

    def test_untagged_allowed_for_sessions(self):
        test_schema = self._schema()
        result = test_schema.execute_sync(
            "{ tagged { value untagged { value } } untaggedRootScalar }",
            context_value=self._context(None),
        )
        assert result.errors is None
        assert result.data == {
            "tagged": {"value": "ok", "untagged": {"value": "secret"}},
            "untaggedRootScalar": "secret",
        }
