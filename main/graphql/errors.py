import typing

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from graphql import GraphQLError, GraphQLSyntaxError
from rest_framework.exceptions import APIException
from strawberry.exceptions import MissingQueryError
from strawberry.extensions import MaskErrors
from strawberry.schema.exceptions import InvalidOperationTypeError
from strawberry.utils.logging import StrawberryLogger

from apps.api_token.scopes import is_scope_denial
from main.graphql.limits import INVALID_OPERATION, LIMIT_EXCEEDED
from main.logging import log_extra
from utils.strawberry.mutations import _CustomErrorType

if typing.TYPE_CHECKING:
    from strawberry.types import ExecutionContext

UNEXPECTED_ERROR_MESSAGE = _CustomErrorType.DEFAULT_ERROR_MESSAGE
INTERNAL_ERROR_CODE = "internal_error"

# Exceptions raised on purpose by resolvers; their message is meant for the client.
INTENDED_EXCEPTIONS: tuple[type[Exception], ...] = (
    GraphQLError,  # Includes strawberry permission errors and scope denials
    ValidationError,
    APIException,  # DRF, includes serializers.ValidationError
    Http404,
    PermissionDenied,
)


def is_unexpected_error(error: GraphQLError) -> bool:
    """
    True for an error raised while resolving a field by an exception outside INTENDED_EXCEPTIONS.
    Parse, validation, limit and variable errors have no path and are never unexpected.
    """
    if error.path is None or error.original_error is None:
        return False
    return not isinstance(error.original_error, INTENDED_EXCEPTIONS)


# Exceptions strawberry handles itself (HTTP 400) when raised inside the operation
REQUEST_EXCEPTIONS: tuple[type[Exception], ...] = (MissingQueryError, InvalidOperationTypeError)


class RequestErrorCategory:
    LIMIT_EXCEEDED = LIMIT_EXCEEDED
    SYNTAX_ERROR = "syntax_error"
    VARIABLE_ERROR = "variable_error"
    VALIDATION_ERROR = "validation_error"
    INVALID_OPERATION = INVALID_OPERATION
    INTERNAL_ERROR = "internal_error"


def classify_request_error(error: GraphQLError) -> str:
    """
    Stable category of an error without a path (raised before any field resolved). The category carries no user
    input, unlike the message, which can quote the query or submitted variable values.
    """
    code = (error.extensions or {}).get("code")
    if code == LIMIT_EXCEEDED:
        return RequestErrorCategory.LIMIT_EXCEEDED
    if code == INVALID_OPERATION:
        return RequestErrorCategory.INVALID_OPERATION
    if code == INTERNAL_ERROR_CODE:
        return RequestErrorCategory.INTERNAL_ERROR
    if isinstance(error, GraphQLSyntaxError):
        return RequestErrorCategory.SYNTAX_ERROR
    if error.message.startswith("Variable '$"):
        return RequestErrorCategory.VARIABLE_ERROR
    return RequestErrorCategory.VALIDATION_ERROR


def log_errors(errors: list[GraphQLError], execution_context: "ExecutionContext | None") -> None:
    """
    - Scope denials are expected for API tokens: INFO, no traceback.
    - Errors without a path (syntax, validation, limit and variable errors) are client errors: INFO with their
      category, no traceback and no message (it can quote submitted values). Limit errors keep their message.
    - Every other error (raised while resolving a field) is logged at ERROR with the original exception as
      `exc_info`, so Sentry gets it. The log has the message, path, operation name and exception type, never the
      query source excerpt that `str(error)` adds (it can hold literals of other arguments).
    """
    for error in errors:
        if is_scope_denial(error):
            StrawberryLogger.logger.info(
                "API token scope denial: %s",
                error.message,
                extra=log_extra({"path": error.path, "code": (error.extensions or {}).get("code")}),
            )
        elif error.path is None:
            category = classify_request_error(error)
            StrawberryLogger.logger.info(
                "GraphQL request rejected: %s",
                error.message if category == RequestErrorCategory.LIMIT_EXCEEDED else category,
                extra=log_extra({"category": category}),
            )
        else:
            original_error = error.original_error
            StrawberryLogger.logger.error(
                "GraphQL field error: %s",
                error.message,
                exc_info=original_error,
                extra=log_extra(
                    {
                        "path": error.path,
                        "operation_name": execution_context.operation_name if execution_context else None,
                        "exception": type(original_error).__name__ if original_error else None,
                    },
                ),
            )


class MaskUnexpectedErrors(MaskErrors):
    """
    Replaces the message of unexpected errors (see `is_unexpected_error`) with a generic one.
    Runs after `log_errors`, so logs and Sentry keep the original exception.

    An unexpected exception that escapes the operation (raised by an extension hook or outside field resolution)
    is logged at ERROR with its traceback and replaced by a GraphQLError with the generic message.
    """

    def __init__(self, *, execution_context=None) -> None:
        super().__init__(should_mask_error=is_unexpected_error, error_message=UNEXPECTED_ERROR_MESSAGE)

    @typing.override
    def on_operation(self):
        try:
            yield from super().on_operation()
        except (*INTENDED_EXCEPTIONS, *REQUEST_EXCEPTIONS):
            raise
        except Exception as error:
            StrawberryLogger.logger.error("Unexpected error in GraphQL operation", exc_info=error)
            raise GraphQLError(UNEXPECTED_ERROR_MESSAGE, extensions={"code": INTERNAL_ERROR_CODE}) from error
