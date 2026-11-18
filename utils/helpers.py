"""
utils/helpers.py - small reusable functions used by several routes.
"""
import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import abort, request, session

from utils.database import get_db

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- CSRF protection ----------
# CSRF is an attack where another website tricks your browser into sending a
# form to SkillBridge. We stop it by putting a secret random token in every
# form and refusing any POST request that does not send the matching token.

def generate_csrf_token():
    """Return this visitor's CSRF token, creating one if needed."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(16)
    return session["_csrf_token"]


def protect_from_csrf():
    """Runs before every request. Rejects form posts without a valid token."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        expected = session.get("_csrf_token", "")
        sent = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not sent or not secrets.compare_digest(sent, expected):
            abort(400)


# ---------- Safe redirects ----------
def is_safe_redirect_target(target):
    """Only allow redirects to pages inside this site (stops "open redirects")."""
    if not target:
        return False
    parsed = urlparse(target)
    return (
        target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
        and not parsed.scheme
        and not parsed.netloc
    )


# ---------- Validation ----------
def validate_registration(name, email, password, confirm_password):
    """Check the registration form. Returns a dict of {field: error message}."""
    errors = {}

    if not 2 <= len(name) <= 60:
        errors["name"] = "Enter your name using 2 to 60 characters."

    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        errors["email"] = "Enter a valid email address, such as name@example.com."

    if len(password) < 8:
        errors["password"] = "Use at least 8 characters."
    elif len(password) > 128:
        errors["password"] = "Use 128 characters or fewer."
    elif not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        errors["password"] = "Include at least one letter and one number."

    if "password" not in errors and password != confirm_password:
        errors["confirm_password"] = "The two passwords do not match."

    return errors


# ---------- Activity feed ----------
def log_activity(user_id, activity_type, description):
    """Add a line to the user's recent-activity feed."""
    db = get_db()
    db.execute(
        "INSERT INTO activities (user_id, activity_type, description) VALUES (?, ?, ?)",
        (user_id, activity_type, description),
    )
    db.commit()


# ---------- Friendly dates for templates ----------
# SQLite stores times as UTC text like "2026-11-10 14:30:00".
# These two functions are registered as Jinja filters in app.py.

def time_ago(value):
    """'2026-11-10 14:30:00' -> 'Just now', '5 minutes ago', '3 hours ago', '2 days ago' ..."""
    try:
        then = datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return value or ""

    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    return then.strftime("%d %b %Y")


def date_label(value):
    """'2026-11-10' or '2026-11-10 14:30:00' -> '10 Nov 2026'."""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value or ""
