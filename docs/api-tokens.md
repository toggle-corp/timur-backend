# API tokens

Personal API tokens let a user call the GraphQL API (`/graphql/`) from scripts. A token acts as the user who created it, limited to the scopes picked at creation.

Code: `apps/api_token/`.

## Token

- Format: `tc_timur_` followed by 40 random characters (`[A-Za-z0-9]`).
- Storage: only the SHA-256 hash of the full token and `prefix` (the first 8 random characters, after `tc_timur_`) are stored. The full token is returned once, in the `createApiToken` response, and can't be recovered.
- Fields: `user`, `name`, `prefix`, `hash`, `scopes`, `created_at`, `expires_at`, `last_used_at`, `revoked_at`, `expiry_reminder_sent_at`, `expired_notice_sent_at`.
- Tokens can't be changed after creation (no rename, no scope change, no new expiry).
- Name: trimmed, not blank, at most 100 characters, printable characters only. Unique per user among active tokens (case-insensitive).
- Limit: 10 active tokens per user. Expired and revoked tokens don't count.
- The name and limit checks run while holding a lock on the user row, so parallel creates for one user can't exceed them.
- Expiry: `expiresAt` is a `DateTime`. The client sends the end of the chosen day in the user's local time, converted to UTC. It must be more than 1 hour and at most 367 days from now (the extra days let the end of the local day one year ahead fit in every timezone, with room for client clock skew). A value without an offset is read as UTC. It is stored as given, in UTC. There is no "never expires" option.
- Times: the API takes and returns datetimes in ISO 8601, and returns them in UTC.
- Revoke: sets `revoked_at` (soft delete). `revokeApiToken` on an expired token returns the error "Token has already expired". Superusers can still revoke expired tokens in Django admin.
- `myApiTokens` lists active tokens, plus expired and revoked tokens for 30 days after `expires_at` or `revoked_at`.
- Status: `REVOKED` if `revoked_at` is set, else `EXPIRED` if `expires_at` has passed, else `ACTIVE`.

## Authentication

Send the token in the `Authorization` header:

```
Authorization: Bearer tc_timur_...
```

- Only the GraphQL view reads this header (`CustomAsyncGraphQLView.dispatch`, `dispatch_with_api_token` in `apps/api_token/auth.py`). Other endpoints ignore it.
- When a request has an `Authorization` header, the token decides the request user and the session cookie is ignored, even if the token is invalid. Requests without an `Authorization` header use the session.
- The header must hold exactly one `Bearer <token>` value. The scheme is case-insensitive and may be followed by any whitespace. Anything else is rejected as `invalid_token`: another scheme (`Basic`, `Token`, ...), a missing token, extra parts, or several values (repeated `Authorization` headers arrive comma-joined).
- Every GraphQL response carries `Vary: Authorization`, so a cache never reuses a response without a token for a request with one. Responses to requests with an `Authorization` header (including 401s and 500 error pages) also carry `Cache-Control: private, no-store`. Both are set by `main.middlewares.GraphQLCacheHeadersMiddleware`, which also sees the responses Django builds for unhandled exceptions.
- If the token can't be used, the view returns HTTP 401 with `WWW-Authenticate: Bearer ...` before running the query:

  ```json
  {"errors": [{"message": "API token has expired", "extensions": {"code": "token_expired"}}]}
  ```

  | Code | When |
  |---|---|
  | `invalid_token` | Empty, malformed (other scheme, no token, extra parts, several values) or unknown token |
  | `token_revoked` | `revoked_at` is set |
  | `token_expired` | `expires_at` has passed |
  | `user_inactive` | The user has `is_active=False`. The token is not revoked and works again if the user is reactivated |

