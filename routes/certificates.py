"""
routes/certificates.py - Certificate Vault (part of Career Studio).

A student's certificates and badges live in two places:

  certificates        the details (title, organisation, dates, credential id...)
  instance/career_studio/<user_id>/<random>.<ext>   the actual file

The file is never under "static", so it has no public URL. Every route checks
the signed-in user, downloads go through this module, and deleting a record
also deletes its file. Uploads are checked by extension, size and the first
bytes of the file before anything is written.
"""
import os
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, send_file, url_for,
)
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity
from utils.storage import (
    CERTIFICATE_EXTENSIONS, MAX_CERTIFICATE_BYTES, UploadError,
    delete_document, document_path, save_upload,
)

certificates_bp = Blueprint("certificates", __name__)

CATEGORIES = [
    "Technical Certifications",
    "Programming Courses",
    "AI/ML Certifications",
    "Cybersecurity",
    "Internships",
    "Hackathons",
    "Workshops",
    "Competitions",
    "Academic Achievements",
    "Other",
]

SORT_OPTIONS = {
    "newest": "Newest uploaded",
    "oldest": "Oldest uploaded",
    "issued": "Issue date (newest first)",
    "expiry": "Expiry date (soonest first)",
}

EXPIRING_SOON_DAYS = 60


