# Changelog

## [v0.1.5](https://github.com/toggle-corp/timur-backend/compare/v0.1.4..v0.1.5) - 2026-04-07
### Changes:

#### 🚀  Features

- Add release using banjo-action - ([7df29c0](https://github.com/toggle-corp/timur-backend/commit/7df29c0e97b9bf0cec4ac676dde9d8cb6607927b))
- Integrate with banjo-action(+fugit) for github action - ([7b01ddb](https://github.com/toggle-corp/timur-backend/commit/7b01ddb2b08ed8d63c08468c50863de3254fba3d))
- Add update-snapshots from fugit - ([2a62fa9](https://github.com/toggle-corp/timur-backend/commit/2a62fa924a16a499f84038af3d1dd0657ac5edc2))
- Add fugit - ([a9cba08](https://github.com/toggle-corp/timur-backend/commit/a9cba082a554e86578f5b9f46714732bbb3f7621))
- Use 95% for disk usage max - ([06796bd](https://github.com/toggle-corp/timur-backend/commit/06796bd81ed0a1dc735626428db77ffacd1371aa))

#### 🐛 Bug Fixes

- *(lint)* Replace toml with pyproject in pre-commit - ([aa8349a](https://github.com/toggle-corp/timur-backend/commit/aa8349a25d0a17a526bad2324bc5efe7bac6aea1))

#### 📚 Documentation

- Add TODO related to version in pyproject - ([916b03d](https://github.com/toggle-corp/timur-backend/commit/916b03dbed8981060f95f4f89d4f7d417aa5cb1a))

### 🍻 Pull Requests (1)
- (#82) [Feat: add fugit](https://github.com/toggle-corp/timur-backend/pull/82)


## [v0.1.4](https://github.com/toggle-corp/timur-backend/compare/v0.1.3..v0.1.4) - 2025-07-24
### Changes:

#### 🚀  Features

- *(admin-panel)* Show Event/Dealine google_calendar_html_link as anchor - ([8de2b73](https://github.com/toggle-corp/timur-backend/commit/8de2b73f04b23c625947f4ea9a81dbeebc661537))
- *(s3)* Cache generated url using redis - ([9462a3f](https://github.com/toggle-corp/timur-backend/commit/9462a3f00c48a39fd06b548e8b6826a16c543614))
- Publish helm on push to develop - ([1c87ebf](https://github.com/toggle-corp/timur-backend/commit/1c87ebf7073d497201eba31383ce0649d0d6f899))

#### 🐛 Bug Fixes

- *(standup)* Fix assignable users - ([aeebbff](https://github.com/toggle-corp/timur-backend/commit/aeebbffad4673ec4308f992f47c6a1723228bce6))
- *(standup)* Exclude inactive user for standup assignment - ([6a90d8c](https://github.com/toggle-corp/timur-backend/commit/6a90d8c605a3e02ea16968b03e8732c2f95feb9c))

### 🍻 Pull Requests (3)
- (#65) [Chore(deps): update dependency ubuntu to v24](https://github.com/toggle-corp/timur-backend/pull/65)
- (#67) [Feat/s3 url cache](https://github.com/toggle-corp/timur-backend/pull/67)
- (#71) [Chore/july](https://github.com/toggle-corp/timur-backend/pull/71)


## [v0.1.3](https://github.com/toggle-corp/timur-backend/compare/v0.1.2..v0.1.3) - 2025-06-02
### Changes:

#### 🚀  Features

- *(event)* Add description - ([2dfa1fc](https://github.com/toggle-corp/timur-backend/commit/2dfa1fc26d51c6782523a142ba8959633311193b))

### 🍻 Pull Requests (1)
- (#66) [Feat(event): add description](https://github.com/toggle-corp/timur-backend/pull/66)


## [v0.1.2](https://github.com/toggle-corp/timur-backend/compare/v0.1.1..v0.1.2) - 2025-05-25
### Changes:

#### 🚀  Features

- *(release)* Extend release body with helm metadata - ([80d2e09](https://github.com/toggle-corp/timur-backend/commit/80d2e09d801e7fb9af01dc432eebeddfe78ca792))
- *(release)* Add semver validator in release.sh - ([69c0c87](https://github.com/toggle-corp/timur-backend/commit/69c0c87e89791da43671a9898886d4cbc3003f17))


## [v0.1.1] - 2025-05-25
### Changes:

#### 🚀  Features

- *(changelog)* Add git cliff - ([ed0ce0b](https://github.com/toggle-corp/timur-backend/commit/ed0ce0b75ecf71592e609d5db5d421da4c9d37b5))
- *(ci)* Add pre-commit and uv - ([359102b](https://github.com/toggle-corp/timur-backend/commit/359102be4523dbe50b1491e1e09918539241a257))
- *(cli)* Add management commands and cron jobs for standup and Slack sync - ([4c339c9](https://github.com/toggle-corp/timur-backend/commit/4c339c991bef16e54989c226871b5966919d1ad5))
- *(cli)* Add subcommand to delete all google calendar data - ([ecaffa4](https://github.com/toggle-corp/timur-backend/commit/ecaffa46a000c91427b5862070349305f00f2e82))
- *(cli)* Add command to reset calendar metadata - ([b0d1c5d](https://github.com/toggle-corp/timur-backend/commit/b0d1c5d58f156e95b4a7cfec44476a09a457290b))
- *(cli)* Add wait_for_resources command - ([94827ba](https://github.com/toggle-corp/timur-backend/commit/94827babc499a08482ae59c89a0cc093164309db))
- *(cli)* Add sync and acl listing for google_calender cli - ([bb6ad87](https://github.com/toggle-corp/timur-backend/commit/bb6ad87d0416a2f7d3d7bd6d641799e00b8c06a2))
- *(db)* Add config for SSLMODE - ([8f604e0](https://github.com/toggle-corp/timur-backend/commit/8f604e0e56db273b0c05271b329fca7ed6d28ad8))
- *(deadline)* Add project short_name - ([1174653](https://github.com/toggle-corp/timur-backend/commit/1174653a5372065f47a01a5234f434b61236cb11))
- *(debug)* Add payload in description - ([a9ddd81](https://github.com/toggle-corp/timur-backend/commit/a9ddd81fb99ff32e2dd074714739895619fc5b93))
- *(deploy)* Add script for uwsgi (web) - ([16627a9](https://github.com/toggle-corp/timur-backend/commit/16627a9ff145483b9ced9cc8ed220bf17d742d04))
- *(django-admin)* Add filters and action for google calendar sync - ([cb338d2](https://github.com/toggle-corp/timur-backend/commit/cb338d237ff5fdd73491a3c8619d11eb81a3e6ab))
- *(djangoql)* Add djangoql to admin panel - ([5c3fa48](https://github.com/toggle-corp/timur-backend/commit/5c3fa48aa2bdda6f231757d48d1d95c7c02cd25b))
- *(docker)* Move backend related docker compose config here - ([7b774bb](https://github.com/toggle-corp/timur-backend/commit/7b774bba862e7cb7a4e5b6eaa6d247659ba5ec80))
- *(google-calendar)* Add description to google events - ([48cd257](https://github.com/toggle-corp/timur-backend/commit/48cd257f6eeee0334f2c231c4b7d076d80f7f94f))
- *(google-calendar)* Add emoji and color to the Calendar events - ([758d69c](https://github.com/toggle-corp/timur-backend/commit/758d69cddbf924330480bb1f6f54c8effb15150f))
- *(google-calendar)* Sync Event and Deadline with Google Calendar - ([0f016d8](https://github.com/toggle-corp/timur-backend/commit/0f016d89d2dcf23291f34de2c04425c6d787478c))
- *(google-calendar)* Add cli to manage calendar from service account - ([9016953](https://github.com/toggle-corp/timur-backend/commit/90169533971b81408ff153fc50deab105aca5864))
- *(helm)* Add helm config (using toggle django-app chart) - ([829efdf](https://github.com/toggle-corp/timur-backend/commit/829efdf27c6d67d1aa4833978bddbbcd4d2377e4))
- *(helm)* Add helm config - ([650817e](https://github.com/toggle-corp/timur-backend/commit/650817e18fde1f5168f7e8a0bf087830ead9e43f))
- *(lint)* Enable reportImplicitOverride - ([e062581](https://github.com/toggle-corp/timur-backend/commit/e06258154d5ce646c8c214541569f970df6fc193))
- *(logging)* Setup logging config - ([7e4737b](https://github.com/toggle-corp/timur-backend/commit/7e4737b260de2e188468db4f522a3138f45eaa0d))
- *(package-manager)* Replace poetry with uv - ([45b1b83](https://github.com/toggle-corp/timur-backend/commit/45b1b83c044f197cf5fb077c98a9f6f671c9a1f4))
- *(pre-commit)* Replace black, isort with uv - ([dad84bd](https://github.com/toggle-corp/timur-backend/commit/dad84bd316e015ae36434a136a11d78f4211e58f))
- *(quote)* Add last_viewed in Quote for simple queue - ([8798900](https://github.com/toggle-corp/timur-backend/commit/87989008ce17c4953cda957e36af6a92656a99b8))
- *(sentry)* Add config to disable cron monitor - ([f6a2c7c](https://github.com/toggle-corp/timur-backend/commit/f6a2c7cb9e2ac08c2bde85384e974e004d145d6c))
- *(sentry)* Add cron monitor - ([3c9562e](https://github.com/toggle-corp/timur-backend/commit/3c9562ee2dac12759856a663de3b0d292a1f3faa))
- *(settings)* Refactor - ([9b0eed7](https://github.com/toggle-corp/timur-backend/commit/9b0eed7c1eea9dffbdbc220b20b19c2a4a89ad4b))
- *(slack)* Add Slack bot configuration and utility class - ([54a9cae](https://github.com/toggle-corp/timur-backend/commit/54a9cae91867ef43cf9baa2268130c98afc4c27e))
- *(sso)* [**breaking**] Replace custom code with django-allauth - ([abd17d3](https://github.com/toggle-corp/timur-backend/commit/abd17d3cc074f4383d88d0171123386729d057f8))
- *(sso)* Enable SSO using environment - ([efdbcb0](https://github.com/toggle-corp/timur-backend/commit/efdbcb054c35c0e75cff3c5e82a7d8cf72085442))
- *(standup)* Add StandupGatherAroundMedia model and integrate with daily standup reminder - ([9c3a9fd](https://github.com/toggle-corp/timur-backend/commit/9c3a9fdd2f4ab4a13f6b917df2431617c0b12086))
- *(standup)* Check holidays/WFH for daily_standup assignment - ([309040d](https://github.com/toggle-corp/timur-backend/commit/309040df1efb7bbc5300532457e12c6ab7935fe3))
- *(standup)* Automate daily standup coordination and Slack messaging - ([452cdac](https://github.com/toggle-corp/timur-backend/commit/452cdac3309494ac841c840150e867c03334b655))
- *(standup)* Add DailyUserStandup model and Slack-related user fields - ([03cd140](https://github.com/toggle-corp/timur-backend/commit/03cd140ebcff6d56db6c4369ce5a71ecd03ff76c))
- *(workflow)* Update CI/CD to include helm - ([bb38d26](https://github.com/toggle-corp/timur-backend/commit/bb38d26a9377babc27feb04cd55d7d1c0e3d48bb))
- Add 'auto_select' field to quote and media models - ([abbd113](https://github.com/toggle-corp/timur-backend/commit/abbd113d711bebf13479668335649bca5b19d616))

#### 🐛 Bug Fixes

- *(admin-panel)* Add correct ordering field names for track models - ([dcc8303](https://github.com/toggle-corp/timur-backend/commit/dcc8303939463f73a41165d928295d860e0b8165))
- *(ci)* Use repository owner instead of full repo path for Helm OCI repo - ([c91c433](https://github.com/toggle-corp/timur-backend/commit/c91c43301c1da07d63bdc2e43299740c4c98ac99))
- *(cronjob)* Update before-standup-reminder schedule to 9:10 AM - ([9da1fd2](https://github.com/toggle-corp/timur-backend/commit/9da1fd239f6f7896690c179dcdb3ff53479ef3a2))
- *(cronjob)* Add timezone - ([67e41e9](https://github.com/toggle-corp/timur-backend/commit/67e41e94ae5a5bf3e5190118687d73de89673bc8))
- *(dev)* Exempt GraphiQL view from CSRF in debug mode - ([5dd73eb](https://github.com/toggle-corp/timur-backend/commit/5dd73eb645ef514c68aa9e6f0c94fbb8d9c82c8a))
- *(django)* Ignore csrf_exempt for graphql - ([18ad81a](https://github.com/toggle-corp/timur-backend/commit/18ad81af038104b71d36f8459273fab2191426ef))
- *(entry-clone)* Generate new ULID for cloned time entry - ([75a039b](https://github.com/toggle-corp/timur-backend/commit/75a039bf432012a303e40278300cad863b253a11))
- *(google-calendar)* Add fallback to auto-heal deleted/cancelled google events - ([db9ec71](https://github.com/toggle-corp/timur-backend/commit/db9ec71e627fb3d675a79c823da0b3b9eedb46b5))
- *(lint)* Pre-commit fixes and manual typing fixes - ([3a24db7](https://github.com/toggle-corp/timur-backend/commit/3a24db761cead9dbb65add490b6bb68494483767))
- *(settings)* Fix allowed host error - ([4e4d1ef](https://github.com/toggle-corp/timur-backend/commit/4e4d1efb5f3698f3c33b6c3e3a65e28de0b47ce7))
- *(typo)* Fix typo in slack reminder text - ([af37126](https://github.com/toggle-corp/timur-backend/commit/af37126efbc7f809460e8492023ff4979703025a))
- *(typo)* Rename google-calender to google_calendar - ([948d2ca](https://github.com/toggle-corp/timur-backend/commit/948d2ca0ffd725ec5563b7fb489d36be3b2894c7))
- *(word)* Change APP_TYPE -> DJANGO_APP_TYPE - ([279dcc0](https://github.com/toggle-corp/timur-backend/commit/279dcc072dbeb68e9fa3f049822dc377bd0174a7))

#### 🚜 Refactor

- *(sso)* Update ui, css theming, and login session expiry indicator - ([08519ea](https://github.com/toggle-corp/timur-backend/commit/08519eae55cb67a851929ec85ebe7340d98f81c0))
- Centralize settings access via typed config module - ([8852e7e](https://github.com/toggle-corp/timur-backend/commit/8852e7e5411e7707164a58a9a25184ad462ee53e))

#### 🧪 Testing

- *(standup,user)* Add tests for standup tasks, CLI commands, and Slack sync - ([b481329](https://github.com/toggle-corp/timur-backend/commit/b4813294d1869a5de79dfe7131e237585024c02f))

#### ⚙️ Miscellaneous Tasks

- *(cd)* Remove branch push rules for helm-publish - ([e1a0edc](https://github.com/toggle-corp/timur-backend/commit/e1a0edcf7363715a12d5f8d1f3326c0d8b0da639))
- *(helm)* Update django-app chart dependency to v0.1.1 - ([5f25f9b](https://github.com/toggle-corp/timur-backend/commit/5f25f9b2e01bb77af94ae810f1aaacdf6b1ea415))
- *(renovate)* Add config from uv - ([3506236](https://github.com/toggle-corp/timur-backend/commit/35062368fc2e71c24ace0d8cc884fd87e492f3a7))
- *(sentry)* Refactor configuration using dataclass - ([1ee0bff](https://github.com/toggle-corp/timur-backend/commit/1ee0bff17c3c1f3014e0381e1e6acf5302e7b651))
- *(standup)* Use slack block for message - ([ffdc841](https://github.com/toggle-corp/timur-backend/commit/ffdc841c0698be28d59de42f93c3cbea69cde5a6))
- *(typo)* Change Quote function get_random_quote to get_random - ([578904a](https://github.com/toggle-corp/timur-backend/commit/578904a9b1d04225e926400d0a287306c1f2b130))
- More renovate config to json5 - ([a25606e](https://github.com/toggle-corp/timur-backend/commit/a25606ea10dcc5f468ad7a249e7432e3aa5e3f4b))

#### Cli

- *(google-calendar)* Add force-update in sync data command - ([ce9c900](https://github.com/toggle-corp/timur-backend/commit/ce9c900d4bad20de71b0705086ecd2e843e3b52a))

#### Lint

- *(pyright)* Add additional checks - ([945cc3d](https://github.com/toggle-corp/timur-backend/commit/945cc3d9c9ec4d048da10649f865801d22ac67f4))

### 🍻 Pull Requests (16)
- (#1) [Add linting and docker build](https://github.com/toggle-corp/timur-backend/pull/1)
- (#11) [Feature/admin panel fixes](https://github.com/toggle-corp/timur-backend/pull/11)
- (#13) [Integration feedbacks changes](https://github.com/toggle-corp/timur-backend/pull/13)
- (#39) [Feature/uv ruff](https://github.com/toggle-corp/timur-backend/pull/39)
- (#40) [Feature/google calender](https://github.com/toggle-corp/timur-backend/pull/40)
- (#41) [Feature/helm](https://github.com/toggle-corp/timur-backend/pull/41)
- (#42) [Fix/k8s cronjob](https://github.com/toggle-corp/timur-backend/pull/42)
- (#43) [Feat(sso)!: Replace custom code with django-allauth](https://github.com/toggle-corp/timur-backend/pull/43)
- (#44) [Refactor: centralize settings access via typed config module](https://github.com/toggle-corp/timur-backend/pull/44)
- (#45) [Chore: Configure Renovate](https://github.com/toggle-corp/timur-backend/pull/45)
- (#49) [Renovate/configure](https://github.com/toggle-corp/timur-backend/pull/49)
- (#52) [Chore(deps): update astral-sh/setup-uv action to v6](https://github.com/toggle-corp/timur-backend/pull/52)
- (#53) [Feature/daily standup](https://github.com/toggle-corp/timur-backend/pull/53)
- (#59) [Feature/standup media](https://github.com/toggle-corp/timur-backend/pull/59)
- (#62) [Feat(sentry): add cron monitor](https://github.com/toggle-corp/timur-backend/pull/62)
- (#64) [Chore/2025 may](https://github.com/toggle-corp/timur-backend/pull/64)


<!-- generated by git-cliff -->