- `last_used_at` is written at most once every 60 seconds per token.
- Every request with an `Authorization` header writes one INFO log line `API token request` (logger `apps.api_token.auth`). Its context has the client IP, the HTTP `status` and a `result`:

  | `result` | When | Extra fields |
  |---|---|---|
  | `executed` | The operation ran (it may still have field errors, such as missing scopes) | `token_id`, `user_id`, `operation_name` |
  | `pre_execution_error` | Rejected before any resolver ran | same, plus `error` (category, below) and, for `limit_exceeded`, `limit` (`depth`, `aliases` or `tokens`) |
  | `http_error` | Rejected by the view (a body that isn't JSON, no query, a mutation over GET) or the view raised (`status` 500) | `token_id`, `user_id`, `operation_name` when known |
  | `unauthorized` | HTTP 401 | `code`; `token_id` and `user_id` when the token was found (revoked, expired, inactive user); `token_prefix` when the value looks like a token |

  `error` is one of `syntax_error`, `validation_error`, `variable_error`, `invalid_operation` (unknown `operationName`, or no operation in the document), `limit_exceeded` or `internal_error`. Error messages are never logged: they can quote the query or submitted variable values.

  `ApiTokenAuditExtension` records the operation name and outcome; `dispatch_with_api_token` writes the line. The IP is the rightmost `X-Forwarded-For` entry (added by the ingress), else `REMOTE_ADDR`. The token itself is never logged, at most its 8-character prefix.
- No rate limiting.

## Scopes

| Scope | Grants |
|---|---|
| `time_entry:read` | Your own time entries (`myTimeEntries`). `dailySummary` needs `time_entry:read` and `journal:read` |
| `time_entry:write` | `createTimeEntry`, `updateTimeEntry`, `bulkTimeEntry`, `cudTimeEntry` |
| `journal:read` | Your journal (text, leave, work from home). With `user:read`, also today's leave and work-from-home status of every user (`leaveToday`, `workFromHomeToday`) |
| `journal:write` | `updateJournal` |
| `project:read` | Clients, contractors, projects, contracts, tasks, deadlines |
| `user:read` | Profiles of all users (`UserType`) |
| `event:read` | Events and holidays |

- A write scope includes read. On create, `x:read` is stored with every `x:write`, so the token list shows both. The scope check also treats `x:write` as `x:read`.
- Scopes are listed in `enums { ApiTokenScopes { key label description resource resourceLabel resourceDescription } }`. `resource` is the part before `:` (e.g. `time_entry`), so clients can group read and write per resource.
- New scopes are never added to existing tokens.
- `enums` needs no scope. `public { me }` works for any token, except fields that read other resources (`leaveToday` and `workFromHomeToday` need `journal:read`, `myLastWorkingDate` needs `journal:read` and `event:read`).
- No scope reaches other users' time entries. `timeEntries` and `allTimeEntries` return every user's entries; they are superuser only for sessions and never available to tokens.
- Session only (token requests get an error):
  - token management: `myApiTokens`, `createApiToken`, `revokeApiToken`
  - session: `public.login`, `public.logout`, `me.loginExpire`
  - daily standup: `dailyStandup` and all standup types
  - all users' time entries: `timeEntries`, `allTimeEntries`
- Session requests have no scope checks.

### Enforcement

`ApiTokenScopeExtension` (`apps/api_token/scopes.py`) is a Strawberry schema extension. For token requests it checks every resolved field, at any depth, against:

1. The field tag, if the field has one.
2. The type tag of the field's return type, after unwrapping lists and non-null. For an interface return type, the interface and every type that implements it. For a union, every member type. The concrete type is only known after the field resolves, so the token needs the scopes of all of them.

Fields that return scalars or enums are covered by their parent's type tag. Values computed from the holiday calendar (`dailySummary.isHoliday`/`targetMinutes`, `DeadlineType.totalDays`/`usedDays`/`remainingDays`) don't require `event:read`. A scalar field that exposes another resource's data needs its own field tag, e.g. `UserType.leaveToday` is tagged `journal:read`.

So `myTimeEntries { task { contract { project { id } } } user { id } }` needs `time_entry:read` (the root field and `TimeEntryType`), `project:read` (`TaskType`, `ContractType`, `ProjectType`) and `user:read` (`UserType`).

A missing scope is a GraphQL error on that field with message `missing scope: <scope>` and `extensions.code = "missing_scope"`. The field does not resolve, so a mutation without its write scope never runs. As usual in GraphQL, an error on a non-null field nulls its nearest nullable parent.

The rules fail closed. A token request is denied (`extensions.code = "token_not_allowed"`) when:

- the return type (or, for an interface or union, any possible type) has no type tag,
- the field or its return type is tagged `ScopeTag.SESSION_ONLY`,
- the field belongs to a `ScopeTag.ROOT` type (`Query`, `Mutation`, `PublicQuery`, `PrivateQuery`, `PublicMutation`, `PrivateMutation`, `UserMeType`) and has no field tag. This includes scalar fields, so a new field on `public` or `me` is closed to tokens until it is tagged.

A scope denial is logged at INFO (logger `strawberry.execution`, message `API token scope denial: ...`) without a traceback, so it doesn't reach Sentry.

### Tagging

Type tags (class decorator, placed above the Strawberry decorator):

```python
from apps.api_token.scopes import ApiTokenScope, ScopeTag, field_scope, type_scope


@type_scope(ApiTokenScope.PROJECT_READ)
@strawberry_django.type(Project)
class ProjectType: ...


@type_scope(ScopeTag.NO_SCOPE)  # containers and value objects
@strawberry.type
class CountList(Generic[T]): ...
```

Field tags (field metadata):

```python
@strawberry_django.field(metadata=field_scope(ApiTokenScope.TIME_ENTRY_READ, ApiTokenScope.JOURNAL_READ))
async def daily_summary(...) -> list[DailySummaryType]: ...

@strawberry.mutation(metadata=field_scope(ApiTokenScope.TIME_ENTRY_WRITE))
async def create_time_entry(...) -> MutationResponseType[TimeEntryType]: ...

projects: CountList[ProjectType] = pagination_field(..., metadata=field_scope(ApiTokenScope.PROJECT_READ))

# Field helpers take the same metadata
first_name = string_field(User.first_name, metadata=field_scope(ScopeTag.NO_SCOPE))
```

| Tag | Meaning |
|---|---|
| `ApiTokenScope...` (one or more) | Token needs all listed scopes |
| `ScopeTag.NO_SCOPE` | No scope needed. Use for containers (pagination, mutation responses, errors) and value objects |
| `ScopeTag.SESSION_ONLY` | Never available to tokens |
| `ScopeTag.ROOT` | Type needs no scope, but each of its fields, scalars included, must have a field tag |

Rules for new code:

- Every new object or interface type reachable from the schema needs a type tag. Tags are not inherited, so a subclass needs its own. Interfaces used as mixins can be `NO_SCOPE`, because a field returning the interface also needs the scopes of every implementing type.
- A scalar or enum field that derives its value from another resource needs a field tag with that resource's scope.
- Specialized generics (`CountList[ProjectType]`, `MutationResponseType[TimeEntryType]`) use the tag of the generic class.
- Every new field on a `ROOT` type (`PublicQuery`, `PrivateQuery`, `PublicMutation`, `PrivateMutation`, `UserMeType`) needs a field tag. Mutations take the write scope. `UserMeType` inherits the fields of `UserBaseType`, so those carry field tags too.
- A new scope goes in `ApiTokenScope` with a description in `API_TOKEN_SCOPE_DESCRIPTIONS`. A new resource also needs a label and description in `API_TOKEN_RESOURCES`.

`apps/api_token/tests/test_schema.py` walks every type reachable from `Query` and `Mutation` (field return types, implemented interfaces, interface implementations and union members) and fails on any untagged type or any untagged field (scalars included) of a `ROOT` type, so CI catches a missing tag. It can't detect a scalar field on a scoped type that leaks another resource's data; that needs review.

## Limits and errors

These apply to every request, session or token (`main/graphql/limits.py`, `main/graphql/errors.py`):

| Limit | Value | Error |
|---|---|---|
| Query depth (nested fields with a selection; introspection fields ignored) | 12 | `'<operation>' exceeds maximum operation depth of 12` |
| Aliases per operation | 15 | `16 aliases found. Allowed: 15` |
| Introspection depth (`__schema` / `__type` selection, all fields counted) | 16 | `Maximum introspection depth exceeded` |
| Nested introspection lists (`fields`, `interfaces`, `possibleTypes`, `inputFields`) | 2 | `Maximum introspection depth exceeded` |
| Tokens per document | 500 | `Syntax Error: Document contains more than 500 tokens. Parsing aborted.` |
| `dailySummary` date range | 366 days | `Date range can be at most 366 days.` |

Depth and aliases are counted per operation with every fragment spread expanded (each fragment is measured once, so the check is linear in the document size). Limit errors have `extensions = {"code": "limit_exceeded", "limit": "depth" | "aliases" | "introspection_depth" | "tokens"}` and are returned before the operation runs.

The web app's largest operation has depth 6, no aliases and about 130 tokens. The standard introspection query (GraphiQL, codegen; graphql-js and graphql-core `getIntrospectionQuery` with all options) has about 210 tokens, introspection depth 14 and one introspection list level. The introspection list limit matches graphql-js `MaxIntrospectionDepthRule`: those lists branch, so each nested level multiplies the response size.

An unknown `operationName` (or a document without an operation) returns `extensions = {"code": "invalid_operation"}` before the operation runs, like the other request errors. Without `operationName`, the first operation in the document runs.

Errors raised before any field resolves (syntax, validation, limit, variable and operation errors) are client errors: they are logged at INFO (logger `strawberry.execution`, message `GraphQL request rejected: <category>`, or the limit message for limit errors) without a traceback or the error message.

An unexpected exception, raised while resolving a field or by a schema extension, returns the message "Something unexpected has occurred. Please contact an admin to fix this issue." (`extensions.code = "internal_error"` for the latter). The full exception is logged (logger `strawberry.execution`, ERROR, with the error message, path, operation name and exception type, never the query source) and reaches Sentry. These keep their message: `GraphQLError` (scope denials, permission errors, the limits above), Django `ValidationError`, `PermissionDenied` and `Http404`, DRF `APIException`, and syntax, validation and variable errors. Mutation input errors are returned in the `errors` field of the mutation response.

## Expiry emails

The `api_token_expiry_notify` management command runs as a CronJob every day at 09:00 Asia/Kathmandu (`helm/values.yaml`, Sentry monitor `api_token_expiry_notify` in `main/sentry.py`). It sends email directly, without Celery.

- Reminder: once per token, when the token expires within the next 7 days (`expiry_reminder_sent_at`).
- Expired notice: once per token, in the first 7 days after it expired (`expired_notice_sent_at`). Tokens that expired earlier never get it. A token that expires before its reminder was sent only gets the expired notice.
- Skipped: revoked tokens, users with `is_active=False`, users with `invalid_email=True`.
- Content: greeting with the user's name (email if the user has no name), token name, prefix, expiry (`Nov 20, 2026, 18:14 UTC`), last used date or "Never" with a note that it seems like it isn't used, and a link to `APP_FRONTEND_HOST/settings/api-tokens`.
- Dates in emails are in UTC and labelled "UTC", since the reader's timezone is unknown.
- Templates: `apps/api_token/templates/api_token/emails/` (plain text and HTML, inline styles).
- Each token is claimed before sending: a conditional update sets the sent marker only if it is still empty, so overlapping runs never send the same notice twice.
- A failed send clears the marker so the next run retries, and the command exits non-zero so the Sentry cron check-in fails.

Email settings:

| Env | Use |
|---|---|
| `EMAIL_BACKEND` | `SMTP` to send over SMTP (console otherwise) |
| `SMTP_EMAIL_HOST`, `SMTP_EMAIL_PORT`, `SMTP_EMAIL_USERNAME`, `SMTP_EMAIL_PASSWORD` | SMTP server and login |
| `EMAIL_USE_TLS` | `true` for STARTTLS (default `false`) |
| `EMAIL_TIMEOUT` | Seconds before a stalled SMTP connection fails (default `30`) |
| `EMAIL_FROM` | Sender, also used as `DEFAULT_FROM_EMAIL`, e.g. `Timur <timur@example.com>` |

## Admin

Only superusers can see tokens in Django admin. They can list and filter them (status, user, dates) and revoke them, including expired ones, with the "Revoke selected tokens" action. The admin never shows the hash or the token. Tokens can't be added or deleted there.
