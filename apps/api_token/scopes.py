"""
API token scopes and their enforcement on the GraphQL schema.

Every GraphQL object/interface type carries a type tag (`type_scope`) and fields can carry a field tag
(`field_scope`). For requests authenticated with an API token, `ApiTokenScopeExtension` checks each resolved
field against:
- the field tag, if any
- the type tag of the field's return type (lists and non-null wrappers are unwrapped)

Rules (token requests only, session requests are not checked):
- An untagged return type is denied (fail closed). For an interface or union return type, the interface and
  every possible concrete type must be tagged, and the token needs the scopes of all of them.
- `ScopeTag.SESSION_ONLY` on a field or type is denied.
- `ScopeTag.ROOT` types (Query, Mutation, public/private roots, `UserMeType`) require a tag on each of their fields,
  scalars included.
- `ScopeTag.NO_SCOPE` needs no scope: containers (pagination, mutation responses), value objects.
- Missing scopes raise a GraphQL error on that field: `missing scope: <scope>`.
"""

import enum
import functools
import typing

from django.db import models
from django.utils.translation import gettext_lazy as _
from graphql import (
    GraphQLError,
    GraphQLField,
    GraphQLInterfaceType,
    GraphQLNamedType,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLUnionType,
    get_named_type,
)
from strawberry.extensions import SchemaExtension
from strawberry.schema.schema_converter import GraphQLCoreConverter
from strawberry.types.base import StrawberryObjectDefinition

if typing.TYPE_CHECKING:
    from graphql import GraphQLResolveInfo


class ApiTokenScope(models.TextChoices):
    """
    Per-resource scopes. A write scope also grants read access to the same resource.
    """

    TIME_ENTRY_READ = "time_entry:read", _("Time entries: read")
    TIME_ENTRY_WRITE = "time_entry:write", _("Time entries: write")
    JOURNAL_READ = "journal:read", _("Journal: read")
    JOURNAL_WRITE = "journal:write", _("Journal: write")
    PROJECT_READ = "project:read", _("Projects: read")
    USER_READ = "user:read", _("Users: read")
    EVENT_READ = "event:read", _("Events: read")

    # Extra fields of `enums { ApiTokenScopes }` items (main/graphql/enums.py)
    __enum_collection_fields__ = ("description", "resource", "resource_label", "resource_description")

    @property
    def description(self) -> str:
        return str(API_TOKEN_SCOPE_DESCRIPTIONS[self])

    @property
    def resource(self) -> str:
        return self.value.partition(":")[0]

    @property
    def resource_label(self) -> str:
        return str(API_TOKEN_RESOURCES[self.resource][0])

    @property
    def resource_description(self) -> str:
        return str(API_TOKEN_RESOURCES[self.resource][1])


API_TOKEN_SCOPE_DESCRIPTIONS = {
    ApiTokenScope.TIME_ENTRY_READ: _("Read your time entries. Daily time summaries also need Journal: read."),
    ApiTokenScope.TIME_ENTRY_WRITE: _("Create, update and delete your time entries."),
    ApiTokenScope.JOURNAL_READ: _(
        "Read your journal, leave and work-from-home entries. With Users: read, also today's leave and"
        " work-from-home status of every user.",
    ),
    ApiTokenScope.JOURNAL_WRITE: _("Update your journal text, leave and work-from-home entries."),
    ApiTokenScope.PROJECT_READ: _("Read all clients, contractors, projects, contracts, tasks and deadlines."),
    ApiTokenScope.USER_READ: _("Read the profiles of all users."),
    ApiTokenScope.EVENT_READ: _("Read events and holidays."),
}


# resource: (label, description)
API_TOKEN_RESOURCES = {
    "time_entry": (_("Time entries"), _("Your time entries and daily time summaries (with Journal: read).")),
    "journal": (
        _("Journal (incl. leave & WFH)"),
        _("Your journal text, leave and work-from-home entries, and today's leave and work-from-home status of every user."),
    ),
    "project": (_("Projects"), _("All clients, contractors, projects, contracts, tasks and deadlines.")),
    "user": (_("Users"), _("Profiles of all users.")),
    "event": (_("Events"), _("Events and holidays.")),
}


def with_implied_scopes(scopes: typing.Iterable[str]) -> set[str]:
    """
    Add `x:read` for every `x:write`.
    """
    result = set(scopes)
    for scope in scopes:
        resource, _sep, action = scope.partition(":")
        if action == "write" and f"{resource}:read" in ApiTokenScope.values:
            result.add(f"{resource}:read")
    return result


class ScopeTag(enum.Enum):
    NO_SCOPE = "no_scope"
    """No scope needed. Access is controlled by the parent field (containers, value objects, public roots)."""

    SESSION_ONLY = "session_only"
    """Never available to API tokens."""

    ROOT = "root"
    """No scope needed for the type itself, but each of its fields (scalars included) must carry a field tag."""


Tag = ScopeTag | frozenset[ApiTokenScope]

TYPE_TAG_ATTR = "__api_token_scope__"
FIELD_TAG_KEY = "api_token_scope"

_TypeT = typing.TypeVar("_TypeT", bound=type)


