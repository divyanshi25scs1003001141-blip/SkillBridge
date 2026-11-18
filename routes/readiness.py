"""
routes/readiness.py - Phase 10: the Career Readiness Report.

The report turns data the student already has into one number, using fixed
weights that are shown on the page:

    skill coverage vs the chosen career   35%
    career roadmap completion             25%
    latest assessment scores              20%
    finished projects                     10%
    goals completed                       10%

Nothing is invented: every part is read from the database for the signed-in
user only, and each row shows the evidence behind its score. The report never
claims the student will be hired.
"""
from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from routes.career import build_skill_gap, selected_career_id
from routes.goals import progress_percentage
from routes.roadmap import build_roadmap_view, current_roadmap_id
from utils.database import get_db

readiness_bp = Blueprint("readiness", __name__)

WEIGHTS = {
    "skills": 35,
    "roadmap": 25,
    "assessments": 20,
    "projects": 10,
    "goals": 10,
}

# Three finished projects is treated as a full score for that part.
PROJECT_TARGET = 3


def readiness_band(score):
    """A plain-language label for a 0-100 score."""
    if score >= 75:
        return "Interview-ready foundations"
    if score >= 50:
        return "Building momentum"
    if score >= 25:
        return "Getting started"
    return "First steps"


def _assessment_summary(db, user_id):
    """Count of assessments taken and the average of each one's latest score."""
    row = db.execute(
        """
        SELECT COUNT(*) AS taken, COALESCE(AVG(percentage), 0) AS average
        FROM (
            SELECT r.assessment_id, r.percentage
            FROM assessment_results r
            WHERE r.user_id = ?
              AND r.id = (
                  SELECT MAX(r2.id) FROM assessment_results r2
                  WHERE r2.user_id = r.user_id
                    AND r2.assessment_id = r.assessment_id
              )
        )
        """,
        (user_id,),
    ).fetchone()
    return row["taken"], int(round(row["average"] or 0))


