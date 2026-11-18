"""
routes/resumes.py - Career Studio: the ATS-friendly resume builder.

A resume is one row in "resumes" plus any number of ordered rows in
"resume_items" (education, skills, projects, experience, certifications and
free-form extra sections). Everything is scoped to the signed-in student.

Projects can be imported from the project tracker, skills from My Skills, the
name/college from the profile, and certifications from the Certificate Vault.
Imports only copy what already exists — nothing is invented.
"""
import re
from datetime import date

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for, Response,
)
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity
from utils.resume_pdf import TEMPLATES, build_resume_pdf

resumes_bp = Blueprint("resumes", __name__)

TEMPLATE_CHOICES = [(key, value["label"]) for key, value in TEMPLATES.items()]

KIND_ORDER = ["education", "skill", "project", "experience", "certification", "section"]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LINK_PATTERN = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)

MAX_ITEMS = {"education": 6, "skill": 12, "project": 8, "experience": 6,
             "certification": 20, "section": 8}

FIELD_LIMITS = {
    "title": 80, "full_name": 80, "email": 120, "phone": 30, "location": 90,
    "linkedin": 300, "github": 300, "portfolio": 300, "summary": 1500,
    "objective": 1500,
}

PERSONAL_FIELDS = ["full_name", "email", "phone", "location", "linkedin", "github",
                   "portfolio", "summary", "objective"]


# ------------------------------------------------------------------ helpers
def _clean(value, limit):
    return " ".join((value or "").split())[:limit]


def _long_text(value, limit):
    """Keep the student's own line breaks in summaries and descriptions."""
    return (value or "").replace("\r\n", "\n").strip()[:limit]


def _values(form, name, limit):
    return [(value or "").strip() for value in form.getlist(name)][:limit]


def _at(values, index):
    return values[index] if index < len(values) else ""


def _tidy_meta(*parts):
    return " | ".join(part for part in parts if part)


def _link_or_blank(value, field, errors):
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) > 300 or not LINK_PATTERN.match(value):
        errors[field] = "Use a full link that starts with http:// or https://"
        return ""
    return value


def load_resume(db, resume_id):
    row = db.execute(
        "SELECT * FROM resumes WHERE id = ? AND user_id = ?",
        (resume_id, current_user.id),
    ).fetchone()
    if not row:
        abort(404)
    return dict(row)