def _make_tag(values: tuple[ApiTokenScope | ScopeTag, ...]) -> Tag:
    if len(values) == 1 and isinstance(values[0], ScopeTag):
        return values[0]
    if values and all(isinstance(value, ApiTokenScope) for value in values):
        return frozenset(typing.cast("tuple[ApiTokenScope, ...]", values))
    raise ValueError(f"Use one ScopeTag or one or more ApiTokenScope values, got {values!r}")


def type_scope(*values: ApiTokenScope | ScopeTag) -> typing.Callable[[_TypeT], _TypeT]:
    """
    Class decorator to tag a strawberry type. Tags are not inherited by subclasses.
    """
    tag = _make_tag(values)

    def decorator(cls: _TypeT) -> _TypeT:
        setattr(cls, TYPE_TAG_ATTR, tag)
        return cls

    return decorator


def field_scope(*values: ApiTokenScope | ScopeTag) -> dict[str, Tag]:
    """
    Field metadata to tag a strawberry field: `@strawberry.field(metadata=field_scope(...))`.
    """
    return {FIELD_TAG_KEY: _make_tag(values)}


def get_type_tag(graphql_type: GraphQLNamedType) -> Tag | None:
    definition = graphql_type.extensions.get(GraphQLCoreConverter.DEFINITION_BACKREF)
    if not isinstance(definition, StrawberryObjectDefinition):
        return None
    # Specialized generics (e.g. CountList[ProjectType]) use the tag of the generic type
    while definition.concrete_of is not None:
        definition = definition.concrete_of
    return definition.origin.__dict__.get(TYPE_TAG_ATTR)


def get_field_tag(graphql_field: GraphQLField) -> Tag | None:
    strawberry_field = graphql_field.extensions.get(GraphQLCoreConverter.DEFINITION_BACKREF)
    if strawberry_field is None:
        return None
    return (strawberry_field.metadata or {}).get(FIELD_TAG_KEY)


class Denied(typing.NamedTuple):
    reason: str


def get_return_type_tags(schema: GraphQLSchema, return_type: GraphQLNamedType) -> list[Tag | None] | None:
    """
    Tags that apply to a field returning `return_type`, or None for leaf types (scalars, enums).
    Abstract types use their own tag (interfaces) and the tags of every possible concrete type, since the
    concrete type is only known after the field resolves.
    """
    if isinstance(return_type, GraphQLObjectType):
        return [get_type_tag(return_type)]
    if isinstance(return_type, GraphQLInterfaceType):
        return [get_type_tag(return_type), *(get_type_tag(t) for t in schema.get_possible_types(return_type))]
    if isinstance(return_type, GraphQLUnionType):
        return [get_type_tag(t) for t in schema.get_possible_types(return_type)]
    return None


@functools.cache
def get_field_requirement(
    schema: GraphQLSchema,
    parent_type: GraphQLObjectType,
    field_name: str,
) -> frozenset[ApiTokenScope] | Denied:
    """
    Scopes a token needs to resolve `parent_type.field_name`, or Denied.
    """
    if field_name.startswith("__") or parent_type.name.startswith("__"):
        # Introspection
        return frozenset()
    graphql_field = parent_type.fields[field_name]
    denied = Denied(f"{parent_type.name}.{field_name} is not available to API tokens")
    required: set[ApiTokenScope] = set()

    field_tag = get_field_tag(graphql_field)
    if field_tag is None and get_type_tag(parent_type) is ScopeTag.ROOT:
        return denied
    if field_tag is ScopeTag.SESSION_ONLY:
        return denied
    if isinstance(field_tag, frozenset):
        required |= field_tag

    for type_tag in get_return_type_tags(schema, get_named_type(graphql_field.type)) or []:
        if type_tag is None or type_tag is ScopeTag.SESSION_ONLY:
            return denied
        if isinstance(type_tag, frozenset):
            required |= type_tag
    return frozenset(required)


SCOPE_DENIAL_CODES = frozenset({"token_not_allowed", "missing_scope"})


def is_scope_denial(error: GraphQLError) -> bool:
    return (error.extensions or {}).get("code") in SCOPE_DENIAL_CODES


class ApiTokenScopeExtension(SchemaExtension):
    """
    Checks the scopes of API token requests for every resolved field. Session requests pass through.
    """

    @typing.override
    def resolve(self, _next, root, info: "GraphQLResolveInfo", *args, **kwargs):
        request = getattr(info.context, "request", None)
        token = getattr(request, "api_token", None)
        if token is None:
            return _next(root, info, *args, **kwargs)

        requirement = get_field_requirement(info.schema, info.parent_type, info.field_name)
        if isinstance(requirement, Denied):
            raise GraphQLError(requirement.reason, extensions={"code": "token_not_allowed"})
        token_scopes = with_implied_scopes(token.scopes)
        missing = sorted(scope.value for scope in requirement if scope.value not in token_scopes)
        if missing:
            raise GraphQLError(
                f"missing scope: {', '.join(missing)}",
                extensions={"code": "missing_scope", "scopes": missing},
            )
        return _next(root, info, *args, **kwargs)
