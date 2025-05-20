from django.contrib.sessions.management.commands.clearsessions import Command as OgCommand

from main.sentry import SentryMonitorConfig, monitor


@monitor(SentryMonitorConfig.CronJob.CLEARSESSIONS)
class Command(OgCommand): ...
