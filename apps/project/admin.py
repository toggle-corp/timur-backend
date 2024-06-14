from django.contrib import admin

from .models import Client, Contractor, Project

# TODO: Use autocomplete
admin.site.register(Project)
admin.site.register(Client)
admin.site.register(Contractor)
