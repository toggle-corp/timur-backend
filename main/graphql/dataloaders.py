from django.utils.functional import cached_property

from apps.journal.dataloaders import JournalDataLoader
from apps.project.dataloaders import ProjectDataLoader
from apps.track.dataloaders import TrackDataLoader
from apps.user.dataloaders import UserDataLoader


# TODO: Use optimizer instead?
class GlobalDataLoader:
    @cached_property
    def user(self):
        return UserDataLoader()

    @cached_property
    def track(self):
        return TrackDataLoader()

    @cached_property
    def project(self):
        return ProjectDataLoader()

    @cached_property
    def journal(self):
        return JournalDataLoader()
