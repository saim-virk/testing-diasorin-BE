import logging
import uuid

from django.utils import translation

from . import messages

logger = logging.getLogger(__name__)


class RequestLanguageMiddleware:
    """Run each /api/ request in the caller's language (Accept-Language, then the profile) so Django's and DRF's
    own messages, which are built while the view runs, come out in Italian for Italian users."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)
        with translation.override(messages.request_language(request)):
            return self.get_response(request)


class RequestIdMiddleware:
    """Give every response an `X-Request-ID` (the caller's own when sent) and log it with any 500, so the
    reference shown in the UI's "Server error" message can be found in the server log."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID", "")[:64] or uuid.uuid4().hex[:12]
        request.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        if response.status_code >= 500:
            logger.error("Server error %s %s (request id %s)", request.method, request.path, request_id)
        return response
