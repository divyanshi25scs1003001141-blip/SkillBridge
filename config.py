"""
config.py - settings for the SkillBridge application.

Nothing secret is written in this file. The secret key (used to sign login
sessions) is read from an environment variable, or created automatically on
your computer the first time you run the app and saved in the "instance"
folder, which is excluded from GitHub by .gitignore.
"""
import os
import secrets
from datetime import timedelta
from pathlib import Path

# The folder that contains this file (the SkillBridge project folder).
BASE_DIR = Path(__file__).resolve().parent


def load_secret_key():
    """Return the secret key, creating and saving one if needed."""
    key_from_environment = os.environ.get("SECRET_KEY")
    if key_from_environment:
        return key_from_environment

    instance_folder = BASE_DIR / "instance"
    instance_folder.mkdir(exist_ok=True)
    key_file = instance_folder / "secret_key.txt"

    if key_file.exists():
        saved_key = key_file.read_text(encoding="utf-8").strip()
        if saved_key:
            return saved_key

    new_key = secrets.token_hex(32)
    key_file.write_text(new_key, encoding="utf-8")
    return new_key


class Config:
    SECRET_KEY = load_secret_key()

    # Where the SQLite database file lives (used from Phase 2 onwards).
    DATABASE = os.environ.get(
        "DATABASE_PATH", str(BASE_DIR / "database" / "skillbridge.db")
    )

    # Safer session cookies.
    SESSION_COOKIE_HTTPONLY = True       # JavaScript cannot read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"      # not sent along with most cross-site requests
    # Only send the cookie over HTTPS when the app runs in production.
    SESSION_COOKIE_SECURE = os.environ.get("SKILLBRIDGE_ENV") == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Reject unexpectedly large requests. Career Studio uploads a resume or a
    # certificate, so the ceiling is 10 MB; each file is checked again (and
    # limited to 8 MB) in utils/storage.py before anything is saved.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
