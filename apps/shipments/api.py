import csv

from django.db.models import Prefetch, Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import translation
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListCreateAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from apps.accounts.authentication import Session401Authentication
from apps.accounts.permissions import HasPermission

from . import messages
from .enums import Status
from .models import RequestEvent, ShipmentRequest
from .serializers import (
    DECISION_ACTIONS,
    AttachmentSerializer,
    AttachmentUploadSerializer,
    RequestDetailSerializer,
    RequestListSerializer,
    RequestWriteSerializer,
    SubmitBodySerializer,
)
from .services import attachments, drafts, workflow
from .services.errors import StepValidationError

CLOSED = (Status.DELIVERED, Status.CANCELLED)
ATTENTION = (Status.DRAFT, Status.REJECTED, Status.RETURNED)
FILTERS = {
    "all": None,
    "open": [s for s in Status.values if s not in CLOSED],
    "attention": list(ATTENTION),
    "drafts": [Status.DRAFT],
    "closed": list(CLOSED),
}
SORTS = {
    "reference": "reference",
    "-reference": "-reference",
    "ship_day": "ship_day_requested",
    "-ship_day": "-ship_day_requested",
    "created": "created_at",
    "-created": "-created_at",
}

CSV_HEADERS = {
    "en": ["Reference", "Created", "Recipient", "Branch", "Scope", "Ship day", "Lines", "PVARI codes",
           "Total kg", "Temperature", "Cost centre", "Approval", "Status"],
    "it": ["Riferimento", "Creata", "Destinatario", "Filiale", "Ambito", "Giorno di spedizione", "Righe",
           "Codici PVARI", "Kg totali", "Temperatura", "Centro di costo", "Approvazione", "Stato"],
}  # fmt: skip
CSV_STATUS = {"en": dict(Status.choices), "it": messages.STATUS_IT}
CSV_SCOPE = {
    "en": {"ITALY": "Italy", "EU": "EU", "EXTRA_EU": "Extra-EU", "USA": "USA"},
    "it": {"ITALY": "Italia", "EU": "Unione Europea", "EXTRA_EU": "Extra-UE", "USA": "USA"},
}
CSV_TEMPERATURE = {
    "en": {"AMBIENT": "Ambient", "COOL_2_8": "+2 +8 °C", "DRY_ICE": "Dry ice"},
    "it": {"AMBIENT": "Ambiente", "COOL_2_8": "+2 +8 °C", "DRY_ICE": "Ghiaccio secco"},
}
CSV_APPROVAL = {
    "en": {"NOT_REQUIRED": "Not required", "SKIPPED": "Skipped", "PENDING": "Pending", "APPROVED": "Approved",
           "REJECTED": "Rejected", "HELD": "On hold", "SUPERSEDED": "Superseded",
           "AUTO_APPROVED": "Approved automatically (self)"},
    "it": {"NOT_REQUIRED": "Non richiesta", "SKIPPED": "Saltata", "PENDING": "In attesa", "APPROVED": "Approvata",
           "REJECTED": "Rifiutata", "HELD": "In sospeso", "SUPERSEDED": "Sostituita",
           "AUTO_APPROVED": "Approvata automaticamente (autoapprovazione)"},
}  # fmt: skip


def exception_handler(exc, context):
    """StepValidationError -> 400 {message, step, errors, failed_steps}; everything else is DRF's default.

    Every error body carries a human `message`, in the language of the request (Accept-Language, then the
    profile): English or Italian.
    """
    if isinstance(exc, StepValidationError):
        response = Response(
            {
                "message": "Please correct the highlighted fields.",
                "step": exc.step,
                "errors": exc.errors,
                "failed_steps": exc.failed_steps,
            },
            status=http.HTTP_400_BAD_REQUEST,
        )
    else:
        lang = messages.request_language(context["request"])
        with translation.override("it" if lang == "it" else "en"):  # DRF's own Italian catalogue
            response = drf_exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    if isinstance(data, dict) and "message" not in data:
        detail = data.get("detail")
        data = {"message": str(detail) if detail else "Please correct the highlighted fields.", **data}
    elif isinstance(data, list):
        data = {"message": "Please correct the highlighted fields.", "errors": data}
    response.data = messages.translate(data, messages.request_language(context["request"]))
    return response


def decision_events_prefetch(actions=DECISION_ACTIONS, to_attr="decision_events") -> Prefetch:
    """The decision events of each listed request (newest first): rows show the latest note."""
    return Prefetch(
        "events",
        queryset=RequestEvent.objects.filter(action__in=actions)
        .select_related("actor")
        .order_by("-at", "-id"),
        to_attr=to_attr,
    )


def _get(ref: str) -> ShipmentRequest:
    return get_object_or_404(ShipmentRequest, reference=ref)


def _get_visible(user, ref: str) -> ShipmentRequest:
    req = _get(ref)
    if not drafts.can_view(user, req):
        raise NotFound("Not found.")  # same answer as an unknown reference: do not confirm it exists
    return req


