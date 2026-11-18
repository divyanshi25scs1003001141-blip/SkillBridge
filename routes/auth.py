"""
routes/auth.py - register, log in and log out.
"""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from models import User
from utils.helpers import is_safe_redirect_target, log_activity, validate_registration

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # Someone who is already logged in has no need to register.
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    form = {"name": "", "email": ""}   # what to show back in the form if something is wrong
    errors = {}

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        form = {"name": name, "email": email}

        errors = validate_registration(name, email, password, confirm_password)

        # Email must be unique.
        if "email" not in errors and User.get_by_email(email):
            errors["email"] = "An account with this email already exists. Try logging in instead."

        if not errors:
            try:
                User.create(name, email, password)
            except sqlite3.IntegrityError:
                # Two people registering the same email at the same moment.
                errors["email"] = "An account with this email already exists. Try logging in instead."
            else:
                flash("Your account has been created. Log in to get started.", "success")
                return redirect(url_for("auth.login"))

    return render_template("register.html", form=form, errors=errors)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    email = ""
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.get_by_email(email) if email else None

        if user and user.check_password(password):
            # Start a fresh session after login. This stops "session fixation",
            # where an attacker plants a session id before the victim logs in.
            session.clear()
            login_user(user)
            session.permanent = True
            log_activity(user.id, "login", "Logged in to SkillBridge")
            flash(f"Welcome back, {user.name}.", "success")

            # If the visitor was sent here from a private page, take them back to it.
            next_url = request.args.get("next")
            if is_safe_redirect_target(next_url):
                return redirect(next_url)
            return redirect(url_for("dashboard.home"))

        # One message for both "no such email" and "wrong password", so the
        # form never reveals which emails have accounts.
        error = "That email and password do not match. Check them and try again."

    return render_template("login.html", email=email, error=error)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
