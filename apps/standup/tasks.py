import logging
import typing

from django.utils import timezone

from apps.common.models import Event
from apps.standup.models import DailyUserStandup, Quote
from apps.user.models import User
from main import config
from utils.slack import TimurSlack

logger = logging.getLogger(__name__)


class SlackMessage:
    type MessageType = typing.Literal["assign", "read_doc", "morning"]

    DOC_REF = config.DAILY_STANDUP_DOCUMENTATION_REF or "N/A"
    MEET_LINK = config.DAILY_STANDUP_MEET_LINK or ""

    @classmethod
    def get_normal_message(
        cls,
        message_type: typing.Literal["before_standup"],
    ) -> TimurSlack.TimurSlackMessageArgumentType:
        if message_type == "before_standup":
            text = (
                "Hey <!everyone>"
                "\n"
                "Good morning :sunny: "
                "Let’s get ready for our daily standup :rocket:"
                "\n\n"
                f":link: Join here: {cls.MEET_LINK}"
            )

            blocks = [
                {
                    "type": "markdown",
                    "text": ("Hey <!everyone>\nGood morning :sunny: \nLet’s get ready for our daily standup :rocket:"),
                },
                {
                    "type": "image",
                    "image_url": config.DAILY_STANDUP_GATHER_ROUND_GIF,
                    "alt_text": "People gathering",
                },
                {"type": "divider"},
                {
                    "type": "markdown",
                    "text": f":link: For WFH, Join here: {cls.MEET_LINK}",
                },
            ]

            return {
                "text": text,
                "blocks": blocks,
            }

        typing.assert_never()

    @classmethod
    def get_message(
        cls,
        daily_standup: DailyUserStandup,
        message_type: "MessageType",
    ) -> TimurSlack.TimurSlackMessageArgumentType:
        date = daily_standup.date.strftime("%A, %B %-d, %Y")
        conductor_id = daily_standup.conductor.slack_user_id
        fallback_conductor_id = daily_standup.fallback_conductor.slack_user_id

        if message_type == "assign":
            text = (
                f"*Hey <@{conductor_id}>, congratulations!* :tada:"
                "\n\n"
                f"You're now leading the next *Daily Standup* session: :calendar: {date}"
                "\n\n"
                f":warning: If <@{conductor_id}> is unavailable, <@{fallback_conductor_id}> will take over. :handshake:"
            )

            blocks = [
                {
                    "type": "markdown",
                    "text": (
                        f"**Hey <@{conductor_id}>, congratulations!** :tada:"
                        "\n\n"
                        "You're now leading the next **Daily Standup** session"
                    ),
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*Date*: {date}"
                            "\n"
                            "*Time*: 9:15 - 9:30am"
                            "\n"
                            f"*Lead*: <@{conductor_id}>"
                            "\n"
                            f"*Acting Lead*: <@{fallback_conductor_id}>"
                        ),
                    },
                    "accessory": {
                        "type": "image",
                        "image_url": "https://a.slack-edge.com/80588/img/calendar/calendar-emoji.png",
                        "alt_text": "calendar thumbnail",
                    },
                },
                {"type": "divider"},
                {
                    "type": "markdown",
                    "text": (
                        f":information_source: If <@{conductor_id}> is unavailable, <@{fallback_conductor_id}> will take over. :handshake:"  # noqa: E501
                    ),
                },
            ]

            return {
                "text": text,
                "blocks": blocks,
            }

        if message_type == "read_doc":
            text = (
                f"*Hey <@{conductor_id}> (and <@{fallback_conductor_id}>)* :wave:"
                "\n"
                f"Please take a moment to review the *{cls.DOC_REF}*."
                "\n\n"
                "See you at the next standup at :clock9: *9:00 AM*!"
            )

            return {
                "text": text,
                "blocks": TimurSlack.get_basic_block(text),
            }

        if message_type == "morning":
            text = (
                f"*Hey <@{conductor_id}> (and <@{fallback_conductor_id}>)* :wave:\n"
                "\n"
                "Just a friendly early morning reminder! 🌅\n"
                "\n"
                "Don't be late! 😄 See you at the standup at :clock9: *9:00 AM*!"
            )

            return {
                "text": text,
                "blocks": TimurSlack.get_basic_block(text),
            }

        typing.assert_never()


