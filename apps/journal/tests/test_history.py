import datetime
import typing

import reversion
from django.urls import reverse
from reversion.models import Version

from apps.journal.factories import JournalFactory
from apps.journal.models import Journal, JournalAvailabilityHistory
from apps.user.factories import UserFactory
from main.tests import TestCase

LT = Journal.LeaveType
WT = Journal.WorkFromHomeType
Source = JournalAvailabilityHistory.Source

UPDATE_JOURNAL = """
    mutation ($date: Date!, $data: JournalUpdateInput!) {
      private {
        updateJournal(date: $date, data: $data) {
          ok
          errors
        }
      }
    }
"""


class TestJournalAvailabilityHistory(TestCase):
    @classmethod
    @typing.override
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.date = datetime.date(2026, 10, 13)

    def update_journal(self, data: dict, date: datetime.date | None = None):
        self.force_login(self.user)
        content = self.query_check(UPDATE_JOURNAL, variables={"date": (date or self.date).isoformat(), "data": data})
        assert content["data"]["private"]["updateJournal"]["ok"] is True, content

    def history(self) -> list[tuple]:
        return list(
            JournalAvailabilityHistory.objects.order_by("id").values_list(
                "journal__date",
                "leave_type_before",
                "wfh_type_before",
                "leave_type_after",
                "wfh_type_after",
                "source",
                "changed_by",
                "slack_availability_run",
            ),
        )

    def test_create_with_leave_is_recorded(self):
        self.update_journal({"leaveType": "FULL", "journalText": ""})
        assert self.history() == [(self.date, None, None, LT.FULL, None, Source.MANUAL, self.user.pk, None)]

    def test_update_is_recorded(self):
        JournalFactory.create(user=self.user, date=self.date, leave_type=LT.FULL)

        self.update_journal({"leaveType": None, "wfhType": "FULL"})
        self.update_journal({"leaveType": "FIRST_HALF", "wfhType": "SECOND_HALF"})
        assert self.history() == [
            (self.date, LT.FULL, None, None, WT.FULL, Source.MANUAL, self.user.pk, None),
            (self.date, None, WT.FULL, LT.FIRST_HALF, WT.SECOND_HALF, Source.MANUAL, self.user.pk, None),
        ]

    def test_unchanged_leave_and_wfh_are_not_recorded(self):
        # Journal text only
        self.update_journal({"journalText": "Did things"})
        JournalFactory.create(user=self.user, date=self.date + datetime.timedelta(days=1), wfh_type=WT.FULL)
        self.update_journal({"journalText": "More things"}, date=self.date + datetime.timedelta(days=1))
        # Same values again
        self.update_journal({"wfhType": "FULL", "journalText": "Same"}, date=self.date + datetime.timedelta(days=1))
        assert self.history() == []

    def test_admin_is_superuser_only(self):
        journal = JournalFactory.create(user=self.user, date=self.date, leave_type=LT.FULL)
        JournalAvailabilityHistory.objects.create(
            journal=journal,
            leave_type_after=LT.FULL,
            source=Source.MANUAL,
            changed_by=self.user,
        )
        changelist = reverse("admin:journal_journalavailabilityhistory_changelist")

        self.client.force_login(UserFactory.create(is_staff=True))
        assert self.client.get(changelist).status_code == 403

        self.client.force_login(UserFactory.create(is_staff=True, is_superuser=True))
        assert self.client.get(changelist).status_code == 200
        response = self.client.get(reverse("admin:journal_journal_change", args=[journal.pk]))
        assert response.status_code == 200
        assert "Availability history" in response.content.decode()


class TestJournalAdminHistory(TestCase):
    @classmethod
    @typing.override
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.admin = UserFactory.create(is_staff=True, is_superuser=True, first_name="Alex", last_name="Admin")
        cls.date = datetime.date(2026, 10, 13)

    @typing.override
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def history(self) -> list[tuple]:
        return list(
            JournalAvailabilityHistory.objects.order_by("id").values_list(
                "leave_type_before",
                "wfh_type_before",
                "leave_type_after",
                "wfh_type_after",
                "source",
                "changed_by",
            ),
        )

    def submit(self, url: str, **changes) -> None:
        """
        Post the admin form shown at url, with the given field changes
        """
        response = self.client.get(url)
        assert response.status_code == 200
        forms = [response.context["adminform"].form]
        for inline in response.context["inline_admin_formsets"]:
            forms.extend([inline.formset.management_form, *inline.formset.forms])
        data = {}
        for form in forms:
            for field in form:
                value = field.value()
                data[field.html_name] = "" if value is None else value
        data.update({name: "" if value is None else value for name, value in changes.items()})
        response = self.client.post(url, data)
        assert response.status_code == 302, response.context and response.context["adminform"].form.errors

    def test_add_and_change_are_recorded(self):
        self.submit(
            reverse("admin:journal_journal_add"),
            user=self.user.pk,
            date=self.date.isoformat(),
            leave_type=LT.FULL,
        )
        journal = Journal.objects.get(user=self.user, date=self.date)
        change_url = reverse("admin:journal_journal_change", args=[journal.pk])
        self.submit(change_url, leave_type=None, wfh_type=WT.FULL)
        # Journal text only, and the same values again
        self.submit(change_url, journal_text="Did things")
        self.submit(change_url, wfh_type=WT.FULL)

        assert self.history() == [
            (None, None, LT.FULL, None, Source.ADMIN, self.admin.pk),
            (LT.FULL, None, None, WT.FULL, Source.ADMIN, self.admin.pk),
        ]

    def test_revert_is_recorded(self):
        journal = JournalFactory.create(user=self.user, date=self.date, leave_type=LT.FULL)
        with reversion.create_revision():
            journal.save()
        version = Version.objects.get(content_type__model="journal", object_id=str(journal.pk))
        Journal.objects.filter(pk=journal.pk).update(leave_type=None, wfh_type=WT.FULL)

        self.submit(reverse("admin:journal_journal_revision", args=[journal.pk, version.pk]))

        assert Journal.objects.get(pk=journal.pk).leave_type == LT.FULL
        assert self.history() == [(None, WT.FULL, LT.FULL, None, Source.ADMIN, self.admin.pk)]

    def test_recover_is_recorded(self):
        journal = JournalFactory.create(user=self.user, date=self.date, wfh_type=WT.FIRST_HALF)
        with reversion.create_revision():
            journal.save()
        version = Version.objects.get(content_type__model="journal", object_id=str(journal.pk))
        journal.delete()

        self.submit(reverse("admin:journal_journal_recover", args=[version.pk]))

        assert Journal.objects.get(user=self.user, date=self.date).wfh_type == WT.FIRST_HALF
        assert self.history() == [(None, None, None, WT.FIRST_HALF, Source.ADMIN, self.admin.pk)]
