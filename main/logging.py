import logging

import requests
from banjo_utils.health import is_health_probe_path


def skip_health_probe_logs(record: logging.LogRecord):
    """Drop *successful* request-line log records for k8s health-probe paths (/healthz/*)."""
    args = record.args
    path = ""
    status = ""
    if isinstance(args, dict):  # gunicorn.access
        path = str(args.get("U", ""))
        status = str(args.get("s", ""))
    elif isinstance(args, tuple | list) and args:  # django.server request line
        request_line = str(args[0]).strip('"').split(" ")
        if len(request_line) >= 2:
            path = request_line[1]
        if len(args) >= 2:
            status = str(args[1])
    is_probe_ok = is_health_probe_path(path) and status.startswith("2")
    return not is_probe_ok


def log_render_custom_field(record: logging.LogRecord):
    """
    Append extra->context to logs
    NOTE: This will appear in logs when used with logger.xxx(..., extra={'context': {..content}})

    Add short_name using name
    """
    extra_str = ""
    if extra_raw := getattr(record, "context", None):
        extra_str = f" - EXTRA:{str(extra_raw)}"
    record.context = extra_str

    # Break the logger name into parts
    parts = record.name.split(".")
    # Take the last two components (or fewer if not available)
    record.short_name = ".".join(parts[-2:]) if len(parts) >= 2 else record.name
    return True


def log_extra(extra: dict):
    """
    Basic helper function to view extra argument in logs using log_render_custom_field
    """
    return {
        "context": extra,
    }


def log_extra_response(
    *,
    response: requests.Response,
    **kwargs: str | int | None,
):
    return log_extra(
        {
            **kwargs,
            "response": {
                "url": response.url,
                "status_code": response.status_code,
                "content": response.content,
            },
        },
    )