def resume_items(db, resume_id):
    rows = db.execute(
        """SELECT * FROM resume_items WHERE resume_id = ?
           ORDER BY CASE kind
                        WHEN 'education' THEN 0 WHEN 'skill' THEN 1
                        WHEN 'project' THEN 2 WHEN 'experience' THEN 3
                        WHEN 'certification' THEN 4 ELSE 5
                    END, position, id""",
        (resume_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def group_items(items):
    grouped = {kind: [] for kind in KIND_ORDER}
    for item in items:
        grouped.setdefault(item["kind"], []).append(item)
    return grouped


def vault_certificates(db):
    return [dict(row) for row in db.execute(
        """SELECT id, title, organization, issue_date, credential_id, credential_url
           FROM certificates WHERE user_id = ? ORDER BY issue_date DESC, id DESC""",
        (current_user.id,),
    ).fetchall()]


def blank_resume(db):
    """A new resume pre-filled with what the profile already knows."""
    profile = db.execute(
        """SELECT college_name, education_details, year_of_study
           FROM user_profiles WHERE user_id = ?""",
        (current_user.id,),
    ).fetchone()
    return {
        "id": None,
        "title": "My resume",
        "template": "classic",
        "full_name": current_user.name,
        "email": current_user.email,
        "phone": "",
        "location": "",
        "linkedin": "",
        "github": "",
        "portfolio": "",
        "summary": "",
        "objective": "",
        "profile": dict(profile) if profile else {},
    }


# ------------------------------------------------------------------ form parsing
def parse_resume_form(form, db):
    """Turn the submitted editor form into (resume_data, items, errors)."""
    errors = {}
    data = {"template": form.get("template", "classic")}
    if data["template"] not in TEMPLATES:
        data["template"] = "classic"
    data["title"] = _clean(form.get("title"), FIELD_LIMITS["title"]) or "My resume"

    for field in PERSONAL_FIELDS:
        limit = FIELD_LIMITS[field]
        raw = form.get(field, "")
        data[field] = _long_text(raw, limit) if field in ("summary", "objective") else _clean(raw, limit)

    if not data["full_name"]:
        errors["full_name"] = "Enter the name that should appear on the resume."
    if data["email"] and not EMAIL_PATTERN.match(data["email"]):
        errors["email"] = "Enter a valid email address, or leave it empty."
    for field in ("linkedin", "github", "portfolio"):
        data[field] = _link_or_blank(data[field], field, errors)

    items = []
    position = 0

    # --- education -------------------------------------------------------
    institutions = _values(form, "edu_institution", MAX_ITEMS["education"])
    degrees = _values(form, "edu_degree", MAX_ITEMS["education"])
    fields_ = _values(form, "edu_field", MAX_ITEMS["education"])
    start_years = _values(form, "edu_start", MAX_ITEMS["education"])
    end_years = _values(form, "edu_end", MAX_ITEMS["education"])
    grades = _values(form, "edu_grade", MAX_ITEMS["education"])
    coursework = _values(form, "edu_coursework", MAX_ITEMS["education"])
    for index, institution in enumerate(institutions):
        degree = _at(degrees, index)
        if not institution and not degree:
            continue
        period = " - ".join(part for part in (_at(start_years, index), _at(end_years, index)) if part)
        items.append({
            "kind": "education", "position": position,
            "title": _clean(degree or "Degree", 120),
            "subtitle": _clean(institution, 120),
            "meta": _tidy_meta(_clean(fields_[index] if index < len(fields_) else "", 80),
                               period, _clean(_at(grades, index), 40)),
            "detail": _long_text(_at(coursework, index), 400),
            "link": "", "link2": "", "extra": "", "source_id": None,
        })
        position += 1

    # --- skills ----------------------------------------------------------
    skill_categories = _values(form, "skill_category", MAX_ITEMS["skill"])
    skill_items = _values(form, "skill_items", MAX_ITEMS["skill"])
    for index, category in enumerate(skill_categories):
        listed = _at(skill_items, index)
        if not category and not listed:
            continue
        items.append({
            "kind": "skill", "position": position,
            "title": _clean(listed, 400), "subtitle": _clean(category or "Skills", 60),
            "meta": "", "detail": "", "link": "", "link2": "", "extra": "",
            "source_id": None,
        })
        position += 1

    # --- projects --------------------------------------------------------
    project_titles = _values(form, "proj_title", MAX_ITEMS["project"])
    project_tech = _values(form, "proj_tech", MAX_ITEMS["project"])
    project_duration = _values(form, "proj_duration", MAX_ITEMS["project"])
    project_description = _values(form, "proj_description", MAX_ITEMS["project"])
    project_contributions = _values(form, "proj_contributions", MAX_ITEMS["project"])
    project_github = _values(form, "proj_github", MAX_ITEMS["project"])
    project_live = _values(form, "proj_live", MAX_ITEMS["project"])
    project_sources = _values(form, "proj_source_id", MAX_ITEMS["project"])
    for index, title in enumerate(project_titles):
        if not title and not _at(project_description, index):
            continue
        source = _at(project_sources, index)
        items.append({
            "kind": "project", "position": position,
            "title": _clean(title or "Project", 120),
            "subtitle": "",
            "meta": _tidy_meta(_clean(_at(project_tech, index), 160),
                               _clean(_at(project_duration, index), 60)),
            "detail": _long_text(_at(project_description, index), 1200),
            "extra": _long_text(_at(project_contributions, index), 800),
            "link": _clean_url(_at(project_github, index)),
            "link2": _clean_url(_at(project_live, index)),
            "source_id": int(source) if source.isdigit() else None,
        })
        position += 1

    # --- experience ------------------------------------------------------
    experience_orgs = _values(form, "exp_org", MAX_ITEMS["experience"])
    experience_roles = _values(form, "exp_role", MAX_ITEMS["experience"])
    experience_types = _values(form, "exp_type", MAX_ITEMS["experience"])
    experience_start = _values(form, "exp_start", MAX_ITEMS["experience"])
    experience_end = _values(form, "exp_end", MAX_ITEMS["experience"])
    experience_resp = _values(form, "exp_responsibilities", MAX_ITEMS["experience"])
    experience_ach = _values(form, "exp_achievements", MAX_ITEMS["experience"])
    experience_tech = _values(form, "exp_tech", MAX_ITEMS["experience"])
    for index, organization in enumerate(experience_orgs):
        role = _at(experience_roles, index)
        if not organization and not role:
            continue
        period = " - ".join(part for part in (_at(experience_start, index), _at(experience_end, index)) if part)
        technologies = _clean(_at(experience_tech, index), 200)
        achievements = _long_text(_at(experience_ach, index), 800)
        extras = [part for part in (achievements,
                                    f"Technologies: {technologies}" if technologies else "") if part]
        items.append({
            "kind": "experience", "position": position,
            "title": _clean(role, 120), "subtitle": _clean(organization, 120),
            "meta": _tidy_meta(_clean(_at(experience_types, index), 40), period),
            "detail": _long_text(_at(experience_resp, index), 1200),
            "extra": "\n".join(extras)[:1000],
            "link": "", "link2": "",
            "source_id": None,
        })
        position += 1

    # --- certifications from the vault -----------------------------------
    selected_ids = []
    for value in form.getlist("certificate_ids"):
        if str(value).isdigit() and int(value) not in selected_ids:
            selected_ids.append(int(value))
    if selected_ids:
        placeholders = ",".join("?" for _ in selected_ids)
        rows = db.execute(
            f"""SELECT id, title, organization, issue_date, credential_id, credential_url
                FROM certificates WHERE user_id = ? AND id IN ({placeholders})""",
            (current_user.id, *selected_ids),
        ).fetchall()
        for row in rows:
            items.append({
                "kind": "certification", "position": position,
                "title": _clean(row["title"], 140),
                "subtitle": _clean(row["organization"], 120),
                "meta": _tidy_meta(
                    row["issue_date"],
                    f"Credential ID {row['credential_id']}" if row["credential_id"] else "",
                ),
                "detail": "", "link": _clean_url(row["credential_url"]),
                "link2": "", "extra": "", "source_id": row["id"],
            })
            position += 1

    # --- certifications typed in by hand ---------------------------------
    custom_names = _values(form, "cert_name", 10)
    custom_orgs = _values(form, "cert_org", 10)
    custom_dates = _values(form, "cert_date", 10)
    custom_ids = _values(form, "cert_id", 10)
    custom_urls = _values(form, "cert_url", 10)
    for index, name in enumerate(custom_names):
        if not name:
            continue
        items.append({
            "kind": "certification", "position": position,
            "title": _clean(name, 140), "subtitle": _clean(_at(custom_orgs, index), 120),
            "meta": _tidy_meta(_clean(_at(custom_dates, index), 20),
                               f"Credential ID {_clean(_at(custom_ids, index), 80)}"
                               if _at(custom_ids, index) else ""),
            "detail": "", "link": _clean_url(_at(custom_urls, index)),
            "link2": "", "extra": "", "source_id": None,
        })
        position += 1

    # --- optional extra sections ----------------------------------------
    section_titles = _values(form, "section_title", MAX_ITEMS["section"])
    section_bodies = _values(form, "section_body", MAX_ITEMS["section"])
    for index, title in enumerate(section_titles):
        body = _at(section_bodies, index)
        if not title and not body:
            continue
        items.append({
            "kind": "section", "position": position,
            "title": _clean(title or "Additional information", 80),
            "subtitle": "", "meta": "",
            "detail": _long_text(body, 1200),
            "link": "", "link2": "", "extra": "", "source_id": None,
        })
        position += 1

    return data, items, errors


def _clean_url(value):
    value = (value or "").strip()
    return value if LINK_PATTERN.match(value) and len(value) <= 300 else ""


# ------------------------------------------------------------------ saving
def _save_items(db, resume_id, items):
    db.execute("DELETE FROM resume_items WHERE resume_id = ?", (resume_id,))
    for item in items:
        db.execute(
            """INSERT INTO resume_items
                   (resume_id, kind, position, title, subtitle, meta, detail,
                    link, link2, extra, source_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                resume_id, item["kind"], item["position"], item["title"], item["subtitle"],
                item["meta"], item["detail"], item["link"], item["link2"],
                item.get("extra", ""), item.get("source_id"),
            ),
        )


def save_resume(db, data, items, resume_id=None):
    values = (
        data["title"], data["template"], data["full_name"], data["email"],
        data["phone"], data["location"], data["linkedin"], data["github"],
        data["portfolio"], data["summary"], data["objective"],
    )
    if resume_id is None:
        cursor = db.execute(
            """INSERT INTO resumes
                   (user_id, title, template, full_name, email, phone, location,
                    linkedin, github, portfolio, summary, objective)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (current_user.id, *values),
        )
        resume_id = cursor.lastrowid
    else:
        db.execute(
            """UPDATE resumes
               SET title = ?, template = ?, full_name = ?, email = ?, phone = ?,
                   location = ?, linkedin = ?, github = ?, portfolio = ?,
                   summary = ?, objective = ?, updated_at = datetime('now')
               WHERE id = ? AND user_id = ?""",
            (*values, resume_id, current_user.id),
        )
    _save_items(db, resume_id, items)
    db.commit()
    return resume_id


# ------------------------------------------------------------------ rendering
def editor_context(db, resume, items, errors=None):
    return {
        "resume": resume,
        "grouped": group_items(items),
        "items": items,
        "errors": errors or {},
        "templates": TEMPLATE_CHOICES,
        "certificates": vault_certificates(db),
        "selected_certificates": {
            item["source_id"] for item in items
            if item["kind"] == "certification" and item["source_id"]
        },
        "max_items": MAX_ITEMS,
        "today": date.today().isoformat(),
    }


# ------------------------------------------------------------------ routes
@resumes_bp.route("/career-studio/resumes")
@login_required
def list_resumes():
    db = get_db()
    rows = [dict(row) for row in db.execute(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM resume_items i WHERE i.resume_id = r.id) AS item_count
           FROM resumes r WHERE r.user_id = ?
           ORDER BY r.updated_at DESC, r.id DESC""",
        (current_user.id,),
    ).fetchall()]
    return render_template(
        "career_studio/resumes.html",
        resumes=rows,
        templates=dict((key, value["label"]) for key, value in TEMPLATES.items()),
        certificate_total=db.execute(
            "SELECT COUNT(*) FROM certificates WHERE user_id = ?", (current_user.id,)
        ).fetchone()[0],
    )


@resumes_bp.route("/career-studio/resumes/new", methods=["GET", "POST"])
@login_required
def create_resume():
    db = get_db()
    if request.method == "POST":
        data, items, errors = parse_resume_form(request.form, db)
        if not errors:
            resume_id = save_resume(db, data, items)
            log_activity(current_user.id, "resume", f"Created a resume: {data['title']}")
            flash("Resume created. You can keep editing it here.", "success")
            return redirect(url_for("resumes.edit_resume", resume_id=resume_id))
        draft = dict(blank_resume(db), **{key: value for key, value in data.items()
                                          if key in PERSONAL_FIELDS or key in ("title", "template")})
        return render_template(
            "career_studio/resume_editor.html",
            **editor_context(db, draft, items, errors),
        )

    resume = blank_resume(db)
    return render_template(
        "career_studio/resume_editor.html",
        **editor_context(db, resume, []),
    )


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/edit", methods=["GET", "POST"])
@login_required
def edit_resume(resume_id):
    db = get_db()
    resume = load_resume(db, resume_id)

    if request.method == "POST":
        data, items, errors = parse_resume_form(request.form, db)
        if not errors:
            save_resume(db, data, items, resume_id=resume_id)
            log_activity(current_user.id, "resume", f"Updated a resume: {data['title']}")
            flash("Resume saved.", "success")
            return redirect(url_for("resumes.edit_resume", resume_id=resume_id))
        draft = dict(resume, **{key: value for key, value in data.items()
                               if key in PERSONAL_FIELDS or key in ("title", "template")})
        return render_template(
            "career_studio/resume_editor.html",
            **editor_context(db, draft, items, errors),
        )

    return render_template(
        "career_studio/resume_editor.html",
        **editor_context(db, resume, resume_items(db, resume_id)),
    )


@resumes_bp.route("/career-studio/resumes/preview", methods=["POST"])
@login_required
def preview_resume():
    """Live preview: render the submitted (unsaved) form as a resume page."""
    db = get_db()
    data, items, _errors = parse_resume_form(request.form, db)
    resume = dict(data, id=None)
    return render_template(
        "career_studio/_resume_preview.html",
        resume=resume,
        grouped=group_items(items),
    )


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/pdf")
@login_required
def download_pdf(resume_id):
    db = get_db()
    resume = load_resume(db, resume_id)
    items = resume_items(db, resume_id)
    pdf_bytes = build_resume_pdf(resume, items, group_items(items))
    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "-", resume["title"]).strip("-") or "resume"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
    )


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/print")
@login_required
def print_resume(resume_id):
    db = get_db()
    resume = load_resume(db, resume_id)
    items = resume_items(db, resume_id)
    return render_template(
        "career_studio/resume_print.html",
        resume=resume,
        grouped=group_items(items),
    )


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/duplicate", methods=["POST"])
@login_required
def duplicate_resume(resume_id):
    db = get_db()
    resume = load_resume(db, resume_id)
    items = resume_items(db, resume_id)
    new_title = f"{resume['title']} (copy)"[:80]
    cursor = db.execute(
        """INSERT INTO resumes
               (user_id, title, template, full_name, email, phone, location,
                linkedin, github, portfolio, summary, objective)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            current_user.id, new_title, resume["template"], resume["full_name"],
            resume["email"], resume["phone"], resume["location"], resume["linkedin"],
            resume["github"], resume["portfolio"], resume["summary"], resume["objective"],
        ),
    )
    new_id = cursor.lastrowid
    _save_items(db, new_id, items)
    db.commit()
    log_activity(current_user.id, "resume", f"Duplicated a resume: {resume['title']}")
    flash("Resume duplicated. Edit the copy as much as you like.", "success")
    return redirect(url_for("resumes.edit_resume", resume_id=new_id))


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required
def delete_resume(resume_id):
    db = get_db()
    resume = load_resume(db, resume_id)
    db.execute("DELETE FROM resumes WHERE id = ? AND user_id = ?", (resume_id, current_user.id))
    db.commit()
    log_activity(current_user.id, "resume", f"Deleted a resume: {resume['title']}")
    flash("Resume deleted.", "success")
    return redirect(url_for("resumes.list_resumes"))


# ------------------------------------------------------------------ imports
@resumes_bp.route("/career-studio/resumes/<int:resume_id>/import/skills", methods=["POST"])
@login_required
def import_skills(resume_id):
    db = get_db()
    load_resume(db, resume_id)
    existing = {item["subtitle"].lower() for item in resume_items(db, resume_id)
                if item["kind"] == "skill"}
    rows = db.execute(
        """SELECT s.name, s.category FROM user_skills us
           JOIN skills s ON s.id = us.skill_id
           WHERE us.user_id = ?
           ORDER BY s.category, s.name""",
        (current_user.id,),
    ).fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["category"], []).append(row["name"])

    position = max([item["position"] for item in resume_items(db, resume_id)] or [0]) + 1
    added = 0
    for category, names in grouped.items():
        if category.lower() in existing:
            continue
        db.execute(
            """INSERT INTO resume_items (resume_id, kind, position, title, subtitle)
               VALUES (?, 'skill', ?, ?, ?)""",
            (resume_id, position, ", ".join(names)[:400], category[:60]),
        )
        position += 1
        added += 1
    db.commit()
    if added:
        flash(f"Imported {added} skill group(s) from My Skills. Review the wording before you send it.", "success")
    else:
        flash("Your SkillBridge skills are already on this resume.", "info")
    return redirect(url_for("resumes.edit_resume", resume_id=resume_id))


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/import/projects", methods=["POST"])
@login_required
def import_projects(resume_id):
    db = get_db()
    load_resume(db, resume_id)
    items = resume_items(db, resume_id)
    linked = {item["source_id"] for item in items if item["kind"] == "project" and item["source_id"]}
    rows = db.execute(
        """SELECT id, title, description, technologies, github_url, live_url, status
           FROM projects WHERE user_id = ? ORDER BY updated_at DESC""",
        (current_user.id,),
    ).fetchall()
    position = max([item["position"] for item in items] or [0]) + 1
    added = 0
    for row in rows:
        if row["id"] in linked:
            continue
        db.execute(
            """INSERT INTO resume_items
                   (resume_id, kind, position, title, meta, detail, link, link2, source_id)
               VALUES (?, 'project', ?, ?, ?, ?, ?, ?, ?)""",
            (
                resume_id, position, row["title"][:120], row["technologies"][:160],
                row["description"][:1200], _clean_url(row["github_url"]),
                _clean_url(row["live_url"]), row["id"],
            ),
        )
        position += 1
        added += 1
    db.commit()
    if added:
        flash(f"Imported {added} project(s). Add the part you personally built before sending it.", "success")
    else:
        flash("Your projects are already on this resume.", "info")
    return redirect(url_for("resumes.edit_resume", resume_id=resume_id))


