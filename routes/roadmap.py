"""
routes/roadmap.py - Phase 6: career roadmaps.

Each career path has an ordered list of learning steps. A student follows the
roadmap for the career they picked and ticks steps off as they finish them.

Progress is always calculated from the database:
    percentage = completed steps / total steps
Only a step that belongs to the student's current roadmap can be changed, and
the completed steps of one student are never visible to another.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

roadmap_bp = Blueprint("roadmap", __name__)

# Predefined roadmaps, shared by every student. Each step is
# (title, description), written in the order it should be learned.
ROADMAP_CATALOGUE = [
    {
        "title": "Python Developer",
        "description": (
            "From Python syntax to a deployed project: the path most students "
            "follow to start writing back-end code professionally."
        ),
        "steps": [
            ("Python Fundamentals", "Variables, data types, conditions, loops, functions and files."),
            ("Object-Oriented Programming", "Classes, objects, inheritance and writing reusable code."),
            ("Data Structures and Algorithms", "Lists, stacks, queues, searching, sorting and complexity."),
            ("SQL and Database Management", "Tables, keys, joins and reading data from SQLite or PostgreSQL."),
            ("Flask or Django", "Build a small web application with routes, forms and templates."),
            ("Practical Projects", "Two or three real projects that use a database and handle errors."),
            ("Git and GitHub", "Branches, commits, pull requests and a tidy repository history."),
            ("Deployment", "Put a project online and keep configuration and secrets out of the code."),
        ],
    },
    {
        "title": "Web Developer",
        "description": (
            "Build responsive, accessible websites that fetch real data and "
            "can be shared with a live link."
        ),
        "steps": [
            ("HTML and CSS Fundamentals", "Page structure, semantic elements, selectors and the box model."),
            ("Responsive Layouts", "Flexbox, grid and media queries for phones, tablets and desktops."),
            ("JavaScript Basics", "Variables, functions, arrays, objects and strict equality."),
            ("The DOM and Browser Events", "Select elements, react to clicks and update the page safely."),
            ("Working with APIs", "Fetch JSON, handle loading and error states, and render the data."),
            ("Version Control with Git", "Commit meaningful changes and publish the project on GitHub."),
            ("Deploying a Website", "Host the site online, check the live pages and fix broken links."),
        ],
    },
    {
        "title": "Data Analyst",
        "description": (
            "Turn raw data into clear answers: clean it, question it, "
            "visualise it and explain what it means."
        ),
        "steps": [
            ("Spreadsheet Basics", "Sort, filter, pivot and use formulas in a spreadsheet."),
            ("SQL for Analysis", "SELECT, WHERE, GROUP BY, joins and aggregate functions."),
            ("Statistics Essentials", "Mean, median, spread, probability and reading a chart honestly."),
            ("Data Cleaning with Python", "Handle missing values, duplicates and wrong types with pandas."),
            ("Data Visualisation", "Choose the right chart and label axes so the message is obvious."),
            ("Exploratory Data Analysis", "Ask questions of a dataset and check your assumptions."),
            ("Presenting Insights", "Write a short, honest summary with the numbers that support it."),
        ],
    },
    {
        "title": "AI/ML Engineer",
        "description": (
            "Understand the maths behind machine learning, train and evaluate "
            "models, and explain their limits."
        ),
        "steps": [
            ("Python for Machine Learning", "Functions, NumPy arrays and the Jupyter workflow."),
            ("Mathematics for ML", "Vectors, matrices, derivatives and basic probability."),
            ("Data Preparation with NumPy and Pandas", "Load, clean, scale and split a dataset."),
            ("Core Machine Learning Algorithms", "Linear regression, logistic regression, trees and k-means."),
            ("Model Evaluation", "Train/test splits, accuracy, precision, recall and overfitting."),
            ("Deep Learning Basics", "Neural networks, layers, activation functions and training loops."),
            ("An End-to-End ML Project", "Frame a problem, build the model, evaluate it and report honestly."),
        ],
    },
    {
        "title": "Cybersecurity Analyst",
        "description": (
            "Learn how systems are attacked and defended, then practise the "
            "habits that keep them safe."
        ),
        "steps": [
            ("Networking Fundamentals", "IP addresses, DNS, ports, TCP/IP and how a request travels."),
            ("Linux Command Line", "Files, permissions, processes and reading system logs."),
            ("Security Fundamentals", "Confidentiality, integrity, availability and the CIA-based mindset."),
            ("Common Attacks and Defences", "Phishing, injection, weak passwords and how to stop each one."),
            ("Web Application Security", "Authentication, sessions, input validation and the OWASP basics."),
            ("Monitoring and Log Analysis", "Spot unusual activity and understand what a log line proves."),
            ("Security Practice Project", "Harden a small system and document what you changed and why."),
        ],
    },
]


def ensure_roadmap_seed_data(db):
    """Insert missing roadmaps and steps (safe to repeat).

    Existing roadmaps and steps are updated in place and never deleted, so a
    student's completed steps stay valid across restarts and upgrades.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        for roadmap in ROADMAP_CATALOGUE:
            db.execute(
                "INSERT OR IGNORE INTO roadmaps (title, description) VALUES (?, ?)",
                (roadmap["title"], roadmap["description"]),
            )
            db.execute(
                "UPDATE roadmaps SET description = ? WHERE title = ?",
                (roadmap["description"], roadmap["title"]),
            )
            roadmap_row = db.execute(
                "SELECT id FROM roadmaps WHERE title = ?", (roadmap["title"],)
            ).fetchone()
            roadmap_id = roadmap_row["id"]

            for index, (title, description) in enumerate(roadmap["steps"], start=1):
                db.execute(
                    "INSERT OR IGNORE INTO roadmap_steps "
                    "(roadmap_id, step_number, title, description) VALUES (?, ?, ?, ?)",
                    (roadmap_id, index, title, description),
                )
                db.execute(
                    "UPDATE roadmap_steps SET title = ?, description = ? "
                    "WHERE roadmap_id = ? AND step_number = ?",
                    (title, description, roadmap_id, index),
                )
        db.commit()
    except Exception:
        db.rollback()
        raise


