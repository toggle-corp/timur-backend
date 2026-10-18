import datetime
import json
import typing
from unittest import mock

import pytest
import requests
from django.test import override_settings

from apps.slack_availability.parsers import (
    OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    AvailabilityParserError,
    OllamaAvailabilityParser,
    build_user_prompt,
    format_calendar,
    get_parser,
    parse_output,
)
from apps.slack_availability.structs import AvailabilityRange, Half, MissingDetail, ThreadMessage, UnclearPart
from main import config
from main.tests import TestCase

from . import AVAILABILITY_SETTINGS

TODAY = datetime.date(2026, 10, 12)

VALID_OUTPUT = {
    "is_about_poster_availability": True,
    "availability": [
        {
            "source_phrase": " leave Tue and Wed ",
            "start_date": "2026-10-13",
            "end_date": "2026-10-14",
            "leave": "full",
            "wfh": "none",
        },
        {"start_date": "2026-10-15", "end_date": "2026-10-15", "leave": "first_half", "wfh": "second_half"},
        {"start_date": "2026-10-16", "end_date": "2026-10-16", "leave": "half_unknown", "wfh": "none"},
        {"start_date": "2026-10-19", "end_date": "2026-10-19", "leave": "full", "wfh": "none", "open_end": True},
    ],
    "unclear": [
        {"phrase": "on leave till further notice", "missing": "end_date"},
        {"phrase": " ", "missing": "dates"},
        {"phrase": "off sometime", "missing": "unknown"},
        "next week sometime",
    ],
    "needs_care": True,
    "confidence": 0.8,
}


def test_parse_output():
    result = parse_output(VALID_OUTPUT)
    assert result.ranges == [
        AvailabilityRange(
            datetime.date(2026, 10, 13),
            datetime.date(2026, 10, 14),
            leave=Half.FULL,
            source_phrase="leave Tue and Wed",
        ),
        # A missing source phrase is accepted
        AvailabilityRange(
            datetime.date(2026, 10, 15),
            datetime.date(2026, 10, 15),
            leave=Half.FIRST_HALF,
            wfh=Half.SECOND_HALF,
        ),
        AvailabilityRange(datetime.date(2026, 10, 16), datetime.date(2026, 10, 16), leave=Half.UNKNOWN),
        AvailabilityRange(datetime.date(2026, 10, 19), datetime.date(2026, 10, 19), leave=Half.FULL, open_end=True),
    ]
    assert result.is_about_availability is True
    assert result.unclear == [
        UnclearPart("on leave till further notice", MissingDetail.END_DATE),
        # An unknown missing detail asks for both
        UnclearPart("off sometime", MissingDetail.DATES_AND_TYPE),
        UnclearPart("next week sometime", MissingDetail.DATES_AND_TYPE),
    ]
    assert result.needs_care is True
    assert result.confidence == 0.8
    assert result.raw == VALID_OUTPUT
    assert result.model == ""


def test_parse_output_not_about_availability():
    result = parse_output({**VALID_OUTPUT, "is_about_poster_availability": False})
    assert result.is_about_availability is False


def test_output_schema_decides_relevance_first():
    assert next(iter(OUTPUT_SCHEMA["properties"])) == "is_about_poster_availability"
    assert "is_about_poster_availability" in OUTPUT_SCHEMA["required"]


def test_output_schema_quotes_source_phrase_first():
    item_schema = OUTPUT_SCHEMA["properties"]["availability"]["items"]
    assert next(iter(item_schema["properties"])) == "source_phrase"
    assert "source_phrase" in item_schema["required"]
    assert "open_end" in item_schema["required"]
    assert "source_phrase" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"availability": [], "unclear": [], "confidence": 1},
        {"is_about_poster_availability": "yes", "availability": [], "unclear": [], "confidence": 1},
        {"is_about_poster_availability": True, "availability": [], "unclear": []},
        {"is_about_poster_availability": True, "availability": {}, "unclear": [], "confidence": 1},
        {"is_about_poster_availability": True, "availability": ["x"], "unclear": [], "confidence": 1},
        {
            "is_about_poster_availability": True,
            "availability": [{"start_date": "13-10-2026", "end_date": "2026-10-13", "leave": "full", "wfh": "none"}],
            "unclear": [],
            "confidence": 1,
        },
        {
            "is_about_poster_availability": True,
            "availability": [{"start_date": "2026-10-13", "end_date": "2026-10-13", "leave": "morning", "wfh": "none"}],
            "unclear": [],
            "confidence": 1,
        },
    ],
)
def test_parse_output_invalid(data):
    with pytest.raises(AvailabilityParserError):
        parse_output(data)