@resumes_bp.route("/career-studio/resumes/<int:resume_id>/import/profile", methods=["POST"])
@login_required
def import_profile(resume_id):
    db = get_db()
    resume = load_resume(db, resume_id)
    profile = db.execute(
        """SELECT college_name, education_details, year_of_study
           FROM user_profiles WHERE user_id = ?""",
        (current_user.id,),
    ).fetchone()

    updates = {}
    if not resume["full_name"]:
        updates["full_name"] = current_user.name
    if not resume["email"]:
        updates["email"] = current_user.email
    if updates:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        db.execute(
            f"UPDATE resumes SET {assignments}, updated_at = datetime('now') WHERE id = ?",
            (*updates.values(), resume_id),
        )

    added = 0
    if profile and profile["college_name"] and not [
        item for item in resume_items(db, resume_id) if item["kind"] == "education"
    ]:
        db.execute(
            """INSERT INTO resume_items (resume_id, kind, position, title, subtitle, meta, detail)
               VALUES (?, 'education', 0, ?, ?, ?, ?)""",
            (
                resume_id,
                profile["education_details"] or "Degree",
                profile["college_name"],
                profile["year_of_study"] or "",
                "Imported from your profile — edit the years and grade.",
            ),
        )
        added = 1
    db.commit()
    flash(
        "Imported your name and college from your profile. Check every line before sending it.",
        "success" if (updates or added) else "info",
    )
    return redirect(url_for("resumes.edit_resume", resume_id=resume_id))
