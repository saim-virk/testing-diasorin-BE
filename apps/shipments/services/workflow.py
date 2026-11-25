"""All state changes of a request go through here (events and emails are written in the same transaction)."""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.enums import AppRole
from apps.accounts.models import User
from apps.accounts.permissions import has_permission
from apps.accounts.services.roles import primary_role
from apps.masterdata.models import CostCentreApprover
from apps.notifications.models import EmailOutbox
from apps.notifications.phrases import phrase
from apps.notifications.services import dispatcher
from apps.notifications.services.render import language_for, render_email
from apps.platform_config.models import SiteConfig

from ..enums import EventKind, RoundState, SkipReason, Status
from ..models import ApprovalRound, ShipmentRequest
from . import derive, drafts, routing
from .errors import TransitionError
from .validation import validate_all

logger = logging.getLogger(__name__)


def request_url(req: ShipmentRequest) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/requests/{req.reference}"


def _queue(req, key, to, context, stamp) -> EmailOutbox | None:
    """Queue one email in the recipient's language; None when the template does not exist."""
    rendered = render_email(key, {"request": req, "url": request_url(req), **context}, to)
    if rendered is None:
        return None
    subject, body = rendered
    row, created = EmailOutbox.objects.get_or_create(
        dedupe_key=f"{key}:{req.reference}:{to}:{stamp}",
        defaults={
            "template_key": key,
            "request": req,
            "to_addresses": [to],
            "subject": subject,
            "body": body,
        },
    )
    return row if created else None


def _flush(rows) -> None:
    """Hand the rows queued by one action to the background sender once the transaction commits."""
    dispatcher.after_commit([r.pk for r in rows if r is not None])


def _next_step_key(result: routing.RoutingResult | None) -> str:
    if result is None or not result.required or result.auto_approved:
        return "customer_management_verifies"
    if result.held:
        return "held"
    return "escalated_to_admins" if result.escalated_to_admins else "approvers_notified"


def _summary_key(req: ShipmentRequest, result: routing.RoutingResult | None) -> str:
    """For `oeNew`: a fresh routing says "no approval needed"; a resubmit that skipped routing depends on
    the last round ("already given" only when it was APPROVED)."""
    if result is not None and result.auto_approved:
        return "self_approved"
    if result is None:
        last = req.approval_rounds.order_by("-round_number").first()
        if last is not None and last.state == RoundState.APPROVED:
            return "approval_already_given"
    return "no_approval_needed"


def _notify(
    req: ShipmentRequest,
    result: routing.RoutingResult | None,
    resubmitted_to: str | None = None,
) -> None:
    """`resubmitted_to`: the person who sent the request back (they get "Corrected and resubmitted")."""
    stamp = (req.last_submitted_at or timezone.now()).isoformat()
    lang = language_for(req.applicant_email)
    rows = [
        _queue(
            req,
            "submitted",
            req.applicant_email,
            {"next_step": phrase(_next_step_key(result), lang)},
            stamp,
        )
    ]

    if result is not None and result.required and not result.auto_approved:
        for approver in result.approvers:  # none when the round is HELD
            rows.append(_queue(req, "approvalRequired", approver.email, {}, stamp))
        if result.held:
            admins = routing.administrators(exclude=req.requester)
            if not admins:
                logger.warning("%s is on hold and there is no active administrator to tell", req.reference)
            for admin in admins:
                rows.append(_queue(req, "approvalHeld", admin.email, {}, stamp))
    else:
        mailbox = SiteConfig.load().customer_mgmt_mailbox
        summary = phrase(_summary_key(req, result), language_for(mailbox))
        rows.append(_queue(req, "oeNew", mailbox, {"approval_summary": summary}, stamp))
    if resubmitted_to:
        rows.append(_queue(req, "resubmitted", resubmitted_to, {}, stamp))
    _flush(rows)


AUTO_APPROVED_NOTE = "Approved automatically: the requester is an approver of this cost centre"


