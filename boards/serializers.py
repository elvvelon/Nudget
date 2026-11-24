from rest_framework import serializers

from users.models import User
from users.serializers import UserShortSerializer

from .models import Board, BoardMember, Card, CardActivity, Column, Subtask
from .permissions import get_role


class SubtaskSerializer(serializers.ModelSerializer):
    """A checklist item; position defaults to the end of the card's list."""

    class Meta:
        model = Subtask
        fields = ["id", "title", "is_completed", "position"]
        extra_kwargs = {"position": {"required": False}}


class ColumnShortSerializer(serializers.ModelSerializer):
    """Column id and title, used inside activity entries."""

    class Meta:
        model = Column
        fields = ["id", "title"]


class CardActivitySerializer(serializers.ModelSerializer):
    """One history entry of a card."""

    user = UserShortSerializer(read_only=True)
    target_user = UserShortSerializer(read_only=True)
    source_column = ColumnShortSerializer(read_only=True)
    destination_column = ColumnShortSerializer(read_only=True)

    class Meta:
        model = CardActivity
        fields = [
            "id",
            "action_type",
            "user",
            "target_user",
            "source_column",
            "destination_column",
            "created_at",
        ]


class CardSerializer(serializers.ModelSerializer):
    """Card fields for create and update.

    `assignee_id` and `column_id` are validated against the card's board:
    the assignee must be a board member and the column must belong to the same board.
    """

    assignee = UserShortSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source="assignee",
        queryset=User.objects.all(),
        allow_null=True,
        required=False,
        write_only=True,
    )
    column_id = serializers.PrimaryKeyRelatedField(
        source="column", queryset=Column.objects.all(), required=False
    )

    class Meta:
        model = Card
        fields = [
            "id",
            "column_id",
            "title",
            "description",
            "priority",
            "position",
            "due_date",
            "assignee",
            "assignee_id",
            "last_nudged_at",
            "updated_at",
        ]
        read_only_fields = ["last_nudged_at", "updated_at"]
        extra_kwargs = {"position": {"required": False}}

    def get_board(self):
        """The board this card belongs to (from the context on create, from the card on update)."""
        if self.instance is not None:
            return self.instance.column.board
        return self.context["board"]

    def validate_assignee_id(self, user):
        if user is not None and get_role(user, self.get_board()) is None:
            raise serializers.ValidationError("The assignee must be a member of this board.")
        return user

    def validate_column_id(self, column):
        if column.board_id != self.get_board().id:
            raise serializers.ValidationError("The column must belong to the same board.")
        return column


class CardDetailSerializer(CardSerializer):
    """Full card for the modal window: fields plus subtasks and activity history."""

    subtasks = SubtaskSerializer(many=True, read_only=True)
    activities = CardActivitySerializer(many=True, read_only=True)

    class Meta(CardSerializer.Meta):
        fields = CardSerializer.Meta.fields + ["subtasks", "activities"]


class CardOnBoardSerializer(serializers.ModelSerializer):
    """Compact card shown inside a column on the kanban view."""

    assignee = UserShortSerializer(read_only=True)
    subtasks_total = serializers.SerializerMethodField()
    subtasks_done = serializers.SerializerMethodField()

    class Meta:
        model = Card
        fields = [
            "id",
            "title",
            "priority",
            "position",
            "due_date",
            "assignee",
            "subtasks_total",
            "subtasks_done",
            "updated_at",
        ]

    def get_subtasks_total(self, card):
        return len(card.subtasks.all())

    def get_subtasks_done(self, card):
        return sum(1 for subtask in card.subtasks.all() if subtask.is_completed)


class ColumnSerializer(serializers.ModelSerializer):
    """Column fields for create and update; position defaults to the end of the board."""

    class Meta:
        model = Column
        fields = ["id", "title", "position", "is_done_column"]
        extra_kwargs = {"position": {"required": False}}


class ColumnWithCardsSerializer(ColumnSerializer):
    """Column with its cards, used in the full board view."""

    cards = CardOnBoardSerializer(many=True, read_only=True)

    class Meta(ColumnSerializer.Meta):
        fields = ColumnSerializer.Meta.fields + ["cards"]


class BoardMemberSerializer(serializers.ModelSerializer):
    """A board member with their role."""

    user = UserShortSerializer(read_only=True)

    class Meta:
        model = BoardMember
        fields = ["id", "user", "role", "joined_at"]
        read_only_fields = ["joined_at"]


class AddMemberSerializer(serializers.Serializer):
    """Input for inviting a user by username or email with the member or viewer role."""

    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    role = serializers.ChoiceField(
        choices=[BoardMember.Role.MEMBER, BoardMember.Role.VIEWER],
        default=BoardMember.Role.MEMBER,
    )

    def validate(self, data):
        username, email = data.get("username"), data.get("email")
        if bool(username) == bool(email):
            raise serializers.ValidationError("Provide either username or email.")
        lookup = {"username": username} if username else {"email__iexact": email}
        user = User.objects.filter(**lookup).first()
        if user is None:
            raise serializers.ValidationError("User not found.")
        board = self.context["board"]
        if BoardMember.objects.filter(board=board, user=user).exists():
            raise serializers.ValidationError("This user is already a member of the board.")
        data["user"] = user
        return data


class BoardSerializer(serializers.ModelSerializer):
    """Board settings plus the current user's role on it."""

    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = ["id", "title", "description", "discord_webhook_url", "created_at", "my_role"]
        read_only_fields = ["created_at"]

    def get_my_role(self, board):
        return get_role(self.context["request"].user, board)


class BoardDetailSerializer(BoardSerializer):
    """Full board for the kanban view: settings, members, columns and their cards."""

    members = BoardMemberSerializer(many=True, read_only=True)
    columns = ColumnWithCardsSerializer(many=True, read_only=True)

    class Meta(BoardSerializer.Meta):
        fields = BoardSerializer.Meta.fields + ["members", "columns"]
