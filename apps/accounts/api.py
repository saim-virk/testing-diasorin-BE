from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.masterdata.models import CostCentre

from .authentication import Session401Authentication
from .models import User
from .permissions import AREAS, PERMISSIONS, HasPermission, effective_permissions
from .services import otp, roles
from .services.profile import approval_hint
from .services.sessions import end_current_session, start_session

ROLE_CHOICES = [roles.REQUESTER, roles.APPROVER, roles.CUSTOMER_MANAGEMENT, roles.ADMIN]


class ApprovalHintSerializer(serializers.Serializer):
    """What submit would do for the cost centre (the routing function in dry-run mode)."""

    required = serializers.BooleanField()
    why = serializers.CharField()
    approvers = serializers.ListField(child=serializers.CharField())


class PermissionMapSerializer(serializers.DictField):
    """{area: {action: bool}}"""

    def __init__(self, **kw):
        super().__init__(child=serializers.DictField(child=serializers.BooleanField()), **kw)


class MeSerializer(serializers.ModelSerializer):
    """Read shape of /api/me. `view` and `roles` are computed."""

    default_cost_centre = serializers.SlugRelatedField(
        slug_field="code", queryset=CostCentre.objects.filter(is_active=True), allow_null=True, required=False
    )
    roles = serializers.SerializerMethodField()
    view = serializers.SerializerMethodField()
    approval_hint = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "department",
            "job_title",
            "phone",
            "language",
            "default_cost_centre",
            "roles",
            "view",
            "approval_hint",
            "permissions",
        ]
        read_only_fields = ["email", "roles", "view", "approval_hint", "permissions"]

    def get_roles(self, user) -> list[str]:
        return roles.roles_for(user)

    def get_view(self, user) -> str:
        return current_view(self.context["request"], user)

    @extend_schema_field(PermissionMapSerializer())
    def get_permissions(self, user):
        return effective_permissions(user)

    @extend_schema_field(ApprovalHintSerializer(allow_null=True))
    def get_approval_hint(self, user):
        return approval_hint(user, user.default_cost_centre)


def current_view(request, user) -> str:
    """The session's view, falling back to the primary role if it is unset or no longer held."""
    held = roles.roles_for(user)
    view = request.session.get("view")
    return view if view in held else roles.primary_role(user)


def _client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR") or None


@method_decorator(csrf_protect, name="dispatch")  # login CSRF: the SPA calls GET /api/auth/csrf first
class _Anon(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]


class RequestCodeView(_Anon):
    @extend_schema(
        request=inline_serializer(
            "RequestCodeIn",
            {
                "email": serializers.CharField(),
                "language": serializers.ChoiceField(choices=["en", "it"], required=False),
            },
        ),
        responses={
            200: inline_serializer(
                "RequestCodeOut",
                {
                    "expires_in_minutes": serializers.IntegerField(),
                    "resend_after_seconds": serializers.IntegerField(),
                },
            ),
            403: OpenApiResponse(description="Refused: {code, message}"),
            429: OpenApiResponse(description="Cooldown or rate limit: {code, message, retry_after_seconds}"),
        },
        auth=[],
    )
    def post(self, request):
        email = str(request.data.get("email", ""))
        try:
            language = str(request.data.get("language", "")).lower()
            return Response(otp.request_code(email, _client_ip(request), language))
        except otp.AccessRefused as e:
            return Response({"code": e.code, "message": e.message}, status=403)
        except otp.RateLimited as e:
            msg = (
                "Please wait a moment before requesting another code."
                if e.code == "cooldown"
                else "Too many code requests. Try again later."
            )
            return Response(
                {"code": e.code, "message": msg, "retry_after_seconds": e.retry_after_seconds},
                status=429,
                headers={"Retry-After": str(e.retry_after_seconds)},
            )


class VerifyView(_Anon):
    @extend_schema(
        request=inline_serializer(
            "VerifyIn", {"email": serializers.CharField(), "code": serializers.CharField()}
        ),
        responses={
            200: MeSerializer,
            400: OpenApiResponse(description="{code: wrong|expired|locked, message}"),
            403: OpenApiResponse(description="Refused: {code, message}"),
        },
        auth=[],
    )
    def post(self, request):
        email = str(request.data.get("email", ""))
        code = str(request.data.get("code", ""))
        try:
            user = otp.verify_code(email, code)
        except otp.OTPError as e:
            messages = {
                "wrong": "That code is not right. Check it and try again.",
                "expired": "This code has expired or was replaced. Request a new one.",
                "locked": "Too many wrong attempts. Request a new code.",
            }
            return Response({"code": e.code, "message": messages[e.code]}, status=400)
        except otp.AccessRefused as e:
            return Response({"code": e.code, "message": e.message}, status=403)
        start_session(request, user, roles.primary_role(user))
        return Response(MeSerializer(user, context={"request": request}).data)


class LogoutView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        end_current_session(request)
        return Response(status=204)


class CsrfView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None}, auth=[])
    def get(self, request):
        get_token(request)  # makes CsrfViewMiddleware set the cookie
        return Response(status=204)


class MeView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=MeSerializer, responses=MeSerializer)
    def patch(self, request):
        # profile fields only: the serializer has no writable email / roles / view
        ser = MeSerializer(request.user, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class MeViewSwitchView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer("SwitchViewIn", {"view": serializers.ChoiceField(choices=ROLE_CHOICES)}),
        responses=MeSerializer,
    )
    def post(self, request):
        view = request.data.get("view")
        if view not in roles.roles_for(request.user):
            return Response({"view": ["You do not hold that role."]}, status=400)
        request.session["view"] = view
        return Response(MeSerializer(request.user, context={"request": request}).data)


class PermissionsView(APIView):
    """Read-only role -> area -> action map (admin tab, DSF-09.14)."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("admin.access", "view")]

    @extend_schema(
        responses=inline_serializer(
            "PermissionsOut",
            {
                "roles": serializers.DictField(child=PermissionMapSerializer()),
                "areas": serializers.ListField(child=serializers.CharField()),
            },
        )
    )
    def get(self, request):
        return Response({"roles": PERMISSIONS, "areas": list(AREAS)})
