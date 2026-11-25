"""Italian texts for the API's error messages. The backend writes English; the exception handler translates
every string of an error response when the request's language is Italian (Accept-Language, then the profile)."""

import re

from .enums import Status

IT = {
    # generic
    "Please correct the highlighted fields.": "Correggi i campi evidenziati.",
    "This field is required.": "Questo campo è obbligatorio.",
    "Send the version you read.": "Invia la versione che hai letto.",
    "This field does not belong to this step.": "Questo campo non appartiene a questo passaggio.",
    "This request was changed in another tab or window. Reload the latest version.": (
        "Questa richiesta è stata modificata in un'altra scheda o finestra. Ricarica l'ultima versione."
    ),
    "Only the person who made the request can change it.": "Solo chi ha creato la richiesta può modificarla.",
    "Only the person who made the request can duplicate it.": (
        "Solo chi ha creato la richiesta può duplicarla."
    ),
    "You cannot see this request.": "Non puoi vedere questa richiesta.",
    "Only a draft that was never submitted can be discarded.": (
        "Si può scartare solo una bozza mai inviata."
    ),
    "Only scope=mine is available.": "È disponibile solo scope=mine.",
    "The first save is step 1 or a plain draft.": "Il primo salvataggio è il passaggio 1 o una semplice bozza.",
    "Steps are 1 to 4.": "I passaggi vanno da 1 a 4.",
    "Allowed file types: PDF, PNG, JPG, DOCX, XLSX.": "Tipi di file ammessi: PDF, PNG, JPG, DOCX, XLSX.",
    "The file is larger than 20 MB.": "Il file supera i 20 MB.",
    "The file is empty.": "Il file è vuoto.",
    "The file content does not match its type.": "Il contenuto del file non corrisponde al suo tipo.",
    "Choose MSDS, COA or OTHER.": "Scegli MSDS, COA oppure OTHER.",
    "Attachment not found.": "Allegato non trovato.",
    "Authentication credentials were not provided.": "Accesso non effettuato.",
    "You do not have permission to perform this action.": "Non hai i permessi per questa azione.",
    "Not found.": "Non trovato.",
    # step 1
    "Choose where the shipment is going.": "Scegli la destinazione della spedizione.",
    "Choose a valid destination.": "Scegli una destinazione valida.",
    "Applicant is mandatory.": "Il richiedente è obbligatorio.",
    "A contact phone is mandatory.": "Il telefono di contatto è obbligatorio.",
    "Enter a valid phone number (digits, spaces, + - ( ), at least 6 digits).": (
        "Inserisci un numero di telefono valido (cifre, spazi, + - ( ), almeno 6 cifre)."
    ),
    "Choose where the shipment leaves from.": "Scegli da dove parte la spedizione.",
    "Choose a ships-from warehouse from the list.": "Scegli un magazzino di partenza dall'elenco.",
    "Requested shipping day is mandatory.": "Il giorno di spedizione richiesto è obbligatorio.",
    "The shipping day cannot be in the past.": "Il giorno di spedizione non può essere nel passato.",
    "Say whether the goods are pending a credit note.": "Indica se la merce è in attesa di nota di credito.",
    # step 2
    "Recipient code is mandatory.": "Il codice destinatario è obbligatorio.",
    "Pick a recipient code from the list.": "Scegli un codice destinatario dall'elenco.",
    "This recipient code does not belong to the selected destination.": (
        "Questo codice destinatario non appartiene alla destinazione selezionata."
    ),
    "Reason code is mandatory.": "Il codice causale è obbligatorio.",
    "This reason code is not valid for the selected destination.": (
        "Questo codice causale non è valido per la destinazione selezionata."
    ),
    "Company / institution is mandatory.": "Azienda / istituto è obbligatorio.",
    "Contact first name is mandatory.": "Il nome del referente è obbligatorio.",
    "Surname is mandatory.": "Il cognome è obbligatorio.",
    "Street and number are mandatory.": "Via e numero sono obbligatori.",
    "Postal code is mandatory.": "Il CAP è obbligatorio.",
    "City is mandatory.": "La città è obbligatoria.",
    "A recipient phone number is mandatory — the carrier needs it.": (
        "Il telefono del destinatario è obbligatorio: serve al corriere."
    ),
    "That does not look like an email address.": "Questo non sembra un indirizzo email.",
    "Country is mandatory.": "Il paese è obbligatorio.",
    "This country is not valid for the selected destination.": (
        "Questo paese non è valido per la destinazione selezionata."
    ),
    "The country is fixed to Italy for Italian destinations.": (
        "Per le destinazioni italiane il paese è fisso: Italia."
    ),
    "The country is fixed to United States for USA destinations.": (
        "Per le destinazioni USA il paese è fisso: Stati Uniti."
    ),
    "PO number is mandatory for DS Inc. shipments (SOP 15.0016).": (
        "Il numero PO è obbligatorio per le spedizioni DS Inc. (SOP 15.0016)."
    ),
    "Cost centre to be charged is mandatory.": "Il centro di costo di addebito è obbligatorio.",
    "Pick an active cost centre from the list.": "Scegli un centro di costo attivo dall'elenco.",
    # step 3
    "Pick a PVARI code from the list.": "Scegli un codice PVARI dall'elenco.",
    "Description is mandatory.": "La descrizione è obbligatoria.",
    "Quantity is mandatory.": "La quantità è obbligatoria.",
    "Choose a unit.": "Scegli un'unità di misura.",
    "Choose the transport temperature for this line.": "Scegli la temperatura di trasporto per questa riga.",
    "Enter a number greater than 0.": "Inserisci un numero maggiore di 0.",
    "Lot / batch is mandatory for PVARI lines.": "Il lotto è obbligatorio per le righe PVARI.",
    "Net weight is mandatory for PVARI lines.": "Il peso netto è obbligatorio per le righe PVARI.",
    "Standard price is mandatory for PVARI lines.": "Il prezzo standard è obbligatorio per le righe PVARI.",
    "Currency is mandatory for PVARI lines.": "La valuta è obbligatoria per le righe PVARI.",
    "Country of origin is mandatory for PVARI lines.": "Il paese di origine è obbligatorio per le righe PVARI.",
    "Net weight must be greater than zero.": "Il peso netto deve essere maggiore di zero.",
    "Standard price cannot be negative.": "Il prezzo standard non può essere negativo.",
    "Add at least one line.": "Aggiungi almeno una riga.",
    "Choose the dangerous features of the material.": "Scegli le caratteristiche di pericolosità del materiale.",
    "The lines contain infectious material, so this must be Infectious.": (
        "Le righe contengono materiale infetto: la scelta deve essere Infetto."
    ),
    "This choice does not match the PVARI codes on the lines.": (
        "Questa scelta non corrisponde ai codici PVARI delle righe."
    ),
    "Describe the other hazard (from the MSDS).": "Descrivi l'altro pericolo (dalla scheda di sicurezza).",
    "Attach the Material Safety Data Sheet (MSDS).": "Allega la scheda di sicurezza (MSDS).",
    "Select the material type.": "Seleziona il tipo di materiale.",
    "Specify the material type.": "Specifica il tipo di materiale.",
    # step 4
    "The datalogger choice is mandatory.": "La scelta del datalogger è obbligatoria.",
    "Say which dedicated transport supplier is needed.": "Indica quale fornitore di trasporto dedicato serve.",
    "Number of parcels must be at least 1.": "Il numero di colli deve essere almeno 1.",
    "Gross weight cannot be negative.": "Il peso lordo non può essere negativo.",
    "Answer Yes or No (DSI-SOP-000354).": "Rispondi Sì o No (DSI-SOP-000354).",
    "The USDA guideline number is mandatory.": "Il numero della linea guida USDA è obbligatorio.",
    "You cannot decide on your own request.": "Non puoi decidere sulla tua stessa richiesta.",
    "The requester cannot approve their own request.": "Il richiedente non può approvare la propria richiesta.",
    "Approved automatically: the requester is an approver of this cost centre": (
        "Approvata automaticamente: il richiedente è un approvatore di questo centro di costo"
    ),
    # step 5
    "Confirm the declaration to submit.": "Conferma la dichiarazione per inviare.",
}

