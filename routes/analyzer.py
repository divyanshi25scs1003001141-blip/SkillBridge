"""
routes/analyzer.py - Career Studio: the Resume Analyzer.

A student uploads a PDF/DOCX resume or picks a resume saved in the builder,
pastes a target job description, and gets a rule-based estimate of ATS
compatibility plus matched/missing skills, keywords, structure checks and
practical improvements.

The uploaded file is read in memory and then discarded: only the extracted
text statistics and the results are stored, so no document is kept on disk.
"""
import json
from datetime import date

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required

from utils.analyzer import ExtractionError, analyze_resume, extract_text
from utils.database import get_db
from utils.helpers import log_activity
from utils.storage import ANALYSIS_EXTENSIONS, MAX_ANALYSIS_BYTES, UploadError, save_upload, read_bytes, delete_document

analyzer_bp = Blueprint("analyzer", __name__)

SUGGESTED_ROLES = [
    "Python Developer", "Web Developer", "Data Analyst", "AI/ML Engineer",
    "Software Developer", "Cybersecurity Analyst", "Frontend Developer", "Backend Developer",
]

EXPERIENCE_LEVELS = ["Internship", "Fresher", "1-2 years", "3-5 years", "5+ years"]


def _load_analysis(analysis_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM resume_analyses WHERE id = ? AND user_id = ?",
        (analysis_id, current_user.id),
    ).fetchone()
    if not row:
        abort(404)
    return dict(row)


def _decode(row):
    """Turn the stored JSON columns back into a view dictionary."""
    scores = json.loads(row["scores_json"] or "{}")
    keywords = json.loads(row["keywords_json"] or "{}")
    return {
        "id": row["id"],
        "source_name": row["source_name"],
        "job_title": row["job_title"],
        "company": row["company"],
        "industry": row["industry"],
        "experience_level": row["experience_level"],
        "overall": row["overall_score"],
        "word_count": row["word_count"],
        "created_at": row["created_at"],
        "scores": scores.get("scores", {}),
        "score_maxima": scores.get("score_maxima", {}),
        "normalised": scores.get("normalised", False),
        "structure_checks": scores.get("structure_checks", []),
        "sections_present": scores.get("sections_present", []),
        "extra_skills": scores.get("extra_skills", []),
        "unsupported": scores.get("unsupported", []),
        "job_skills": scores.get("job_skills", []),
        "resume_skills": scores.get("resume_skills", []),
        "has_job": scores.get("has_job", False),
        "matched": json.loads(row["matched_json"] or "[]"),
        "missing": json.loads(row["missing_json"] or "[]"),
        "keywords_found": keywords.get("found", []),
        "keywords_missing": keywords.get("missing", []),
        "strengths": json.loads(row["strengths_json"] or "[]"),
        "improvements": json.loads(row["improvements_json"] or "[]"),
        "checklist": scores.get("checklist", []),
        "content_notes": scores.get("content_notes", []),
    }


def resume_text(resume, items):
    """Flatten a saved resume into plain text, the same way a reader sees it."""
    lines = [resume["full_name"], resume["email"], resume["phone"], resume["location"],
             resume["linkedin"], resume["github"], resume["portfolio"]]
    if resume["summary"]:
        lines += ["PROFESSIONAL SUMMARY", resume["summary"]]
    if resume["objective"]:
        lines += ["CAREER OBJECTIVE", resume["objective"]]

    headings = {
        "education": "EDUCATION", "skill": "TECHNICAL SKILLS", "project": "PROJECTS",
        "experience": "INTERNSHIP AND WORK EXPERIENCE", "certification": "CERTIFICATIONS",
    }
    for kind, heading in headings.items():
        rows = [item for item in items if item["kind"] == kind]
        if not rows:
            continue
        lines.append(heading)
        for item in rows:
            if kind == "skill":
                lines.append(f"{item['subtitle']}: {item['title']}")
            else:
                parts = [item["title"], item["subtitle"], item["meta"], item["detail"], item["extra"]]
                lines.append(" ".join(part for part in parts if part))
    for item in items:
        if item["kind"] == "section":
            lines += [item["title"].upper(), item["detail"]]
    return "\n".join(line for line in lines if line)


def _saved_resumes(db):
    return [dict(row) for row in db.execute(
        "SELECT id, title, full_name FROM resumes WHERE user_id = ? ORDER BY updated_at DESC",
        (current_user.id,),
    ).fetchall()]


def _history(db, limit=20):
    return [dict(row) for row in db.execute(
        """SELECT id, job_title, company, source_name, overall_score, created_at
           FROM resume_analyses WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?""",
        (current_user.id, limit),
    ).fetchall()]


@analyzer_bp.route("/career-studio/analyzer")
@login_required
def analyzer_home():
    db = get_db()
    return render_template(
        "career_studio/analyzer.html",
        roles=SUGGESTED_ROLES,
        levels=EXPERIENCE_LEVELS,
        resumes=_saved_resumes(db),
        history=_history(db, limit=5),
        form={},
        error="",
        max_mb=MAX_ANALYSIS_BYTES // (1024 * 1024),
        today=date.today().isoformat(),
    )


