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


class CardTests(BoardAPITestCase):
    def create_card(self, column=None, **data):
        column = column or self.todo
        return self.client.post(
            f"/api/columns/{column.id}/cards/", {"title": "Write tests", **data}
        )

    def test_member_creates_card_and_activity_is_logged(self):
        self.login(self.member)

        response = self.create_card(priority="high")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["priority"], "high")
        card = Card.objects.get(pk=response.data["id"])
        self.assertEqual(card.activities.get().action_type, "created")

    def test_viewer_cannot_create_card(self):
        self.login(self.viewer)

        response = self.create_card()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_new_cards_go_to_the_end_of_the_column(self):
        first = self.create_card().data
        second = self.create_card().data

        self.assertEqual((first["position"], second["position"]), (0, 1))

    def test_assignee_must_be_board_member(self):
        response = self.create_card(assignee_id=self.outsider.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assignee_id", response.data)

    def test_card_cannot_move_to_another_board(self):
        card_id = self.create_card().data["id"]
        other_board_id = self.client.post("/api/boards/", {"title": "Other"}).data["id"]
        foreign_column = Column.objects.filter(board_id=other_board_id).first()

        response = self.client.patch(
            f"/api/cards/{card_id}/", {"column_id": foreign_column.id}
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("column_id", response.data)

    def test_moving_card_logs_moved_activity(self):
        card_id = self.create_card().data["id"]

        response = self.client.patch(f"/api/cards/{card_id}/", {"column_id": self.done.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        moved = CardActivity.objects.get(card_id=card_id, action_type="moved")
        self.assertEqual(moved.source_column, self.todo)
        self.assertEqual(moved.destination_column, self.done)

    def test_assigning_and_editing_card_are_logged(self):
        card_id = self.create_card().data["id"]

        self.client.patch(
            f"/api/cards/{card_id}/", {"assignee_id": self.member.id, "title": "Write more tests"}
        )

        actions = set(
            CardActivity.objects.filter(card_id=card_id).values_list("action_type", flat=True)
        )
        self.assertEqual(actions, {"created", "updated", "assigned"})

    def test_viewer_can_read_card_with_history(self):
        card_id = self.create_card().data["id"]
        self.login(self.viewer)

        response = self.client.get(f"/api/cards/{card_id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["activities"]), 1)
        self.assertEqual(response.data["subtasks"], [])

    def test_viewer_cannot_edit_or_delete_card(self):
        card_id = self.create_card().data["id"]
        self.login(self.viewer)

        patch = self.client.patch(f"/api/cards/{card_id}/", {"title": "Hacked"})
        delete = self.client.delete(f"/api/cards/{card_id}/")

        self.assertEqual(patch.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_gets_404_for_card(self):
        card_id = self.create_card().data["id"]
        self.login(self.outsider)

        response = self.client.get(f"/api/cards/{card_id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_member_deletes_card(self):
        card_id = self.create_card().data["id"]
        self.login(self.member)

        response = self.client.delete(f"/api/cards/{card_id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Card.objects.filter(pk=card_id).exists())


class SubtaskTests(BoardAPITestCase):
    def setUp(self):
        super().setUp()
        self.card = Card.objects.create(column=self.todo, title="Write tests")

    def test_member_adds_subtask(self):
        self.login(self.member)

        response = self.client.post(
            f"/api/cards/{self.card.id}/subtasks/", {"title": "Auth tests"}
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["is_completed"])

    def test_viewer_cannot_add_subtask(self):
        self.login(self.viewer)

        response = self.client.post(
            f"/api/cards/{self.card.id}/subtasks/", {"title": "Auth tests"}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_ticking_subtask_updates_board_progress(self):
        subtask = Subtask.objects.create(card=self.card, title="Auth tests")
        Subtask.objects.create(card=self.card, title="Board tests")

        response = self.client.patch(f"/api/subtasks/{subtask.id}/", {"is_completed": True})
        board = self.client.get(f"/api/boards/{self.board.id}/").data

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        card_on_board = board["columns"][0]["cards"][0]
        self.assertEqual(card_on_board["subtasks_total"], 2)
        self.assertEqual(card_on_board["subtasks_done"], 1)

    def test_member_deletes_subtask(self):
        subtask = Subtask.objects.create(card=self.card, title="Auth tests")
        self.login(self.member)

        response = self.client.delete(f"/api/subtasks/{subtask.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Subtask.objects.filter(pk=subtask.id).exists())
