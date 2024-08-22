from django.db import models

from apps.common.models import UserResource

# from apps.user.models import User


# class DailyUserStandup(models.Model):
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     date = models.DateField()

#     slack_thread_id = models.CharField(max_length=200)  # TODO: Check length
#     text = models.TextField()  # TODO: Do we need this?


class Quote(UserResource):
    text = models.TextField()
    author = models.CharField(max_length=225)
