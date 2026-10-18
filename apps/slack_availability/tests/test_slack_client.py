from unittest import mock

from utils.slack import TimurSlack

PARENT_TS = "1760000000.000100"


def reply(ts: str) -> dict:
    return {"type": "message", "user": "U1", "text": ts, "ts": ts, "thread_ts": PARENT_TS}


def test_fetch_thread_messages_skips_repeated_parent():
    parent = {"type": "message", "user": "U1", "text": "Leave today", "ts": PARENT_TS, "thread_ts": PARENT_TS}
    slack = TimurSlack.__new__(TimurSlack)
    slack.client = mock.Mock()
    slack.client.conversations_replies.side_effect = [
        {"messages": [parent, reply("1760000001.000100")], "response_metadata": {"next_cursor": "page-2"}},
        # Slack repeats the parent at the top of later pages
        {"messages": [parent, reply("1760000002.000100")], "response_metadata": {"next_cursor": ""}},
    ]

    messages = slack.fetch_thread_messages("C1", PARENT_TS)

    assert [message["ts"] for message in messages] == [PARENT_TS, "1760000001.000100", "1760000002.000100"]
    assert [call.kwargs["cursor"] for call in slack.client.conversations_replies.call_args_list] == [None, "page-2"]


def test_send_slack_message_unfurl():
    slack = TimurSlack.__new__(TimurSlack)
    slack.client = mock.Mock()
    slack.standup_channel_id = "C-STANDUP"
    slack.bot_name = "Timur"
    slack.bot_icon = None

    slack.send_slack_message(text="Hi")
    slack.send_slack_message(text="Hi", channel="C1", unfurl=False)

    first, second = slack.client.chat_postMessage.call_args_list
    assert (first.kwargs["unfurl_links"], first.kwargs["unfurl_media"]) == (True, True)
    assert (second.kwargs["unfurl_links"], second.kwargs["unfurl_media"]) == (False, False)
