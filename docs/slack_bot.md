# Slack Bot

> [!IMPORTANT]
> This is work in progress

## Setup

```json
{
    "display_information": {
        "name": "Timur",
        "description": "Timur",
        "background_color": "#1c0d03"
    },
    "features": {
        "bot_user": {
            "display_name": "Timur",
            "always_online": false
        }
    },
    "oauth_config": {
        "scopes": {
            "bot": [
                "channels:history",
                "chat:write",
                "chat:write.customize",
                "groups:history",
                "im:history",
                "incoming-webhook",
                "mpim:history",
                "reactions:write",
                "users:read",
                "users:read.email"
            ]
        }
    },
    "settings": {
        "allowed_ip_address_ranges": [
            "110.34.1.108/32"
        ],
        "event_subscriptions": {
            "request_url": "https://<APP_DOMAIN>/slack/events/",
            "bot_events": [
                "message.channels",
                "message.groups",
                "message.im",
                "message.mpim"
            ]
        },
        "interactivity": {
            "is_enabled": true,
            "request_url": "https://<APP_DOMAIN>/slack/interactions/"
        },
        "org_deploy_enabled": false,
        "socket_mode_enabled": false,
        "token_rotation_enabled": false
    }
}
```

## Events
- https://api.slack.com/apis/events-api
- https://api.slack.com/apis/socket-mode [Dev]
- https://api.slack.com/apis/http [Prod]

## Availability channel

Timur reads leave and WFH messages from the availability channel (e.g. `#tc-availability`) and updates the poster's journal.

- Endpoint: `POST /slack/events/` (Events API, verified with `SLACK_SIGNING_SECRET`)
- Timur's replies have a "How did Timur decide?" button. It opens a modal with the steps of the run (message,
  understood dates with the quoted words, working days, journal before/after), only for the person who posted
  and for Timur admins (active superusers whose `slack_user_id` is the clicker's Slack id).
  Endpoint: `POST /slack/interactions/` (interactivity request URL, verified with `SLACK_SIGNING_SECRET`)
- Invite the bot to the channel and set `SLACK_AVAILABILITY_CHANNEL_ID`
- `SLACK_AVAILABILITY_MODE`:
  - `off`: events are ignored. Slack's URL verification is still answered when `SLACK_SIGNING_SECRET` is set
  - `shadow`: messages are parsed and the planned journal changes are saved (Django admin > Slack availability runs). No journal writes, reactions or replies
  - `live`: journal is updated, Timur reacts and replies in the thread
- Parser: Ollama (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, optional `OLLAMA_API_KEY` sent as a bearer token)
- Requires a Celery worker (`celery -A main worker`)
- `SLACK_API_BASE_URL` points the Slack client at another Web API URL (e.g. a local mock)
- Message-derived text (parser input, unclear and quoted phrases, the steps shown by the button, reply, error) is blanked after `SLACK_AVAILABILITY_RETENTION_DAYS` (default 90) by the `slack_availability_purge` cronjob. Dates and leave/WFH types are kept
