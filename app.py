"""
app.py - the starting point of SkillBridge.

Run it with:   python app.py
This file creates the Flask application, sets up the database and login
system, connects the route files (called "blueprints") and sets up
friendly error pages.
"""
from datetime import datetime

from flask import Flask, render_template
from flask_login import LoginManager

from config import Config
from models import User
from utils import database
from utils.helpers import date_label, generate_csrf_token, protect_from_csrf, time_ago

# Flask-Login keeps track of who is logged in.
login_manager = LoginManager()
login_manager.login_view = "auth.login"          # where to send logged-out visitors
login_manager.login_message = "Please log in to open that page."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login calls this on every request to find the logged-in user."""
    return User.get_by_id(user_id)


def create_app(test_config=None):
    """Build and return the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    # Database: create the file and tables if they do not exist yet.
    database.init_app(app)

    # Login system.
    login_manager.init_app(app)

    # CSRF protection: check every form post, and let templates add the token.
    app.before_request(protect_from_csrf)
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    # Filters that turn database timestamps into friendly text in templates:
    #   {{ value|time_ago }}  ->  "3 hours ago"      {{ value|date_label }}  ->  "10 Nov 2026"
    app.jinja_env.filters["time_ago"] = time_ago
    app.jinja_env.filters["date_label"] = date_label

    # Connect the route files.
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.profile import profile_bp
    from routes.skills import skills_bp, ensure_phase4_seed_data
    from routes.career import career_bp, ensure_career_seed_data
    from routes.roadmap import roadmap_bp, ensure_roadmap_seed_data
    from routes.resources import resources_bp, ensure_resource_seed_data
    from routes.projects import projects_bp
    from routes.goals import goals_bp
    from routes.readiness import readiness_bp
    from routes.certificates import certificates_bp
    from routes.resumes import resumes_bp
    from routes.analyzer import analyzer_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(career_bp)
    app.register_blueprint(roadmap_bp)
    app.register_blueprint(resources_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(readiness_bp)
    app.register_blueprint(certificates_bp)
    app.register_blueprint(resumes_bp)
    app.register_blueprint(analyzer_bp)

    # Seed starter skills, assessments, careers, roadmaps and resources once
    # during app creation, not on every page visit. Every seeder is idempotent
    # and preserves existing users, skills, selections, roadmap progress,
    # favourites and assessment attempts.
    with app.app_context():
        ensure_phase4_seed_data(database.get_db())
        ensure_career_seed_data(database.get_db())
        ensure_roadmap_seed_data(database.get_db())
        ensure_resource_seed_data(database.get_db())

    register_error_pages(app)

    # Make the current year available in every template (used in the footer).
    @app.context_processor
    def inject_current_year():
        return {"current_year": datetime.now().year}

    return app


def register_error_pages(app):
    """Show a styled page instead of Flask's plain default error text."""

    def show_error(code, title, message):
        page = render_template(
            "errors/error.html", code=code, title=title, message=message
        )
        return page, code

    @app.errorhandler(400)
    def bad_request(error):
        return show_error(
            400,
            "That form could not be verified",
            "Your session may have expired. Go back, reload the page and try again.",
        )

    @app.errorhandler(404)
    def page_not_found(error):
        return show_error(
            404,
            "We couldn't find that page",
            "The address may be mistyped, or the page may have moved.",
        )

    @app.errorhandler(405)
    def method_not_allowed(error):
        return show_error(
            405,
            "That action is not allowed here",
            "Use the buttons on the page instead of typing the address.",
        )

    @app.errorhandler(413)
    def too_large(error):
        return show_error(
            413,
            "That request was too large",
            "Please send less data and try again.",
        )

    @app.errorhandler(500)
    def server_error(error):
        return show_error(
            500,
            "Something went wrong on our side",
            "Please try again in a moment. If it keeps happening, go back to the home page.",
        )


if __name__ == "__main__":
    # debug=True reloads the server when you save a file and shows detailed
    # errors. Use it only on your own computer, never on a public server.
    create_app().run(debug=True)
