"""Italian versions of the 16 email templates (machine-assisted: Diasorin to review, see
docs/progress/data-model-v2.md). Same Django-template variables as the English ones.
Frozen copy used by the data migration.
"""

_FOOTER = "\n\n— Diasorin Modulo di Spedizione Digitale"

# key -> (subject_it, body_it)
TEMPLATES_IT = {
    "otp": (
        "Il tuo codice di accesso Diasorin",
        "Il tuo codice di accesso monouso è {{ code }}.\nScade tra {{ minutes }} minuti e può essere usato una sola volta.",
    ),
    "submitted": (
        "{{ request.reference }} inviata — {{ next_step }}",
        "La tua richiesta di spedizione {{ request.reference }} è stata inviata.\n{{ next_step }}",
    ),
    "approvalRequired": (
        "Azione richiesta: approva {{ request.reference }} per {{ request.cost_centre_code }}",
        "{{ request.applicant_name }} chiede l'approvazione di {{ request.reference }} (centro di costo {{ request.cost_centre_code }}).\nAprila qui: {{ url }}",
    ),
    "approved": (
        "{{ request.reference }} approvata — ora al customer management",
        "{{ actor_name }} ha approvato {{ request.reference }}. Il customer management la verificherà ora.",
    ),
    "rejected": (
        "{{ request.reference }} non approvata — da rivedere",
        "{{ actor_name }} non ha approvato {{ request.reference }}.\nMotivo: {{ note }}\nPuoi correggerla e reinviarla: {{ url }}",
    ),
    "oeNew": (
        "{{ request.reference }} pronta da elaborare — {{ approval_summary }}",
        "{{ request.reference }} di {{ request.applicant_name }} è pronta per la verifica.\nAprila qui: {{ url }}",
    ),
    "returned": (
        "{{ request.reference }} restituita per correzione",
        "{{ actor_name }} ha restituito {{ request.reference }} per correzione.\nNota: {{ note }}\nCorreggi e reinvia: {{ url }}",
    ),
    "question": (
        "Domanda su {{ request.reference }} da {{ actor_name }}",
        "{{ actor_name }} ha chiesto:\n{{ note }}\nRispondi sulla richiesta: {{ url }}",
    ),
    "resubmitted": (
        "{{ request.reference }} reinviata da {{ request.applicant_name }}",
        "{{ request.applicant_name }} ha corretto e reinviato {{ request.reference }}.\nAprila qui: {{ url }}",
    ),
    "verified": (
        "{{ request.reference }} verificata — in preparazione",
        "I dati di {{ request.reference }} sono stati verificati. La spedizione è in preparazione.",
    ),
    "packed": (
        "{{ request.reference }} imballata — pronta per il ritiro",
        "{{ request.reference }} è stata prelevata e imballata ed è pronta per il ritiro.",
    ),
    "shipped": (
        "{{ request.reference }} è in viaggio — {{ request.carrier_name }} {{ request.awb }}",
        "{{ request.reference }} è stata consegnata a {{ request.carrier_name }}.\nTracking (AWB): {{ request.awb }}",
    ),
    "delivered": (
        "{{ request.reference }} consegnata — richiesta chiusa",
        "{{ request.reference }} è stata consegnata. La richiesta è chiusa.",
    ),
    "cancelled": (
        "{{ request.reference }} annullata da {{ actor_name }}",
        "{{ request.reference }} è stata annullata da {{ actor_name }}. Non sono necessarie altre azioni.",
    ),
    "reminder": (
        "Sollecito: {{ request.reference }} è in attesa da {{ hours }} ore",
        "{{ request.reference }} è ancora in attesa della tua approvazione ({{ hours }} ore).\nAprila qui: {{ url }}",
    ),
    "escalation": (
        "Escalation: {{ request.reference }} in sospeso da {{ hours }} ore",
        "{{ request.reference }} è in attesa di approvazione da {{ hours }} ore.\nIn qualità di amministratore puoi ora deciderla: {{ url }}",
    ),
}

TEMPLATES_IT = {k: (s, b + _FOOTER) for k, (s, b) in TEMPLATES_IT.items()}
