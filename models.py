"""
models.py - the User class used by Flask-Login.

A "model" is a Python class that represents a row in a database table.
All SQL here uses "?" placeholders, so user input can never change the
meaning of a query (this prevents SQL injection).
"""
import sqlite3

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from utils.database import get_db


class User(UserMixin):
    def __init__(self, id, name, email, password_hash, created_at):
        self.id = id
        self.name = name
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at

    @staticmethod
    def from_row(row):
        return User(
            row["id"], row["name"], row["email"], row["password_hash"], row["created_at"]
        )

    @staticmethod
    def get_by_id(user_id):
        row = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return User.from_row(row) if row else None

    @staticmethod
    def get_by_email(email):
        row = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        return User.from_row(row) if row else None

    @staticmethod
    def create(name, email, password):
        """Save a new user, plus an empty profile and a first activity entry."""
        db = get_db()
        try:
            cursor = db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email.lower(), generate_password_hash(password)),
            )
            user_id = cursor.lastrowid
            db.execute("INSERT INTO user_profiles (user_id) VALUES (?)", (user_id,))
            db.execute(
                "INSERT INTO activities (user_id, activity_type, description) VALUES (?, ?, ?)",
                (user_id, "account", "Created your SkillBridge account"),
            )
            db.commit()
        except sqlite3.Error:
            db.rollback()
            raise
        return user_id

    def check_password(self, password):
        """True if the password matches the stored hash."""
        return check_password_hash(self.password_hash, password)
