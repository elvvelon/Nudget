from rest_framework.exceptions import PermissionDenied

from .models import BoardMember

ROLE_RANK = {
    BoardMember.Role.VIEWER: 0,
    BoardMember.Role.MEMBER: 1,
    BoardMember.Role.OWNER: 2,
}


def get_role(user, board):
    """Return the user's role on the board, or None if they are not a member."""
    membership = BoardMember.objects.filter(board=board, user=user).first()
    return membership.role if membership else None


def require_role(user, board, minimum):
    """Raise 403 unless the user's role on the board is at least `minimum`.

    Roles are ordered viewer < member < owner, so "member" also lets owners through.
    """
    role = get_role(user, board)
    if role is None or ROLE_RANK[role] < ROLE_RANK[minimum]:
        raise PermissionDenied(f"This action requires the '{minimum}' role or higher on this board.")
    return role
