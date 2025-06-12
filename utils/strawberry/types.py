import hashlib
import json
import typing

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage, default_storage
from django.db import models
from django.db.models.fields import Field as DjangoBaseField
from django.db.models.fields import files
from strawberry_django.fields.types import field_type_map

import strawberry
from main.caches import CacheKey
from main.graphql.context import Info

if typing.TYPE_CHECKING:
    from django.db.models.fields import _FieldDescriptor


GenericScalar = strawberry.scalar(
    typing.NewType("GenericScalar", typing.Any),  # type: ignore[reportGeneralTypeIssues]
    description="The GenericScalar scalar type represents a generic GraphQL scalar value that could be: List or Object.",
    serialize=lambda v: v,
    parse_value=lambda v: v,
)

# This is used to provide description only
TimeDuration = strawberry.scalar(
    typing.NewType("TimeDuration", int),
    description="The `TimeDuration` scalar type represents Duration values in minutes",
)


class GIS:
    @staticmethod
    def serialize(geometry):
        return json.loads(geometry.geojson)

    @classmethod
    def parse_value(cls, node):
        geometry = GEOSGeometry(node.value)
        return json.loads(geometry.geojson)


PolygonScalar = strawberry.scalar(
    typing.NewType("PolygonScalar", typing.Any),  # type: ignore[reportGeneralTypeIssues]
    description="",  # TODO: Add description
    serialize=GIS.serialize,
    parse_value=GIS.parse_value,
)


def string_field(
    field: typing.Union[
        DjangoBaseField,
        models.query_utils.DeferredAttribute,
        "_FieldDescriptor",
    ],
):
    """
    Behaviour:
        blank = true, is_null = True
            - String (Null if empty)
        blank = true, is_null = false
            - String (Null if empty)
        blank = false, is_null = false
            - String!
    """

    _field = field
    if isinstance(field, models.query_utils.DeferredAttribute):
        _field = field.field

    def _get_value(root) -> None | str:
        return getattr(root, _field.attname)  # type: ignore[reportGeneralTypeIssues] FIXME

    @strawberry.field
    def string_(root) -> str:
        return _get_value(root)  # type: ignore[reportGeneralTypeIssues] FIXME

    @strawberry.field
    def nullable_string_(root) -> str | None:
        _value = _get_value(root)
        if _value == "":
            return None
        return _value

    if _field.null or _field.blank:  # type: ignore[reportGeneralTypeIssues] FIXME
        return nullable_string_
    return string_


@strawberry.type
class DjangoFileType:
    name: str
    size: int

    @staticmethod
    def _cached_s3_url(root: files.FieldFile) -> str:
        url_hash = hashlib.sha1((root.name or "").encode("utf-8")).hexdigest()
        url_hash_key = CacheKey.DJANGO_FILE_S3_KEY_FORMAT.format(url_hash)
        if url := cache.get(url_hash_key):
            return url

        url = root.url
        cache.set(url_hash_key, url, timeout=settings.AWS_S3_CACHED_TTL)
        return url

    @strawberry.field
    @classmethod
    def url(cls, root: files.FieldFile, info: Info) -> str:
        if isinstance(default_storage, FileSystemStorage):
            return info.context.request.build_absolute_uri(root.url)
        return cls._cached_s3_url(root)


@strawberry.type
class DjangoImageType(DjangoFileType):
    width: int
    height: int


# Update the strawberry django field type mapping
field_type_map.update(
    {
        files.FileField: DjangoFileType,
        files.ImageField: DjangoImageType,
    },
)