# ------------------------------------------------------------------ helpers
def parse_date(value):
    """'2026-05-04' -> date, or None when the box is empty / not a date."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def clean_text(form, name, limit, label, errors, required=False):
    value = " ".join((form.get(name) or "").split())
    if required and not value:
        errors[name] = f"Enter the {label}."
    elif len(value) > limit:
        errors[name] = f"Use {limit} characters or fewer."
    return value


def clean_url(value, label, errors, field):
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) > 500:
        errors[field] = f"That {label} is too long."
        return ""
    if not (value.startswith("http://") or value.startswith("https://")):
        errors[field] = f"The {label} must start with http:// or https://"
        return ""
    if " " in value:
        errors[field] = f"The {label} cannot contain spaces."
        return ""
    return value


def validate_certificate(form, today=None):
    """Check a certificate form. Returns (data, errors)."""
    today = today or date.today()
    errors = {}
    data = {
        "title": clean_text(form, "title", 120, "certificate title", errors, required=True),
        "organization": clean_text(form, "organization", 120, "issuing organisation", errors),
        "category": " ".join((form.get("category") or "Other").split()) or "Other",
        "issue_date": (form.get("issue_date") or "").strip(),
        "expiry_date": (form.get("expiry_date") or "").strip(),
        "credential_id": clean_text(form, "credential_id", 80, "credential ID", errors),
        "credential_url": clean_url(form.get("credential_url"), "verification link", errors, "credential_url"),
        "skills": clean_text(form, "skills", 200, "skills", errors),
        "description": " ".join((form.get("description") or "").split())[:500],
    }

    if len(data["category"]) > 60:
        errors["category"] = "Use 60 characters or fewer for the category."

    issue = parse_date(data["issue_date"]) if data["issue_date"] else None
    expiry = parse_date(data["expiry_date"]) if data["expiry_date"] else None
    if data["issue_date"] and issue is None:
        errors["issue_date"] = "Enter the issue date as YYYY-MM-DD."
    if data["expiry_date"] and expiry is None:
        errors["expiry_date"] = "Enter the expiry date as YYYY-MM-DD."
    if issue and issue > today:
        errors["issue_date"] = "The issue date cannot be in the future."
    if issue and expiry and expiry < issue:
        errors["expiry_date"] = "The expiry date must be on or after the issue date."

    return data, errors


def certificates_for_user(db, user_id):
    return [dict(row) for row in db.execute(
        """SELECT * FROM certificates WHERE user_id = ?
           ORDER BY uploaded_at DESC, id DESC""",
        (user_id,),
    ).fetchall()]


def certificate_for_user(db, certificate_id):
    row = db.execute(
        "SELECT * FROM certificates WHERE id = ? AND user_id = ?",
        (certificate_id, current_user.id),
    ).fetchone()
    if not row:
        abort(404)
    return dict(row)


def decorate(certificate, today=None):
    """Add display-only fields (never written back to the database)."""
    today = today or date.today()
    certificate["skills_list"] = [
        part.strip() for part in (certificate["skills"] or "").split(",") if part.strip()
    ]
    certificate["is_image"] = certificate["mime_type"] in ("image/png", "image/jpeg")
    certificate["expiry_state"] = ""
    certificate["days_to_expiry"] = None
    expiry = parse_date(certificate["expiry_date"])
    if expiry:
        days = (expiry - today).days
        certificate["days_to_expiry"] = days
        if days < 0:
            certificate["expiry_state"] = "expired"
        elif days <= EXPIRING_SOON_DAYS:
            certificate["expiry_state"] = "soon"
    certificate["verified_note"] = (
        "Verification link provided by you" if certificate["credential_url"]
        else "Uploaded certificate"
    )
    return certificate


# ------------------------------------------------------------------ routes
@certificates_bp.route("/career-studio/certificates")
@login_required
def vault():
    db = get_db()
    today = date.today()
    all_certificates = [decorate(row, today) for row in certificates_for_user(db, current_user.id)]

    search = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    sort = request.args.get("sort", "newest")
    if sort not in SORT_OPTIONS:
        sort = "newest"

    shown = all_certificates
    if search:
        needle = search.lower()
        shown = [
            row for row in shown
            if needle in row["title"].lower()
            or needle in row["organization"].lower()
            or needle in row["skills"].lower()
        ]
    if category:
        shown = [row for row in shown if row["category"] == category]

    if sort == "oldest":
        shown = sorted(shown, key=lambda row: (row["uploaded_at"], row["id"]))
    elif sort == "issued":
        shown = sorted(shown, key=lambda row: row["issue_date"] or "", reverse=True)
    elif sort == "expiry":
        shown = sorted(shown, key=lambda row: row["expiry_date"] or "9999-12-31")

    counts = {}
    for row in all_certificates:
        counts[row["category"]] = counts.get(row["category"], 0) + 1

    return render_template(
        "career_studio/certificates.html",
        certificates=shown,
        total=len(all_certificates),
        counts=counts,
        categories=CATEGORIES,
        category=category,
        search=search,
        sort=sort,
        sort_options=SORT_OPTIONS,
        expiring=[row for row in all_certificates if row["expiry_state"] in ("soon", "expired")],
        today=today,
    )


@certificates_bp.route("/career-studio/certificates/new", methods=["GET", "POST"])
@login_required
def upload_certificate():
    form = {key: "" for key in (
        "title", "organization", "category", "issue_date", "expiry_date",
        "credential_id", "credential_url", "skills", "description",
    )}
    form["category"] = CATEGORIES[0]
    errors = {}

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in form}
        data, errors = validate_certificate(request.form)
        saved_file = None
        try:
            saved_file = save_upload(
                request.files.get("document"), current_user.id,
                CERTIFICATE_EXTENSIONS, MAX_CERTIFICATE_BYTES,
            )
        except UploadError as problem:
            errors["document"] = str(problem)

        if not errors and saved_file:
            db = get_db()
            db.execute(
                """INSERT INTO certificates
                       (user_id, title, organization, category, issue_date, expiry_date,
                        credential_id, credential_url, skills, description,
                        stored_filename, original_filename, mime_type, file_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    current_user.id, data["title"], data["organization"], data["category"],
                    data["issue_date"], data["expiry_date"], data["credential_id"],
                    data["credential_url"], data["skills"], data["description"],
                    saved_file["stored_filename"], saved_file["original_filename"],
                    saved_file["mime_type"], saved_file["file_size"],
                ),
            )
            db.commit()
            log_activity(current_user.id, "certificate", f"Uploaded a certificate: {data['title']}")
            flash("Certificate saved in your vault.", "success")
            return redirect(url_for("certificates.vault"))

    return render_template(
        "career_studio/certificate_form.html",
        form=form,
        errors=errors,
        categories=CATEGORIES,
        mode="new",
        max_mb=MAX_CERTIFICATE_BYTES // (1024 * 1024),
        today=date.today().isoformat(),
    )


