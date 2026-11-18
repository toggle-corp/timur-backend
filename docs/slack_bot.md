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
  shortcuts:
    - name: Why did Timur do this?
      type: message
      callback_id: timur_why
      description: See how Timur read this message
oauth_config:
  scopes:
    bot:
    - chat:write
    - chat:write.customize
    - users:read
    - users:read.email
    - reactions:write
    - emoji:read
    - commands
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
- Reactions: see [Availability: reactions](#availability-reactions)
- Timur's replies have a "How did Timur decide?" button. It opens a modal with the steps of the run (message,
  understood dates with the quoted words, working days, journal before/after), only for the person who posted
  and for Timur admins (active superusers whose `slack_user_id` is the clicker's Slack id).
  Endpoint: `POST /slack/interactions/` (interactivity request URL, verified with `SLACK_SIGNING_SECRET`)
- The "Why did Timur do this?" message shortcut (callback ID `timur_why`, in a message's **More actions** menu)
  opens the same modal for any message in the channel: the latest run triggered by that message, or for a
  top-level message, by any message of its thread. The modal also shows the result of the run and the latest
  journal changes of its dates (who changed them, and when). The author of the message and Timur admins can open
  it. When there is no run, the modal says why (another channel, a bot message, a reply by someone other than
  the poster, a deleted thread, an old message, or Timur is off).
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
   | `chat:write` | replies, standup messages (`chat.postMessage`), notices only the poster sees (`chat.postEphemeral`) |
   | `chat:write.customize` | bot name and icon on messages |
   | `reactions:write` | adding and removing the seen and outcome reactions (`reactions.add`, `reactions.remove`) |
   | `emoji:read` | finding the custom Timur emojis (`emoji.list`). Without it, Timur uses the native emojis |
   | `commands` | the "Why did Timur do this?" message shortcut. Slack refuses shortcuts without it |
   | `channels:history` | `message.channels` events, reading thread replies (`conversations.replies`) |
   | `groups:history` | the same for a private channel |
   | `users:read`, `users:read.email` | matching Slack users to Timur users (`users.list`, `users.info`, `users.lookupByEmail`) |

   Opening the "How did Timur decide?" modal (`views.open`) and reading the workspace URL for message links
   (`auth.test`) need no scope.
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
   3. **Shortcuts** > **Create New Shortcut** > **On messages**:
      - Name: `Why did Timur do this?`
      - Short description: `See how Timur read this message`
      - Callback ID: `timur_why`
   4. **Save Changes**. Reinstall if Slack asks.
7. Invite the bot to the channel (`/invite @Timur`). Get the channel ID from the channel name > **About** >
   bottom (`C0...`) and set `SLACK_AVAILABILITY_CHANNEL_ID`.
8. Roll out:
   1. `SLACK_AVAILABILITY_MODE=shadow`: Timur parses new posts and saves the planned journal changes, without
      writing the journal, reacting or replying. Check **Django admin > Slack availability runs** after a few
      posts.
   2. `SLACK_AVAILABILITY_MODE=live`: Timur reacts (seen while it reads a post, then the outcome, see
      [Availability: reactions](#availability-reactions)), updates the journal and replies in the thread.
      Click "How did Timur decide?" on a reply to see the steps.
      Deleting a message doesn't change the journal right away. Changes and cancellations go in a thread reply.
      - A deleted reply is left out the next time Timur reads the thread (on its next reply or edit), so that
        read can change the journal.
      - A thread whose top-level message is deleted is no longer read. Its journal values stay.
      - When the journal still holds values from the thread, Timur replies once to a deleted reply and once to a
        deleted top-level message.
   3. Rollback: `SLACK_AVAILABILITY_MODE=off`. Events are then ignored.

## Availability: values set outside a thread

Timur owns a journal day it wrote from a thread until the value changes outside that thread: in Timur (the
`updateJournal` mutation, from the web app or an API token), in Django admin (the journal form, and reverting or
recovering a version), or by another thread. A manual or admin change ends ownership even when the same value is
set again. Each leave/WFH change of a journal is recorded in **Django admin > Journal availability history** (also
inline on the journal), with its source: manual (who), Django admin (who) or Timur from Slack (which run).

When the poster replies in a thread that changed their journal, and some of its days now hold a value the thread
doesn't own (set in Timur, set by another thread, or a value Timur would have changed but was set by hand), Timur
reacts with `:timur-manual:` and sends a notice only the poster sees (`chat.postEphemeral`), at most once per
reply. Per day it says the current value, who set it (you or another person in Timur or in Timur admin, with the
time, or a link to the other thread, or unknown when there is no matching history), and links to the journal page
of that date.

## Availability: reactions

Timur adds the seen reaction to each post it reads. When the run is done, it replaces it with one outcome
reaction. A later run on the same message (e.g. an edit) replaces the earlier outcome.

Each reaction is a custom emoji. Upload the images (128x128 PNG) in Slack > **Customize workspace** > **Emoji**
with exactly these names. Timur lists the workspace emojis (`emoji.list`, cached for an hour) and uses the native
emoji for a name that is missing, or when the `emoji:read` scope is missing.

| Custom emoji | Native fallback | Meaning |
|---|---|---|
| `:timur-seen:` | `:eyes:` | Reading the post |
| `:timur-applied:` | `:white_check_mark:` | Journal updated |
| `:timur-no-change:` | `:heavy_minus_sign:` | Read, nothing to change |
| `:timur-not-about:` | `:see_no_evil:` | Not about leave or WFH |
| `:timur-unsure:` | `:question:` | Not sure enough, nothing changed |
| `:timur-manual:` | `:raised_hand:` | Kept a value set outside this thread (a date the thread asks for, or one it wrote that was changed since) |
| `:timur-stale:` | `:hourglass:` | Skipped, the thread changed while Timur read it. A newer read applies |
| `:timur-failed:` | `:warning:` | Failed, the Slack account isn't linked to a Timur user, or the reply couldn't be sent |

Reaction errors are logged and never fail a run. In `shadow` mode there are no reactions.

### Troubleshooting

- **Request URL not verified**: the backend is missing `SLACK_SIGNING_SECRET` (it then returns an empty `200`,
  which Slack rejects), the secret doesn't match the app's Signing Secret (`401`), the endpoint isn't deployed
  yet (`404`), or the URL lacks the trailing slash.
- **No reaction on a post**:
  - `SLACK_AVAILABILITY_MODE` is `off` or `shadow`
  - `SLACK_AVAILABILITY_CHANNEL_ID` is the channel name instead of the ID
  - the bot isn't in the channel, or `message.channels` isn't subscribed
  - the Celery worker isn't running (events are queued, check the worker logs)
- **`:timur-failed:` (`:warning:`) and no reply**: the poster's Slack account isn't linked to a Timur user
  (`slack_user_id`). Run `python manage.py sync_slack_users_id` or set it in Django admin.
- **Native emojis instead of the Timur ones**: the `emoji:read` scope is missing (add it and reinstall), or the
  uploaded name differs from the table. The emoji list is cached for up to an hour.
- **Button shows nothing**: Interactivity is off or its Request URL is wrong, or the mode is `off`.
- **Shortcut missing from a message's menu**: the shortcut isn't created (step 6), or the app wasn't reinstalled.
  Its callback ID must be `timur_why`.
- **`missing_scope` or `not_allowed_token_type` in logs**: add the scope from step 2 and reinstall.
- **`invalid_auth` from the backend**: the bot token changed, or `allowed_ip_address_ranges` in the app
  settings doesn't include the cluster's outbound IP.
