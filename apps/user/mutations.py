import strawberry
from asgiref.sync import sync_to_async
from django.contrib.auth import login, logout
from strawberry.types import Info

from utils.strawberry.mutations import (
    MutationEmptyResponseType,
    MutationResponseType,
    mutation_is_not_valid,
    process_input_data,
)
from utils.strawberry.transformers import convert_serializer_to_type

from .queries import UserMeType
from .serializers import LoginSerializer

LoginInput = convert_serializer_to_type(LoginSerializer, name="LoginInput")


@strawberry.type
class PublicMutation:

    @strawberry.mutation
    @sync_to_async
    def login(
        self,
        data: LoginInput,  # type: ignore[reportInvalidTypeForm]
        info: Info,
    ) -> MutationResponseType[UserMeType]:
        serializer = LoginSerializer(data=process_input_data(data), context={"request": info.context.request})
        if errors := mutation_is_not_valid(serializer):
            return MutationResponseType(
                ok=False,
                errors=errors,
            )
        user = serializer.validated_data["user"]
        login(info.context.request, user)
        return MutationResponseType(
            result=user,
        )

    @strawberry.mutation
    @sync_to_async
    def logout(self, info: Info) -> MutationEmptyResponseType:
        if info.context.request.user.is_authenticated:
            logout(info.context.request)
            return MutationEmptyResponseType(ok=True)
        return MutationEmptyResponseType(ok=False)
