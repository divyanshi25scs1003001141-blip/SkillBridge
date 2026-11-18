"""
routes/career.py - Phase 5: choose a target career and see your skill gap.

The gap compares the skills the chosen career asks for with the skills in the
student's own list:

    Acquired skill    -> 100% of that skill's weight
    Learning skill    ->  50%
    Not in the list   ->   0%

Core skills count twice as much as supporting ones, because they matter more
for that career. The result is guidance only: an assessment score is shown as
extra insight and never changes a skill's status by itself.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

career_bp = Blueprint("career", __name__)

CORE_WEIGHT = 2
SUPPORTING_WEIGHT = 1
STATUS_SCORE = {"Acquired": 1.0, "Learning": 0.5}

# Predefined career data, shared by every student. Each skill entry is
# (skill name, skill category, is_core). Seeding is idempotent and never
# deletes a student's skills, selections or assessment attempts.
CAREER_CATALOGUE = [
    {
        "title": "Python Developer",
        "description": (
            "Build back-end services, automation scripts and APIs with Python, "
            "and keep them tested and version controlled."
        ),
        "skills": [
            ("Python", "Programming", 1),
            ("Data Structures", "Computer Science", 1),
            ("SQL", "Database", 1),
            ("Flask", "Web Development", 1),
            ("Git & GitHub", "Tools", 0),
            ("Unit Testing", "Tools", 0),
        ],
    },
    {
        "title": "Web Developer",
        "description": (
            "Create responsive websites and web applications using HTML, CSS "
            "and JavaScript, working with real data from an API."
        ),
        "skills": [
            ("HTML", "Web Development", 1),
            ("CSS", "Web Development", 1),
            ("JavaScript", "Web Development", 1),
            ("REST APIs", "Web Development", 1),
            ("Git & GitHub", "Tools", 0),
            ("SQL", "Database", 0),
        ],
    },
    {
        "title": "Data Analyst",
        "description": (
            "Turn raw data into clear answers and charts using SQL, "
            "spreadsheets and Python."
        ),
        "skills": [
            ("SQL", "Database", 1),
            ("Excel", "Data & Analytics", 1),
            ("Statistics", "Data & Analytics", 1),
            ("Data Visualisation", "Data & Analytics", 1),
            ("Python", "Programming", 0),
            ("NumPy & Pandas", "AI & Data", 0),
        ],
    },
    {
        "title": "AI/ML Engineer",
        "description": (
            "Train, evaluate and use machine learning models, from cleaning "
            "the data to explaining how well a model works."
        ),
        "skills": [
            ("Python", "Programming", 1),
            ("Machine Learning", "AI & Data", 1),
            ("Statistics", "Data & Analytics", 1),
            ("NumPy & Pandas", "AI & Data", 1),
            ("Deep Learning", "AI & Data", 0),
            ("Data Visualisation", "Data & Analytics", 0),
        ],
    },
    {
        "title": "Cybersecurity Analyst",
        "description": (
            "Protect systems and networks: understand how attacks work, "
            "harden machines and spot unusual activity."
        ),
        "skills": [
            ("Networking", "Security", 1),
            ("Linux", "Tools", 1),
            ("Security Basics", "Security", 1),
            ("Cybersecurity", "Security", 1),
            ("Python", "Programming", 0),
            ("SQL", "Database", 0),
        ],
    },
]

# An assessment gives extra insight for a skill when its title matches.
# The assessment never changes the skill's status: the student decides that.
ASSESSMENT_FOR_SKILL = {
    "Python": "Python",
    "C++": "C++",
    "Java": "Java",
    "HTML": "HTML and CSS",
    "CSS": "HTML and CSS",
    "JavaScript": "JavaScript",
    "SQL": "SQL",
    "Data Structures": "Basic Programming Concepts",
    "REST APIs": "Web Development",
    "HTML and CSS": "HTML and CSS",
    "Web Development": "Web Development",
    "Basic Programming Concepts": "Basic Programming Concepts",
}


def ensure_career_seed_data(db):
    """Insert missing careers, skills and career-skill links (safe to repeat).

    Existing rows are updated in place, never deleted, so a student's saved
    career choice, skills and assessment history are preserved.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        for career in CAREER_CATALOGUE:
            db.execute(
                "INSERT OR IGNORE INTO careers (title, description) VALUES (?, ?)",
                (career["title"], career["description"]),
            )
            # Keep the description in step with this file.
            db.execute(
                "UPDATE careers SET description = ? WHERE title = ?",
                (career["description"], career["title"]),
            )
            career_row = db.execute(
                "SELECT id FROM careers WHERE title = ?", (career["title"],)
            ).fetchone()
            career_id = career_row["id"]

            for name, category, is_core in career["skills"]:
                # Make sure the skill itself exists in the master list.
                db.execute(
                    "INSERT OR IGNORE INTO skills (name, category) VALUES (?, ?)",
                    (name, category),
                )
                skill_row = db.execute(
                    "SELECT id FROM skills WHERE name = ?", (name,)
                ).fetchone()
                db.execute(
                    "INSERT OR IGNORE INTO career_skills (career_id, skill_id, is_core) "
                    "VALUES (?, ?, ?)",
                    (career_id, skill_row["id"], is_core),
                )
                db.execute(
                    "UPDATE career_skills SET is_core = ? "
                    "WHERE career_id = ? AND skill_id = ?",
                    (is_core, career_id, skill_row["id"]),
                )
        db.commit()
    except Exception:
        db.rollback()
        raise


