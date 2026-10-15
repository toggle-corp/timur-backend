import os
import subprocess
import sys

import pytest
from django.conf import settings

from apps.slack_availability.parsers import PARSERS

LIVE_ENV = {
    "SLACK_BOT_ENABLED": "true",
    "SLACK_BOT_NAME": "Timur",
    "SLACK_BOT_ICON": "https://example.com/icon.png",
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_BOT_CHANNEL": "C-STANDUP",
    "SLACK_AVAILABILITY_MODE": "live",
    "SLACK_AVAILABILITY_CHANNEL_ID": "C-AVAILABILITY",
    "SLACK_SIGNING_SECRET": "test-signing-secret",
    "SLACK_AVAILABILITY_PARSER": "ollama",
    "OLLAMA_BASE_URL": "http://ollama.test",
    "OLLAMA_MODEL": "test-model",
}


def load_settings(**overrides: str | None) -> subprocess.CompletedProcess:
    env = {**os.environ, **LIVE_ENV, **overrides}
    env = {key: value for key, value in env.items() if value is not None}
    return subprocess.run(
        [sys.executable, "-c", "import main.settings"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_parsers_match_settings():
    assert set(PARSERS) == set(settings.SLACK_AVAILABILITY_PARSERS)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({}, None),
        ({"SLACK_AVAILABILITY_PARSER": "olama"}, "Invalid SLACK_AVAILABILITY_PARSER: olama"),
        ({"SLACK_AVAILABILITY_MODE": "on"}, "Invalid SLACK_AVAILABILITY_MODE: on"),
        ({"SLACK_SIGNING_SECRET": None}, "SLACK_AVAILABILITY_MODE requires SLACK_SIGNING_SECRET"),
        # Off mode does not need the availability settings
        (
            {
                "SLACK_AVAILABILITY_MODE": "off",
                "SLACK_SIGNING_SECRET": None,
                "SLACK_AVAILABILITY_PARSER": "olama",
            },
            None,
        ),
    ],
)
def test_settings_validation(overrides: dict[str, str | None], error: str | None):
    result = load_settings(**overrides)
    if error is None:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert error in result.stderr
