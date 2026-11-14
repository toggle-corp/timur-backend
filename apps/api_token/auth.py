import dataclasses
import datetime
import logging
import typing

from django.db import models
from django.http import HttpRequest, HttpResponseServerError, JsonResponse
from django.http.response import HttpResponseBase
from django.utils import timezone
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension
from strawberry.types.execution import PreExecutionError

from main.graphql.errors import REQUEST_EXCEPTIONS, classify_request_error
from main.logging import log_extra

from .models import ApiToken

logger = logging.getLogger(__name__)

LAST_USED_AT_THROTTLE = datetime.timedelta(seconds=60)


class ApiTokenAuthError(Exception):
    INVALID_TOKEN = "invalid_token"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_REVOKED = "token_revoked"
    USER_INACTIVE = "user_inactive"

    MESSAGES: typing.ClassVar[dict[str, str]] = {
        INVALID_TOKEN: "Invalid API token",
        TOKEN_EXPIRED: "API token has expired",
        TOKEN_REVOKED: "API token has been revoked",
        USER_INACTIVE: "User of this API token is inactive",
    }

    def __init__(self, code: str, token: ApiToken | None = None):
        self.code = code
        self.token = token
        super().__init__(self.MESSAGES[code])

    def as_response(self) -> JsonResponse:
        response = JsonResponse(
            {"errors": [{"message": str(self), "extensions": {"code": self.code}}]},
            status=401,
        )
        response["WWW-Authenticate"] = f'Bearer error="invalid_token", error_description="{self.code}"'
        return response


def get_bearer_secret(request: HttpRequest) -> str | None:
    """
    Return the secret from `Authorization: Bearer <secret>`, or None when the request has no Authorization header.
    The scheme is case-insensitive and may be followed by any whitespace. Any other Authorization value (another
    scheme, no secret, extra parts, or several values, which arrive comma-joined) is returned as "" so that it fails
    as an invalid token.
    """
    header = request.headers.get("Authorization")
    if header is None:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or "," in parts[1]:
        return ""
    return parts[1]


def get_secret_prefix(secret: str) -> str | None:
    """
    The non-secret `prefix` part of a well-formed token secret, for logs.
    """
    if not secret.startswith(ApiToken.SECRET_PREFIX):
        return None
    prefix = secret[len(ApiToken.SECRET_PREFIX) :][: ApiToken.PREFIX_LENGTH]
    if len(prefix) != ApiToken.PREFIX_LENGTH or not all(char in ApiToken.SECRET_ALPHABET for char in prefix):
        return None
    return prefix


async def authenticate_secret(secret: str) -> ApiToken:
    """
    Raises ApiTokenAuthError when the token can't be used.
    """
    if not secret.startswith(ApiToken.SECRET_PREFIX):
        raise ApiTokenAuthError(ApiTokenAuthError.INVALID_TOKEN)
    token = await ApiToken.objects.select_related("user").filter(hash=ApiToken.hash_secret(secret)).afirst()
    if token is None:
        raise ApiTokenAuthError(ApiTokenAuthError.INVALID_TOKEN)
    if token.revoked_at is not None:
        raise ApiTokenAuthError(ApiTokenAuthError.TOKEN_REVOKED, token)
    if token.expires_at <= timezone.now():
        raise ApiTokenAuthError(ApiTokenAuthError.TOKEN_EXPIRED, token)
    if not token.user.is_active:
        raise ApiTokenAuthError(ApiTokenAuthError.USER_INACTIVE, token)
    return token


async def touch_last_used_at(token: ApiToken):
    now = timezone.now()
    await (
        ApiToken.objects.filter(pk=token.pk)
        .filter(models.Q(last_used_at__isnull=True) | models.Q(last_used_at__lte=now - LAST_USED_AT_THROTTLE))
        .aupdate(last_used_at=now)
    )


def get_client_ip(request: HttpRequest) -> str | None:
    """
    The rightmost X-Forwarded-For entry is the one added by our ingress; entries to its left come from the client.
    """
    if forwarded_for := request.META.get("HTTP_X_FORWARDED_FOR"):
        return forwarded_for.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR")


class AuditResult:
    EXECUTED = "executed"
    """The operation ran (it may still have field errors, e.g. scope denials)."""
    PRE_EXECUTION_ERROR = "pre_execution_error"
    """Rejected before any resolver ran: syntax, validation, limit or variable errors."""
    HTTP_ERROR = "http_error"
    """Rejected by the view (e.g. a malformed body, no query, a mutation over GET) or failed with HTTP 500."""
    UNAUTHORIZED = "unauthorized"
    """The token was not accepted (HTTP 401)."""


@dataclasses.dataclass
class OperationAudit:
    operation_name: str | None
    result: str
    error: str | None = None
    """Error category (see `classify_request_error`), never the error message."""
    limit: str | None = None
    """Name of the exceeded limit, for `limit_exceeded`."""

    @classmethod
    def rejected(cls, operation_name: str | None, error: GraphQLError) -> "OperationAudit":
        return cls(
            operation_name=operation_name,
            result=AuditResult.PRE_EXECUTION_ERROR,
            error=classify_request_error(error),
            limit=(error.extensions or {}).get("limit"),
        )


