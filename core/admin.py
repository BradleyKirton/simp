from django.contrib import admin
from core import models as core_models


@admin.register(core_models.Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "address",
        "version",
        "sys_period",
    )
    readonly_fields = (
        "version",
        "sys_period",
    )


@admin.register(core_models.CustomerHistory)
class CustomerHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "address",
        "version",
        "sys_period",
    )
    readonly_fields = (
        "version",
        "sys_period",
    )
