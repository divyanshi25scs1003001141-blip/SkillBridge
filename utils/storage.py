"""
utils/storage.py - private file storage for Career Studio documents.

Files never live under "static", so nothing is reachable by URL. Each upload
gets a random 32-character filename inside its owner's folder, the extension is
checked against an allow-list and the first bytes of the file are checked to
make sure the content matches the extension. Downloads always go through a
route that checks the signed-in user first.

The folder lives in the Flask "instance" directory, which .gitignore already
excludes, so student documents are never committed.
"""
import re
import uuid
from pathlib import Path

from flask import current_app

# What each kind of upload is allowed to be.
CERTIFICATE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
ANALYSIS_EXTENSIONS = {"pdf", "docx"}

MAX_CERTIFICATE_BYTES = 8 * 1024 * 1024   # 8 MB
MAX_ANALYSIS_BYTES = 5 * 1024 * 1024      # 5 MB

# Only the names this module generates can ever be read back.
STORED_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg|jpeg|docx)$")

_MAGIC_BYTES = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "docx": (b"PK\x03\x04",),
}


class UploadError(Exception):
    """Raised when an upload is empty, too large, the wrong type or unreadable."""


def upload_root():
    """The private folder that holds every Career Studio document.

    Defaults to instance/career_studio. Tests point it at a temporary folder
    with the CAREER_STUDIO_UPLOAD_ROOT setting so they never touch real files.
    """
    configured = current_app.config.get("CAREER_STUDIO_UPLOAD_ROOT")
    if configured:
        return Path(configured)
    return Path(current_app.instance_path) / "career_studio"


def user_folder(user_id):
    folder = upload_root() / str(int(user_id))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _extension(filename):
    return Path(filename or "").suffix.lower().lstrip(".")


def _matches_magic(extension, head):
    expected = _MAGIC_BYTES.get(extension, ())
    return any(head.startswith(signature) for signature in expected)


def save_upload(file_storage, user_id, allowed_extensions, max_bytes):
    """Validate and store one uploaded file. Returns its metadata dictionary."""
    if file_storage is None or not (file_storage.filename or "").strip():
        raise UploadError("Choose a file to upload.")

    original = Path(file_storage.filename).name  # strips any folder part
    extension = _extension(original)
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(ext.upper() for ext in allowed_extensions))
        raise UploadError(f"That file type is not supported. Use {allowed}.")

    stream = file_storage.stream
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if size == 0:
        raise UploadError("That file is empty.")
    if size > max_bytes:
        raise UploadError(
            f"That file is {size / (1024 * 1024):.1f} MB. The limit is "
            f"{max_bytes // (1024 * 1024)} MB."
        )

    head = stream.read(16)
    stream.seek(0)
    if not _matches_magic(extension, head):
        raise UploadError(
            "The file contents do not match its extension. Please upload the real document."
        )

    stored_name = f"{uuid.uuid4().hex}.{extension}"
    destination = user_folder(user_id) / stored_name
    stream.seek(0)
    with destination.open("wb") as handle:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            handle.write(chunk)

    mimetype = file_storage.mimetype or {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(extension, "application/octet-stream")

    return {
        "stored_filename": stored_name,
        "original_filename": original[:180],
        "mime_type": mimetype,
        "extension": extension,
        "file_size": size,
    }


def document_path(user_id, stored_filename):
    """Absolute path for a stored file, or None if the name is not one we made."""
    if not stored_filename or not STORED_NAME_PATTERN.match(stored_filename):
        return None
    folder = (upload_root() / str(int(user_id))).resolve()
    candidate = (folder / stored_filename).resolve()
    if candidate.parent != folder:
        return None
    return candidate


def read_bytes(stored_filename, user_id):
    path = document_path(user_id, stored_filename)
    if path is None or not path.is_file():
        return None
    return path.read_bytes()


def delete_document(user_id, stored_filename):
    """Remove the stored file (the database row is removed by the route)."""
    path = document_path(user_id, stored_filename)
    if path is not None and path.is_file():
        path.unlink()
        return True
    return False
