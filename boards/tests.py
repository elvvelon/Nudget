"""Tests for the boards API: boards, members, columns, cards, subtasks and activity history."""

from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User

from .models import Board, BoardMember, Card, CardActivity, Column, Subtask

PASSWORD = "Str0ng-pass-123"


class BoardAPITestCase(APITestCase):
    """Common setup: a board owned by `owner`, with a member, a viewer and an outsider."""

    def setUp(self):
        self.owner = self.make_user("owner")
        self.member = self.make_user("member")
        self.viewer = self.make_user("viewer")
        self.outsider = self.make_user("outsider")

        self.login(self.owner)
        self.board = Board.objects.get(
            pk=self.client.post("/api/boards/", {"title": "Final project"}).data["id"]
        )
        BoardMember.objects.create(board=self.board, user=self.member, role="member")
        BoardMember.objects.create(board=self.board, user=self.viewer, role="viewer")
        self.todo = self.board.columns.get(title="To Do")
        self.done = self.board.columns.get(title="Done")

    def make_user(self, username):
        return User.objects.create_user(username, f"{username}@example.com", PASSWORD)

    def login(self, user):
        """Log in through the API and send the access token with every request."""
        tokens = self.client.post(
            "/api/auth/login/", {"username": user.username, "password": PASSWORD}
        ).data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def owner_membership(self):
        return BoardMember.objects.get(board=self.board, user=self.owner)


class BoardTests(BoardAPITestCase):
    def test_boards_require_login(self):
        self.client.credentials()

        response = self.client.get("/api/boards/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_new_board_gets_owner_and_default_columns(self):
        self.assertEqual(self.owner_membership().role, "owner")
        self.assertEqual(
            list(self.board.columns.values_list("title", flat=True)),
            ["To Do", "In Progress", "Review", "Done"],
        )
        self.assertTrue(self.done.is_done_column)

    def test_list_shows_only_my_boards(self):
        Board.objects.create(title="Someone else's board")

        response = self.client.get("/api/boards/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([board["title"] for board in response.data], ["Final project"])
        self.assertEqual(response.data[0]["my_role"], "owner")

    def test_detail_contains_members_and_columns(self):
        response = self.client.get(f"/api/boards/{self.board.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["members"]), 3)
        self.assertEqual(len(response.data["columns"]), 4)

    def test_outsider_gets_404_not_403(self):
        """Boards of other teams are hidden, so their existence is not revealed."""
        self.login(self.outsider)

        response = self.client.get(f"/api/boards/{self.board.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_rename_board(self):
        response = self.client.patch(f"/api/boards/{self.board.id}/", {"title": "Nudget"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.board.refresh_from_db()
        self.assertEqual(self.board.title, "Nudget")

    def test_member_cannot_rename_or_delete_board(self):
        self.login(self.member)

        patch = self.client.patch(f"/api/boards/{self.board.id}/", {"title": "Mine"})
        delete = self.client.delete(f"/api/boards/{self.board.id}/")

        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Board.objects.filter(pk=self.board.id).exists())

    def test_owner_can_delete_board(self):
        response = self.client.delete(f"/api/boards/{self.board.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Board.objects.filter(pk=self.board.id).exists())


class MemberTests(BoardAPITestCase):
    def members_url(self, member_id=None):
        url = f"/api/boards/{self.board.id}/members/"
        return f"{url}{member_id}/" if member_id else url

    def test_owner_invites_user_by_email(self):
        response = self.client.post(
            self.members_url(), {"email": "outsider@example.com", "role": "viewer"}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], "viewer")
        self.assertTrue(
            BoardMember.objects.filter(board=self.board, user=self.outsider).exists()
        )

    def test_invite_needs_exactly_one_of_username_or_email(self):
        response = self.client.post(self.members_url(), {"role": "member"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_invite_existing_member(self):
        response = self.client.post(self.members_url(), {"username": "member"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_cannot_invite(self):
        self.login(self.member)

        response = self.client.post(self.members_url(), {"username": "outsider"})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_changes_member_role(self):
        membership = BoardMember.objects.get(board=self.board, user=self.viewer)

        response = self.client.patch(self.members_url(membership.id), {"role": "member"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        membership.refresh_from_db()
        self.assertEqual(membership.role, "member")

    def test_last_owner_cannot_be_demoted(self):
        response = self.client.patch(
            self.members_url(self.owner_membership().id), {"role": "member"}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.owner_membership().role, "owner")

    def test_last_owner_cannot_leave(self):
        response = self.client.delete(self.members_url(self.owner_membership().id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_can_leave_board(self):
        membership = BoardMember.objects.get(board=self.board, user=self.member)
        self.login(self.member)

        response = self.client.delete(self.members_url(membership.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BoardMember.objects.filter(pk=membership.id).exists())

    def test_member_cannot_remove_someone_else(self):
        membership = BoardMember.objects.get(board=self.board, user=self.viewer)
        self.login(self.member)

        response = self.client.delete(self.members_url(membership.id))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ColumnTests(BoardAPITestCase):
    def test_owner_adds_column_to_the_end(self):
        response = self.client.post(
            f"/api/boards/{self.board.id}/columns/", {"title": "Backlog"}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["position"], 4)

    def test_member_cannot_add_column(self):
        self.login(self.member)

        response = self.client.post(
            f"/api/boards/{self.board.id}/columns/", {"title": "Backlog"}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_renames_and_deletes_column(self):
        rename = self.client.patch(f"/api/columns/{self.todo.id}/", {"title": "Backlog"})
        delete = self.client.delete(f"/api/columns/{self.done.id}/")

        self.assertEqual(rename.status_code, status.HTTP_200_OK)
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Column.objects.filter(pk=self.done.id).exists())

    def test_member_cannot_delete_column(self):
        self.login(self.member)

        response = self.client.delete(f"/api/columns/{self.todo.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
