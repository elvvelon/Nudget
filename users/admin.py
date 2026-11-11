from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class NudgetUserAdmin(UserAdmin):
    """Default user admin with the Nudget profile fields added."""

    fieldsets = UserAdmin.fieldsets + (
        ("Nudget", {"fields": ("display_name", "discord_id", "profile_img_url")}),
    )