@transaction.atomic
def submit(req_id: int, user, declaration: bool) -> ShipmentRequest:
    """Validate every step, snapshot, route, and move the request on. Raises StepValidationError."""
    req = ShipmentRequest.objects.select_for_update().get(pk=req_id)
    drafts.require_owner(user, req)
    drafts.require_editable(req)

    drafts.resolve_refs(req)  # master data may have changed since the steps were saved
    drafts.refresh_line_snapshots(req)  # UN number + hazard snapshot of the PVARI rows as they are now
    drafts.update_derived(req, lock=False)
    validate_all(req, declaration=declaration)

    now = timezone.now()
    old = req.status
    resubmitted = old in (Status.REJECTED, Status.RETURNED)
    sent_back_by = _sent_back_by(req, old) if resubmitted else None

    result = None
    if routing.resubmit_skip(req):
        new_status = (
            Status.TO_VERIFY
        )  # previous round was approved / not required and the centre is unchanged
    else:
        result = routing.route(req.requester, req.cost_centre_ref, request=req)
        new_status = result.status

    if req.destination != "USA":
        for f in (
            "us_usda_guideline",
            "us_usda_guideline_number",
            "us_usda_permit",
            "us_attach_000614",
            "us_cdc_permit",
            "us_importer_certification_statement",
        ):
            setattr(req, f, None)
    req.declaration_accepted_at = now
    if req.submitted_at is None:
        req.submitted_at = now
    req.last_submitted_at = now
    req.status = new_status
    req.save()
    kept = resubmitted and result is None
    note = ""
    if resubmitted:
        note = "Corrected and resubmitted — approval retained" if kept else "Corrected and resubmitted"
    drafts.record_event(
        req,
        user,
        "Resubmitted" if resubmitted else "Submitted",
        from_status=old,
        to_status=new_status,
        in_conversation=True,
        note=note,
    )
    if result is not None and result.auto_approved:
        drafts.record_event(
            req,
            None,
            "Approved automatically",
            from_status=new_status,
            to_status=new_status,
            in_conversation=True,
            note=AUTO_APPROVED_NOTE,
        )
    _notify(req, result, sent_back_by.email if sent_back_by else None)
    req.refresh_from_db()
    return req


def _skipped_on_resubmit(req: ShipmentRequest, last) -> bool:
    """The last submit reused an older round instead of routing again (that round predates the submit)."""
    return (
        last is not None
        and req.last_submitted_at is not None
        and req.submitted_at != req.last_submitted_at
        and last.started_at < req.last_submitted_at
    )


def next_steps(req: ShipmentRequest) -> dict:
    """The routing part of the confirmation page ("What happens next"), built from what submit really did."""
    infectious = derive.derived_hazard(list(req.lines.all())) == "INFECTIOUS"
    cfg = SiteConfig.load()
    last = req.approval_rounds.order_by("-round_number").first()
    auto = bool(last and last.skip_reason == SkipReason.SELF_AUTO_APPROVED)
    note = last.skip_reason if last and (not last.required or auto) else None
    required = bool(last and last.required) and not auto
    if req.status == Status.TO_VERIFY and _skipped_on_resubmit(req, last):
        required = False
        note = "APPROVAL_ALREADY_GIVEN" if last.state == RoundState.APPROVED else "NOT_NEEDED"
    return {
        "approval_required": required,
        "approvers": (
            [u.get_full_name() or u.email for u in last.eligible_approvers.all()] if required and last else []
        ),
        "approval_note": note,
        "reminder_hours": cfg.reminder_hours,
        "escalate_hours": cfg.escalate_hours,
        "specialised_courier": infectious,
    }


# ------------------------------------------------------------------ decisions and other transitions
CANCEL_BY_OWNER = (Status.DRAFT, Status.PENDING_APPROVAL, Status.TO_VERIFY, Status.REJECTED, Status.RETURNED)
CLOSED = (Status.DELIVERED, Status.CANCELLED)
WORKED_ON_BY_CM = (Status.TO_VERIFY, Status.VERIFIED, Status.PACKED, Status.IN_TRANSIT)
POST_KINDS = {"comment": EventKind.COMMENT, "question": EventKind.QUESTION, "note": EventKind.NOTE}
MAX_TEXT = 2000


