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
            "bot_events": [
                "message.channels",
                "message.groups",
                "message.im",
                "message.mpim"
            ]
        },
        "interactivity": {
            "is_enabled": true
        },
        "org_deploy_enabled": false,
        "socket_mode_enabled": true,
        "token_rotation_enabled": false
    }
}
```

## Events
- https://api.slack.com/apis/events-api
- https://api.slack.com/apis/socket-mode [Dev]
- https://api.slack.com/apis/http [Prod]
