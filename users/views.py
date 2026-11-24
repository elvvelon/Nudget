from rest_framework import generics
from rest_framework.permissions import AllowAny

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — sign up a new user."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []


class MeView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/me/ — read or edit the current user's profile."""

    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user