def selected_career_id(db, user_id):
    """Return the career id this student picked, or None."""
    row = db.execute(
        "SELECT selected_career_id FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["selected_career_id"] if row else None


def latest_assessment_scores(db, user_id):
    """Return {assessment title: latest result row} for one student."""
    rows = db.execute(
        """
        SELECT a.title, r.percentage, r.weak_topics
        FROM assessment_results r
        JOIN assessments a ON a.id = r.assessment_id
        WHERE r.user_id = ?
          AND r.id = (
              SELECT MAX(r2.id) FROM assessment_results r2
              WHERE r2.user_id = r.user_id AND r2.assessment_id = r.assessment_id
          )
        """,
        (user_id,),
    ).fetchall()
    return {row["title"]: row for row in rows}


def build_skill_gap(db, user_id, career_id):
    """Compare one student's skills with one career. Returns None if unknown.

    Every number here comes from the database: the career's required skills,
    the student's own skill rows, and their latest assessment scores.
    """
    career = db.execute(
        "SELECT id, title, description FROM careers WHERE id = ?", (career_id,)
    ).fetchone()
    if not career:
        return None

    rows = db.execute(
        """
        SELECT s.name, s.category, cs.is_core, us.status
        FROM career_skills cs
        JOIN skills s ON s.id = cs.skill_id
        LEFT JOIN user_skills us
               ON us.skill_id = cs.skill_id AND us.user_id = ?
        WHERE cs.career_id = ?
        ORDER BY cs.is_core DESC, s.category, s.name
        """,
        (user_id, career_id),
    ).fetchall()

    scores = latest_assessment_scores(db, user_id)
    items = []
    earned = 0.0
    possible = 0
    counts = {"Acquired": 0, "Learning": 0, "Missing": 0}

    for row in rows:
        status = row["status"] or "Missing"
        weight = CORE_WEIGHT if row["is_core"] else SUPPORTING_WEIGHT
        earned += weight * STATUS_SCORE.get(status, 0.0)
        possible += weight
        counts[status] += 1

        # Extra insight only: the latest score for a matching assessment.
        assessment = scores.get(ASSESSMENT_FOR_SKILL.get(row["name"], ""))
        items.append(
            {
                "name": row["name"],
                "category": row["category"],
                "is_core": bool(row["is_core"]),
                "status": status,
                "weight": weight,
                "assessment_percentage": (
                    round(assessment["percentage"]) if assessment else None
                ),
                "weak_topics": assessment["weak_topics"] if assessment else "",
            }
        )

    percentage = round((earned / possible) * 100) if possible else 0

    missing_core = [
        item["name"] for item in items if item["status"] == "Missing" and item["is_core"]
    ]
    missing_other = [
        item["name"]
        for item in items
        if item["status"] == "Missing" and not item["is_core"]
    ]
    learning = [item["name"] for item in items if item["status"] == "Learning"]

    recommendations = []
    if missing_core:
        recommendations.append(
            "Start with the core skills your career needs: "
            + ", ".join(missing_core)
            + "."
        )
    if missing_other:
        recommendations.append(
            "Then add these supporting skills: " + ", ".join(missing_other) + "."
        )
    if learning:
        recommendations.append(
            "Finish what you have already started and mark it Acquired when you "
            "feel confident: " + ", ".join(learning) + "."
        )
    if not recommendations:
        recommendations.append(
            "Every required skill is marked Acquired. Keep practising with real "
            "projects so the knowledge stays fresh."
        )

    return {
        "career": career,
        # Named "skills", not "items": in Jinja, gap.items would return the
        # dictionary's items() method instead of this list.
        "skills": items,
        "percentage": percentage,
        "required_count": len(items),
        "core_count": sum(1 for item in items if item["is_core"]),
        "counts": counts,
        "missing_core": missing_core,
        "missing_other": missing_other,
        "learning": learning,
        "recommendations": recommendations,
    }


@career_bp.route("/career", methods=["GET", "POST"])
@login_required
def choose_career():
    """Show the five career paths and save the one the student picks."""
    db = get_db()
    user_id = current_user.id

    if request.method == "POST":
        try:
            career_id = int(request.form.get("career_id", ""))
        except (TypeError, ValueError):
            career_id = 0
        career = db.execute(
            "SELECT id, title FROM careers WHERE id = ?", (career_id,)
        ).fetchone()
        if not career:
            flash("Choose one of the careers in the list.", "error")
        else:
            # The profile row always exists for a registered user; INSERT OR
            # IGNORE keeps this safe for accounts created before Phase 3.
            db.execute(
                "INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,)
            )
            # The roadmap with the same title follows the career, so the
            # student's plan and target stay in step (Phase 6).
            db.execute(
                """UPDATE user_profiles
                   SET selected_career_id = ?,
                       selected_roadmap_id = (
                           SELECT id FROM roadmaps WHERE title = ?
                       ),
                       updated_at = datetime('now')
                   WHERE user_id = ?""",
                (career_id, career["title"], user_id),
            )
            db.commit()
            log_activity(
                user_id,
                "career",
                f"Selected {career['title']} as the target career",
            )
            flash(f"{career['title']} is now your target career.", "success")
            return redirect(url_for("career.skill_gap"))

    careers = db.execute(
        """
        SELECT c.id, c.title, c.description,
               COUNT(cs.id) AS skill_count,
               COALESCE(SUM(CASE WHEN cs.is_core = 1 THEN 1 ELSE 0 END), 0) AS core_count
        FROM careers c
        LEFT JOIN career_skills cs ON cs.career_id = c.id
        GROUP BY c.id
        ORDER BY c.id
        """
    ).fetchall()

    selected_id = selected_career_id(db, user_id)
    selected = next((item for item in careers if item["id"] == selected_id), None)
    gap = build_skill_gap(db, user_id, selected_id) if selected else None

    return render_template(
        "dashboard/career.html", careers=careers, selected=selected, gap=gap
    )


@career_bp.route("/skill-gap")
@login_required
def skill_gap():
    """Show the skill gap for the career this student selected."""
    db = get_db()
    user_id = current_user.id
    career_id = selected_career_id(db, user_id)

    if not career_id:
        flash("Choose a career path to see your skill gap.", "info")
        return redirect(url_for("career.choose_career"))

    gap = build_skill_gap(db, user_id, career_id)
    if not gap:
        # The saved career no longer exists (for example after a manual edit).
        flash("That career is no longer available. Please choose another one.", "error")
        return redirect(url_for("career.choose_career"))

    return render_template("dashboard/skill_gap.html", gap=gap)