def _name(user) -> str:
    return user.get_full_name() or user.email


def _sent_back_by(req: ShipmentRequest, status: str):
    """Whoever moved the request into `status` (the approver who rejected it, customer management who returned it)."""
    event = req.events.filter(to_status=status).select_related("actor").order_by("-at", "-id").first()
    return event.actor if event else None


def _open_round(req: ShipmentRequest) -> ApprovalRound | None:
    return req.approval_rounds.filter(state__in=[RoundState.PENDING, RoundState.HELD]).first()


def _lock(req_id: int) -> ShipmentRequest:
    return ShipmentRequest.objects.select_for_update().get(pk=req_id)


# -- guards: the services raise, `available_actions` asks the same functions
def check_decide(req: ShipmentRequest, user) -> ApprovalRound:
    """Approve / reject: the request waits for approval and the user is eligible on the open round."""
    if req.requester_id == user.pk:
        raise PermissionDenied("You cannot decide on your own request.")
    if req.status != Status.PENDING_APPROVAL:
        raise TransitionError(
            f"A request in status {Status(req.status).label} is not waiting for approval.", "not_pending"
        )
    rnd = _open_round(req)
    if rnd is None or rnd.state == RoundState.HELD:
        raise TransitionError(
            "No approver is assigned yet: an administrator has to assign one first.", "round_held"
        )
    if not rnd.eligible_approvers.filter(pk=user.pk).exists():
        raise PermissionDenied("You are not an approver for this request.")
    return rnd


def check_cancel(req: ShipmentRequest, user) -> None:
    owner = req.requester_id == user.pk
    admin = has_permission(user, "requests", "manage")
    if not (owner or admin):
        raise PermissionDenied("Only the person who made the request or an administrator can cancel it.")
    if owner and req.status in CANCEL_BY_OWNER:
        return
    if admin and req.status not in CLOSED:
        return
    raise TransitionError(
        f"A request in status {Status(req.status).label} cannot be cancelled by you.", "cannot_cancel"
    )


def check_return(req: ShipmentRequest, user) -> None:
    if not has_permission(user, "workbench", "decide"):
        raise PermissionDenied("Only customer management can return a request for correction.")
    if req.status != Status.TO_VERIFY:
        raise TransitionError(
            "Only a request that is waiting to be verified can be returned.", "not_to_verify"
        )


def _check_admin_on_open_round(req: ShipmentRequest, user) -> ApprovalRound:
    if not has_permission(user, "requests", "manage"):
        raise PermissionDenied("Only an administrator can do this.")
    rnd = _open_round(req) if req.status == Status.PENDING_APPROVAL else None
    if rnd is None:
        raise TransitionError("The request is not waiting for approval.", "not_pending")
    return rnd


def check_reassign(req: ShipmentRequest, user) -> ApprovalRound:
    return _check_admin_on_open_round(req, user)


def check_skip(req: ShipmentRequest, user) -> ApprovalRound:
    return _check_admin_on_open_round(req, user)


def check_post(req: ShipmentRequest, user, kind: str) -> None:
    if kind not in POST_KINDS:
        raise ValidationError({"kind": ["Use comment, question or note."]})
    if req.status == Status.DRAFT:
        raise TransitionError("A draft has no conversation yet.", "not_submitted")
    if kind != "comment" and req.requester_id == user.pk:
        raise PermissionDenied("Questions and internal notes are for the people handling the request.")


def available_actions(req: ShipmentRequest, user) -> list[str]:
    """What this user may do now, from the same guards the services use (the UI never re-derives it)."""
    owner = req.requester_id == user.pk
    checks = {
        "approve": lambda: check_decide(req, user),
        "reject": lambda: check_decide(req, user),
        "return": lambda: check_return(req, user),
        "cancel": lambda: check_cancel(req, user),
        "reassign_approver": lambda: check_reassign(req, user),
        "skip_approval": lambda: check_skip(req, user),
        "comment": lambda: check_post(req, user, "comment"),
        "question": lambda: check_post(req, user, "question"),
        "note": lambda: check_post(req, user, "note"),
    }
    actions = []
    for name, check in checks.items():
        try:
            check()
        except (PermissionDenied, TransitionError, ValidationError):
            continue
        actions.append(name)
    if owner and req.status == Status.DRAFT:
        actions.append("edit")
    if owner and req.status in (Status.REJECTED, Status.RETURNED):
        actions.append("revise")
    if owner and req.status != Status.DRAFT:
        actions.append("duplicate")
    return actions


