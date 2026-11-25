"""Deactivating users and blocking addresses. Users are never deleted."""

from django.db import transaction
from django.utils import timezone

from ..models import BlockedEmail, User
from .sessions import end_sessions


@transaction.atomic
def deactivate_user(user: User, by: User | None = None) -> None:
    """is_active=False + who/when, and every existing session ends on its next request."""
    user.is_active = False
    user.deactivated_at = timezone.now()
    user.deactivated_by = by
    user.sessions_revoked_at = user.deactivated_at
    user.save(update_fields=["is_active", "deactivated_at", "deactivated_by", "sessions_revoked_at"])


@transaction.atomic
def reactivate_user(user: User) -> None:
    user.is_active = True
    user.deactivated_at = None
    user.deactivated_by = None
    user.save(update_fields=["is_active", "deactivated_at", "deactivated_by"])


@transaction.atomic
def block_email(email: str, reason: str = "", by: User | None = None) -> BlockedEmail:
    """Add to the block list and log out that person's existing sessions."""
    row, _ = BlockedEmail.objects.get_or_create(
        email=email.strip().lower(), defaults={"reason": reason, "added_by": by}
    )
    user = User.objects.filter(email__iexact=row.email).first()
    if user is not None:
        end_sessions(user)
    return row
