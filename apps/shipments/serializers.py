from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.api import ApprovalHintSerializer

from .models import ApprovalRound, Attachment, Parcel, RequestEvent, RequestLine, ShipmentRequest
from .services import access, derive, drafts, routing, workflow
from .services.drafts import ALL_FIELDS, LINE_FIELDS, PARCEL_FIELDS

DECISION_ACTIONS = ("Rejected", "Returned")


# ---------------------------------------------------------------- write
class LineWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestLine
        fields = LINE_FIELDS
        extra_kwargs = {f: {"required": False} for f in LINE_FIELDS}


class ParcelWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = PARCEL_FIELDS
        extra_kwargs = {f: {"required": False} for f in PARCEL_FIELDS}


class RequestWriteSerializer(serializers.ModelSerializer):
    """Every editable field is optional and nullable: type checks only, the rules live in services/validation.py."""

    lines = LineWriteSerializer(many=True, required=False)
    parcels = ParcelWriteSerializer(many=True, required=False)

    class Meta:
        model = ShipmentRequest
        fields = ALL_FIELDS
        extra_kwargs = {f: {"required": False} for f in ALL_FIELDS}


class SaveBodySerializer(serializers.Serializer):
    """Documentation shape of a save: the request fields plus the `version` read."""

    version = serializers.CharField()


class SubmitBodySerializer(serializers.Serializer):
    declaration = serializers.BooleanField()


class AttachmentUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["MSDS", "COA", "OTHER"])
    file = serializers.FileField()


# ---------------------------------------------------------------- read
class LineSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequestLine
        fields = [*LINE_FIELDS, "un_number", "hazard"]


class ParcelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Parcel
        fields = PARCEL_FIELDS


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ["id", "kind", "original_name", "content_type", "size_bytes", "uploaded_at"]


class EventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = RequestEvent
        fields = [
            "at",
            "actor_name",
            "actor_role",
            "kind",
            "in_conversation",
            "action",
            "from_status",
            "to_status",
            "note",
        ]

    def get_actor_name(self, obj) -> str | None:
        return (obj.actor.get_full_name() or obj.actor.email) if obj.actor else None


class DerivedSerializer(serializers.Serializer):
    un_numbers = serializers.ListField(child=serializers.CharField())
    hazard = serializers.CharField(allow_null=True)
    overall_temperature = serializers.CharField(allow_null=True)
    total_weight_kg = serializers.DecimalField(max_digits=12, decimal_places=3)
    line_count = serializers.IntegerField()
    dangerous_features_locked = serializers.BooleanField()


class NextStepsSerializer(serializers.Serializer):
    approval_required = serializers.BooleanField()
    approvers = serializers.ListField(child=serializers.CharField())
    approval_note = serializers.CharField(allow_null=True)
    reminder_hours = serializers.IntegerField()
    escalate_hours = serializers.IntegerField()
    specialised_courier = serializers.BooleanField()


DETAIL_FIELDS = [
    "reference",
    "status",
    "created_at",
    "updated_at",
    "submitted_at",
    "last_submitted_at",
    "applicant_email",
    *[f for f in ALL_FIELDS if f not in ("lines", "parcels")],
    "recipient_branch_name",
    "reason_label_it",
    "reason_label_en",
    "consignee_country_name",
    "cost_centre_name",
    "declaration_accepted_at",
    "overall_temperature",
]


