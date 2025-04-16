import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import Event

EventTypeEnum = strawberry.enum(Event.Type, name="EventTypeEnum")


enum_map = {get_enum_name_from_django_field(field): enum for field, enum in ((Event.type, EventTypeEnum),)}
