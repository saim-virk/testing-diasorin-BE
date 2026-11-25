"""The 16 email templates (prototype TEMPLATES). Frozen copy used by the data migration.

Bodies are plain Django templates. Context available (filled in by the sender service, day 5):
`request` (ShipmentRequest), `actor_name`, `url`, `code` (otp), `carrier`/`awb`, `hours`, `note`.
"""

_FOOTER = "\n\n— Diasorin Digital Shipment Form"

# key, name, recipients, trigger, subject, body
TEMPLATES = [
    (
        "otp",
        "One-time sign-in code",
        "Person signing in",
        "A user on an allowed address requests access.",
        "Your Diasorin sign-in code: {{ code }}",
        "Your one-time sign-in code is {{ code }}.\nIt expires in {{ minutes }} minutes and can be used once.",
    ),
    (
        "submitted",
        "Submission confirmation",
        "Requester",
        "A requester submits a shipment request.",
        "{{ request.reference }} submitted — {{ next_step }}",
        "Your shipment request {{ request.reference }} has been submitted.\n{{ next_step }}",
    ),
    (
        "approvalRequired",
        "Approval required",
        "Approvers of the cost centre",
        "A submitted request is routed to the approver(s) mapped to its CoC code.",
        "Action needed: approve {{ request.reference }} for {{ request.cost_centre_code }}",
        "{{ request.applicant_name }} asks for approval of {{ request.reference }} (cost centre {{ request.cost_centre_code }}).\nOpen it here: {{ url }}",
    ),
    (
        "approved",
        "Request approved",
        "Requester",
        "A cost centre approver approves the request.",
        "{{ request.reference }} approved — now with customer management",
        "{{ actor_name }} approved {{ request.reference }}. Customer management will verify it next.",
    ),
    (
        "rejected",
        "Request rejected",
        "Requester",
        "A cost centre approver rejects the request. A reason is mandatory.",
        "{{ request.reference }} not approved — please review",
        "{{ actor_name }} did not approve {{ request.reference }}.\nReason: {{ note }}\nYou can revise and resubmit it: {{ url }}",
    ),
    (
        "oeNew",
        "New request in your queue",
        "Customer management team",
        "A request clears approval, or approval was not required.",
        "{{ request.reference }} ready to process — {{ approval_summary }}",
        "{{ request.reference }} from {{ request.applicant_name }} is ready for verification.\nOpen it here: {{ url }}",
    ),
    (
        "returned",
        "Returned for correction",
        "Requester",
        "Customer management finds a data problem and returns the request.",
        "{{ request.reference }} returned for correction",
        "{{ actor_name }} returned {{ request.reference }} for correction.\nNote: {{ note }}\nRevise and resubmit: {{ url }}",
    ),
    (
        "question",
        "Question on your request",
        "Requester",
        "An approver or customer management posts a question on the request.",
        "Question on {{ request.reference }} from {{ actor_name }}",
        "{{ actor_name }} asked:\n{{ note }}\nReply on the request: {{ url }}",
    ),
    (
        "resubmitted",
        "Corrected and resubmitted",
        "Whoever sent it back",
        "A requester resubmits a rejected or returned request.",
        "{{ request.reference }} resubmitted by {{ request.applicant_name }}",
        "{{ request.applicant_name }} corrected and resubmitted {{ request.reference }}.\nOpen it here: {{ url }}",
    ),
    (
        "verified",
        "Data verified",
        "Requester",
        "Customer management marks the request data as verified.",
        "{{ request.reference }} verified — being prepared",
        "The data of {{ request.reference }} has been verified. The shipment is being prepared.",
    ),
    (
        "packed",
        "Picked and packed",
        "Requester",
        "Customer management marks the shipment as picked and packed.",
        "{{ request.reference }} packed — ready for collection",
        "{{ request.reference }} has been picked and packed and is ready for collection.",
    ),
    (
        "shipped",
        "Handed to carrier — tracking",
        "Requester",
        "Customer management records carrier and AWB and moves the request to in transit.",
        "{{ request.reference }} is on its way — {{ request.carrier_name }} {{ request.awb }}",
        "{{ request.reference }} was handed to {{ request.carrier_name }}.\nTracking (AWB): {{ request.awb }}",
    ),
    (
        "delivered",
        "Delivered — request closed",
        "Requester",
        "Customer management records delivery and closes the request.",
        "{{ request.reference }} delivered — request closed",
        "{{ request.reference }} has been delivered. The request is closed.",
    ),
    (
        "cancelled",
        "Request cancelled",
        "Customer management",
        "A requester cancels a request that had already been routed onward.",
        "{{ request.reference }} cancelled by {{ actor_name }}",
        "{{ request.reference }} was cancelled by {{ actor_name }}. No further action is needed.",
    ),
    (
        "reminder",
        "Approval reminder",
        "Approvers who have not decided",
        "A request has been pending approval longer than the reminder interval.",
        "Reminder: {{ request.reference }} has been waiting {{ hours }} hours",
        "{{ request.reference }} is still waiting for your approval ({{ hours }} hours).\nOpen it here: {{ url }}",
    ),
    (
        "escalation",
        "Approval escalation",
        "Administrators",
        "A request has been pending approval longer than the escalation threshold.",
        "Escalation: {{ request.reference }} pending for {{ hours }} hours",
        "{{ request.reference }} has been pending approval for {{ hours }} hours.\nAs administrator you can now decide it: {{ url }}",
    ),
]

TEMPLATES = [(k, n, r, t, s, b + _FOOTER) for (k, n, r, t, s, b) in TEMPLATES]