@certificates_bp.route("/career-studio/certificates/<int:certificate_id>")
@login_required
def view_certificate(certificate_id):
    db = get_db()
    certificate = decorate(certificate_for_user(db, certificate_id))
    return render_template(
        "career_studio/certificate_detail.html",
        certificate=certificate,
        today=date.today(),
    )


@certificates_bp.route("/career-studio/certificates/<int:certificate_id>/file")
@login_required
def preview_file(certificate_id):
    db = get_db()
    certificate = certificate_for_user(db, certificate_id)
    path = document_path(current_user.id, certificate["stored_filename"])
    if path is None or not path.is_file():
        abort(404)
    return send_file(
        path,
        mimetype=certificate["mime_type"] or "application/octet-stream",
        as_attachment=False,
        download_name=certificate["original_filename"] or "certificate",
        conditional=True,
    )


@certificates_bp.route("/career-studio/certificates/<int:certificate_id>/download")
@login_required
def download_file(certificate_id):
    db = get_db()
    certificate = certificate_for_user(db, certificate_id)
    path = document_path(current_user.id, certificate["stored_filename"])
    if path is None or not path.is_file():
        abort(404)
    safe_stem = "".join(
        char for char in (certificate["title"] or "certificate")
        if char.isalnum() or char in (" ", "-", "_")
    ).strip() or "certificate"
    extension = os.path.splitext(certificate["stored_filename"])[1]
    return send_file(
        path,
        mimetype=certificate["mime_type"] or "application/octet-stream",
        as_attachment=True,
        download_name=f"{safe_stem[:60]}{extension}",
        conditional=True,
    )


@certificates_bp.route("/career-studio/certificates/<int:certificate_id>/edit", methods=["GET", "POST"])
@login_required
def edit_certificate(certificate_id):
    db = get_db()
    certificate = certificate_for_user(db, certificate_id)
    errors = {}
    form = dict(certificate)

    if request.method == "POST":
        form = {key: request.form.get(key, "") for key in (
            "title", "organization", "category", "issue_date", "expiry_date",
            "credential_id", "credential_url", "skills", "description",
        )}
        data, errors = validate_certificate(request.form)
        if not errors:
            db.execute(
                """UPDATE certificates
                   SET title = ?, organization = ?, category = ?, issue_date = ?,
                       expiry_date = ?, credential_id = ?, credential_url = ?,
                       skills = ?, description = ?, updated_at = datetime('now')
                   WHERE id = ? AND user_id = ?""",
                (
                    data["title"], data["organization"], data["category"], data["issue_date"],
                    data["expiry_date"], data["credential_id"], data["credential_url"],
                    data["skills"], data["description"], certificate_id, current_user.id,
                ),
            )
            db.commit()
            log_activity(current_user.id, "certificate", f"Updated a certificate: {data['title']}")
            flash("Certificate details updated.", "success")
            return redirect(url_for("certificates.view_certificate", certificate_id=certificate_id))

    return render_template(
        "career_studio/certificate_form.html",
        form=form,
        errors=errors,
        categories=CATEGORIES + sorted(
            {row["category"] for row in certificates_for_user(db, current_user.id)} - set(CATEGORIES)
        ),
        mode="edit",
        certificate=certificate,
        max_mb=MAX_CERTIFICATE_BYTES // (1024 * 1024),
        today=date.today().isoformat(),
    )


@certificates_bp.route("/career-studio/certificates/<int:certificate_id>/delete", methods=["POST"])
@login_required
def delete_certificate(certificate_id):
    db = get_db()
    certificate = certificate_for_user(db, certificate_id)
    db.execute(
        "DELETE FROM certificates WHERE id = ? AND user_id = ?",
        (certificate_id, current_user.id),
    )
    db.commit()
    delete_document(current_user.id, certificate["stored_filename"])
    log_activity(current_user.id, "certificate", f"Deleted a certificate: {certificate['title']}")
    flash("Certificate and its file were deleted.", "success")
    return redirect(url_for("certificates.vault"))

