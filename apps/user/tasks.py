import logging

from apps.user.models import User
from utils.slack import TimurSlack

logger = logging.getLogger(__name__)


def sync_slack_users_id():
    users_to_sync_qs = User.get_users_without_slack_user_id()
    timur_slack = TimurSlack()

    users_to_sync_qs_count = users_to_sync_qs.count()
    if users_to_sync_qs_count == 0:
        logger.info("All users have user slack id. Nothing to do here")
        return
    logger.info("%s users to sync", users_to_sync_qs_count)

    email_to_slack_user_id_map = {
        slack_user["profile"]["email"]: slack_user["id"]
        for slack_user in timur_slack.fetch_users(
            exclude_bot=True,
            exclude_deleted=True,
        )
    }

    # TODO: try/catch
    for user in users_to_sync_qs:
        if slack_user_id := email_to_slack_user_id_map.get(user.email):
            user.slack_user_id = slack_user_id
            # FIXME: Bulk manager
            user.save(update_fields=("slack_user_id",))
