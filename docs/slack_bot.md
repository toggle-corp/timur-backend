# Slack Bot

> [!IMPORTANT]
> This is work in progress

## Setup

```yaml
display_information:
  name: Timur
  description: Timur
  background_color: "#b34c2e"
features:
  bot_user:
    display_name: Timur
    always_online: false
oauth_config:
  scopes:
    bot:
    - chat:write
    - chat:write.customize
    - users:read
    - users:read.email
    - reactions:write
    # For Private channel
    - groups:history
    # (Optional) For Public channel
    - channels:history
    # For DM
    # - im:history
    # - mpim:history
  pkce_enabled: false
settings:
  allowed_ip_address_ranges:  # Only access from Togglecorp network
    - XX.XX.XX.XX/32
  event_subscriptions:
    request_url: https://<APP_DOMAIN>/slack/events/
    bot_events:
      # For Private channel
      - message.groups
      # (Optional) For Public channel
      - message.channels
      # For DM
      # - message.im
      # - message.mpim
  interactivity:
    is_enabled: true
    request_url: https://<APP_DOMAIN>/slack/interactions/
  org_deploy_enabled: false
  socket_mode_enabled: false
  is_mcp_enabled: false
  app_level_token_rotation_enabled: false
  token_rotation_enabled: false
```

## Events
- https://api.slack.com/apis/events-api
- https://api.slack.com/apis/socket-mode [Dev]
- https://api.slack.com/apis/http [Prod]

## Standup channel

Standup messages go to `SLACK_STANDUP_CHANNEL_ID`, the channel ID (e.g. `C0123ABCD`, from the channel details), not its name. Invite the bot to the channel.

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

## Availability: Slack app setup

Do these steps once per Slack app, in [api.slack.com/apps](https://api.slack.com/apps) > the Timur app.
`<APP_DOMAIN>` is the backend's public host. Slack sends events and
button clicks to it over HTTPS, so it must be reachable from the internet.

1. Deploy the backend first, with these set:
   - `SLACK_SIGNING_SECRET` (step 3)
   - `SLACK_AVAILABILITY_CHANNEL_ID`, `SLACK_STANDUP_CHANNEL_ID` (step 7)
   - `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY`
   - `SLACK_AVAILABILITY_MODE=off`

   With the signing secret set, `/slack/events/` answers Slack's URL verification in every mode, so steps 4
   and 5 work while the feature is off.
   Check: `curl -X POST https://<APP_DOMAIN>/slack/events/` returns `401`. A `404` means the deployed backend
   doesn't have the endpoint yet.
2. **OAuth & Permissions > Scopes > Bot Token Scopes**: make sure these are present.

   | Scope | Used for |
   |---|---|
   | `chat:write` | replies, standup messages (`chat.postMessage`) |
   | `chat:write.customize` | bot name and icon on messages |
   | `reactions:write` | `:eyes:`, `:white_check_mark:`, `:warning:` reactions (new for availability) |
   | `channels:history` | `message.channels` events, reading thread replies (`conversations.replies`) |
   | `groups:history` | the same for a private channel |
   | `users:read`, `users:read.email` | matching Slack users to Timur users (`users.list`, `users.info`, `users.lookupByEmail`) |

   Opening the "How did Timur decide?" modal (`views.open`) needs no scope.
   If you added a scope, click **Reinstall to Workspace** (the banner at the top). The bot token
   (`xoxb-...`, `SLACK_BOT_TOKEN`) stays the same after a reinstall. If it ever changes, update the secret.
3. **Basic Information > App Credentials > Signing Secret**: copy it into `SLACK_SIGNING_SECRET` and redeploy.
4. **Socket Mode**: turn it off. With Socket Mode on, Slack sends events over a websocket instead of HTTP and
   hides the Request URL fields. Timur only takes HTTP.
5. **Event Subscriptions**:
   1. Turn on **Enable Events**.
   2. **Request URL**: `https://<APP_DOMAIN>/slack/events/` (keep the trailing slash). Wait for **Verified**.
   3. **Subscribe to bot events**: add `message.channels` (and `message.groups` if the channel is private).
      Edits, deletes and thread replies arrive as `message` events, so nothing else is needed.
   4. **Save Changes**. Reinstall if Slack asks.
6. **Interactivity & Shortcuts**:
   1. Turn on **Interactivity**.
   2. **Request URL**: `https://<APP_DOMAIN>/slack/interactions/`. Slack doesn't verify this URL on save.
   3. **Save Changes**.
7. Invite the bot to the channel (`/invite @Timur`). Get the channel ID from the channel name > **About** >
   bottom (`C0...`) and set `SLACK_AVAILABILITY_CHANNEL_ID`.
8. Roll out:
   1. `SLACK_AVAILABILITY_MODE=shadow`: Timur parses new posts and saves the planned journal changes, without
      writing the journal, reacting or replying. Check **Django admin > Slack availability runs** after a few
      posts.
   2. `SLACK_AVAILABILITY_MODE=live`: Timur reacts (`:eyes:` on every post it reads, `:white_check_mark:` when
      the journal changed, `:warning:` on failure or an unknown user), updates the journal and replies in the
      thread. Click "How did Timur decide?" on a reply to see the steps.
   3. Rollback: `SLACK_AVAILABILITY_MODE=off`. Events are then ignored.

### Troubleshooting

- **Request URL not verified**: the backend is missing `SLACK_SIGNING_SECRET` (it then returns an empty `200`,
  which Slack rejects), the secret doesn't match the app's Signing Secret (`401`), the endpoint isn't deployed
  yet (`404`), or the URL lacks the trailing slash.
- **No reaction on a post**:
  - `SLACK_AVAILABILITY_MODE` is `off` or `shadow`
  - `SLACK_AVAILABILITY_CHANNEL_ID` is the channel name instead of the ID
  - the bot isn't in the channel, or `message.channels` isn't subscribed
  - the Celery worker isn't running (events are queued, check the worker logs)
- **`:warning:` and no reply**: the poster's Slack account isn't linked to a Timur user (`slack_user_id`). Run
  `python manage.py sync_slack_users_id` or set it in Django admin.
- **Button shows nothing**: Interactivity is off or its Request URL is wrong, or the mode is `off`.
- **`missing_scope` or `not_allowed_token_type` in logs**: add the scope from step 2 and reinstall.
- **`invalid_auth` from the backend**: the bot token changed, or `allowed_ip_address_ranges` in the app
  settings doesn't include the cluster's outbound IP.
