import os
from logging.config import dictConfig

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "main.settings")

app = Celery("main")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def setup_django_logging(**_):
    """Use Django's LOGGING in the worker instead of Celery's handlers"""
    from django.conf import settings

    dictConfig(settings.LOGGING)
