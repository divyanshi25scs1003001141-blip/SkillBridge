"""
routes/goals.py - Phase 9: weekly and monthly learning goals.

A student sets goals with a target date, marks them complete and can reopen
one if it was ticked too early. Every query filters on the signed-in user's
id, so goals are private. All progress numbers come from these rows.
"""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

goals_bp = Blueprint("goals", __name__)

GOAL_TYPES = ["Weekly", "Monthly"]
MAX_TITLE = 120
MAX_DESCRIPTION = 500


def progress_percentage(completed, total):
    """Whole-number percentage, rounding .5 up (1 of 3 shows 33%)."""
    if not total:
        return 0
    return (completed * 100 + total // 2) // total


def _parse_date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _validate(form):
    """Return (data, errors); data can be re-shown in the form safely."""
    data = {
        "title": (form.get("title") or "").strip(),
        "description": (form.get("description") or "").strip(),
        "goal_type": (form.get("goal_type") or "").strip(),
        "target_date": (form.get("target_date") or "").strip(),
    }
    errors = []

    if not data["title"]:
        errors.append("Give your goal a title.")
    elif len(data["title"]) > MAX_TITLE:
        errors.append(f"Titles can be up to {MAX_TITLE} characters.")

    if len(data["description"]) > MAX_DESCRIPTION:
        errors.append(f"Descriptions can be up to {MAX_DESCRIPTION} characters.")

    if data["goal_type"] not in GOAL_TYPES:
        errors.append("Choose Weekly or Monthly for the goal type.")

    parsed_date = _parse_date(data["target_date"])
    if parsed_date is None:
        errors.append("Choose a target date (YYYY-MM-DD).")

    return data, errors


def _load_goals(db, user_id, today):
    rows = db.execute(
        """
        SELECT id, title, description, goal_type, target_date,
               is_completed, completed_at, created_at
        FROM goals
        WHERE user_id = ?
        ORDER BY is_completed ASC, date(target_date) ASC, id DESC
        """,
        (user_id,),
    ).fetchall()

    goals = []
    for row in rows:
        goal = dict(row)
        goal["overdue"] = goal["is_completed"] == 0 and goal["target_date"] < today
        goals.append(goal)

    open_goals = [goal for goal in goals if not goal["is_completed"]]
    completed_goals = [goal for goal in goals if goal["is_completed"]]
    by_type = {
        goal_type: [goal for goal in open_goals if goal["goal_type"] == goal_type]
        for goal_type in GOAL_TYPES
    }
    counts = {
        "total": len(goals),
        "completed": len(completed_goals),
        "open": len(open_goals),
        "overdue": sum(1 for goal in goals if goal["overdue"]),
    }
    return goals, by_type, completed_goals, counts


def _render(db, user_id, form=None):
    today = date.today().isoformat()
    goals, by_type, completed_goals, counts = _load_goals(db, user_id, today)
    return render_template(
        "dashboard/goals.html",
        goals=goals,
        by_type=by_type,
        completed_goals=completed_goals,
        counts=counts,
        percentage=progress_percentage(counts["completed"], counts["total"]),
        goal_types=GOAL_TYPES,
        today=today,
        max_title=MAX_TITLE,
        max_description=MAX_DESCRIPTION,
        form=form or {},
    )


@goals_bp.route("/goals")
@login_required
def list_goals():
    return _render(get_db(), current_user.id)


@goals_bp.route("/goals/new", methods=["POST"])
@login_required
def create_goal():
    db = get_db()
    user_id = current_user.id
    data, errors = _validate(request.form)
    if errors:
        for message in errors:
            flash(message, "error")
        return _render(db, user_id, form=data)

    db.execute(
        """INSERT INTO goals (user_id, title, description, goal_type, target_date)
           VALUES (?, ?, ?, ?, ?)""",
        (
            user_id,
            data["title"],
            data["description"],
            data["goal_type"],
            data["target_date"],
        ),
    )
    db.commit()
    log_activity(user_id, "goal", f"Added a {data['goal_type'].lower()} goal: {data['title']}")
    flash(f"Goal “{data['title']}” added.", "success")
    return redirect(url_for("goals.list_goals"))


@goals_bp.route("/goals/<int:goal_id>/complete", methods=["POST"])
@login_required
def complete_goal(goal_id):
    db = get_db()
    user_id = current_user.id

    goal = db.execute(
        "SELECT id, title, is_completed FROM goals WHERE id = ? AND user_id = ?",
        (goal_id, user_id),
    ).fetchone()
    if not goal:
        flash("That goal could not be found.", "error")
        return redirect(url_for("goals.list_goals"))

    if goal["is_completed"]:
        flash(f"“{goal['title']}” is already complete.", "info")
        return redirect(url_for("goals.list_goals"))

    db.execute(
        """UPDATE goals
           SET is_completed = 1, completed_at = datetime('now')
           WHERE id = ? AND user_id = ?""",
        (goal_id, user_id),
    )
    db.commit()
    log_activity(user_id, "goal", f"Completed a goal: {goal['title']}")
    flash(f"“{goal['title']}” marked complete.", "success")
    return redirect(url_for("goals.list_goals"))


@goals_bp.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    """Delete one of this student's own goals."""
    db = get_db()
    user_id = current_user.id

    goal = db.execute(
        "SELECT title FROM goals WHERE id = ? AND user_id = ?",
        (goal_id, user_id),
    ).fetchone()
    if not goal:
        flash("That goal could not be found.", "error")
        return redirect(url_for("goals.list_goals"))

    db.execute("DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, user_id))
    db.commit()
    log_activity(user_id, "goal", f"Deleted a goal: {goal['title']}")
    flash(f"Goal “{goal['title']}” deleted.", "info")
    return redirect(url_for("goals.list_goals"))


@goals_bp.route("/goals/<int:goal_id>/reopen", methods=["POST"])
@login_required
def reopen_goal(goal_id):
    db = get_db()
    user_id = current_user.id

    goal = db.execute(
        "SELECT id, title, is_completed FROM goals WHERE id = ? AND user_id = ?",
        (goal_id, user_id),
    ).fetchone()
    if not goal:
        flash("That goal could not be found.", "error")
        return redirect(url_for("goals.list_goals"))

    if not goal["is_completed"]:
        flash(f"“{goal['title']}” is already open.", "info")
        return redirect(url_for("goals.list_goals"))

    db.execute(
        """UPDATE goals
           SET is_completed = 0, completed_at = NULL
           WHERE id = ? AND user_id = ?""",
        (goal_id, user_id),
    )
    db.commit()
    log_activity(user_id, "goal", f"Reopened a goal: {goal['title']}")
    flash(f"“{goal['title']}” reopened.", "success")
    return redirect(url_for("goals.list_goals"))