STATUS_IT = {
    "DRAFT": "Bozza", "PENDING_APPROVAL": "In attesa di approvazione", "REJECTED": "Rifiutata",
    "TO_VERIFY": "Da verificare", "RETURNED": "Restituita per correzione", "VERIFIED": "Verificata",
    "PACKED": "Prelevata e imballata", "IN_TRANSIT": "In transito", "DELIVERED": "Consegnata",
    "CANCELLED": "Annullata",
}  # fmt: skip
_STATUS_BY_LABEL = {label: STATUS_IT[value] for value, label in Status.choices}

IT_DAYS = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mer", "Thu": "Gio", "Fri": "Ven", "Sat": "Sab", "Sun": "Dom"}
_DAY_RE = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")
_NOT_DAY = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) is not a shipping day\. (.+) ships (.+)\.$")
_PARCELS = re.compile(r"^At most (\d+) parcel lines are allowed\.$")
_STATUS = re.compile(r"^A request in status (.+) can no longer be edited\.$")
_UNKNOWN = re.compile(r"^Unknown status: (.+)\.$")
_USE = re.compile(r"^Use one of: (.+)\.$")


def _days(text: str) -> str:
    return _DAY_RE.sub(lambda m: IT_DAYS[m.group(1)], text)


def to_italian(text: str) -> str:
    if text in IT:
        return IT[text]
    if m := _NOT_DAY.match(text):
        return (
            f"{IT_DAYS[m.group(1)]} non è un giorno di spedizione. {m.group(2)} spedisce {_days(m.group(3))}."
        )
    if m := _PARCELS.match(text):
        return f"Sono ammesse al massimo {m.group(1)} righe di colli."
    if m := _STATUS.match(text):
        status = _STATUS_BY_LABEL.get(m.group(1), m.group(1))
        return f"Una richiesta in stato «{status}» non può più essere modificata."
    if m := _UNKNOWN.match(text):
        return f"Stato sconosciuto: {m.group(1)}."
    if m := _USE.match(text):
        return f"Usa uno tra: {m.group(1)}."
    return text


def translate(data, lang: str):
    """Translate every string in a (nested) error payload; other values are left alone."""
    if lang != "it":
        return data
    if isinstance(data, str):
        return to_italian(data)
    if isinstance(data, list):
        return [translate(v, lang) for v in data]
    if isinstance(data, dict):
        return {k: translate(v, lang) for k, v in data.items()}
    return data


def request_language(request) -> str:
    """Accept-Language (en / it), then the signed-in user's profile language, then English."""
    header = (request.headers.get("Accept-Language") or "").lower()
    for part in header.split(","):
        code = part.split(";")[0].strip()[:2]
        if code in ("en", "it"):
            return code
    user = getattr(request, "user", None)
    return (
        user.language if getattr(user, "is_authenticated", False) and user.language in ("en", "it") else "en"
    )
