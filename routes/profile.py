"""
routes/profile.py - view and edit the logged-in user's profile.

The profile is stored in two places:
  users          -> name (and email, which cannot be changed here)
  user_profiles  -> college, education, year of study, interests, fields
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

profile_bp = Blueprint("profile", __name__)

# The choices shown in the form. Edit these lists to change the options.
YEAR_OPTIONS = [
    "1st year", "2nd year", "3rd year", "4th year", "Postgraduate", "Already graduated",
]
FIELD_OPTIONS = [
    "Web development",
    "AI and machine learning",
    "Data science and analytics",
    "Cybersecurity",
    "Mobile app development",
    "Cloud computing",
    "Game development",
    "Embedded systems and IoT",
]

EMPTY_PROFILE = {
    "college_name": "",
    "education_details": "",
    "year_of_study": "",
    "career_interests": "",
    "preferred_fields": "",
}


def split_fields(text):
    """'Web development, Cybersecurity' -> ['Web development', 'Cybersecurity']"""
    return [item.strip() for item in text.split(",") if item.strip()]


def load_profile(user_id):
    """Return the saved profile as a dictionary (empty values if none yet)."""
    row = get_db().execute(
        """
        SELECT college_name, education_details, year_of_study,
               career_interests, preferred_fields
        FROM user_profiles
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    return dict(row) if row else dict(EMPTY_PROFILE)


def validate_profile(form):
    """Check the submitted values. Returns a dict of {field: error message}."""
    errors = {}

    if not 2 <= len(form["name"]) <= 60:
        errors["name"] = "Enter your name using 2 to 60 characters."
    if len(form["college_name"]) > 120:
        errors["college_name"] = "Use 120 characters or fewer."
    if len(form["education_details"]) > 150:
        errors["education_details"] = "Use 150 characters or fewer."
    if form["year_of_study"] and form["year_of_study"] not in YEAR_OPTIONS:
        errors["year_of_study"] = "Choose one of the options in the list."
    if len(form["career_interests"]) > 300:
        errors["career_interests"] = "Use 300 characters or fewer."
    if any(item not in FIELD_OPTIONS for item in form["fields"]):
        errors["preferred_fields"] = "Choose only from the fields shown."

    return errors


@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def my_profile():
    user_id = current_user.id       # the profile always belongs to the logged-in user
    saved = load_profile(user_id)

    # Values shown in the form: the saved ones, or what was just submitted.
    form = {
        "name": current_user.name,
        "college_name": saved["college_name"],
        "education_details": saved["education_details"],
        "year_of_study": saved["year_of_study"],
        "career_interests": saved["career_interests"],
        "fields": split_fields(saved["preferred_fields"]),
    }
    errors = {}

    if request.method == "POST":
        form = {
            "name": " ".join(request.form.get("name", "").split()),
            "college_name": " ".join(request.form.get("college_name", "").split()),
            "education_details": " ".join(request.form.get("education_details", "").split()),
            "year_of_study": request.form.get("year_of_study", "").strip(),
            "career_interests": request.form.get("career_interests", "").strip(),
            "fields": request.form.getlist("preferred_fields"),
        }
        errors = validate_profile(form)

        if not errors:
            # Keep the checkboxes in the same order as FIELD_OPTIONS, without repeats.
            chosen_fields = [item for item in FIELD_OPTIONS if item in form["fields"]]

            db = get_db()
            db.execute("UPDATE users SET name = ? WHERE id = ?", (form["name"], user_id))
            db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
            db.execute(
                """
                UPDATE user_profiles
                SET college_name = ?, education_details = ?, year_of_study = ?,
                    career_interests = ?, preferred_fields = ?,
                    updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (
                    form["college_name"],
                    form["education_details"],
                    form["year_of_study"],
                    form["career_interests"],
                    ", ".join(chosen_fields),
                    user_id,
                ),
            )
            db.commit()
            log_activity(user_id, "profile", "Updated your profile")

            flash("Your profile has been updated.", "success")
            # Redirect after saving so that refreshing the page does not resend the form.
            return redirect(url_for("profile.my_profile"))

    return render_template(
        "dashboard/profile.html",
        form=form,
        errors=errors,
        saved=saved,
        saved_fields=split_fields(saved["preferred_fields"]),
        year_options=YEAR_OPTIONS,
        field_options=FIELD_OPTIONS,
    )
