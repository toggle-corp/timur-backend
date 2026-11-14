import re

import strawberry
from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from apps.user.models import User
from main.graphql.context import Info
from utils.strawberry.mutations import (
    CustomErrorType,
    ModelMutation,
    MutationResponseType,
    generate_error_message,
    get_serializer_context,
    mutation_is_not_valid,
    process_input_data,
)

from .models import ApiToken
from .scopes import ScopeTag, field_scope
from .serializers import ApiTokenCreateSerializer
from .types import ApiTokenType, CreatedApiTokenType

ApiTokenMutation = ModelMutation("ApiToken", ApiTokenCreateSerializer)

TOKEN_ID_RE = re.compile(r"[0-9]+")


@sync_to_async
def _create(data: dict, info: Info) -> tuple[CustomErrorType | None, ApiToken | None]:
    with transaction.atomic():
        # Lock the user row so concurrent creates for the same user run the active-token limit and
        # unique-name checks one at a time
        User.objects.select_for_update().only("pk").get(pk=info.context.request.user.pk)
        serializer = ApiTokenCreateSerializer(data=data, context=get_serializer_context(info, None))
        if errors := mutation_is_not_valid(serializer):
            return errors, None
        return None, serializer.save()


@sync_to_async
def _revoke(token: ApiToken) -> ApiToken:
    if token.revoked_at is None:
        token.revoked_at = timezone.now()
        token.save(update_fields=("revoked_at",))
    return token


@strawberry.type
class PrivateMutation:
    @strawberry.mutation(metadata=field_scope(ScopeTag.SESSION_ONLY))
    async def create_api_token(
        self,
        data: ApiTokenMutation.InputType,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[CreatedApiTokenType]:
        errors, token = await _create(process_input_data(data), info)  # type: ignore[reportArgumentType]
        if errors or token is None:
            return MutationResponseType(ok=False, errors=errors)
        return MutationResponseType(
            result=CreatedApiTokenType(
                token=token,  # type: ignore[reportArgumentType]
                secret=token.secret,  # type: ignore[reportAttributeAccessIssue]
            ),
        )

    @strawberry.mutation(metadata=field_scope(ScopeTag.SESSION_ONLY))
    async def revoke_api_token(
        self,
        id: strawberry.ID,  # noqa: A002
        info: Info,
    ) -> MutationResponseType[ApiTokenType]:
        token = None
        if TOKEN_ID_RE.fullmatch(id):
            token = await ApiToken.objects.filter(user=info.context.request.user, id=int(id)).afirst()
        if token is None:
            return MutationResponseType(
                ok=False,
                errors=generate_error_message("Token not found"),
            )
        if token.revoked_at is None and token.get_status() == ApiToken.Status.EXPIRED:
            return MutationResponseType(
                ok=False,
                errors=generate_error_message("Token has already expired"),
            )
        return MutationResponseType(result=await _revoke(token))  # type: ignore[reportArgumentType]