@analyzer_bp.route("/career-studio/analyzer/run", methods=["POST"])
@login_required
def run_analysis():
    db = get_db()
    form = {
        "job_title": " ".join((request.form.get("job_title") or "").split())[:120],
        "company": " ".join((request.form.get("company") or "").split())[:120],
        "industry": " ".join((request.form.get("industry") or "").split())[:120],
        "experience_level": (request.form.get("experience_level") or "").strip(),
        "description": (request.form.get("description") or "").strip()[:8000],
        "resume_id": (request.form.get("resume_id") or "").strip(),
    }
    if form["experience_level"] not in EXPERIENCE_LEVELS:
        form["experience_level"] = ""
    if not form["job_title"]:
        form["job_title"] = ""

    def show_error(message):
        return render_template(
            "career_studio/analyzer.html",
            roles=SUGGESTED_ROLES,
            levels=EXPERIENCE_LEVELS,
            resumes=_saved_resumes(db),
            history=_history(db, limit=5),
            form=form,
            error=message,
            max_mb=MAX_ANALYSIS_BYTES // (1024 * 1024),
            today=date.today().isoformat(),
        )

    source_name = ""
    text = ""
    resume_id = None

    upload = request.files.get("document")
    has_upload = bool(upload and (upload.filename or "").strip())

    if has_upload:
        try:
            stored = save_upload(
                upload, current_user.id, ANALYSIS_EXTENSIONS, MAX_ANALYSIS_BYTES
            )
        except UploadError as problem:
            return show_error(str(problem))

        # Read it, then delete it: the persona document is not kept.
        try:
            data = read_bytes(stored["stored_filename"], current_user.id)
            if data is None:
                raise ExtractionError("That upload could not be read. Please try again.")
            text = extract_text(data, stored["extension"])
        except ExtractionError as problem:
            return show_error(str(problem))
        finally:
            delete_document(current_user.id, stored["stored_filename"])
        source_name = stored["original_filename"]
    elif form["resume_id"].isdigit():
        resume = db.execute(
            "SELECT * FROM resumes WHERE id = ? AND user_id = ?",
            (int(form["resume_id"]), current_user.id),
        ).fetchone()
        if not resume:
            return show_error("That saved resume could not be found.")
        resume_id = resume["id"]
        items = db.execute(
            "SELECT * FROM resume_items WHERE resume_id = ? ORDER BY position, id",
            (resume_id,),
        ).fetchall()
        text = resume_text(dict(resume), [dict(row) for row in items])
        source_name = f"SkillBridge resume: {resume['title']}"
    else:
        return show_error("Upload a PDF or DOCX file, or choose a saved resume to analyse.")

    try:
        analysis = analyze_resume(
            text,
            job_title=form["job_title"],
            description=form["description"],
            company=form["company"],
            industry=form["industry"],
            experience_level=form["experience_level"],
            source_name=source_name,
        )
    except ExtractionError as problem:
        return show_error(str(problem))

    scores_payload = {
        "scores": analysis["scores"],
        "score_maxima": analysis["score_maxima"],
        "normalised": analysis["normalised"],
        "structure_checks": analysis["structure_checks"],
        "sections_present": analysis["sections_present"],
        "content_notes": analysis["content_notes"],
        "checklist": analysis["checklist"],
        "extra_skills": analysis["extra_skills"],
        "unsupported": analysis["unsupported"],
        "resume_skills": analysis["resume_skills"],
        "job_skills": analysis["job_skills"],
        "has_job": analysis["has_job"],
    }
    cursor = db.execute(
        """INSERT INTO resume_analyses
               (user_id, resume_id, source_name, job_title, company, industry,
                experience_level, overall_score, scores_json, matched_json,
                missing_json, keywords_json, strengths_json, improvements_json,
                sections_json, word_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            current_user.id, resume_id, source_name, analysis["job_title"],
            analysis["company"], analysis["industry"], analysis["experience_level"],
            analysis["overall"], json.dumps(scores_payload),
            json.dumps(analysis["matched"]), json.dumps(analysis["missing"]),
            json.dumps({"found": analysis["keywords_found"], "missing": analysis["keywords_missing"]}),
            json.dumps(analysis["strengths"]), json.dumps(analysis["improvements"]),
            json.dumps({"sections": analysis["sections_present"]}),
            analysis["word_count"],
        ),
    )
    db.commit()
    log_activity(
        current_user.id, "analysis",
        f"Analysed a resume for {analysis['job_title'] or 'a target role'} "
        f"(estimated ATS compatibility {analysis['overall']}/100)",
    )
    flash("Analysis complete. The uploaded file was read and then deleted.", "success")
    return redirect(url_for("analyzer.view_analysis", analysis_id=cursor.lastrowid))


@analyzer_bp.route("/career-studio/analyzer/<int:analysis_id>")
@login_required
def view_analysis(analysis_id):
    db = get_db()
    row = _load_analysis(analysis_id)
    return render_template(
        "career_studio/analysis.html",
        analysis=_decode(row),
        history=_history(db, limit=5),
    )


@analyzer_bp.route("/career-studio/analyzer/history")
@login_required
def analysis_history():
    db = get_db()
    return render_template(
        "career_studio/analyzer_history.html",
        history=_history(db, limit=50),
    )


@analyzer_bp.route("/career-studio/analyzer/<int:analysis_id>/delete", methods=["POST"])
@login_required
def delete_analysis(analysis_id):
    db = get_db()
    row = _load_analysis(analysis_id)
    db.execute(
        "DELETE FROM resume_analyses WHERE id = ? AND user_id = ?",
        (analysis_id, current_user.id),
    )
    db.commit()
    log_activity(current_user.id, "analysis", "Deleted a resume analysis")
    flash("Analysis deleted.", "success")
    return redirect(url_for("analyzer.analysis_history"))
