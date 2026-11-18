"""
routes/dashboard.py - the dashboard home page. It needs a login.

Every number and list on this page is read from the database with a query
that filters on the logged-in user's id, so nobody can see another
person's records. The readiness figures come from build_readiness(), the
same function the readiness report uses, so the two pages always agree.
"""
from datetime import date, timedelta

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from routes.readiness import build_readiness
from utils.database import get_db

dashboard_bp = Blueprint("dashboard", __name__)


def count_rows(db, sql, user_id):
    """Run a "SELECT COUNT(*) ..." query for one user and return the number."""
    return db.execute(sql, (user_id,)).fetchone()[0]


@dashboard_bp.route("/dashboard")
@login_required
def home():
    db = get_db()
    user_id = current_user.id
    today = date.today()

    # --- the numbers in the summary strip ---
    total_skills = count_rows(
        db, "SELECT COUNT(*) FROM user_skills WHERE user_id = ?", user_id)
    skills_learning = count_rows(
        db, "SELECT COUNT(*) FROM user_skills WHERE user_id = ? AND status = 'Learning'", user_id)
    skills_acquired = count_rows(
        db, "SELECT COUNT(*) FROM user_skills WHERE user_id = ? AND status = 'Acquired'", user_id)
    goals_completed = count_rows(
        db, "SELECT COUNT(*) FROM goals WHERE user_id = ? AND is_completed = 1", user_id)

    # --- goals: real totals, completion percentage and overdue count ---
    goal_counts = db.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(is_completed), 0) AS completed,
               COALESCE(SUM(CASE WHEN is_completed = 0 AND target_date < ? THEN 1 ELSE 0 END), 0) AS overdue
        FROM goals
        WHERE user_id = ?
        """,
        (today.isoformat(), user_id),
    ).fetchone()
    goals_total = goal_counts["total"]
    goals_summary = {
        "total": goals_total,
        "completed": goals_completed,
        "open": goals_total - goals_completed,
        "overdue": goal_counts["overdue"],
        # Same rounding as the roadmap: 1 of 3 shows 33%, not 32%.
        "percentage": (
            (goals_completed * 100 + goals_total // 2) // goals_total
            if goals_total
            else 0
        ),
    }

    # --- latest score for each assessment the user has taken ---
    latest_scores = db.execute(
        """
        SELECT a.title, r.score, r.total_questions, r.percentage, r.taken_at
        FROM assessment_results r
        JOIN assessments a ON a.id = r.assessment_id
        WHERE r.user_id = ?
          AND r.id = (
              SELECT MAX(r2.id) FROM assessment_results r2
              WHERE r2.user_id = r.user_id AND r2.assessment_id = r.assessment_id
          )
        ORDER BY r.id DESC
        """,
        (user_id,),
    ).fetchall()

    # --- goals that are not finished and not overdue, soonest first ---
    upcoming_goals = db.execute(
        """
        SELECT title, goal_type, target_date
        FROM goals
        WHERE user_id = ? AND is_completed = 0 AND target_date >= ?
        ORDER BY target_date ASC, id ASC
        LIMIT 5
        """,
        (user_id, today.isoformat()),
    ).fetchall()

    # --- the latest few things the user did ---
    activities = db.execute(
        """
        SELECT description, created_at
        FROM activities
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 6
        """,
        (user_id,),
    ).fetchall()

    # --- a real 7-day activity count for the sparkline ---
    week_start = today - timedelta(days=6)
    week_rows = db.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
        FROM activities
        WHERE user_id = ? AND created_at >= ?
        GROUP BY day
        """,
        (user_id, week_start.isoformat() + " 00:00:00"),
    ).fetchall()
    week_counts = {row["day"]: row["total"] for row in week_rows}
    week_days = [week_start + timedelta(days=offset) for offset in range(7)]
    week_values = [week_counts.get(day.isoformat(), 0) for day in week_days]
    week_labels = [day.strftime("%a") for day in week_days]
    week_total = sum(week_values)

    # --- is the profile still missing the basics? ---
    profile = db.execute(
        "SELECT college_name, year_of_study FROM user_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    profile_incomplete = profile is None or not (profile["college_name"] and profile["year_of_study"])

    first_name = current_user.name.split()[0] if current_user.name.split() else current_user.name
    today_label = today.strftime("%A, %d %B %Y")

    # --- readiness, the target career and its roadmap (shared with the report) ---
    report = build_readiness(db, user_id)
    career_gap = report["gap"]
    roadmap_view = report["roadmap"]

    # The donut is split into the three states the skill gap already counts.
    skill_breakdown = []
    if career_gap and career_gap["required_count"]:
        skill_breakdown = [
            {"label": "Acquired", "value": career_gap["counts"]["Acquired"], "tone": "mint"},
            {"label": "Learning", "value": career_gap["counts"]["Learning"], "tone": "accent"},
            {"label": "Not started", "value": career_gap["counts"]["Missing"], "tone": "muted"},
        ]

    # One bar per assessment, using the latest score for that subject.
    score_bars = [
        {
            "label": row["title"],
            "value": int(round(row["percentage"])),
            "display": str(int(round(row["percentage"]))) + "%",
        }
        for row in latest_scores[:6]
    ]

    return render_template(
        "dashboard/home.html",
        first_name=first_name,
        today_label=today_label,
        career_gap=career_gap,
        roadmap_view=roadmap_view,
        total_skills=total_skills,
        skills_learning=skills_learning,
        skills_acquired=skills_acquired,
        goals_completed=goals_completed,
        goals_summary=goals_summary,
        latest_scores=latest_scores,
        upcoming_goals=upcoming_goals,
        activities=activities,
        profile_incomplete=profile_incomplete,
        report=report,
        skill_breakdown=skill_breakdown,
        score_bars=score_bars,
        week_values=week_values,
        week_labels=week_labels,
        week_total=week_total,
    )
