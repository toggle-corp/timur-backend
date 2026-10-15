import datetime

from apps.common.factories import EventFactory
from apps.common.models import Event
from apps.user.factories import UserFactory
from main.tests import TestCase


class TestEventGenerateDates(TestCase):
    def test_generate_dates(self):
        user = UserFactory.create()
        today = datetime.date.today()
        # Next Monday, so the week starts with a working day
        monday = today + datetime.timedelta(days=7 - today.weekday())
        wednesday = monday + datetime.timedelta(days=2)
        EventFactory.create(
            type=Event.Type.HOLIDAY,
            start_date=wednesday,
            end_date=wednesday,
            created_by=user,
            modified_by=user,
        )
        saturday = monday + datetime.timedelta(days=5)

        # Range: skips holidays and weekends
        assert Event.generate_dates(monday, monday + datetime.timedelta(days=6)) == [
            monday,
            monday + datetime.timedelta(days=1),
            monday + datetime.timedelta(days=3),
            monday + datetime.timedelta(days=4),
        ]
        # Single day: working day
        assert Event.generate_dates(monday, monday) == [monday]
        # Single day: weekend
        assert Event.generate_dates(saturday, saturday) == []
        assert Event.generate_dates(saturday, saturday, include_weekends=True) == [saturday]
        # Single day: holiday
        assert Event.generate_dates(wednesday, wednesday) == []
        assert Event.generate_dates(wednesday, wednesday, include_holidays=True) == [wednesday]
