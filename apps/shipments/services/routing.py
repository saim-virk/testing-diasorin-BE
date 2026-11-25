"""Approval routing (REQUIREMENTS section 5).

`route()` is the single implementation: submit calls it to create the ApprovalRound, and the cost-centre
hint on the form calls it in dry-run mode, so the hint always says what submit will do (AC-03.06.3).
"""

from dataclasses import dataclass, field

from apps.accounts.enums import AppRole
from apps.accounts.models import RoleAssignment, User
from apps.platform_config.models import NoApproverFallback, SelfApprovalMode, SiteConfig

from ..enums import RoundState, SkipReason, Status
from ..models import ApprovalRound, ShipmentRequest

# `why` values (shared with the hint shown on the form)
REQUIRED = "required"
GLOBAL_OFF = "global_off"
EXEMPT = "exempt"
CENTRE_OFF = "cost_centre_off"
NO_APPROVER_ADMIN = "no_approver_admin"
NO_APPROVER_SKIP = "no_approver_skip"
NO_APPROVER_HOLD = "no_approver_hold"
SELF_AUTO_APPROVED = "self_auto_approved"

SKIP_REASON = {
    GLOBAL_OFF: SkipReason.GLOBAL_OFF,
    EXEMPT: SkipReason.REQUESTER_EXEMPT,
    CENTRE_OFF: SkipReason.CENTRE_OFF,
    NO_APPROVER_SKIP: SkipReason.NO_APPROVER_SKIP,
    SELF_AUTO_APPROVED: SkipReason.SELF_AUTO_APPROVED,
}


@dataclass
class RoutingResult:
    required: bool
    why: str
    status: str  # PENDING_APPROVAL or TO_VERIFY
    round_state: str
    skip_reason: str | None = None
    approvers: list[User] = field(default_factory=list)
    escalated_to_admins: bool = False
    round: ApprovalRound | None = None

    @property
    def auto_approved(self) -> bool:
        return self.why == SELF_AUTO_APPROVED

    @property
    def held(self) -> bool:
        return self.round_state == RoundState.HELD


def administrators(exclude: User | None = None) -> list[User]:
    """Active administrators, never `exclude` (the requester: nobody approves their own request)."""
    ids = RoleAssignment.objects.filter(role=AppRole.ADMIN.value).values_list("user_id", flat=True)
    users = User.objects.filter(pk__in=ids, is_active=True)
    if exclude is not None:
        users = users.exclude(pk=exclude.pk)
    return list(users.order_by("last_name", "first_name", "email"))


def centre_approvers(cost_centre) -> list[User]:
    return [
        a.user
        for a in cost_centre.approvers.select_related("user").order_by("user__last_name", "user__first_name")
        if a.user.is_active
    ]


def route(requester: User, cost_centre, *, request: ShipmentRequest | None = None, dry_run: bool = False):
    """Decide where a submission goes. With `dry_run` (or without a request) nothing is written."""
    cfg = SiteConfig.load()
    result = _decide(requester, cost_centre, cfg)
    if not dry_run and request is not None:
        result.round = _create_round(request, result, cost_centre)
    return result


def _decide(requester: User, cost_centre, cfg: SiteConfig) -> RoutingResult:
    def skip(why):
        return RoutingResult(False, why, Status.TO_VERIFY, RoundState.NOT_REQUIRED, SKIP_REASON[why])

    if not cfg.approval_global_enabled:
        return skip(GLOBAL_OFF)
    if requester.approval_exempt:
        return skip(EXEMPT)
    if cost_centre is None or not cost_centre.approval_required:
        return skip(CENTRE_OFF)

    def escalate(admins):
        return RoutingResult(
            True,
            NO_APPROVER_ADMIN,
            Status.PENDING_APPROVAL,
            RoundState.PENDING,
            approvers=admins,
            escalated_to_admins=True,
        )

    def auto():  # approved by the system; the round records it with decided_by = None
        return RoutingResult(
            True, SELF_AUTO_APPROVED, Status.TO_VERIFY, RoundState.APPROVED, SKIP_REASON[SELF_AUTO_APPROVED]
        )

    approvers = centre_approvers(cost_centre)
    if approvers:
        if any(u.pk == requester.pk for u in approvers):  # the requester approves for this cost centre
            if cfg.self_approval_mode == SelfApprovalMode.AUTO_APPROVE:
                return auto()
            others = [u for u in approvers if u.pk != requester.pk]
            if others:
                return RoutingResult(
                    True, REQUIRED, Status.PENDING_APPROVAL, RoundState.PENDING, approvers=others
                )
            admins = administrators(exclude=requester)
            return escalate(admins) if admins else auto()
        return RoutingResult(True, REQUIRED, Status.PENDING_APPROVAL, RoundState.PENDING, approvers=approvers)

    fallback = cfg.no_approver_fallback
    if fallback == NoApproverFallback.SKIP:
        return skip(NO_APPROVER_SKIP)
    if fallback == NoApproverFallback.ADMIN:
        admins = administrators(exclude=requester)
        return escalate(admins) if admins else auto()
    # HOLD: nobody can decide until an admin reassigns
    return RoutingResult(True, NO_APPROVER_HOLD, Status.PENDING_APPROVAL, RoundState.HELD)


def _create_round(request: ShipmentRequest, result: RoutingResult, cost_centre) -> ApprovalRound:
    # an earlier open round (cannot normally exist on a resubmit) is closed first
    request.approval_rounds.filter(state__in=[RoundState.PENDING, RoundState.HELD]).update(
        state=RoundState.SUPERSEDED
    )
    last = request.approval_rounds.order_by("-round_number").first()
    rnd = ApprovalRound.objects.create(
        request=request,
        round_number=(last.round_number + 1) if last else 1,
        required=result.required,
        skip_reason=result.skip_reason,
        cost_centre_code=cost_centre.code if cost_centre else "",
        escalated_to_admins=result.escalated_to_admins,
        state=result.round_state,
    )
    if result.auto_approved:
        rnd.decided_at = rnd.started_at
        rnd.save(update_fields=["decided_at"])
    rnd.eligible_approvers.set(result.approvers)
    return rnd


ALREADY_GIVEN = "approval_already_given"
NOT_NEEDED = "no_approval_needed"


def resubmit_skip(req: ShipmentRequest) -> str | None:
    """A Returned request goes straight back to verification when its last round was approved (or not required)
    and the cost centre is unchanged. Returns ALREADY_GIVEN / NOT_NEEDED for that case, else None.
    The single source for submit, the form hint and the confirmation page."""
    if req.status != Status.RETURNED:
        return None
    last = req.approval_rounds.order_by("-round_number").first()
    if last is None or last.cost_centre_code != (req.cost_centre_code or ""):
        return None
    if last.state == RoundState.APPROVED:
        return ALREADY_GIVEN
    if last.state == RoundState.NOT_REQUIRED:
        return NOT_NEEDED
    return None


def request_hint(req: ShipmentRequest) -> dict | None:
    """The hint for this request's saved cost centre when it differs from the cost centre's own: only the
    skipped re-approval of a Returned request. None = use the cost centre's hint."""
    why = resubmit_skip(req)
    return {"required": False, "why": why, "approvers": []} if why else None


def hint(requester: User, cost_centre) -> dict | None:
    """The routing outcome shown under the cost centre (dry run of `route`)."""
    if cost_centre is None:
        return None
    res = route(requester, cost_centre, dry_run=True)
    return {
        "required": res.required,
        "why": res.why,
        "approvers": [u.get_full_name() or u.email for u in res.approvers],
    }