def ollama_response(content: str, status_code: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps({"message": {"role": "assistant", "content": content}}).encode()
    return response


@override_settings(**AVAILABILITY_SETTINGS)
class TestOllamaAvailabilityParser(TestCase):
    @typing.override
    def setUp(self):
        super().setUp()
        self.parser = OllamaAvailabilityParser(config.SlackAvailability.load_ollama_config())
        self.messages = [
            ThreadMessage(
                ts="1760240000.000100",
                posted_at=datetime.datetime(2026, 10, 12, 9, 5, tzinfo=datetime.UTC),
                text="Leave tomorrow",
            ),
            ThreadMessage(
                ts="1760250000.000100",
                posted_at=datetime.datetime(2026, 10, 12, 11, 30, tzinfo=datetime.UTC),
                text="and wednesday",
            ),
        ]

    @mock.patch("apps.slack_availability.parsers.requests.post")
    def test_parse(self, post_mock):
        post_mock.return_value = ollama_response(json.dumps(VALID_OUTPUT))

        result = self.parser.parse(self.messages, TODAY)

        assert len(result.ranges) == 4
        assert result.model == "test-model"
        post_mock.assert_called_once()
        assert post_mock.call_args.args[0] == "http://ollama.test/api/chat"
        kwargs = post_mock.call_args.kwargs
        assert kwargs["headers"] == {"Authorization": "Bearer test-api-key"}
        assert kwargs["timeout"] == 5
        payload = kwargs["json"]
        assert payload["model"] == "test-model"
        assert payload["stream"] is False
        assert payload["format"] == OUTPUT_SCHEMA
        assert payload["options"] == {"temperature": 0, "num_ctx": 4096}
        assert payload["think"] is False
        assert payload["keep_alive"] == "5m"
        assert payload["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
        user_prompt = payload["messages"][1]["content"]
        assert "Today is Mon 2026-10-12" in user_prompt
        assert (
            "[Mon 2026-10-12 09:05 | today = Mon 2026-10-12 | tomorrow = Tue 2026-10-13"
            " | day after tomorrow = Wed 2026-10-14] Leave tomorrow\n"
            "[Mon 2026-10-12 11:30 | today = Mon 2026-10-12 | tomorrow = Tue 2026-10-13"
            " | day after tomorrow = Wed 2026-10-14] and wednesday"
        ) in user_prompt
        # The prompt that was sent is returned for the run record
        assert result.prompt == user_prompt

    @override_settings(OLLAMA_API_KEY=None)
    @mock.patch("apps.slack_availability.parsers.requests.post")
    def test_parse_without_api_key(self, post_mock):
        post_mock.return_value = ollama_response(json.dumps(VALID_OUTPUT))
        parser = OllamaAvailabilityParser(config.SlackAvailability.load_ollama_config())
        parser.parse(self.messages, TODAY)
        assert post_mock.call_args.kwargs["headers"] == {}

    @mock.patch("apps.slack_availability.parsers.requests.post")
    def test_parse_errors(self, post_mock):
        for side_effect in [
            requests.ConnectionError("down"),
            requests.Timeout("slow"),
            ollama_response("{}", status_code=500),
            ollama_response("not json"),
        ]:
            if isinstance(side_effect, requests.Response):
                post_mock.side_effect = None
                post_mock.return_value = side_effect
            else:
                post_mock.side_effect = side_effect
            with self.assertLogs("apps.slack_availability.parsers", level="WARNING"), pytest.raises(AvailabilityParserError):
                self.parser.parse(self.messages, TODAY)

    def test_get_parser(self):
        assert isinstance(get_parser(), OllamaAvailabilityParser)

    @override_settings(SLACK_AVAILABILITY_PARSER="unknown")
    def test_get_parser_unknown(self):
        with pytest.raises(AvailabilityParserError):
            get_parser()


def test_format_calendar():
    # Fri to the next Tue: weeks start on Monday
    calendar = format_calendar(datetime.date(2026, 10, 16), datetime.date(2026, 10, 20))
    assert calendar.splitlines() == [
        "Mon 2026-10-12, Tue 2026-10-13, Wed 2026-10-14, Thu 2026-10-15, Fri 2026-10-16, Sat 2026-10-17, Sun 2026-10-18",
        "Mon 2026-10-19, Tue 2026-10-20, Wed 2026-10-21, Thu 2026-10-22, Fri 2026-10-23, Sat 2026-10-24, Sun 2026-10-25",
    ]


def test_build_user_prompt_calendar_covers_thread_and_today():
    messages = [
        ThreadMessage(
            ts="1",
            posted_at=datetime.datetime(2026, 8, 11, 10, 0, tzinfo=datetime.UTC),
            text="Leave from Thursday to next Tuesday",
        ),
        ThreadMessage(
            ts="2",
            posted_at=datetime.datetime(2026, 8, 14, 10, 0, tzinfo=datetime.UTC),
            text="only till Monday",
        ),
    ]
    prompt = build_user_prompt(messages, datetime.date(2026, 8, 14))

    calendar = prompt.split("Calendar:\n")[1].split("\n\n")[0].splitlines()
    # From the week of the first message to 21 days after the latest of today and the last message
    assert calendar[0].startswith("Mon 2026-08-10")
    assert "Fri 2026-09-04" in calendar[-1]
    assert "Today is Fri 2026-08-14 (" in prompt
    assert (
        "[Tue 2026-08-11 10:00 | today = Tue 2026-08-11 | tomorrow = Wed 2026-08-12 | day after tomorrow = Thu 2026-08-13]"
        in prompt
    )
    assert (
        "[Fri 2026-08-14 10:00 | today = Fri 2026-08-14 | tomorrow = Sat 2026-08-15 | day after tomorrow = Sun 2026-08-16]"
        in prompt
    )


def test_system_prompt_mentions_nepali_terms():
    for term in ["bholi", "aaja", "parsi", "ghar bata kaam", "bihana", "beluka", "chhutti"]:
        assert term in SYSTEM_PROMPT


def test_system_prompt_guards_against_over_asking():
    assert "is_about_poster_availability" in SYSTEM_PROMPT
    # A plain half day stays unknown, and posts about others are not about the poster
    assert '"Half day leave today"' in SYSTEM_PROMPT
    assert "<@U0123> is sick today" in SYSTEM_PROMPT


def flat_system_prompt() -> str:
    # Line wrapping in the prompt is not significant
    return " ".join(SYSTEM_PROMPT.split())


@pytest.mark.parametrize(
    "example",
    [
        # Explicit halves map to that half
        '"I\'ll be on leave for the second half" -> 2026-10-12..2026-10-12 leave second_half',
        '"Train got cancelled, so first half leave" -> 2026-10-12..2026-10-12 leave first_half',
        # WFH without a half is a full day
        '"WFH today, limited availability" -> 2026-10-12..2026-10-12 wfh full',
        # Leaving and continuing from home is the second half
        '"Leaving at 3, will continue from home" -> 2026-10-12..2026-10-12 wfh second_half',
        # Each range takes its dates from its own phrase
        '"WFH second half today, leave tomorrow" -> 2026-10-12..2026-10-12 wfh second_half and '
        "2026-10-13..2026-10-13 leave full",
        # This week ends on its Friday
        '"Working from home this entire week" -> 2026-10-12..2026-10-16 wfh full',
    ],
)
def test_system_prompt_examples(example):
    assert example in flat_system_prompt()


@pytest.mark.parametrize(
    "phrase",
    [
        '"Will miss the standup today"',
        '"Heading out early to rest"',
        '"Might WFH tomorrow if the plumber comes"',
    ],
)
def test_system_prompt_not_about_availability_examples(phrase):
    not_about = flat_system_prompt().split("is_about_poster_availability false:")[1]
    assert phrase in not_about


def test_system_prompt_half_and_date_rules():
    prompt = flat_system_prompt()
    assert '"half_unknown" only when "half day" is stated with no marker at all' in prompt
    assert "false for conditional or uncertain plans" in prompt
    assert "Take each range's dates only from its source_phrase" in prompt
    assert "whatever the time of day" in prompt
