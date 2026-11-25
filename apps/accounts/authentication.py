from rest_framework.authentication import SessionAuthentication


class Session401Authentication(SessionAuthentication):
    """Session auth that answers 401 (not 403) to anonymous callers, so the SPA can return to sign-in."""

    def authenticate_header(self, request):
        return "Session"
