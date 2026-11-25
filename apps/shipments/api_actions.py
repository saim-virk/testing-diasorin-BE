"""Day-4 endpoints: decisions and other transitions, the conversation, the approver queue, nav counts."""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import Session401Authentication
from apps.accounts.permissions import HasPermission
from apps.masterdata.models import CostCentreApprover
from apps.platform_config.models import SiteConfig

from . import api
from .enums import RoundState, Status
from .models import ApprovalRound, ShipmentRequest
from .serializers import EventSerializer, RequestDetailSerializer
from .services import access, derive, workflow

ROME = ZoneInfo("Europe/Rome")
QUEUE_FILTERS = ("pending", "decided", "all")
QUEUE_ACTIONS = ("Approved", "Rejected")


# ---------------------------------------------------------------- transitions
class CommentBody(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class ReasonBody(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ReturnBody(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ReassignBody(serializers.Serializer):
    email = serializers.EmailField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class PostBody(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["comment", "question", "note"], default="comment")
    text = serializers.CharField(allow_blank=True)


class _Action(APIView):
    """POST one transition; the response is the refreshed request detail."""

    authentication_classes = [Session401Authentication]
    body_class: type[serializers.Serializer] = serializers.Serializer

    def run(self, request, req, data):
        raise NotImplementedError

    def post(self, request, ref):
        body = self.body_class(data=request.data)
        body.is_valid(raise_exception=True)
        req = api._get_visible(request.user, ref)
        return Response(api._detail(request, self.run(request, req, body.validated_data)))


class ApproveView(_Action):
    permission_classes = [HasPermission.require("approvals", "decide")]
    body_class = CommentBody

    @extend_schema(operation_id="requests_approve", request=CommentBody, responses=RequestDetailSerializer)
    def post(self, request, ref):
        return super().post(request, ref)

    def run(self, request, req, data):
        return workflow.approve(req.pk, request.user, data["comment"])


class RejectView(_Action):
    permission_classes = [HasPermission.require("approvals", "decide")]
    body_class = CommentBody

    @extend_schema(operation_id="requests_reject", request=CommentBody, responses=RequestDetailSerializer)
    def post(self, request, ref):
        return super().post(request, ref)

    def run(self, request, req, data):
        return workflow.reject(req.pk, request.user, data["comment"])


class ReturnView(_Action):
    permission_classes = [HasPermission.require("workbench", "decide")]
    body_class = ReturnBody

    @extend_schema(operation_id="requests_return", request=ReturnBody, responses=RequestDetailSerializer)
    def post(self, request, ref):
        return super().post(request, ref)

    def run(self, request, req, data):
        return workflow.return_for_correction(req.pk, request.user, data["note"])


class CancelView(_Action):
    permission_classes = [HasPermission.require("requests", "cancel")]
    body_class = ReasonBody

    @extend_schema(operation_id="requests_cancel", request=ReasonBody, responses=RequestDetailSerializer)
    def post(self, request, ref):
        return super().post(request, ref)

    def run(self, request, req, data):
        return workflow.cancel(req.pk, request.user, data["reason"])


class ReassignApproverView(_Action):
    permission_classes = [HasPermission.require("requests", "manage")]
    body_class = ReassignBody

    @extend_schema(
        operation_id="requests_reassign_approver", request=ReassignBody, responses=RequestDetailSerializer
    )
    def post(self, request, ref):
        return super().post(request, ref)

    def run(self, request, req, data):
        return workflow.reassign_approver(req.pk, request.user, data["email"], data["reason"])


class SkipApprovalView(_Action):
    permission_classes = [HasPermission.require("requests", "manage")]
    body_class = ReasonBody

    @extend_schema(
        operation_id="requests_skip_approval", request=ReasonBody, responses=RequestDetailSerializer
    )
    def post(self, request, ref):
        return super().post(request, ref)

    def run(self, request, req, data):
        return workflow.skip_approval(req.pk, request.user, data["reason"])


# ---------------------------------------------------------------- conversation
class EventsView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "view")]

    @extend_schema(operation_id="requests_events", responses=EventSerializer(many=True))
    def get(self, request, ref):
        req = api._get_visible(request.user, ref)
        return Response(EventSerializer(access.visible_events(request.user, req), many=True).data)


class CommentsView(APIView):
    """The conversation: events with `in_conversation`, as this viewer may see them."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "view")]

    @extend_schema(operation_id="requests_comments_list", responses=EventSerializer(many=True))
    def get(self, request, ref):
        req = api._get_visible(request.user, ref)
        rows = [e for e in access.visible_events(request.user, req) if e.in_conversation]
        return Response(EventSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="requests_comments_create", request=PostBody, responses={201: EventSerializer}
    )
    def post(self, request, ref):
        body = PostBody(data=request.data)
        body.is_valid(raise_exception=True)
        req = api._get_visible(request.user, ref)
        event = workflow.post(req.pk, request.user, body.validated_data["kind"], body.validated_data["text"])
        return Response(EventSerializer(event).data, status=http.HTTP_201_CREATED)


# ---------------------------------------------------------------- approver queue
def _round_age_hours(rnd: ApprovalRound | None, now) -> int | None:
    if rnd is None or rnd.state not in (RoundState.PENDING, RoundState.HELD):
        return None
    return max(0, int((now - rnd.started_at).total_seconds() // 3600))


def sla_class(age_hours: int, cfg: SiteConfig) -> str:
    """Prototype `ageClass`: over at the escalation hours, warn at the SLA hours, else ok."""
    if age_hours >= cfg.escalate_hours:
        return "over"
    return "warn" if age_hours >= cfg.sla_hours else "ok"


class ApprovalRowSerializer(serializers.ModelSerializer):
    requester_name = serializers.SerializerMethodField()
    cost_centre_name = serializers.CharField(read_only=True)
    line_count = serializers.SerializerMethodField()
    total_weight_kg = serializers.SerializerMethodField()
    round_state = serializers.SerializerMethodField()
    age_hours = serializers.SerializerMethodField()
    sla_class = serializers.SerializerMethodField()
    escalated = serializers.SerializerMethodField()
    can_decide = serializers.SerializerMethodField()
    decided_at = serializers.SerializerMethodField()
    decided_by_name = serializers.SerializerMethodField()
    decision_note = serializers.SerializerMethodField()

    class Meta:
        model = ShipmentRequest
        fields = [
            "reference",
            "status",
            "last_submitted_at",
            "applicant_name",
            "requester_name",
            "destination",
            "consignee_company",
            "recipient_branch_name",
            "cost_centre_code",
            "cost_centre_name",
            "line_count",
            "total_weight_kg",
            "overall_temperature",
            "round_state",
            "age_hours",
            "sla_class",
            "escalated",
            "can_decide",
            "decided_at",
            "decided_by_name",
            "decision_note",
        ]

    def _round(self, obj) -> ApprovalRound | None:
        rounds = list(obj.approval_rounds.all())
        return rounds[-1] if rounds else None

    def get_requester_name(self, obj) -> str:
        return obj.requester.get_full_name() or obj.requester.email

    def get_line_count(self, obj) -> int:
        return len(obj.lines.all())

    def get_total_weight_kg(self, obj) -> str:
        return str(derive.total_weight(list(obj.lines.all())))

    def get_round_state(self, obj) -> str | None:
        rnd = self._round(obj)
        return rnd.state if rnd else None

    def get_age_hours(self, obj) -> int | None:
        return _round_age_hours(self._round(obj), self.context["now"])

    def get_sla_class(self, obj) -> str | None:
        age = self.get_age_hours(obj)
        return None if age is None else sla_class(age, self.context["cfg"])

    def get_escalated(self, obj) -> bool:
        rnd, age = self._round(obj), self.get_age_hours(obj)
        if rnd is None or age is None:
            return False
        return rnd.escalated_to_admins or age >= self.context["cfg"].escalate_hours

    def get_can_decide(self, obj) -> bool:
        rnd = self._round(obj)
        user = self.context["request"].user
        return bool(
            obj.status == Status.PENDING_APPROVAL
            and rnd is not None
            and rnd.state == RoundState.PENDING
            and any(u.pk == user.pk for u in rnd.eligible_approvers.all())
        )

    def get_decided_at(self, obj) -> datetime | None:
        rnd = self._round(obj)
        return rnd.decided_at if rnd and rnd.decided_at else None

    def get_decided_by_name(self, obj) -> str | None:
        rnd = self._round(obj)
        who = rnd.decided_by if rnd else None
        return (who.get_full_name() or who.email) if who else None

    def get_decision_note(self, obj) -> str | None:
        event = next(iter(getattr(obj, "queue_events", [])), None)
        return (event.note or None) if event else None


class ApprovalsPagination(PageNumberPagination):
    page_size = 50
    stats: dict = {}

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["stats"] = self.stats
        return response

    def get_paginated_response_schema(self, schema):
        out = super().get_paginated_response_schema(schema)
        counts = {k: {"type": "integer"} for k in ("awaiting", "over_sla", "decided", "approved_this_month")}
        out["properties"]["stats"] = {"type": "object", "properties": counts, "required": list(counts)}
        out["required"] = [*out.get("required", []), "stats"]
        return out


def _stats(user, cfg: SiteConfig, now) -> dict:
    waiting = list(
        access.pending_for(user).prefetch_related("approval_rounds")  # one open round per request
    )
    over = 0
    for req in waiting:
        rnd = req.approval_rounds.filter(state=RoundState.PENDING).first()
        if rnd and _round_age_hours(rnd, now) >= cfg.sla_hours:
            over += 1
    month_start = datetime(now.astimezone(ROME).year, now.astimezone(ROME).month, 1, tzinfo=ROME)
    return {
        "awaiting": len(waiting),
        "over_sla": over,
        "decided": access.decided_by(user).count(),
        "approved_this_month": ApprovalRound.objects.filter(
            decided_by=user, state=RoundState.APPROVED, decided_at__gte=month_start
        ).count(),
    }


class ApprovalsView(ListAPIView):
    """The approver's queue (DSF-04.x approver view): oldest first, with age and SLA class."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("approvals", "view")]
    serializer_class = ApprovalRowSerializer
    pagination_class = ApprovalsPagination

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "cfg": SiteConfig.load(), "now": timezone.now()}

    def get_queryset(self):
        user, params = self.request.user, self.request.query_params
        chip = params.get("filter", "pending")
        if chip not in QUEUE_FILTERS:
            raise ValidationError({"filter": [f"Use one of: {', '.join(QUEUE_FILTERS)}."]})
        base = {
            "pending": access.pending_for,
            "decided": access.decided_by,
            "all": access.queue_requests,
        }[chip](user)
        qs = base.select_related("requester").prefetch_related(
            "lines",
            "approval_rounds__eligible_approvers",
            "approval_rounds__decided_by",
            api.decision_events_prefetch(QUEUE_ACTIONS, "queue_events"),
        )
        if q := params.get("q", "").strip():
            qs = qs.filter(
                Q(reference__icontains=q)
                | Q(applicant_name__icontains=q)
                | Q(consignee_company__icontains=q)
                | Q(recipient_branch_name__icontains=q)
                | Q(cost_centre_code__icontains=q)
            )
        return qs.order_by("last_submitted_at", "id")

    @extend_schema(
        operation_id="approvals_list",
        parameters=[
            OpenApiParameter("filter", str, enum=list(QUEUE_FILTERS), description="Default: pending"),
            OpenApiParameter("q", str, description="Search reference, applicant, recipient, cost centre"),
        ],
    )
    def get(self, request, *args, **kwargs):
        self.paginator.stats = _stats(request.user, SiteConfig.load(), self.get_serializer_context()["now"])
        return super().get(request, *args, **kwargs)


class MyCostCentreSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    approval_required = serializers.BooleanField()
    co_approvers = serializers.ListField(child=serializers.CharField())
    pending = serializers.IntegerField()


class MyCostCentresView(APIView):
    """ "Cost centres you approve for" (queue footer)."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("approvals", "view")]

    @extend_schema(operation_id="approvals_my_cost_centres", responses=MyCostCentreSerializer(many=True))
    def get(self, request):
        links = CostCentreApprover.objects.filter(
            cost_centre__isnull=False, user=request.user
        ).select_related("cost_centre")
        rows = []
        for link in links.order_by("cost_centre__code"):
            cc = link.cost_centre
            others = [
                a.user.get_full_name() or a.user.email
                for a in cc.approvers.select_related("user").exclude(user=request.user)
                if a.user.is_active
            ]
            pending = ShipmentRequest.objects.filter(
                cost_centre_ref=cc,
                status=Status.PENDING_APPROVAL,
                approval_rounds__state=RoundState.PENDING,
            ).distinct()
            rows.append(
                {
                    "code": cc.code,
                    "name": cc.name,
                    "approval_required": cc.approval_required,
                    "co_approvers": others,
                    "pending": pending.count(),
                }
            )
        return Response(MyCostCentreSerializer(rows, many=True).data)


# ---------------------------------------------------------------- nav counts
class MeCountsView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "view")]

    @extend_schema(
        operation_id="me_counts",
        responses=inline_serializer(
            "MeCounts",
            {"approvals_pending": serializers.IntegerField(), "my_open_requests": serializers.IntegerField()},
        ),
    )
    def get(self, request):
        return Response(
            {
                "approvals_pending": access.pending_for(request.user).count(),
                "my_open_requests": ShipmentRequest.objects.filter(requester=request.user)
                .exclude(status__in=api.CLOSED)
                .count(),
            }
        )
