"""Sentences inserted into email templates (`next_step`, `approval_summary`), per recipient language."""

PHRASES = {
    "approvers_notified": {
        "en": "Your cost centre approver has been notified.",
        "it": "L'approvatore del tuo centro di costo è stato avvisato.",
    },
    "escalated_to_admins": {
        "en": "There is no approver for this cost centre, so an administrator has been asked to approve.",
        "it": "Non c'è un approvatore per questo centro di costo, quindi è stato chiesto a un amministratore di approvare.",
    },
    "held": {
        "en": "There is no approver for this cost centre. The request is on hold until an administrator assigns one.",
        "it": "Non c'è un approvatore per questo centro di costo. La richiesta resta in attesa finché un amministratore non ne assegna uno.",
    },
    "customer_management_verifies": {
        "en": "Customer management will verify the data.",
        "it": "L'assistenza clienti verificherà i dati.",
    },
    "approval_already_given": {"en": "approval already given", "it": "approvazione già concessa"},
    "approved_by_approver": {
        "en": "approved by the cost centre approver",
        "it": "approvata dall'approvatore del centro di costo",
    },
    "approval_skipped_by_admin": {
        "en": "approval skipped by an administrator",
        "it": "approvazione saltata da un amministratore",
    },
    "self_approved": {
        "en": "approved automatically (the requester is an approver of the cost centre): self-approved",
        "it": "approvata automaticamente (il richiedente è approvatore del centro di costo): autoapprovazione",
    },
    "no_approval_needed": {"en": "no approval needed", "it": "approvazione non necessaria"},
}


def phrase(key: str, lang: str) -> str:
    return PHRASES[key].get(lang) or PHRASES[key]["en"]
