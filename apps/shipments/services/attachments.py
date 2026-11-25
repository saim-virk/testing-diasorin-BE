"""Attachment upload rules: PDF / PNG / JPG / DOCX / XLSX, max 20 MB, stored under MEDIA_ROOT."""

from pathlib import PurePath

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from ..enums import AttachmentKind
from ..models import Attachment, ShipmentRequest
from . import drafts

MAX_BYTES = 20 * 1024 * 1024
# extension -> (content type, magic-byte prefixes). DOCX / XLSX are zip containers.
ALLOWED = {
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        (b"PK\x03\x04",),
    ),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (b"PK\x03\x04",)),
}


def _check_file(upload) -> str:
    ext = PurePath(upload.name or "").suffix.lower()
    if ext not in ALLOWED:
        raise ValidationError({"file": ["Allowed file types: PDF, PNG, JPG, DOCX, XLSX."]})
    if upload.size > MAX_BYTES:
        raise ValidationError({"file": ["The file is larger than 20 MB."]})
    if upload.size == 0:
        raise ValidationError({"file": ["The file is empty."]})
    head = upload.read(8)
    upload.seek(0)
    if not any(head.startswith(m) for m in ALLOWED[ext][1]):
        raise ValidationError({"file": ["The file content does not match its type."]})
    return ALLOWED[ext][0]


@transaction.atomic
def add_attachment(req_id: int, user, kind: str, upload) -> Attachment:
    req = ShipmentRequest.objects.select_for_update().get(pk=req_id)
    drafts.require_owner(user, req)
    drafts.require_editable(req)
    if kind not in AttachmentKind.values:
        raise ValidationError({"kind": ["Choose MSDS, COA or OTHER."]})
    content_type = _check_file(upload)
    return Attachment.objects.create(
        request=req,
        kind=kind,
        file=upload,
        original_name=PurePath(upload.name).name[:255],
        content_type=content_type,
        size_bytes=upload.size,
        uploaded_by=user,
        uploaded_at=timezone.now(),
    )


@transaction.atomic
def delete_attachment(req_id: int, user, attachment_id: int) -> None:
    req = ShipmentRequest.objects.select_for_update().get(pk=req_id)
    drafts.require_owner(user, req)
    drafts.require_editable(req)
    att = req.attachments.filter(pk=attachment_id).first()
    if att is None:
        raise NotFound("Attachment not found.")
    storage, name = att.file.storage, att.file.name
    att.delete()
    if name:  # only once the delete is committed, so a rollback keeps the file
        transaction.on_commit(lambda: storage.delete(name))