def build_readiness(db, user_id):
    """Return the full report data for one student."""
    career_id = selected_career_id(db, user_id)
    gap = build_skill_gap(db, user_id, career_id) if career_id else None

    roadmap_id = current_roadmap_id(db, user_id)
    roadmap = build_roadmap_view(db, user_id, roadmap_id) if roadmap_id else None

    assessments_taken, assessment_average = _assessment_summary(db, user_id)

    projects = db.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END), 0) AS completed
        FROM projects WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    project_score = (
        min(projects["completed"], PROJECT_TARGET) * 100 + PROJECT_TARGET // 2
    ) // PROJECT_TARGET

    goals = db.execute(
        """
        SELECT COUNT(*) AS total, COALESCE(SUM(is_completed), 0) AS completed
        FROM goals WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    goal_score = progress_percentage(goals["completed"], goals["total"])

    if gap:
        skill_detail = (
            f"{gap['counts']['Acquired']} of {gap['required_count']} required skills acquired"
        )
    else:
        skill_detail = "No career path selected yet"

    if roadmap:
        roadmap_detail = (
            f"{roadmap['completed']} of {roadmap['total']} roadmap steps complete"
        )
    else:
        roadmap_detail = "No roadmap selected yet"

    components = [
        {
            "key": "skills",
            "label": "Skill coverage",
            "score": gap["percentage"] if gap else 0,
            "weight": WEIGHTS["skills"],
            "detail": skill_detail,
        },
        {
            "key": "roadmap",
            "label": "Roadmap progress",
            "score": roadmap["percentage"] if roadmap else 0,
            "weight": WEIGHTS["roadmap"],
            "detail": roadmap_detail,
        },
        {
            "key": "assessments",
            "label": "Assessment results",
            "score": assessment_average,
            "weight": WEIGHTS["assessments"],
            "detail": (
                f"{assessments_taken} assessment(s) taken, latest average {assessment_average}%"
                if assessments_taken
                else "No assessments taken yet"
            ),
        },
        {
            "key": "projects",
            "label": "Finished projects",
            "score": project_score,
            "weight": WEIGHTS["projects"],
            "detail": f"{projects['completed']} completed of {projects['total']} recorded (target {PROJECT_TARGET})",
        },
        {
            "key": "goals",
            "label": "Goals completed",
            "score": goal_score,
            "weight": WEIGHTS["goals"],
            "detail": f"{goals['completed']} of {goals['total']} goals complete",
        },
    ]
    for component in components:
        component["contribution"] = component["score"] * component["weight"] / 100

    overall = (
        sum(component["score"] * component["weight"] for component in components) + 50
    ) // 100

    supporting = {
        "skills_acquired": gap["counts"]["Acquired"] if gap else 0,
        "skills_learning": gap["counts"]["Learning"] if gap else 0,
        "favourites": db.execute(
            "SELECT COUNT(*) FROM favourites WHERE user_id = ?", (user_id,)
        ).fetchone()[0],
        "resources_completed": db.execute(
            "SELECT COUNT(*) FROM resource_notes WHERE user_id = ? AND is_completed = 1",
            (user_id,),
        ).fetchone()[0],
        "projects_planned": db.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id = ? AND status = 'Planned'",
            (user_id,),
        ).fetchone()[0],
        "overdue_goals": db.execute(
            """SELECT COUNT(*) FROM goals
               WHERE user_id = ? AND is_completed = 0 AND target_date < ?""",
            (user_id, date.today().isoformat()),
        ).fetchone()[0],
    }

    next_actions = []
    if not career_id:
        next_actions.append({
            "title": "Choose a career path",
            "detail": "Readiness is measured against a target, so pick the career you are preparing for.",
            "endpoint": "career.choose_career",
            "label": "Choose career",
        })
    elif gap and gap["missing_core"]:
        next_actions.append({
            "title": f"Learn {len(gap['missing_core'])} core skill(s)",
            "detail": "Missing core skills: " + ", ".join(gap["missing_core"]) + ".",
            "endpoint": "career.skill_gap",
            "label": "Open skill gap",
        })
    if roadmap and roadmap["next_step"]:
        next_actions.append({
            "title": "Next roadmap step",
            "detail": roadmap["next_step"]["title"],
            "endpoint": "roadmap.view_roadmap",
            "label": "Open roadmap",
        })
    if supporting["overdue_goals"]:
        next_actions.append({
            "title": f"{supporting['overdue_goals']} overdue goal(s)",
            "detail": "Finish them or delete what is no longer relevant.",
            "endpoint": "goals.list_goals",
            "label": "Open goals",
        })
    if projects["completed"] < PROJECT_TARGET:
        next_actions.append({
            "title": "Finish another project",
            "detail": f"{projects['completed']} of {PROJECT_TARGET} completed projects counted.",
            "endpoint": "projects.list_projects",
            "label": "Open projects",
        })
    if not assessments_taken:
        next_actions.append({
            "title": "Take a skill assessment",
            "detail": "A score gives the assessment part of this report a real value.",
            "endpoint": "skills.assessment_list",
            "label": "Take assessment",
        })

    return {
        "career": gap["career"] if gap else None,
        "gap": gap,
        "roadmap": roadmap,
        "components": components,
        "overall": overall,
        "band": readiness_band(overall),
        "weights": WEIGHTS,
        "supporting": supporting,
        "counts": {
            "assessments_taken": assessments_taken,
            "assessment_average": assessment_average,
            "projects_total": projects["total"],
            "projects_completed": projects["completed"],
            "goals_total": goals["total"],
            "goals_completed": goals["completed"],
        },
        "next_actions": next_actions,
    }


@readiness_bp.route("/readiness")
@login_required
def report():
    db = get_db()
    return render_template(
        "dashboard/readiness.html",
        report=build_readiness(db, current_user.id),
    )