def _decider_role(req: ShipmentRequest, user) -> str:
    """Approver, or administrator when an admin decides without being one of the cost centre's approvers."""
    is_centre_approver = (
        req.cost_centre_ref_id
        and CostCentreApprover.objects.filter(cost_centre_id=req.cost_centre_ref_id, user=user).exists()
    )
    if has_permission(user, "requests", "manage") and not is_centre_approver:
        return AppRole.ADMIN.value
    return AppRole.APPROVER.value


def _event(req, user, action, old, *, role, note="", in_conversation=True, kind=EventKind.EVENT):
    return drafts.record_event(
        req,
        user,
        action,
        from_status=old,
        to_status=req.status,
        note=note,
        in_conversation=in_conversation,
        kind=kind,
        role=role,
    )


def _customer_management_mail(req, event, rows, summary_key: str) -> None:
    mailbox = SiteConfig.load().customer_mgmt_mailbox
    summary = phrase(summary_key, language_for(mailbox))
    rows.append(_queue(req, "oeNew", mailbox, {"approval_summary": summary}, event.pk))


@transaction.atomic
def approve(req_id: int, user, comment: str = "") -> ShipmentRequest:
    req = _lock(req_id)
    rnd = check_decide(req, user)
    old, comment = req.status, (comment or "").strip()
    rnd.state, rnd.decided_by, rnd.decided_at = RoundState.APPROVED, user, timezone.now()
    rnd.save(update_fields=["state", "decided_by", "decided_at"])
    req.status = Status.TO_VERIFY
    req.save(update_fields=["status", "updated_at"])
    event = _event(req, user, "Approved", old, role=_decider_role(req, user), note=comment)
    ctx = {"actor_name": _name(user), "note": comment}
    rows = [_queue(req, "approved", req.applicant_email, ctx, event.pk)]
    _customer_management_mail(req, event, rows, "approved_by_approver")
    _flush(rows)
    return req


@transaction.atomic
def reject(req_id: int, user, comment: str = "") -> ShipmentRequest:
    req = _lock(req_id)
    rnd = check_decide(req, user)
    comment = (comment or "").strip()
    if not comment and SiteConfig.load().reject_comment_required:
        raise ValidationError({"comment": ["A reason is required when rejecting a request."]})
    old = req.status
    rnd.state, rnd.decided_by, rnd.decided_at = RoundState.REJECTED, user, timezone.now()
    rnd.save(update_fields=["state", "decided_by", "decided_at"])
    req.status = Status.REJECTED
    req.save(update_fields=["status", "updated_at"])
    event = _event(req, user, "Rejected", old, role=_decider_role(req, user), note=comment)
    ctx = {"actor_name": _name(user), "note": comment}
    _flush([_queue(req, "rejected", req.applicant_email, ctx, event.pk)])
    return req


@transaction.atomic
def return_for_correction(req_id: int, user, note: str) -> ShipmentRequest:
    req = _lock(req_id)
    check_return(req, user)
    note = (note or "").strip()
    if not note:
        raise ValidationError({"note": ["A note is required when returning a request."]})
    old = req.status
    req.status = Status.RETURNED
    if req.cm_owner_id is None:  # the first customer-management action claims the request
        req.cm_owner = user
    req.save(update_fields=["status", "cm_owner", "updated_at"])
    event = _event(req, user, "Returned", old, role=AppRole.CUSTOMER_MANAGEMENT.value, note=note)
    ctx = {"actor_name": _name(user), "note": note}
    _flush([_queue(req, "returned", req.applicant_email, ctx, event.pk)])
    return req


