import strawberry

from utils.strawberry.enums import get_enum_name_from_django_field

from .models import User

UserDepartmentTypeEnum = strawberry.enum(User.Department, name="UserDepartmentTypeEnum")


enum_map = {get_enum_name_from_django_field(field): enum for field, enum in ((User.department, UserDepartmentTypeEnum),)}
