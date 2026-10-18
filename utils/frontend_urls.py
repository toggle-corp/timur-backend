"""
URL builders for pages in the frontend app (timur-web-app)

Routes are defined in timur-web-app/src/App/routes/index.tsx

TODO: Replace these with backend permalinks (e.g. /permalink/journal/<date>/ redirecting to the frontend),
so links shared outside the app (Slack, email) keep working when frontend routes change.
"""

import datetime

from main import config


def _build(path: str) -> str:
    return f"{config.APP_FRONTEND_HOST.geturl().rstrip('/')}/{path.lstrip('/')}"


def daily_journal(date: datetime.date) -> str:
    return _build(f"daily-journal/{date.isoformat()}/")