@transaction.atomic
def cancel(req_id: int, user, reason: str = "") -> ShipmentRequest:
    req = _lock(req_id)
    check_cancel(req, user)
    old, reason = req.status, (reason or "").strip()
    open_round = _open_round(req)
    recipients: dict[str, None] = {}  # those who were working on it (ordered, no duplicates)
    if open_round is not None and old == Status.PENDING_APPROVAL:
        recipients.update({u.email: None for u in open_round.eligible_approvers.all()})
    if old in WORKED_ON_BY_CM:
        owner = req.cm_owner
        recipients[owner.email if owner else SiteConfig.load().customer_mgmt_mailbox] = None
    if req.requester_id != user.pk:
        recipients[req.applicant_email] = None
    recipients.pop(user.email, None)
    req.approval_rounds.filter(state__in=[RoundState.PENDING, RoundState.HELD]).update(
        state=RoundState.SUPERSEDED
    )
    req.status = Status.CANCELLED
    req.save(update_fields=["status", "updated_at"])
    role = AppRole.REQUESTER.value if req.requester_id == user.pk else AppRole.ADMIN.value
    event = _event(req, user, "Cancelled", old, role=role, note=reason)
    ctx = {"actor_name": _name(user), "note": reason}
    _flush([_queue(req, "cancelled", to, ctx, event.pk) for to in recipients])
    return req


@transaction.atomic
def reassign_approver(req_id: int, user, email: str, reason: str = "") -> ShipmentRequest:
    req = _lock(req_id)
    rnd = check_reassign(req, user)
    target = User.objects.filter(email__iexact=(email or "").strip(), is_active=True).first()
    if target is None:
        raise ValidationError({"email": ["There is no active user with this email address."]})
    if target.pk == req.requester_id:
        raise ValidationError({"email": ["The requester cannot approve their own request."]})
    rnd.eligible_approvers.set([target])
    rnd.state, rnd.escalated_to_admins = RoundState.PENDING, False
    rnd.save(update_fields=["state", "escalated_to_admins"])
    reason = (reason or "").strip()
    note = f"Approver set to {target.email}" + (f": {reason}" if reason else "")
    event = _event(
        req,
        user,
        "Approver reassigned",
        req.status,
        role=AppRole.ADMIN.value,
        note=note,
        in_conversation=False,
    )
    _flush([_queue(req, "approvalRequired", target.email, {}, event.pk)])
    return req


@transaction.atomic
def skip_approval(req_id: int, user, reason: str = "") -> ShipmentRequest:
    req = _lock(req_id)
    rnd = check_skip(req, user)
    old, reason = req.status, (reason or "").strip()
    rnd.state, rnd.skip_reason = RoundState.NOT_REQUIRED, SkipReason.ADMIN_SKIP
    rnd.decided_by, rnd.decided_at = user, timezone.now()
    rnd.save(update_fields=["state", "skip_reason", "decided_by", "decided_at"])
    req.status = Status.TO_VERIFY
    req.save(update_fields=["status", "updated_at"])
    event = _event(
        req, user, "Approval skipped", old, role=AppRole.ADMIN.value, note=reason, in_conversation=False
    )
    rows = []
    _customer_management_mail(req, event, rows, "approval_skipped_by_admin")
    _flush(rows)
    return req


@transaction.atomic
def post(req_id: int, user, kind: str, text: str):
    """A comment, a question (queues the `question` email to the requester) or an internal note."""
    req = _lock(req_id)
    check_post(req, user, kind)
    text = (text or "").strip()
    if not text:
        raise ValidationError({"text": ["Write something first."]})
    if len(text) > MAX_TEXT:
        raise ValidationError({"text": [f"Keep it under {MAX_TEXT} characters."]})
    role = AppRole.REQUESTER.value if req.requester_id == user.pk else primary_role(user)
    # a post is not a status change: no from/to
    event = drafts.record_event(
        req,
        user,
        kind.capitalize(),
        note=text,
        in_conversation=True,
        kind=POST_KINDS[kind],
        role=role,
    )
    if kind == "question":
        ctx = {"actor_name": _name(user), "note": text}
        _flush([_queue(req, "question", req.applicant_email, ctx, event.pk)])
    return event
