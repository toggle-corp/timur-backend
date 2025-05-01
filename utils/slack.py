from slack_sdk import WebClient
from slack_sdk.web.slack_response import SlackResponse

from main import config


class TimurSlackInitializationError(Exception): ...


class TimurSlack:
    def __init__(self):
        slack_config = config.Slack.load_slack_config()
        if slack_config.enabled is False:
            raise TimurSlackInitializationError()
        self.client = WebClient(token=slack_config.token)
        self.channel = slack_config.channel
        self.bot_name = slack_config.bot_name
        self.bot_icon = slack_config.bot_icon

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
        text: str,
        thread_ts: str | None = None,
    ) -> SlackResponse:
        resp = self.client.chat_postMessage(
            channel=self.channel,
            username=self.bot_name,
            icon_url=self.bot_icon,
            text=text,
            thread_ts=thread_ts,
        )

        # TODO: Check if this is required
        resp.validate()

        return resp
