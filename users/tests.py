"""Tests for the auth endpoints: register, login, token refresh and the profile."""

from rest_framework import status
from rest_framework.test import APITestCase

from .models import User

PASSWORD = "Str0ng-pass-123"


class RegisterTests(APITestCase):
    url = "/api/auth/register/"

    def test_register_creates_user_with_hashed_password(self):
        response = self.client.post(
            self.url,
            {"email": "anna@example.com", "username": "anna", "password": PASSWORD},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="anna")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_register_requires_email(self):
        response = self.client.post(self.url, {"username": "anna", "password": PASSWORD})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            self.url, {"email": "anna@example.com", "username": "anna", "password": "123"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user("first", "anna@example.com", PASSWORD)

        response = self.client.post(
            self.url, {"email": "anna@example.com", "username": "second", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_empty_discord_id_is_stored_as_null(self):
        """Two users without Discord must not clash on the unique discord_id."""
        for name in ("anna", "bohdan"):
            response = self.client.post(
                self.url,
                {
                    "email": f"{name}@example.com",
                    "username": name,
                    "password": PASSWORD,
                    "discord_id": "",
                },
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(User.objects.filter(discord_id__isnull=True).count(), 2)


class LoginTests(APITestCase):
    def setUp(self):
        User.objects.create_user("anna", "anna@example.com", PASSWORD)

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "anna", "password": PASSWORD}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_with_wrong_password_returns_401(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "anna", "password": "wrong-password"}
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_returns_new_access_token(self):
        tokens = self.client.post(
            "/api/auth/login/", {"username": "anna", "password": PASSWORD}
        ).data

        response = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)


class MeTests(APITestCase):
    url = "/api/auth/me/"

    def setUp(self):
        self.user = User.objects.create_user("anna", "anna@example.com", PASSWORD)

    def login(self):
        """Log in through the API and send the access token with every request."""
        tokens = self.client.post(
            "/api/auth/login/", {"username": "anna", "password": PASSWORD}
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_me_without_token_returns_401(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        self.login()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "anna")
        self.assertEqual(response.data["email"], "anna@example.com")

    def test_patch_updates_profile_but_not_username(self):
        self.login()

        response = self.client.patch(
            self.url, {"display_name": "Anna K.", "username": "hacker"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "Anna K.")
        self.assertEqual(self.user.username, "anna")