def _get_next_conductors(daily_standup: DailyUserStandup) -> tuple[User, User]:
    assignable_user_qs = User.get_users_with_slack_user_id().filter(assign_for_standup=True)
    assignable_user_count = assignable_user_qs.count()

    assert assignable_user_count > 0, "Make sure there are assignable users"

    available_users_qs = assignable_user_qs.exclude(
        id__in=DailyUserStandup.objects.filter(
            conductor_id__isnull=False,
            date__lt=daily_standup.date,
        )
        .order_by("-date")
        .values("conductor_id")[: assignable_user_count - 1],
    )
    new_conductor = available_users_qs.first()
    # TODO(thenav56): Proper handle
    assert new_conductor is not None, "Conductor should be selected"

    available_fallback_users_qs = (
        assignable_user_qs.exclude(
            id__in=DailyUserStandup.objects.filter(
                fallback_conductor_id__isnull=False,
                date__lt=daily_standup.date,
            )
            .order_by("-date")
            .values("fallback_conductor_id")[: assignable_user_count - 2],
        )
        .exclude(id=new_conductor.pk)
        .order_by("?")
    )

    new_fallback_conductor = available_fallback_users_qs.first()

    # TODO(thenav56): Proper handle
    assert new_fallback_conductor is not None, "Fallback conductor should be selected"
    assert new_conductor.pk != new_fallback_conductor.pk, "Primary and fallback conductor should't be same"

    return new_conductor, new_fallback_conductor


# TODO(thenav56): try/catch
def setup_next_standup():
    timur_slack = TimurSlack()
    now_date = timezone.now().date()
    next_working_day = Event.get_next_working_date(
        now_date=now_date,
        skip_dates=[now_date],
    )
    assert now_date != next_working_day, "Next working day should't be today"

    daily_standup = DailyUserStandup.objects.get_or_create(date=next_working_day)[0]

    if daily_standup.conductor_id is None:
        daily_standup.conductor, daily_standup.fallback_conductor = _get_next_conductors(daily_standup)
        daily_standup.save(update_fields=("conductor", "fallback_conductor"))

    if daily_standup.quote_id is None and (quote := Quote.get_random_quote(track_last_viewed=True)):
        daily_standup.quote = quote
        daily_standup.save(update_fields=("quote",))

    if daily_standup.slack_thread_ts is None:
        slack_response = timur_slack.send_slack_message(
            **SlackMessage.get_message(daily_standup, "assign"),
        )
        daily_standup.slack_thread_ts = slack_response.get("ts")
        daily_standup.save(update_fields=("slack_thread_ts",))


def _today_standup_slack_message(m_type: typing.Literal["before_standup"] | SlackMessage.MessageType):
    timur_slack = TimurSlack()
    today = timezone.now().date()

    slack_message: TimurSlack.TimurSlackMessageArgumentType

    if m_type == "before_standup":
        slack_message = SlackMessage.get_normal_message(m_type)
        slack_thread_ts = None
        if Event.get_next_working_date(now_date=today) != today:
            logger.warning(
                "%s: Not working day: %s",
                m_type,
                today.strftime("%A, %B %-d, %Y"),
            )
            return

    else:
        if m_type == "read_doc":
            next_working_day = Event.get_next_working_date(
                now_date=today,
                skip_dates=[today],
            )
            daily_standup = DailyUserStandup.objects.filter(date=next_working_day).first()
        elif m_type == "morning":
            daily_standup = DailyUserStandup.objects.filter(date=today).first()
        elif m_type == "assign":
            return
        else:
            typing.assert_never(m_type)

        if daily_standup is None:
            logger.warning(
                "%s: There is no daily_standup for today: %s",
                m_type,
                today.strftime("%A, %B %-d, %Y"),
            )
            return

        slack_message = SlackMessage.get_message(daily_standup, m_type)
        slack_thread_ts = daily_standup.slack_thread_ts

    timur_slack.send_slack_message(**slack_message, thread_ts=slack_thread_ts)


def read_doc_reminder():
    _today_standup_slack_message("read_doc")


def morning_reminder():
    _today_standup_slack_message("morning")


def before_standup_reminder():
    _today_standup_slack_message("before_standup")
