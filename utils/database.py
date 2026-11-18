"""
utils/database.py - everything about connecting to SQLite.

get_db()  gives a route a connection to the database.
init_app() creates the database file and tables when the app starts.
"""
import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    """Return this request's database connection, opening it if needed."""
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"])
        # Rows can then be read by column name: row["email"]
        connection.row_factory = sqlite3.Row
        # SQLite ignores foreign keys unless we switch them on for each connection.
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(error=None):
    """Close the connection at the end of every request."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


# Columns added to a table after the first release. schema.sql can only add
# whole new tables, so a missing column is added here with ALTER TABLE.
# Existing rows keep their values; the new column simply starts as NULL.
MIGRATION_COLUMNS = {
    "user_profiles": {
        # The career this student is working towards (Phase 5).
        "selected_career_id": "INTEGER REFERENCES careers(id) ON DELETE SET NULL",
    },
    "resources": {
        # How hard a learning resource is (Phase 7).
        "difficulty": "TEXT NOT NULL DEFAULT 'Beginner'",
    },
    "projects": {
        # Where the finished project can be tried (Phase 8).
        "live_url": "TEXT NOT NULL DEFAULT ''",
    },
}


def migrate_projects_table(connection):
    """Move projects from the old 'Not Started' status to 'Planned' (Phase 8).

    SQLite cannot change a CHECK constraint in place, so one table rebuild is
    needed. It runs only when the old definition is still present, copies every
    row (keeping ids and timestamps) and recreates the user index.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
    ).fetchone()
    if not row or "Not Started" not in (row["sql"] or ""):
        return

    # The column pass in migrate_db() normally adds this first. Adding it here
    # too means the rebuild is safe to call on its own (and in tests).
    columns = {r["name"] for r in connection.execute("PRAGMA table_info(projects)")}
    if "live_url" not in columns:
        connection.execute(
            "ALTER TABLE projects ADD COLUMN live_url TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()

    connection.executescript(
        """
        BEGIN;
        DROP TABLE IF EXISTS projects_migrated;
        CREATE TABLE projects_migrated (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title        TEXT NOT NULL,
            description  TEXT NOT NULL DEFAULT '',
            technologies TEXT NOT NULL DEFAULT '',
            github_url   TEXT NOT NULL DEFAULT '',
            live_url     TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL DEFAULT 'Planned'
                         CHECK (status IN ('Planned', 'In Progress', 'Completed')),
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO projects_migrated
            (id, user_id, title, description, technologies, github_url,
             live_url, status, created_at, updated_at)
        SELECT id, user_id, title, description, technologies, github_url,
               live_url,
               CASE status WHEN 'Not Started' THEN 'Planned' ELSE status END,
               created_at, updated_at
        FROM projects;
        DROP TABLE projects;
        ALTER TABLE projects_migrated RENAME TO projects;
        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        COMMIT;
        """
    )
    connection.commit()


def migrate_db():
    """Add any missing columns to existing tables (safe to repeat)."""
    connection = get_db()
    for table, columns in MIGRATION_COLUMNS.items():
        existing = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                )
    connection.commit()
    # Runs after the column pass, so the rebuild can copy live_url across.
    migrate_projects_table(connection)


def init_db():
    """Create any missing tables by running schema.sql (safe to repeat)."""
    schema_file = Path(current_app.root_path) / "schema.sql"
    connection = get_db()
    connection.executescript(schema_file.read_text(encoding="utf-8"))
    connection.commit()
    migrate_db()


def init_app(app):
    """Connect the database to the Flask app."""
    app.teardown_appcontext(close_db)

    # Make sure the folder for the database file exists.
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    with app.app_context():
        init_db()
