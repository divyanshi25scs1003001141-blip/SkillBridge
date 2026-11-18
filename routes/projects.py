"""
routes/projects.py - Phase 8: the personal project tracker.

A student lists the projects they have built (or plan to build), with the
technologies used, a GitHub link, a live/demo link and a status. Every query
is filtered by the signed-in user's id, so one student never sees, edits or
deletes another student's project.

Statuses are exactly: Planned, In Progress, Completed.
"""
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

projects_bp = Blueprint("projects", __name__)

PROJECT_STATUSES = ["Planned", "In Progress", "Completed"]

MAX_TITLE = 120
MAX_DESCRIPTION = 1000
MAX_TECHNOLOGIES = 300
MAX_URL = 300


def _clean_url(value, label):
    """Return (url, error). Empty is allowed; anything else must be http(s)."""
    if not value:
        return "", None
    if len(value) > MAX_URL:
        return "", f"{label} is too long (maximum {MAX_URL} characters)."
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "", f"{label} must start with http:// or https:// and include a website address."
    return value, None


def _validate(form):
    """Read and check the submitted project form.

    Returns (data, errors). data is always safe to re-show in the form, so a
    beginner does not lose what they typed when one field is wrong.
    """
    data = {
        "title": (form.get("title") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "technologies": (form.get("technologies") or "").strip(),
        "status": (form.get("status") or "Planned").strip(),
        "github_url": (form.get("github_url") or "").strip(),
        "live_url": (form.get("live_url") or "").strip(),
    }
    errors = []

    if not data["title"]:
        errors.append("Give your project a title.")
    elif len(data["title"]) > MAX_TITLE:
        errors.append(f"Titles can be up to {MAX_TITLE} characters.")

    if len(data["description"]) > MAX_DESCRIPTION:
        errors.append(f"Descriptions can be up to {MAX_DESCRIPTION} characters.")

    if len(data["technologies"]) > MAX_TECHNOLOGIES:
        errors.append(f"Technologies can be up to {MAX_TECHNOLOGIES} characters.")

    if data["status"] not in PROJECT_STATUSES:
        errors.append("Choose a valid status: Planned, In Progress or Completed.")

    data["github_url"], github_error = _clean_url(data["github_url"], "GitHub link")
    if github_error:
        errors.append(github_error)

    data["live_url"], live_error = _clean_url(data["live_url"], "Live link")
    if live_error:
        errors.append(live_error)

    return data, errors


def _tech_list(technologies):
    """Turn "Python, Flask, SQLite" into tags without empty entries."""
    return [part.strip() for part in technologies.split(",") if part.strip()]


def _load_projects(db, user_id):
    """Every project for one user, grouped by status in display order."""
    rows = db.execute(
        """
        SELECT id, title, description, technologies, github_url, live_url,
               status, created_at, updated_at
        FROM projects
        WHERE user_id = ?
        ORDER BY CASE status
                     WHEN 'In Progress' THEN 0
                     WHEN 'Planned'     THEN 1
                     ELSE 2
                 END,
                 datetime(updated_at) DESC, id DESC
        """,
        (user_id,),
    ).fetchall()

    projects = []
    for row in rows:
        project = dict(row)
        project["tech"] = _tech_list(project["technologies"])
        projects.append(project)

    grouped = {status: [] for status in PROJECT_STATUSES}
    for project in projects:
        grouped[project["status"]].append(project)

    return projects, grouped


def _render(db, user_id, form=None, errors=()):
    """Render the projects page, optionally with a partly filled form."""
    projects, grouped = _load_projects(db, user_id)
    return render_template(
        "dashboard/projects.html",
        projects=projects,
        grouped=grouped,
        counts={status: len(items) for status, items in grouped.items()},
        statuses=PROJECT_STATUSES,
        form=form or {},
        errors=list(errors),
    )


@projects_bp.route("/projects")
@login_required
def list_projects():
    db = get_db()
    return _render(db, current_user.id)


@projects_bp.route("/projects/new", methods=["POST"])
@login_required
def create_project():
    db = get_db()
    user_id = current_user.id
    data, errors = _validate(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return _render(db, user_id, form=data, errors=errors)

    db.execute(
        """INSERT INTO projects
           (user_id, title, description, technologies, github_url, live_url, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            data["title"],
            data["description"],
            data["technologies"],
            data["github_url"],
            data["live_url"],
            data["status"],
        ),
    )
    db.commit()
    log_activity(user_id, "project", f"Added a project: {data['title']}")
    flash(f"Project “{data['title']}” added.", "success")
    return redirect(url_for("projects.list_projects"))


@projects_bp.route("/projects/<int:project_id>/edit", methods=["POST"])
@login_required
def edit_project(project_id):
    db = get_db()
    user_id = current_user.id

    existing = db.execute(
        "SELECT id, title, status FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not existing:
        flash("That project could not be found.", "error")
        return redirect(url_for("projects.list_projects"))

    data, errors = _validate(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return _render(db, user_id, form=data, errors=errors)

    db.execute(
        """UPDATE projects
           SET title = ?, description = ?, technologies = ?, github_url = ?,
               live_url = ?, status = ?, updated_at = datetime('now')
           WHERE id = ? AND user_id = ?""",
        (
            data["title"],
            data["description"],
            data["technologies"],
            data["github_url"],
            data["live_url"],
            data["status"],
            project_id,
            user_id,
        ),
    )
    db.commit()

    if data["status"] != existing["status"]:
        log_activity(
            user_id,
            "project",
            f"Moved “{data['title']}” to {data['status']}",
        )
        flash(f"“{data['title']}” is now {data['status']}.", "success")
    else:
        flash(f"Project “{data['title']}” updated.", "success")
    return redirect(url_for("projects.list_projects"))


@projects_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def delete_project(project_id):
    db = get_db()
    user_id = current_user.id

    project = db.execute(
        "SELECT title FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not project:
        flash("That project could not be found.", "error")
        return redirect(url_for("projects.list_projects"))

    db.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    db.commit()
    log_activity(user_id, "project", f"Deleted a project: {project['title']}")
    flash(f"Project “{project['title']}” deleted.", "info")
    return redirect(url_for("projects.list_projects"))
