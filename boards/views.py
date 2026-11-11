from django.db import transaction
from django.db.models import Max, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Board, BoardMember, Card, CardActivity, Column, Subtask
from .permissions import require_role
from .serializers import (
    AddMemberSerializer,
    BoardDetailSerializer,
    BoardMemberSerializer,
    BoardSerializer,
    CardDetailSerializer,
    CardSerializer,
    ColumnSerializer,
    SubtaskSerializer,
)

OWNER = BoardMember.Role.OWNER
MEMBER = BoardMember.Role.MEMBER
VIEWER = BoardMember.Role.VIEWER

DEFAULT_COLUMNS = [
    ("To Do", False),
    ("In Progress", False),
    ("Review", False),
    ("Done", True),
]

CARD_TEXT_FIELDS = ["title", "description", "priority", "due_date"]


def next_position(queryset):
    """Position right after the last item, so new items go to the end of the list."""
    last = queryset.aggregate(last=Max("position"))["last"]
    return 0 if last is None else last + 1


class BoardViewSet(viewsets.ModelViewSet):
    """Boards the current user belongs to, plus member and column management.

    Boards where the user is not a member are hidden (404), not forbidden.
    """

    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        queryset = (
            Board.objects.filter(members__user=self.request.user)
            .distinct()
            .order_by("-created_at")
        )
        if self.action == "retrieve":
            cards = Card.objects.select_related("assignee").prefetch_related("subtasks")
            queryset = queryset.prefetch_related(
                Prefetch("members", queryset=BoardMember.objects.select_related("user")),
                Prefetch("columns__cards", queryset=cards),
            )
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return BoardDetailSerializer
        return BoardSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        """Create the board, make the creator its owner and add the default columns."""
        board = serializer.save()
        BoardMember.objects.create(board=board, user=self.request.user, role=OWNER)
        Column.objects.bulk_create(
            Column(board=board, title=title, position=index, is_done_column=is_done)
            for index, (title, is_done) in enumerate(DEFAULT_COLUMNS)
        )

    def perform_update(self, serializer):
        require_role(self.request.user, serializer.instance, OWNER)
        serializer.save()

    def perform_destroy(self, instance):
        require_role(self.request.user, instance, OWNER)
        instance.delete()

    @action(detail=True, methods=["post"], url_path="members")
    def add_member(self, request, pk=None):
        """POST /api/boards/{id}/members/ — invite a user by username or email (owner only)."""
        board = self.get_object()
        require_role(request.user, board, OWNER)
        serializer = AddMemberSerializer(data=request.data, context={"board": board})
        serializer.is_valid(raise_exception=True)
        member = BoardMember.objects.create(
            board=board,
            user=serializer.validated_data["user"],
            role=serializer.validated_data["role"],
        )
        return Response(BoardMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"members/(?P<member_id>\d+)")
    def member_detail(self, request, pk=None, member_id=None):
        """PATCH changes a member's role (owner only).
        DELETE removes a member (owner, or the member leaving the board).

        A board always keeps at least one owner.
        """
        board = self.get_object()
        member = get_object_or_404(BoardMember, pk=member_id, board=board)
        is_last_owner = (
            member.role == OWNER and board.members.filter(role=OWNER).count() == 1
        )

        if request.method == "PATCH":
            require_role(request.user, board, OWNER)
            role = serializers.ChoiceField(choices=BoardMember.Role.choices).run_validation(
                request.data.get("role")
            )
            if is_last_owner and role != OWNER:
                raise ValidationError("The board must keep at least one owner.")
            member.role = role
            member.save(update_fields=["role"])
            return Response(BoardMemberSerializer(member).data)

        if member.user != request.user:
            require_role(request.user, board, OWNER)
        if is_last_owner:
            raise ValidationError("The board must keep at least one owner.")
        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="columns")
    def add_column(self, request, pk=None):
        """POST /api/boards/{id}/columns/ — add a column to the board (owner only)."""
        board = self.get_object()
        require_role(request.user, board, OWNER)
        serializer = ColumnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        position = serializer.validated_data.get("position", next_position(board.columns))
        serializer.save(board=board, position=position)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ColumnViewSet(
    mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Edit or delete a column (owner only) and create cards inside it (member+)."""

    serializer_class = ColumnSerializer
    http_method_names = ["post", "patch", "delete"]

    def get_queryset(self):
        return Column.objects.filter(board__members__user=self.request.user).distinct()

    def perform_update(self, serializer):
        require_role(self.request.user, serializer.instance.board, OWNER)
        serializer.save()

    def perform_destroy(self, instance):
        require_role(self.request.user, instance.board, OWNER)
        instance.delete()

    @action(detail=True, methods=["post"], url_path="cards")
    @transaction.atomic
    def create_card(self, request, pk=None):
        """POST /api/columns/{id}/cards/ — create a card and log a 'created' activity (member+)."""
        column = self.get_object()
        require_role(request.user, column.board, MEMBER)
        serializer = CardSerializer(data=request.data, context={"board": column.board})
        serializer.is_valid(raise_exception=True)
        position = serializer.validated_data.get("position", next_position(column.cards))
        card = serializer.save(column=column, position=position)
        CardActivity.objects.create(
            card=card,
            user=request.user,
            action_type=CardActivity.ActionType.CREATED,
            destination_column=column,
        )
        return Response(CardSerializer(card).data, status=status.HTTP_201_CREATED)


class CardViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Read (viewer+), edit, move or delete a card (member+), and add subtasks (member+).

    Every change is written to the card's activity history.
    """

    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        return (
            Card.objects.filter(column__board__members__user=self.request.user)
            .distinct()
            .select_related("column__board", "assignee")
            .prefetch_related(
                "subtasks",
                Prefetch(
                    "activities",
                    queryset=CardActivity.objects.select_related(
                        "user", "target_user", "source_column", "destination_column"
                    ),
                ),
            )
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CardDetailSerializer
        return CardSerializer

    @transaction.atomic
    def perform_update(self, serializer):
        """Save the change and log 'updated', 'assigned' and/or 'moved' activities."""
        card = serializer.instance
        board = card.column.board
        require_role(self.request.user, board, MEMBER)

        old_column = card.column
        old_assignee = card.assignee
        old_text = {field: getattr(card, field) for field in CARD_TEXT_FIELDS}

        data = serializer.validated_data
        new_column = data.get("column", old_column)
        extra = {}
        if new_column != old_column and "position" not in data:
            extra["position"] = next_position(new_column.cards)
        card = serializer.save(**extra)

        def log(action_type, **fields):
            CardActivity.objects.create(
                card=card, user=self.request.user, action_type=action_type, **fields
            )

        if any(getattr(card, field) != old_text[field] for field in CARD_TEXT_FIELDS):
            log(CardActivity.ActionType.UPDATED)
        if card.assignee != old_assignee:
            log(CardActivity.ActionType.ASSIGNED, target_user=card.assignee)
        if card.column != old_column:
            log(
                CardActivity.ActionType.MOVED,
                source_column=old_column,
                destination_column=card.column,
            )

    def perform_destroy(self, instance):
        require_role(self.request.user, instance.column.board, MEMBER)
        instance.delete()

    @action(detail=True, methods=["post"], url_path="subtasks")
    def add_subtask(self, request, pk=None):
        """POST /api/cards/{id}/subtasks/ — add a checklist item to the card (member+)."""
        card = self.get_object()
        require_role(request.user, card.column.board, MEMBER)
        serializer = SubtaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        position = serializer.validated_data.get("position", next_position(card.subtasks))
        serializer.save(card=card, position=position)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SubtaskViewSet(
    mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Tick, rename, reorder or delete a checklist item (member+)."""

    serializer_class = SubtaskSerializer
    http_method_names = ["patch", "delete"]

    def get_queryset(self):
        return (
            Subtask.objects.filter(card__column__board__members__user=self.request.user)
            .distinct()
            .select_related("card__column__board")
        )

    def perform_update(self, serializer):
        require_role(self.request.user, serializer.instance.card.column.board, MEMBER)
        serializer.save()

    def perform_destroy(self, instance):
        require_role(self.request.user, instance.card.column.board, MEMBER)
        instance.delete()
