import typing

# from asgiref.sync import sync_to_async
from django.db import models

# import datetime


# from apps.common.models import Event
# from apps.journal.models import Journal
# from django.utils.functional import cached_property
# from strawberry.dataloader import DataLoader

DjangoModel = typing.TypeVar("DjangoModel", bound=models.Model)


# -- Helper
def load_model_objects(
    Model: typing.Type[DjangoModel],
    keys: list[int],
) -> list[DjangoModel]:
    qs = Model.objects.filter(id__in=keys)
    _map = {obj.pk: obj for obj in qs}
    return [_map[key] for key in keys]


# -- Common models dataloaders

# def load_user_last_working_date(keys: list[int]) -> list[datetime.date]:
#     """
#     WITH recursive_days AS (
#         SELECT
#             DATE_SUB(:input_date, INTERVAL 1 DAY) AS prev_day
#         UNION ALL
#         SELECT
#             DATE_SUB(prev_day, INTERVAL 1 DAY)
#         FROM recursive_days
#         WHERE
#             prev_day NOT IN (
#                 SELECT
#                     {Event.date.db_column}
#                 FROM {Event._meta.db_table}
#                 WHERE {Event.type.db_column} IN (
#                     {Event.Type.HOLIDAY.value},
#                     {Event.Type.RETREAT.value}
#                 )
#             )
#             AND DAYOFWEEK(prev_day) NOT IN (1, 7)  -- 1 = Sunday, 7 = Saturday
#             AND (
#                 SELECT COUNT(*) FROM recursive_days
#             ) < %(NUMBER_OF_WORKING_DAYS_TO_SKIP + 1)s  -- Stop after finding N working days
#     )
#     SELECT MIN(prev_day) AS date_before_n_working_days
#     FROM recursive_days;
#     """

#     recent_user_leave_dates_qs = (
#         Journal.as_leave_qs(recent_only=True)
#         .filter(user__in=keys)
#         .values_list('user', 'date')
#     )
#     print(recent_user_leave_dates_qs)
#     return load_model_objects(User, keys)


class CommonLoader:
    # @cached_property
    # def load_user_last_working_date(self):
    #     return DataLoader(load_fn=sync_to_async(load_user_last_working_date))
    ...
