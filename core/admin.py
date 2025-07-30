from django.contrib import admin
from db import models as db_models


@admin.register(db_models.Customer)
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


@admin.register(db_models.CustomerHistory)
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


@admin.register(db_models.Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "content",
    )