def _detail(request, req) -> dict:
    req = (
        ShipmentRequest.objects.select_related("duplicated_from")
        .prefetch_related("lines", "parcels", "attachments", "events__actor")
        .get(pk=req.pk)
    )
    return RequestDetailSerializer(req, context={"request": request}).data


def _parse(data, *, drop=()):
    body = {k: v for k, v in data.items() if k not in drop}
    ser = RequestWriteSerializer(data=body, partial=True)
    if not ser.is_valid():
        raise ValidationError({"errors": ser.errors})
    # keep only what was sent (partial) and the nested rows as plain dicts
    return {
        k: ([dict(r) for r in v] if k in ("lines", "parcels") else v) for k, v in ser.validated_data.items()
    }


# ---------------------------------------------------------------- list / create
def _filtered(request):
    qs = (
        ShipmentRequest.objects.filter(requester=request.user)
        .select_related("duplicated_from")
        .prefetch_related(
            "lines",
            "approval_rounds__eligible_approvers",
            "approval_rounds__decided_by",
            decision_events_prefetch(),
        )
    )
    params = request.query_params
    if params.get("scope", "mine") != "mine":
        raise ValidationError({"scope": ["Only scope=mine is available."]})
    chip = params.get("filter")
    if chip:
        if chip not in FILTERS:
            raise ValidationError({"filter": [f"Use one of: {', '.join(FILTERS)}."]})
        if FILTERS[chip]:
            qs = qs.filter(status__in=FILTERS[chip])
    if statuses := [s for s in params.get("status", "").split(",") if s]:
        bad = [s for s in statuses if s not in Status.values]
        if bad:
            raise ValidationError({"status": [f"Unknown status: {', '.join(bad)}."]})
        qs = qs.filter(status__in=statuses)
    if q := params.get("q", "").strip():
        needle = q.lower()
        labels = [
            v
            for v, label in Status.choices
            if needle in label.lower() or needle in v.lower() or needle in messages.STATUS_IT[v].lower()
        ]
        qs = qs.filter(
            Q(reference__icontains=q)
            | Q(consignee_company__icontains=q)
            | Q(recipient_code__icontains=q)
            | Q(recipient_branch_name__icontains=q)
            | Q(cost_centre_code__icontains=q)
            | Q(lines__pvari_code__icontains=q)
            | Q(lines__description__icontains=q)
            | Q(status__in=labels)
        ).distinct()
    sort = params.get("sort", "-created")
    if sort not in SORTS:
        raise ValidationError({"sort": [f"Use one of: {', '.join(SORTS)}."]})
    return qs.order_by(SORTS[sort], "-id")


