import dataclasses

import strawberry

from apps.api_token.enums import enum_map as api_token_enum_map
from apps.api_token.scopes import ScopeTag, type_scope
from apps.common.enums import enum_map as common_enum_map
from apps.journal.enums import enum_map as journal_enum_map
from apps.track.enums import enum_map as track_enum_map
from apps.user.enums import enum_map as user_enum_map

ENUM_TO_STRAWBERRY_ENUM_MAP: dict[str, type] = {
    **common_enum_map,
    **user_enum_map,
    **track_enum_map,
    **journal_enum_map,
    **api_token_enum_map,
}


def get_enum_extra_fields(Enum) -> tuple[str, ...]:
    """
    String fields an enum adds to its collection items besides key and label, declared on the enum class as
    `__enum_collection_fields__ = ("description", ...)`. Each name is read from the enum member.
    """
    return getattr(Enum, "__enum_collection_fields__", ())


class AppEnumData:
    def __init__(self, enum):
        self.enum = enum
        self.extra_fields = get_enum_extra_fields(type(enum))

    def __getattr__(self, name):
        if name != "extra_fields" and name in self.extra_fields:
            return str(getattr(self.enum, name))
        raise AttributeError(name)

    @property
    def key(self):
        return self.enum

    @property
    def label(self):
        return str(self.enum.label)


def generate_app_enum_collection_data(name):
    return type(
        name,
        (),
        {
            field_name: [AppEnumData(e) for e in enum]  # type: ignore[reportGeneralTypeIssues]
            for field_name, enum in ENUM_TO_STRAWBERRY_ENUM_MAP.items()
        },
    )


AppEnumCollectionData = generate_app_enum_collection_data("AppEnumCollectionData")


def generate_type_for_enum(name, Enum):
    fields = [
        ("key", Enum),
        ("label", str),
        *((field_name, str) for field_name in get_enum_extra_fields(Enum)),
    ]
    return type_scope(ScopeTag.NO_SCOPE)(
        strawberry.type(
            dataclasses.make_dataclass(
                f"AppEnumCollection{name}",
                fields,
            ),
        ),
    )


def _enum_type(name, Enum):
    EnumType = generate_type_for_enum(name, Enum)

    @strawberry.field
    def _field() -> list[EnumType]:  # type: ignore[reportGeneralTypeIssues]
        return [
            EnumType(
                key=e,
                label=e.label,
            )
            for e in Enum
        ]

    return list[EnumType], _field


def generate_type_for_enums():
    enum_fields = [
        (
            enum_field_name,
            *_enum_type(enum_field_name, enum),
        )
        for enum_field_name, enum in ENUM_TO_STRAWBERRY_ENUM_MAP.items()
    ]
    return type_scope(ScopeTag.NO_SCOPE)(
        strawberry.type(
            dataclasses.make_dataclass(
                "AppEnumCollection",
                enum_fields,
            ),
        ),
    )


AppEnumCollection = generate_type_for_enums()
