from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


def empty_to_none(value):
    """Store an empty discord_id as NULL so the unique constraint allows many users without one."""
    return value or None


class RegisterSerializer(serializers.ModelSerializer):
    """Creates a new user with a properly hashed password."""

    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "email", "username", "password", "display_name", "discord_id"]
        extra_kwargs = {"email": {"required": True}}

    def validate_discord_id(self, value):
        return empty_to_none(value)

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserSerializer(serializers.ModelSerializer):
    """Profile of the current user; email and username cannot be changed here."""

    class Meta:
        model = User
        fields = ["id", "email", "username", "display_name", "discord_id", "profile_img_url"]
        read_only_fields = ["id", "email", "username"]

    def validate_discord_id(self, value):
        return empty_to_none(value)


class UserShortSerializer(serializers.ModelSerializer):
    """Compact user info shown on boards, cards and activity entries."""

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "profile_img_url"]
