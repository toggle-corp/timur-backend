import datetime

from asgiref.sync import sync_to_async
from django.utils import timezone
from django.utils.functional import cached_property
from strawberry.dataloader import DataLoader

from .models import Journal


def load_user_leave(keys: list[tuple[int, datetime.date]]) -> list[Journal.LeaveType | None]:
    user_ids = []
    dates = []
    for user_id, date in keys:
        user_ids.append(user_id)
        dates.append(date)

    qs = Journal.objects.filter(
        user__in=user_ids,
        date__in=dates,
    ).values_list("user_id", "date", "leave_type")

    _map = {(user_id, date): leave_type for user_id, date, leave_type in qs}
    return [_map.get(key) for key in keys]


def load_user_work_from_home(keys: list[tuple[int, datetime.date]]) -> list[Journal.WorkFromHomeType | None]:
    user_ids = []
    dates = []
    for user_id, date in keys:
        user_ids.append(user_id)
        dates.append(date)

    qs = Journal.objects.filter(
        user__in=user_ids,
        date__in=dates,
    ).values_list("user_id", "date", "wfh_type")

    _map = {(user_id, date): wfh_type for user_id, date, wfh_type in qs}
    return [_map.get(key) for key in keys]


def load_user_leave_today(keys: list[int]) -> list[Journal.LeaveType | None]:
    qs = Journal.objects.filter(
        user__in=keys,
        date=timezone.now().date(),
    ).values_list("user_id", "leave_type")

    _map = {user_id: leave_type for user_id, leave_type in qs}
    return [_map.get(key) for key in keys]


def load_user_work_from_home_today(keys: list[int]) -> list[Journal.WorkFromHomeType | None]:
    qs = Journal.objects.filter(
        user__in=keys,
        date=timezone.now().date(),
    ).values_list("user_id", "wfh_type")

    _map = {user_id: wfh_type for user_id, wfh_type in qs}
    return [_map.get(key) for key in keys]


class JournalDataLoader:
    @cached_property
    def load_user_leave(self):
        return DataLoader(load_fn=sync_to_async(load_user_leave))

    @cached_property
    def load_user_work_from_home(self):
        return DataLoader(load_fn=sync_to_async(load_user_work_from_home))

    @cached_property
    def load_user_leave_today(self):
        return DataLoader(load_fn=sync_to_async(load_user_leave_today))

    @cached_property
    def load_user_work_from_home_today(self):
        return DataLoader(load_fn=sync_to_async(load_user_work_from_home_today))
