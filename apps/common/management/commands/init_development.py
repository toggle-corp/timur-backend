import dataclasses
import functools
import json
from argparse import FileType
from sys import stdin

from dacite import from_dict
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.project.models import Client, Contractor, Project
from apps.track.models import Contract, Task
from apps.user.models import User


@dataclasses.dataclass
class ImportTask:
    name: str
    hours: float


@dataclasses.dataclass
class ImportContract:
    name: str
    hours: float
    tasks: list[ImportTask]


@dataclasses.dataclass
class ImportProject:
    name: str
    project_manager_email: str
    client: str
    contractor: str
    contracts: list[ImportContract]


@dataclasses.dataclass
class ImportData:
    projects: list[ImportProject]
    user_emails: list[str]


def cache_with_args(*cache_args):
    cache = {}

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract the cache-relevant arguments
            cache_key = tuple(kwargs[arg] if arg in kwargs else args[arg] for arg in cache_args)
            if cache_key in cache:
                return cache[cache_key]
            result = func(*args, **kwargs)
            cache[cache_key] = result
            return result

        return wrapper

    return decorator


# NOTE: This is not meant to be run on PRODUCTION!!
class Command(BaseCommand):
    help = "Generate data for development"

    def add_arguments(self, parser):
        parser.add_argument("input_file", nargs="?", type=FileType("r"), default=stdin)
        # TODO: Generate time track data
        # TODO: Generate journal data

    def handle(self, **options):
        if not (settings.DEBUG and settings.ALLOW_DUMMY_DATA_SCRIPT):
            self.stdout.write(
                self.style.ERROR(
                    "Enable DJANGO_DEBUG and ALLOW_DUMMY_DATA_SCRIPT using environment variable to run this",
                )
            )
            return

        try:
            import_raw_data = json.load(options["input_file"])
        except json.decoder.JSONDecodeError as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Invalid JSON file: {e}",
                )
            )
            return

        import_data: ImportData = from_dict(
            data_class=ImportData,
            data=import_raw_data,
        )
        self.run(import_data)

    def get_user_resource_kwargs(self, user) -> dict:
        return {
            "created_by": user,
            "modified_by": user,
        }

    def create_user(self, email: str, is_admin: bool = False) -> User:
        insecure_password = "password123"  # XXX: Insecure password - Don't use this in production
        if user := User.objects.filter(email=email).first():
            return user
        self.stdout.write(
            self.style.SUCCESS(
                f"Creating user with email: {email=} {insecure_password=} as {"Admin" if is_admin else "Normal"} User",
            )
        )
        if is_admin:
            return User.objects.create_superuser(
                email=email,
                password=insecure_password,
            )
        return User.objects.create_user(
            email=email,
            password=insecure_password,
        )

    @cache_with_args(1)
    def get_user(self, email: str) -> User | None:
        if user := User.objects.filter(email=email).first():
            return user

    @cache_with_args(2)
    def get_or_create_client(self, creator: User, name: str) -> Client:
        client, created = Client.objects.get_or_create(
            name=name,
            defaults=self.get_user_resource_kwargs(creator),
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created client {name=}"))
        return client

    @cache_with_args(2)
    def get_or_create_contractor(self, creator: User, name: str) -> Contractor:
        contractor, created = Contractor.objects.get_or_create(
            name=name,
            defaults=self.get_user_resource_kwargs(creator),
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created contractor {name=}"))
        return contractor

    @cache_with_args(2, 3, 4)
    def get_or_create_project(self, creator: User, name: str, client: Client, contractor: Contractor) -> Project:
        project, created = Project.objects.get_or_create(
            name=name,
            client=client,
            contractor=contractor,
            defaults=self.get_user_resource_kwargs(creator),
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Project {name=} {client=} {contractor=}"))
        return project

    @cache_with_args(2, 3)
    def get_or_create_contract(self, creator: User, name: str, project: Project, hours: float) -> Contract:
        contract, created = Contract.objects.get_or_create(
            name=name,
            project=project,
            total_estimated_hours=hours,
            defaults=self.get_user_resource_kwargs(creator),
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Contract {name=} {project=}"))
        return contract

    @cache_with_args(2, 3)
    def get_or_create_task(self, creator: User, name: str, contract: Contract, hours: float) -> Task:
        task, created = Task.objects.get_or_create(
            name=name,
            contract=contract,
            estimated_hours=hours,
            defaults=self.get_user_resource_kwargs(creator),
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created Task {name=} {contract=}"))
        return task

    def run(self, import_data: ImportData):
        self.stdout.write("---- Generating tasks")
        pm_not_admin_users = set()

        for project_data in import_data.projects:
            pm_user = self.get_user(project_data.project_manager_email)
            if pm_user is None:
                pm_user = self.create_user(project_data.project_manager_email, is_admin=True)

            if not pm_user.is_superuser:
                pm_not_admin_users.add(pm_user)

            project = self.get_or_create_project(
                pm_user,
                project_data.name,
                self.get_or_create_client(pm_user, project_data.client),
                self.get_or_create_contractor(pm_user, project_data.contractor),
            )
            for contract_data in project_data.contracts:
                contract = self.get_or_create_contract(
                    pm_user,
                    contract_data.name,
                    project,
                    contract_data.hours,
                )
                for task_data in contract_data.tasks:
                    self.get_or_create_task(
                        pm_user,
                        task_data.name,
                        contract,
                        contract_data.hours,
                    )

        self.stdout.write("---- Generating Dev users")
        for email in import_data.user_emails:
            self.create_user(email, is_admin=False)

        self.stdout.write("---- Grant missing admin access to new PM")
        for user in pm_not_admin_users:
            print(f"- {user.email}")
            user.is_superuser = True
            user.save(update_fields=("is_superuser",))
