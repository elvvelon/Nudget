from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Nudget user; password hashing and username come from Django."""

    email = models.EmailField(unique=True)
    discord_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=100, blank=True)
    profile_img_url = models.URLField(max_length=500, blank=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.display_name or self.username
