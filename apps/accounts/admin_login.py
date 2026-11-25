from urllib.parse import quote

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

ADMIN_HOME = "/django-admin/"


def admin_login(request, extra_context=None):
    """Replaces the Django Admin password form: anonymous -> SPA sign-in, signed-in non-admin -> 403."""
    user = request.user
    if user.is_authenticated:
        if user.is_active and user.is_staff:
            nxt = request.GET.get("next", "")
            safe = url_has_allowed_host_and_scheme(
                nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            )
            return HttpResponseRedirect(nxt if safe and nxt else ADMIN_HOME)
        raise PermissionDenied("Administrator role required.")
    return HttpResponseRedirect(f"/sign-in?next={quote(ADMIN_HOME, safe='/')}")
