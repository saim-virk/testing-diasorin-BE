from django.utils import timezone

from apps.platform_config.models import SiteConfig

from .models import BlockedEmail
from .services.sessions import end_current_session


class SessionLimitsMiddleware:
    """Absolute (`session_hours`), idle (`session_idle_minutes`) and revoked-session checks on every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            cfg = SiteConfig.load()
            now = timezone.now().timestamp()
            login_at = request.session.get("login_at", 0)
            last = request.session.get("last_activity", 0)
            revoked = request.user.sessions_revoked_at
            if (
                now - login_at > cfg.session_hours * 3600
                or now - last > cfg.session_idle_minutes * 60
                or (revoked is not None and login_at < revoked.timestamp())
                or BlockedEmail.objects.filter(email=request.user.email.strip().lower()).exists()
            ):
                end_current_session(request)  # request.user becomes anonymous
            else:
                request.session["last_activity"] = now
        return self.get_response(request)


class NoStoreApiMiddleware:
    """`Cache-Control: no-store` on every /api/ response: no browser or proxy keeps protected data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store"
        return response
