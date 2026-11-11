from django.conf import settings
from django.db import models


class Board(models.Model):
    """A kanban board that groups columns, cards and members."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    discord_webhook_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "boards"

    def __str__(self):
        return self.title


class BoardMember(models.Model):
    """Membership of a user on a board with a per-board role."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="board_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "board_members"
        constraints = [
            models.UniqueConstraint(fields=["board", "user"], name="unique_board_member"),
        ]

    def __str__(self):
        return f"{self.user} — {self.board} ({self.role})"


class Column(models.Model):
    """A board column such as To Do or Done; cards are ordered inside it."""

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="columns")
    title = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)
    is_done_column = models.BooleanField(default=False)

    class Meta:
        db_table = "columns"
        ordering = ["board", "position"]

    def __str__(self):
        return f"{self.board}: {self.title}"


class Card(models.Model):
    """A task card that lives in a column and may have an assignee."""

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name="cards")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_cards",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    position = models.PositiveIntegerField(default=0)
    due_date = models.DateTimeField(null=True, blank=True)
    last_nudged_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cards"
        ordering = ["column", "position"]

    def __str__(self):
        return self.title


class Subtask(models.Model):
    """A checklist item inside a card."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=200)
    is_completed = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "subtasks"
        ordering = ["card", "position"]

    def __str__(self):
        return self.title


class CardActivity(models.Model):
    """A history entry for a card: created, updated, moved, assigned or nudged."""

    class ActionType(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        MOVED = "moved", "Moved"
        ASSIGNED = "assigned", "Assigned"
        NUDGED = "nudged", "Nudged"

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="activities")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="performed_activities"
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_activities",
    )
    action_type = models.CharField(max_length=10, choices=ActionType.choices)
    source_column = models.ForeignKey(
        Column, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    destination_column = models.ForeignKey(
        Column, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "card_activities"
        ordering = ["-created_at"]
        verbose_name_plural = "card activities"

    def __str__(self):
        return f"{self.card} — {self.action_type}"