class RequestListCreateView(ListCreateAPIView):
    authentication_classes = [Session401Authentication]
    serializer_class = RequestListSerializer
    parser_classes = [JSONParser]

    def get_permissions(self):
        action = "create" if self.request.method == "POST" else "view"
        return [HasPermission.require("requests", action)()]

    def get_queryset(self):
        return _filtered(self.request)

    @extend_schema(
        operation_id="requests_list",
        parameters=[
            OpenApiParameter("scope", str, description="mine (the only value today)"),
            OpenApiParameter(
                "filter", str, enum=list(FILTERS), description="All, Open, Needs attention, Drafts, Closed"
            ),
            OpenApiParameter("status", str, description="Comma-separated statuses"),
            OpenApiParameter(
                "q",
                str,
                description="Search reference, recipient, branch, PVARI code, description, cost centre, status",
            ),
            OpenApiParameter("sort", str, enum=list(SORTS)),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="requests_create",
        request=RequestWriteSerializer,
        responses={201: RequestDetailSerializer},
        description="Create the draft on the first save. Send `step: 1` in the body for Continue (validates step 1 "
        "first and creates nothing on errors); without it this is Save draft.",
    )
    def post(self, request, *args, **kwargs):
        data = request.data
        step = data.get("step")
        if step not in (None, 1):
            raise ValidationError({"step": ["The first save is step 1 or a plain draft."]})
        req = drafts.create_draft(request.user, _parse(data, drop=("step", "version")), step=step)
        return Response(_detail(request, req), status=http.HTTP_201_CREATED)


class RequestExportView(APIView):
    """CSV of the currently filtered list: same rows and columns as the My requests table (DSF-04.02)."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "view")]

    @extend_schema(operation_id="requests_export", responses={(200, "text/csv"): OpenApiResponse()})
    def get(self, request):
        rows = RequestListSerializer(_filtered(request), many=True).data
        lang = "it" if messages.request_language(request) == "it" else "en"
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="my-requests.csv"'
        resp.write("﻿")  # so Excel reads UTF-8
        w = csv.writer(resp)
        w.writerow(CSV_HEADERS[lang])
        for r in rows:
            appr = r["approval"]
            approval = ""
            if appr:
                approval = CSV_APPROVAL[lang].get(appr["state"], appr["state"])
                if appr["names"]:
                    approval += " · " + ", ".join(appr["names"])
            w.writerow(
                [
                    _safe(c)
                    for c in [
                        r["reference"],
                        r["created_at"][:10],
                        r["consignee_company"] or "",
                        r["recipient_branch_name"] or r["recipient_code"] or "",
                        _Label(CSV_SCOPE[lang].get(r["destination"], r["destination"] or "")),
                        r["ship_day_requested"] or "",
                        r["line_count"],
                        " ".join(r["pvari_codes"]),
                        r["total_weight_kg"],
                        _Label(
                            CSV_TEMPERATURE[lang].get(
                                r["overall_temperature"], r["overall_temperature"] or ""
                            )
                        ),
                        r["cost_centre_code"] or "",
                        approval,
                        CSV_STATUS[lang].get(r["status"], r["status"]),
                    ]
                ]
            )
        return resp


class _Label(str):
    """A fixed label from our own lists (e.g. "+2 +8 °C"): not user-typed, so left as it is."""


def _safe(cell):
    """Neutralise spreadsheet formulas in user-typed text."""
    text = str(cell)
    if isinstance(cell, _Label):
        return text
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


# ---------------------------------------------------------------- one request
class RequestDetailView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "view")]

    @extend_schema(operation_id="requests_retrieve", responses=RequestDetailSerializer)
    def get(self, request, ref):
        return Response(_detail(request, _get_visible(request.user, ref)))


class StepSaveView(APIView):
    """Continue: validate step n only, then save it."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "edit")]
    parser_classes = [JSONParser]

    @extend_schema(
        operation_id="requests_save_step",
        request=RequestWriteSerializer,
        responses={200: RequestDetailSerializer, 400: OpenApiResponse(description="{step, errors}")},
    )
    def patch(self, request, ref, n):
        if n not in (1, 2, 3, 4):
            raise ValidationError({"step": ["Steps are 1 to 4."]})
        req = _get_visible(request.user, ref)
        data = _parse(request.data, drop=("version",))
        saved = drafts.save(req.pk, request.user, data, request.data.get("version"), step=n)
        return Response(_detail(request, saved))


class DraftSaveView(APIView):
    """Save draft: save whatever is typed, no validation."""

    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "edit")]
    parser_classes = [JSONParser]

    @extend_schema(
        operation_id="requests_save_draft", request=RequestWriteSerializer, responses=RequestDetailSerializer
    )
    def patch(self, request, ref):
        req = _get_visible(request.user, ref)
        data = _parse(request.data, drop=("version",))
        saved = drafts.save(req.pk, request.user, data, request.data.get("version"))
        return Response(_detail(request, saved))


class DiscardView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "cancel")]

    @extend_schema(operation_id="requests_discard", request=None, responses=RequestDetailSerializer)
    def post(self, request, ref):
        return Response(_detail(request, drafts.discard(_get_visible(request.user, ref).pk, request.user)))


class SubmitView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "create")]

    @extend_schema(
        operation_id="requests_submit",
        request=SubmitBodySerializer,
        responses={200: RequestDetailSerializer, 400: OpenApiResponse(description="{step, errors}")},
    )
    def post(self, request, ref):
        body = SubmitBodySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        req = workflow.submit(
            _get_visible(request.user, ref).pk, request.user, body.validated_data["declaration"]
        )
        return Response(_detail(request, req))


class DuplicateView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "create")]

    @extend_schema(operation_id="requests_duplicate", request=None, responses={201: RequestDetailSerializer})
    def post(self, request, ref):
        return Response(
            _detail(request, drafts.duplicate(_get_visible(request.user, ref).pk, request.user)),
            status=http.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------- attachments
class AttachmentListView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "edit")]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        operation_id="requests_attachments_create",
        request={"multipart/form-data": AttachmentUploadSerializer},
        responses={201: AttachmentSerializer},
    )
    def post(self, request, ref):
        body = AttachmentUploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        att = attachments.add_attachment(
            _get_visible(request.user, ref).pk,
            request.user,
            body.validated_data["kind"],
            body.validated_data["file"],
        )
        return Response(AttachmentSerializer(att).data, status=http.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    authentication_classes = [Session401Authentication]
    permission_classes = [HasPermission.require("requests", "view")]

    @extend_schema(operation_id="requests_attachments_download", responses={(200, "*/*"): OpenApiResponse()})
    def get(self, request, ref, att_id):
        req = _get_visible(request.user, ref)
        att = get_object_or_404(req.attachments, pk=att_id)
        resp = FileResponse(
            att.file.open("rb"),
            as_attachment=True,
            filename=att.original_name,
            content_type=att.content_type or "application/octet-stream",
        )
        resp["X-Content-Type-Options"] = "nosniff"
        return resp

    @extend_schema(operation_id="requests_attachments_delete", responses={204: None})
    def delete(self, request, ref, att_id):
        attachments.delete_attachment(_get_visible(request.user, ref).pk, request.user, att_id)
        return Response(status=http.HTTP_204_NO_CONTENT)
