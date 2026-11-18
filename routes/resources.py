"""
routes/resources.py - Phase 7: learning resources.

Every resource is predefined, free and links to a real public website that
students can open without an account. Students can search by keyword, filter
by skill category and difficulty, and save resources to their own favourites.

Favourites are private: every query filters on the signed-in user's id.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

resources_bp = Blueprint("resources", __name__)

# A private note is short by design: enough for what you learned or want to
# revisit, never a place to paste an entire tutorial.
NOTE_MAX_LENGTH = 500

DIFFICULTIES = ["Beginner", "Intermediate", "Advanced"]
DIFFICULTY_ORDER = {name: index for index, name in enumerate(DIFFICULTIES)}

# Every resource type used by the catalogue, in display order.
RESOURCE_TYPES = [
    "Documentation",
    "Tutorial",
    "Video",
    "Course",
    "Book",
    "Practice",
    "Reference",
    "Guide",
    "Visualisation",
]

# Predefined catalogue. Each entry is
# (title, url, category, difficulty, resource_type, description).
# Every URL is a real, free, publicly readable page.
RESOURCE_CATALOGUE = [
    # --- Python ---
    ("The Python Tutorial (official)", "https://docs.python.org/3/tutorial/", "Python", "Beginner",
     "Documentation", "The official tour of the language: types, control flow, functions and modules."),
    ("Automate the Boring Stuff with Python", "https://automatetheboringstuff.com/", "Python", "Beginner",
     "Book", "A free book that teaches Python through small, useful scripts."),
    ("CS50's Introduction to Programming with Python", "https://cs50.harvard.edu/python/", "Python", "Beginner",
     "Course", "Harvard's free Python course with lectures, notes and problem sets."),
    ("Real Python tutorials", "https://realpython.com/", "Python", "Intermediate",
     "Tutorial", "Practical, example-driven articles on everyday Python topics."),
    ("Flask Quickstart", "https://flask.palletsprojects.com/en/stable/quickstart/", "Python", "Intermediate",
     "Documentation", "Build a small Flask application with routes, templates and forms."),

    # --- C++ ---
    ("cplusplus.com C++ Tutorial", "https://cplusplus.com/doc/tutorial/", "C++", "Beginner",
     "Tutorial", "A step-by-step C++ tutorial covering syntax, functions, classes and pointers."),
    ("Microsoft C++ documentation", "https://learn.microsoft.com/en-us/cpp/cpp/", "C++", "Intermediate",
     "Documentation", "Reference material for modern C++ language features and the standard library."),
    ("cppreference", "https://en.cppreference.com/w/", "C++", "Advanced",
     "Reference", "Precise reference for C++ language rules and library components."),

    # --- Java ---
    ("dev.java: Learn Java", "https://dev.java/learn/", "Java", "Beginner",
     "Tutorial", "The official Java learning path, starting from your first class."),
    ("Java Tutorials (Oracle)", "https://docs.oracle.com/javase/tutorial/", "Java", "Intermediate",
     "Documentation", "Long-running official tutorials on the language and its core libraries."),

    # --- HTML and CSS ---
    ("MDN: Structuring content with HTML", "https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Structuring_content", "HTML and CSS", "Beginner",
     "Tutorial", "How pages are structured with headings, lists, links, images and semantic elements."),
    ("MDN: CSS styling basics", "https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Styling_basics", "HTML and CSS", "Beginner",
     "Tutorial", "Selectors, the box model, colours, fonts and simple layouts."),
    ("web.dev: Learn CSS", "https://web.dev/learn/css", "HTML and CSS", "Intermediate",
     "Course", "A structured CSS course covering layout, responsive design and modern features."),
    ("Frontend Mentor challenges", "https://www.frontendmentor.io/challenges", "HTML and CSS", "Intermediate",
     "Practice", "Free design-to-code challenges with starter files and community feedback."),

    # --- JavaScript ---
    ("MDN JavaScript Guide", "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide", "JavaScript", "Beginner",
     "Documentation", "The language guide: values, functions, objects, promises and modules."),
    ("javascript.info", "https://javascript.info/", "JavaScript", "Beginner",
     "Tutorial", "A modern, free JavaScript tutorial that explains the language from scratch."),
    ("Eloquent JavaScript", "https://eloquentjavascript.net/", "JavaScript", "Intermediate",
     "Book", "A free book on JavaScript, programming practice and browser projects."),

    # --- Web Development ---
    ("MDN: Learn web development", "https://developer.mozilla.org/en-US/docs/Learn_web_development", "Web Development", "Beginner",
     "Course", "A complete beginner path through HTML, CSS, JavaScript and the web platform."),
    ("The Odin Project", "https://www.theodinproject.com/", "Web Development", "Beginner",
     "Course", "A free, project-based full-stack web development curriculum."),
    ("Full Stack Open", "https://fullstackopen.com/en/", "Web Development", "Advanced",
     "Course", "A free university course on modern JavaScript-based web development."),

    # --- SQL ---
    ("SQLBolt", "https://sqlbolt.com/", "SQL", "Beginner",
     "Tutorial", "Interactive lessons that teach SELECT, filtering, joins and aggregation."),
    ("PostgreSQL Tutorial", "https://www.postgresql.org/docs/current/tutorial.html", "SQL", "Intermediate",
     "Documentation", "The official walkthrough of creating tables and querying a relational database."),
    ("SQLite SQL syntax reference", "https://www.sqlite.org/lang.html", "SQL", "Intermediate",
     "Reference", "The exact SQL syntax SQLite accepts, useful for small projects."),

    # --- Data Structures and Algorithms ---
    ("VisuAlgo", "https://visualgo.net/en", "Data Structures and Algorithms", "Beginner",
     "Visualisation", "Animated visualisations of sorting, searching, trees, graphs and more."),
    ("cp-algorithms", "https://cp-algorithms.com/", "Data Structures and Algorithms", "Advanced",
     "Reference", "Explanations and proofs for classic algorithms and data structures."),
    ("MIT 6.006 Introduction to Algorithms", "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/", "Data Structures and Algorithms", "Advanced",
     "Course", "Free MIT lectures and problem sets on algorithms and complexity."),

    # --- Machine Learning ---
    ("scikit-learn: Getting started", "https://scikit-learn.org/stable/getting_started.html", "Machine Learning", "Intermediate",
     "Documentation", "Fit your first model and learn the fit/predict workflow."),
    ("Kaggle Learn", "https://www.kaggle.com/learn", "Machine Learning", "Beginner",
     "Course", "Short, free micro-courses on Python, pandas, data visualisation and ML."),
    ("fast.ai: Practical Deep Learning", "https://course.fast.ai/", "Machine Learning", "Advanced",
     "Course", "A free course that teaches deep learning through working code first."),
    ("NumPy: Absolute Beginners guide", "https://numpy.org/doc/stable/user/absolute_beginners.html", "Machine Learning", "Beginner",
     "Documentation", "How arrays work and how to do fast numerical work in Python."),
    ("pandas: 10 minutes to pandas", "https://pandas.pydata.org/docs/user_guide/10min.html", "Machine Learning", "Beginner",
     "Documentation", "A quick tour of loading, filtering and summarising tabular data."),

    # --- Data Analytics ---
    ("Khan Academy: Statistics and probability", "https://www.khanacademy.org/math/statistics-probability", "Data Analytics", "Beginner",
     "Course", "Free lessons on averages, spread, probability and statistical reasoning."),
    ("Data-to-Viz chart guide", "https://www.data-to-viz.com/", "Data Analytics", "Intermediate",
     "Guide", "Which chart to use for which kind of data, with examples."),

    # --- Cybersecurity ---
    ("OWASP Top Ten", "https://owasp.org/www-project-top-ten/", "Cybersecurity", "Intermediate",
     "Documentation", "The ten most common web application security risks and how to avoid them."),
    ("PortSwigger Web Security Academy", "https://portswigger.net/web-security", "Cybersecurity", "Intermediate",
     "Practice", "Free labs and reading on web security vulnerabilities."),
    ("picoCTF", "https://picoctf.org/", "Cybersecurity", "Beginner",
     "Practice", "Beginner-friendly capture-the-flag challenges and learning materials."),

    # --- Networking ---
    ("Cloudflare Learning Center", "https://www.cloudflare.com/learning/", "Networking", "Beginner",
     "Guide", "Plain-language explanations of DNS, IP, TCP/IP and how the internet works."),

    # --- Linux ---
    ("Linux Journey", "https://linuxjourney.com/", "Linux", "Beginner",
     "Tutorial", "Free lessons on the command line, file permissions and processes."),
    ("OverTheWire: Bandit", "https://overthewire.org/wargames/bandit/", "Linux", "Beginner",
     "Practice", "Learn Linux commands by solving small remote challenges."),
    ("Ubuntu tutorials", "https://ubuntu.com/tutorials", "Linux", "Intermediate",
     "Tutorial", "Step-by-step guides for common Linux tasks and server setup."),

    # --- Video tutorials (free, public YouTube channels and playlists) ---
    ("Python Full Course for Beginners (freeCodeCamp)", "https://www.youtube.com/watch?v=rfscVS0vtbw", "Python", "Beginner",
     "Video", "A complete beginner Python course: syntax, loops, functions, files and classes."),
    ("Python for Beginners (Programming with Mosh)", "https://www.youtube.com/watch?v=kqtD5dpn9C8", "Python", "Beginner",
     "Video", "A one-hour Python crash course that ends with a small project."),
    ("Learn JavaScript - Full Course for Beginners", "https://www.youtube.com/watch?v=PkZNo7MFNFg", "JavaScript", "Beginner",
     "Video", "JavaScript from scratch: variables, functions, objects, the DOM and APIs."),
    ("HTML Full Course for Beginners", "https://www.youtube.com/watch?v=pQN-pnXPaVg", "HTML and CSS", "Beginner",
     "Video", "Build your first web pages and learn how HTML structures content."),
    ("SQL Tutorial - Full Database Course for Beginners", "https://www.youtube.com/watch?v=HXV3zeQKqGY", "SQL", "Beginner",
     "Video", "Database basics, SELECT queries, joins and designing a small schema."),
    ("C++ Tutorial for Beginners", "https://www.youtube.com/watch?v=vLnPwxZdW4Y", "C++", "Beginner",
     "Video", "C++ syntax, functions, classes, pointers and file handling."),
    ("Java Tutorial for Beginners (Programming with Mosh)", "https://www.youtube.com/watch?v=eIrMbAQSU34", "Java", "Beginner",
     "Video", "Java fundamentals with classes, objects and a small project."),
    ("Data Structures - Easy to Advanced", "https://www.youtube.com/watch?v=RBSGKlAvoiM", "Data Structures and Algorithms", "Advanced",
     "Video", "A long-form course on arrays, trees, heaps, graphs and algorithm analysis."),
    ("Machine Learning for Everybody", "https://www.youtube.com/watch?v=i_LwzRVP7bg", "Machine Learning", "Intermediate",
     "Video", "A practical tour of ML models with scikit-learn and real datasets."),
    ("Neural Networks (3Blue1Brown series)", "https://www.youtube.com/playlist?list=PLZHQObOWTQDNU6R1_67000Dx_ZCJB-3pi", "Machine Learning", "Advanced",
     "Video", "Visual explanations of how neural networks learn, step by step."),
    ("Complete Pandas Data Science Tutorial", "https://www.youtube.com/watch?v=vmEHCJofslg", "Data Analytics", "Intermediate",
     "Video", "Load, clean, group and visualise data with pandas in one walkthrough."),
    ("Git and GitHub for Beginners", "https://www.youtube.com/watch?v=RGOj5yH7evk", "Git & GitHub", "Beginner",
     "Video", "Version control basics: commits, branches, remotes and pull requests."),
    ("CS50 lectures (YouTube)", "https://www.youtube.com/@cs50", "Web Development", "Beginner",
     "Video", "Harvard's full CS50 computer science lectures, free to watch."),
    ("OWASP Global (YouTube)", "https://www.youtube.com/@OWASPGLOBAL", "Cybersecurity", "Intermediate",
     "Video", "Talks and walkthroughs on web application security risks."),

    # --- Git and GitHub ---
    ("Pro Git (free book)", "https://git-scm.com/book/en/v2", "Git & GitHub", "Beginner",
     "Book", "The official free book on version control with Git."),
    ("GitHub Docs: Get started", "https://docs.github.com/en/get-started", "Git & GitHub", "Beginner",
     "Documentation", "Create a repository, commit, branch and open your first pull request."),
]


def ensure_resource_seed_data(db):
    """Insert missing resources (safe to repeat).

    The URL is the stable key: an existing row is updated in place, so fixes
    to a title or description never create duplicates or break favourites.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        for title, url, category, difficulty, resource_type, description in RESOURCE_CATALOGUE:
            db.execute(
                """INSERT OR IGNORE INTO resources
                   (title, url, category, description, resource_type, difficulty)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (title, url, category, description, resource_type, difficulty),
            )
            db.execute(
                """UPDATE resources
                   SET title = ?, category = ?, description = ?,
                       resource_type = ?, difficulty = ?
                   WHERE url = ?""",
                (title, category, description, resource_type, difficulty, url),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


def _filters_from(source):
    """Read the filter values from the form or the URL query string."""
    saved = source.get("saved", "")
    resource_type = (source.get("resource_type") or "").strip()
    return {
        "q": (source.get("q") or "").strip()[:100],
        "category": (source.get("category") or "").strip()[:80],
        "difficulty": (source.get("difficulty") or "").strip(),
        "resource_type": resource_type[:40] if resource_type in RESOURCE_TYPES else "",
        "saved": "1" if saved == "1" else "",
    }


def _list_url(filters):
    """Build the resources URL for these filters, leaving empty values out."""
    values = {key: value for key, value in filters.items() if value}
    return url_for("resources.list_resources", **values)


@resources_bp.route("/resources")
@login_required
def list_resources():
    """Browse, search and filter the resources; save and remove favourites."""
    db = get_db()
    user_id = current_user.id
    filters = _filters_from(request.args)

    conditions = []
    # The first two parameters belong to the two LEFT JOINs.
    params = [user_id, user_id]
    if filters["saved"] == "1":
        conditions.append("f.id IS NOT NULL")
    if filters["category"]:
        conditions.append("r.category = ?")
        params.append(filters["category"])
    if filters["difficulty"] in DIFFICULTIES:
        conditions.append("r.difficulty = ?")
        params.append(filters["difficulty"])
    if filters["resource_type"]:
        conditions.append("r.resource_type = ?")
        params.append(filters["resource_type"])
    if filters["q"]:
        conditions.append(
            "(r.title LIKE ? OR r.description LIKE ? OR r.category LIKE ?)"
        )
        term = f"%{filters['q']}%"
        params.extend([term, term, term])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    resources = db.execute(
        f"""
        SELECT r.id, r.title, r.url, r.category, r.description,
               r.resource_type, r.difficulty,
               CASE WHEN f.id IS NULL THEN 0 ELSE 1 END AS is_favourite,
               COALESCE(n.note, '') AS note,
               COALESCE(n.is_completed, 0) AS is_completed
        FROM resources r
        LEFT JOIN favourites f ON f.resource_id = r.id AND f.user_id = ?
        LEFT JOIN resource_notes n ON n.resource_id = r.id AND n.user_id = ?
        {where}
        ORDER BY r.category, r.difficulty, r.title
        """,
        params,
    ).fetchall()

    categories = [
        row["category"]
        for row in db.execute(
            "SELECT DISTINCT category FROM resources ORDER BY category"
        )
    ]
    type_counts = db.execute(
        """SELECT resource_type, COUNT(*) AS count FROM resources
           GROUP BY resource_type ORDER BY count DESC, resource_type"""
    ).fetchall()
    # A readable reminder of what is currently filtering the list, so pressing
    # "Apply filters" always has a visible effect above the results.
    active_filters = []
    if filters["q"]:
        active_filters.append(f"search “{filters['q']}”")
    if filters["category"]:
        active_filters.append(filters["category"])
    if filters["difficulty"]:
        active_filters.append(filters["difficulty"])
    if filters["resource_type"]:
        active_filters.append(filters["resource_type"])
    if filters["saved"] == "1":
        active_filters.append("saved only")

    total = db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
    favourite_count = db.execute(
        "SELECT COUNT(*) FROM favourites WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    completed_count = db.execute(
        "SELECT COUNT(*) FROM resource_notes WHERE user_id = ? AND is_completed = 1",
        (user_id,),
    ).fetchone()[0]

    return render_template(
        "dashboard/resources.html",
        resources=resources,
        categories=categories,
        difficulties=DIFFICULTIES,
        type_counts=type_counts,
        filters=filters,
        total=total,
        active_filters=active_filters,
        favourite_count=favourite_count,
        completed_count=completed_count,
        note_max_length=NOTE_MAX_LENGTH,
    )


@resources_bp.route("/resources/<int:resource_id>/note", methods=["POST"])
@login_required
def save_note(resource_id):
    """Save this student's private note and completed marker for a resource.

    Sending an empty note with the completed box unticked removes the row, so
    clearing a note leaves no empty leftovers in the database.
    """
    db = get_db()
    user_id = current_user.id
    filters = _filters_from(request.form)
    back_to = _list_url(filters)

    resource = db.execute(
        "SELECT id, title FROM resources WHERE id = ?", (resource_id,)
    ).fetchone()
    if not resource:
        flash("That resource is not available.", "error")
        return redirect(back_to)

    note = (request.form.get("note") or "").strip()
    completed = 1 if request.form.get("is_completed") == "1" else 0
    if len(note) > NOTE_MAX_LENGTH:
        flash(f"Notes can be up to {NOTE_MAX_LENGTH} characters.", "error")
        return redirect(back_to)

    existing = db.execute(
        """SELECT id, is_completed FROM resource_notes
           WHERE user_id = ? AND resource_id = ?""",
        (user_id, resource_id),
    ).fetchone()

    if not note and not completed:
        if existing:
            db.execute(
                "DELETE FROM resource_notes WHERE id = ? AND user_id = ?",
                (existing["id"], user_id),
            )
            db.commit()
            flash(f"Cleared your note for “{resource['title']}”.", "info")
        else:
            flash("Add a note or tick completed before saving.", "info")
        return redirect(back_to)

    if existing:
        db.execute(
            """UPDATE resource_notes
               SET note = ?, is_completed = ?, updated_at = datetime('now')
               WHERE id = ? AND user_id = ?""",
            (note, completed, existing["id"], user_id),
        )
    else:
        db.execute(
            """INSERT INTO resource_notes (user_id, resource_id, note, is_completed)
               VALUES (?, ?, ?, ?)""",
            (user_id, resource_id, note, completed),
        )
    db.commit()

    # Only the first time a resource is marked complete is worth an activity line.
    if completed and not (existing and existing["is_completed"]):
        log_activity(
            user_id, "resource", f"Completed a learning resource: {resource['title']}"
        )

    flash(f"Saved your note for “{resource['title']}”.", "success")
    return redirect(back_to)


@resources_bp.route("/resources/<int:resource_id>/favourite", methods=["POST"])
@login_required
def toggle_favourite(resource_id):
    """Save a resource to this student's favourites, or remove it again."""
    db = get_db()
    user_id = current_user.id

    resource = db.execute(
        "SELECT id, title FROM resources WHERE id = ?", (resource_id,)
    ).fetchone()
    filters = _filters_from(request.form)
    back_to = _list_url(filters)

    if not resource:
        flash("That resource is not available.", "error")
        return redirect(back_to)

    existing = db.execute(
        "SELECT id FROM favourites WHERE user_id = ? AND resource_id = ?",
        (user_id, resource_id),
    ).fetchone()

    if existing:
        db.execute(
            "DELETE FROM favourites WHERE id = ? AND user_id = ?",
            (existing["id"], user_id),
        )
        db.commit()
        flash(f"Removed “{resource['title']}” from your favourites.", "info")
    else:
        db.execute(
            "INSERT INTO favourites (user_id, resource_id) VALUES (?, ?)",
            (user_id, resource_id),
        )
        db.commit()
        log_activity(
            user_id, "resource", f"Saved a learning resource: {resource['title']}"
        )
        flash(f"Saved “{resource['title']}” to your favourites.", "success")

    return redirect(back_to)
