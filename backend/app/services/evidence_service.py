import hashlib
import os
from pathlib import Path

import boto3
import magic

from app.config import settings

# Local storage fallback when S3 bucket doesn't exist
LOCAL_STORAGE_DIR = (
    Path(
        settings.BASE_DIR
        if hasattr(settings, "BASE_DIR")
        else os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    )
    / "uploads"
    / "evidence"
)
_use_local = False

try:
    _s3 = boto3.client("s3", region_name=settings.S3_REGION)
    _s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
except Exception:
    _use_local = True
    LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_MIME = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # xlsx
    "application/vnd.ms-excel",  # xls
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # docx
    "application/msword",  # doc
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.ms-powerpoint",  # ppt
    "application/haansofthwp",  # hwp
    "application/x-hwp",  # hwp alt
    "text/csv",
    "text/plain",
    "text/html",
    "text/markdown",
    "text/rtf",
    "application/rtf",  # rtf
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",  # fallback for unknown binary types (txt, md, etc.)
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_mime(data: bytes) -> str:
    """Return the MIME type inferred from the file's magic bytes."""
    return magic.from_buffer(data, mime=True)


# Office Open XML containers (docx/xlsx/pptx) are ZIPs under the hood; libmagic
# only reports 'application/zip'. Keep the client's more specific claim in those
# cases so the stored mime_type stays meaningful for UI display.
_OFFICE_OPENXML = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def validate_upload_mime(claimed: str | None, data: bytes) -> str:
    """Validate the file's real MIME against ALLOWED_MIME and return what to store.

    - If magic detects an allow-listed type, use it.
    - If magic returns 'application/zip' and the client claimed a specific Office
      Open XML type, trust the claim (both are allow-listed, but the claim has
      more signal for display).
    - If magic returns 'application/octet-stream' (binary it can't identify,
      e.g. old HWP/CFBF) and the claim is allow-listed, trust the claim.
    - Otherwise raise HTTPException(400).
    """
    from fastapi import HTTPException

    detected = detect_mime(data)
    if detected == "application/zip" and claimed in _OFFICE_OPENXML:
        return claimed
    if detected == "application/octet-stream" and claimed in ALLOWED_MIME:
        return claimed
    if detected in ALLOWED_MIME:
        return detected
    raise HTTPException(
        status_code=400,
        detail=f"허용되지 않은 파일 형식입니다 (감지된 형식: {detected})",
    )


async def upload_to_s3(file_data: bytes, key: str, content_type: str) -> None:
    if _use_local:
        dest = LOCAL_STORAGE_DIR / key.replace("/", "_")
        dest.write_bytes(file_data)
        return
    _s3.put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=file_data,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )


def generate_download_url(key: str, expires: int = 3600) -> str:
    if _use_local:
        # Return a relative URL; the download endpoint will serve it
        return f"/api/evidence/files/{key.replace('/', '_')}"
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": key},
        ExpiresIn=expires,
    )


async def delete_from_s3(key: str) -> None:
    if _use_local:
        dest = LOCAL_STORAGE_DIR / key.replace("/", "_")
        dest.unlink(missing_ok=True)
        return
    _s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
