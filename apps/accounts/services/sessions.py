"""Session start / end. A user's sessions are ended by stamping `User.sessions_revoked_at`."""

from django.contrib.auth import login, logout
from django.utils import timezone

from ..models import User


def start_session(request, user: User, view: str) -> None:
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    now = timezone.now().timestamp()  # float: compared with sessions_revoked_at to the microsecond
    request.session["login_at"] = now
    request.session["last_activity"] = now
    request.session["view"] = view
    request.session.save()


def end_current_session(request) -> None:
    logout(request)


def end_sessions(user: User) -> None:
    """End every session of a user (block, deactivation, role change).

    Sessions that started before now are logged out on their next request by SessionLimitsMiddleware.
    """
    user.sessions_revoked_at = timezone.now()
    user.save(update_fields=["sessions_revoked_at"])
