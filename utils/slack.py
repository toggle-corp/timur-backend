import typing

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.models.blocks.blocks import Block
from slack_sdk.web.slack_response import SlackResponse

from main import config


class TimurSlackInitializationError(Exception): ...


class TimurSlack:
    class TimurSlackMessageArgumentType(typing.TypedDict):
        text: str
        blocks: typing.Sequence[dict | Block] | None

    def __init__(self):
        slack_config = config.Slack.load_slack_config()
        if slack_config.enabled is False:
            raise TimurSlackInitializationError()
        self.client = WebClient(
            token=slack_config.token,
            # WebClient joins method names onto base_url, so it needs a trailing slash
            base_url=(slack_config.api_base_url.rstrip("/") + "/") if slack_config.api_base_url else WebClient.BASE_URL,
        )
        self.channel = slack_config.channel
        self.bot_name = slack_config.bot_name
        self.bot_icon = slack_config.bot_icon

    @staticmethod
    def get_basic_block(text: str) -> typing.Sequence[dict | Block]:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            },
        ]

    def fetch_users(
        self,
        exclude_bot=True,
        exclude_deleted=True,
    ):
        next_cursor = None
        while True:
            resp = self.client.users_list(cursor=next_cursor)
            for member in resp["members"] or []:
                if exclude_bot and (member["id"] == "USLACKBOT" or member["is_bot"]):
                    continue
                if exclude_deleted and member["deleted"]:
                    continue
                yield member
            next_cursor = resp["response_metadata"]["next_cursor"]  # type: ignore[reportOptionalSubscript]
            if next_cursor in (None, ""):
                break

    def lookup_user_by_email(self, email: str):
        return self.client.users_lookupByEmail(email=email)

    def lookup_user_id_by_email(self, email: str) -> str | None:
        return self.lookup_user_by_email(email).get("user", {}).get("id")

    def send_slack_message(
        self,
        text: str | None = None,
        blocks: str | typing.Sequence[dict | Block] | None = None,
        thread_ts: str | None = None,
        channel: str | None = None,
    ) -> SlackResponse:
        resp = self.client.chat_postMessage(
            channel=channel or self.channel,
            username=self.bot_name,
            icon_url=self.bot_icon,
            blocks=blocks,
            text=text,
            thread_ts=thread_ts,
        )

        # TODO: Check if this is required
        resp.validate()

        return resp

    def add_reaction(self, channel: str, ts: str, name: str):
        try:
            self.client.reactions_add(channel=channel, timestamp=ts, name=name)
        except SlackApiError as e:
            if e.response.get("error") != "already_reacted":
                raise

    def fetch_thread_messages(self, channel: str, thread_ts: str) -> list[dict]:
        """
        Return the parent message followed by its replies, oldest first
        """
        messages: list[dict] = []
        next_cursor = None
        while True:
            try:
                resp = self.client.conversations_replies(
                    channel=channel,
                    ts=thread_ts,
                    cursor=next_cursor,
                    limit=200,
                )
            except SlackApiError as e:
                if e.response.get("error") == "thread_not_found":
                    return []
                raise
            page_messages = resp.get("messages") or []
            if next_cursor is not None:
                # Slack repeats the parent message at the top of every page
                page_messages = [message for message in page_messages if message.get("ts") != thread_ts]
            messages.extend(page_messages)
            next_cursor = (resp.get("response_metadata") or {}).get("next_cursor")
            if next_cursor in (None, ""):
                break
        return messages

    def open_view(self, trigger_id: str, view: dict):
        """
        https://docs.slack.dev/reference/methods/views.open/
        """
        self.client.views_open(trigger_id=trigger_id, view=view)

    def fetch_user_email(self, slack_user_id: str) -> str | None:
        resp = self.client.users_info(user=slack_user_id)
        return ((resp.get("user") or {}).get("profile") or {}).get("email")