class RequestDetailSerializer(serializers.ModelSerializer):
    version = serializers.SerializerMethodField()
    lines = LineSerializer(many=True, read_only=True)
    parcels = ParcelSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    derived = serializers.SerializerMethodField()
    next_steps = serializers.SerializerMethodField()
    routing_hint = serializers.SerializerMethodField()
    po_required = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
    available_actions = serializers.SerializerMethodField()
    duplicated_from = serializers.CharField(source="duplicated_from.reference", read_only=True, default=None)

    class Meta:
        model = ShipmentRequest
        fields = [
            *DETAIL_FIELDS,
            "version",
            "lines",
            "parcels",
            "attachments",
            "derived",
            "next_steps",
            "routing_hint",
            "po_required",
            "can_edit",
            "events",
            "available_actions",
            "duplicated_from",
        ]

    def get_version(self, obj) -> str:
        return drafts.version_of(obj)

    @extend_schema_field(DerivedSerializer())
    def get_derived(self, obj):
        return DerivedSerializer(derive.derived_summary(obj)).data

    @extend_schema_field(NextStepsSerializer())
    def get_next_steps(self, obj):
        return NextStepsSerializer(workflow.next_steps(obj)).data

    @extend_schema_field(ApprovalHintSerializer(allow_null=True))
    def get_routing_hint(self, obj):
        """Set only when submit would skip re-approval (Returned request, same cost centre); else null."""
        return routing.request_hint(obj)

    def get_po_required(self, obj) -> bool:
        from .services.validation import po_required

        return po_required(obj)

    def get_can_edit(self, obj) -> bool:
        user = self.context["request"].user
        return obj.requester_id == user.pk and obj.status in drafts.EDITABLE_STATUSES

    @extend_schema_field(EventSerializer(many=True))
    def get_events(self, obj):
        """Only what this viewer may see: the requester never gets internal notes."""
        return EventSerializer(access.visible_events(self.context["request"].user, obj), many=True).data

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_available_actions(self, obj):
        return workflow.available_actions(obj, self.context["request"].user)


class ApprovalSummarySerializer(serializers.Serializer):
    state = serializers.CharField()
    names = serializers.ListField(child=serializers.CharField())


class RequestListSerializer(serializers.ModelSerializer):
    line_count = serializers.SerializerMethodField()
    pvari_codes = serializers.SerializerMethodField()
    total_weight_kg = serializers.SerializerMethodField()
    approval = serializers.SerializerMethodField()
    decision_note = serializers.SerializerMethodField()
    decision_by = serializers.SerializerMethodField()
    duplicated_from = serializers.CharField(source="duplicated_from.reference", read_only=True, default=None)

    class Meta:
        model = ShipmentRequest
        fields = [
            "reference",
            "created_at",
            "status",
            "destination",
            "consignee_company",
            "recipient_code",
            "recipient_branch_name",
            "ship_day_requested",
            "overall_temperature",
            "cost_centre_code",
            "line_count",
            "pvari_codes",
            "total_weight_kg",
            "approval",
            "decision_note",
            "decision_by",
            "duplicated_from",
        ]

    def _decision(self, obj):
        """The Rejected / Returned event that put the request in its current status (prefetched as
        `decision_events`, newest first), else None."""
        if obj.status not in ("REJECTED", "RETURNED"):
            return None
        events = getattr(obj, "decision_events", None)
        if events is None:
            events = list(
                obj.events.filter(action__in=DECISION_ACTIONS).select_related("actor").order_by("-at", "-id")
            )
        return next((e for e in events if e.to_status == obj.status), None)

    def get_decision_note(self, obj) -> str | None:
        event = self._decision(obj)
        return (event.note or None) if event else None

    def get_decision_by(self, obj) -> str | None:
        event = self._decision(obj)
        return (event.actor.get_full_name() or event.actor.email) if event and event.actor else None

    def _lines(self, obj):
        return list(obj.lines.all())

    def get_line_count(self, obj) -> int:
        return len(self._lines(obj))

    def get_pvari_codes(self, obj) -> list[str]:
        return sorted({ln.pvari_code for ln in self._lines(obj) if ln.pvari_code})

    def get_total_weight_kg(self, obj) -> str:
        return str(derive.total_weight(self._lines(obj)))

    @extend_schema_field(ApprovalSummarySerializer(allow_null=True))
    def get_approval(self, obj):
        """Latest round: state + approver names; null until the request is submitted."""
        rounds = list(obj.approval_rounds.all())
        if not rounds:
            return {"state": "NOT_REQUIRED", "names": []} if obj.submitted_at else None
        latest: ApprovalRound = rounds[-1]
        names = [u.get_full_name() or u.email for u in latest.eligible_approvers.all()]
        if latest.state in ("APPROVED", "REJECTED") and latest.decided_by:
            names = [latest.decided_by.get_full_name() or latest.decided_by.email]
        state = latest.state
        if state == "APPROVED" and latest.skip_reason == "SELF_AUTO_APPROVED":
            return {"state": "AUTO_APPROVED", "names": []}  # never a person's name
        if state == "NOT_REQUIRED" and latest.skip_reason in (
            "REQUESTER_EXEMPT",
            "NO_APPROVER_SKIP",
            "ADMIN_SKIP",
        ):
            state = "SKIPPED"  # approval would apply but was set aside; "Not required" = switched off
        return {"state": state, "names": names}