def current_roadmap_id(db, user_id):
    """Return the roadmap this student follows, or None.

    The roadmap is normally saved when a career is chosen. If only a career
    was saved (an account created in Phase 5), the roadmap with the same title
    is used, so a student never loses their roadmap by upgrading.
    """
    row = db.execute(
        """SELECT selected_roadmap_id, selected_career_id
           FROM user_profiles WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    if not row:
        return None
    roadmap_id = row["selected_roadmap_id"]
    if not roadmap_id and row["selected_career_id"]:
        match = db.execute(
            """SELECT r.id FROM roadmaps r
               JOIN careers c ON c.title = r.title
               WHERE c.id = ?""",
            (row["selected_career_id"],),
        ).fetchone()
        roadmap_id = match["id"] if match else None
    return roadmap_id


def build_roadmap_view(db, user_id, roadmap_id):
    """Build the roadmap page data for one student. Returns None if unknown."""
    roadmap = db.execute(
        "SELECT id, title, description FROM roadmaps WHERE id = ?", (roadmap_id,)
    ).fetchone()
    if not roadmap:
        return None

    steps = db.execute(
        """
        SELECT rs.id, rs.step_number, rs.title, rs.description, urs.completed_at
        FROM roadmap_steps rs
        LEFT JOIN user_roadmap_steps urs
               ON urs.step_id = rs.id AND urs.user_id = ?
        WHERE rs.roadmap_id = ?
        ORDER BY rs.step_number
        """,
        (user_id, roadmap_id),
    ).fetchall()

    total = len(steps)
    completed = sum(1 for step in steps if step["completed_at"])
    # Round half up, so 1 of 8 shows 13% rather than Python's banker's 12%.
    percentage = (completed * 100 + total // 2) // total if total else 0
    next_step = next((step for step in steps if not step["completed_at"]), None)

    return {
        "roadmap": roadmap,
        "steps": steps,
        "total": total,
        "completed": completed,
        "remaining": total - completed,
        "percentage": percentage,
        "next_step": next_step,
    }


def _chosen_roadmap(db, user_id):
    """Return the student's roadmap row, or None when nothing is chosen."""
    roadmap_id = current_roadmap_id(db, user_id)
    return build_roadmap_view(db, user_id, roadmap_id) if roadmap_id else None


@roadmap_bp.route("/roadmap")
@login_required
def view_roadmap():
    """Show the student's roadmap and every step with its state."""
    db = get_db()
    view = _chosen_roadmap(db, current_user.id)

    roadmaps = db.execute(
        """
        SELECT r.id, r.title, r.description, COUNT(rs.id) AS step_count
        FROM roadmaps r
        LEFT JOIN roadmap_steps rs ON rs.roadmap_id = r.id
        GROUP BY r.id
        ORDER BY r.id
        """
    ).fetchall()

    return render_template("dashboard/roadmap.html", view=view, roadmaps=roadmaps)


@roadmap_bp.route("/roadmap/select", methods=["POST"])
@login_required
def select_roadmap():
    """Save the roadmap a student wants to follow."""
    db = get_db()
    user_id = current_user.id

    try:
        roadmap_id = int(request.form.get("roadmap_id", ""))
    except (TypeError, ValueError):
        roadmap_id = 0

    roadmap = db.execute(
        "SELECT id, title FROM roadmaps WHERE id = ?", (roadmap_id,)
    ).fetchone()
    if not roadmap:
        flash("Choose one of the roadmaps in the list.", "error")
        return redirect(url_for("roadmap.view_roadmap"))

    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
    db.execute(
        """
        UPDATE user_profiles
        SET selected_roadmap_id = ?,
            selected_career_id = COALESCE(
                (SELECT id FROM careers WHERE title = ?), selected_career_id
            ),
            updated_at = datetime('now')
        WHERE user_id = ?
        """,
        (roadmap_id, roadmap["title"], user_id),
    )
    db.commit()
    log_activity(user_id, "roadmap", f"Started the {roadmap['title']} roadmap")
    flash(f"{roadmap['title']} is now your roadmap.", "success")
    return redirect(url_for("roadmap.view_roadmap"))


@roadmap_bp.route("/roadmap/steps/<int:step_id>/toggle", methods=["POST"])
@login_required
def toggle_step(step_id):
    """Mark a step complete, or undo it. Only steps of the chosen roadmap."""
    db = get_db()
    user_id = current_user.id
    roadmap_id = current_roadmap_id(db, user_id)

    if not roadmap_id:
        flash("Choose a career path before marking roadmap steps.", "info")
        return redirect(url_for("roadmap.view_roadmap"))

    step = db.execute(
        "SELECT id, title FROM roadmap_steps WHERE id = ? AND roadmap_id = ?",
        (step_id, roadmap_id),
    ).fetchone()
    if not step:
        # The step exists for another roadmap, or does not exist at all.
        flash("That step is not part of your current roadmap.", "error")
        return redirect(url_for("roadmap.view_roadmap"))

    done = db.execute(
        "SELECT id FROM user_roadmap_steps WHERE user_id = ? AND step_id = ?",
        (user_id, step_id),
    ).fetchone()

    if done:
        db.execute(
            "DELETE FROM user_roadmap_steps WHERE id = ? AND user_id = ?",
            (done["id"], user_id),
        )
        db.commit()
        flash(f"'{step['title']}' is now marked as not complete.", "info")
    else:
        db.execute(
            "INSERT INTO user_roadmap_steps (user_id, step_id) VALUES (?, ?)",
            (user_id, step_id),
        )
        db.commit()
        log_activity(user_id, "roadmap", f"Completed roadmap step: {step['title']}")
        flash(f"'{step['title']}' marked as complete.", "success")

    return redirect(url_for("roadmap.view_roadmap"))