OPERATION_AUDIT_ATTR = "api_token_operation_audit"


class ApiTokenAuditExtension(SchemaExtension):
    """
    Records the operation name and outcome of GraphQL operations run with an API token, for the audit log line
    written by `dispatch_with_api_token`.
    """

    def _record(self, audit: OperationAudit):
        request = getattr(self.execution_context.context, "request", None)
        if request is not None and getattr(request, "api_token", None) is not None:
            setattr(request, OPERATION_AUDIT_ATTR, audit)

    @typing.override
    def on_operation(self):
        try:
            yield
        except REQUEST_EXCEPTIONS:
            # strawberry answers these with HTTP 400
            self._record(OperationAudit(operation_name=self.execution_context.operation_name, result=AuditResult.HTTP_ERROR))
            raise
        except GraphQLError as error:
            # Raised by an extension hook (e.g. the token limit while parsing); strawberry returns it as an error.
            # MaskUnexpectedErrors turns any other exception into a GraphQLError before it gets here.
            self._record(OperationAudit.rejected(self.execution_context.operation_name, error))
            raise
        operation_name = self.execution_context.operation_name
        result = self.execution_context.result
        errors = (result.errors if result else None) or []
        not_executed = isinstance(result, PreExecutionError) or (
            # Variable coercion and operation selection fail before any resolver runs
            result is not None and result.data is None and errors and all(error.path is None for error in errors)
        )
        if not_executed and errors:
            self._record(OperationAudit.rejected(operation_name, errors[0]))
        else:
            self._record(OperationAudit(operation_name=operation_name, result=AuditResult.EXECUTED))


def log_token_request(request: HttpRequest, token: ApiToken, response: HttpResponseBase):
    audit: OperationAudit | None = getattr(request, OPERATION_AUDIT_ATTR, None)
    if audit is None:
        audit = OperationAudit(
            operation_name=None,
            result=AuditResult.EXECUTED if response.status_code == 200 else AuditResult.HTTP_ERROR,
        )
    context: dict[str, typing.Any] = {
        "token_id": token.pk,
        "user_id": token.user_id,
        "operation_name": audit.operation_name,
        "ip": get_client_ip(request),
        "status": response.status_code,
        "result": audit.result,
    }
    if audit.error is not None:
        context["error"] = audit.error
    if audit.limit is not None:
        context["limit"] = audit.limit
    logger.info("API token request", extra=log_extra(context))


def log_auth_failure(request: HttpRequest, error: ApiTokenAuthError):
    """
    Never logs the secret: only the token id/user when the token was found, else at most its prefix.
    """
    secret = get_bearer_secret(request) or ""
    logger.info(
        "API token request",
        extra=log_extra(
            {
                "token_id": error.token.pk if error.token else None,
                "user_id": error.token.user_id if error.token else None,
                "token_prefix": get_secret_prefix(secret),
                "ip": get_client_ip(request),
                "status": 401,
                "result": AuditResult.UNAUTHORIZED,
                "code": error.code,
            },
        ),
    )


async def authenticate_request(request: HttpRequest) -> ApiToken | None:
    """
    Authenticate a GraphQL request that carries an Authorization header.

    Returns None when the request has no Authorization header (session auth applies).
    On success the request user is replaced by the token's user; the session user is ignored.
    Raises ApiTokenAuthError on failure; callers must not fall back to the session.
    """
    secret = get_bearer_secret(request)
    if secret is None:
        return None
    token = await authenticate_secret(secret)
    request.user = token.user
    request.api_token = token  # type: ignore[reportAttributeAccessIssue]
    await touch_last_used_at(token)
    return token


def get_request_api_token(request: HttpRequest) -> ApiToken | None:
    return getattr(request, "api_token", None)


async def dispatch_with_api_token(
    request: HttpRequest,
    dispatch: typing.Callable[[], typing.Awaitable[HttpResponseBase]],
) -> HttpResponseBase:
    """
    Wrap the GraphQL view's dispatch.

    Without an Authorization header the request goes to `dispatch` (session auth). With one, the token is
    authenticated (401 on failure, never a session fallback) and one audit log line is written (also for 401s,
    rejected requests and exceptions). Cache headers are set by `main.middlewares.GraphQLCacheHeadersMiddleware`.
    """
    if "Authorization" not in request.headers:
        return await dispatch()
    try:
        token = await authenticate_request(request)
    except ApiTokenAuthError as error:
        log_auth_failure(request, error)
        response = error.as_response()
    else:
        assert token is not None
        try:
            response = await dispatch()
        except Exception:
            log_token_request(request, token, HttpResponseServerError())
            raise
        log_token_request(request, token, response)
    return response
