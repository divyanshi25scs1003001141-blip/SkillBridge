"""
Phase 8 tests: the private project tracker.

Each test runs against a temporary database, so real data is never touched.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_auth import AuthTestCase, USER
from utils.database import get_db, migrate_projects_table

RAVI = {
    "name": "Ravi Kumar",
    "email": "ravi@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}


class PhaseEightTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.post("/register", USER)
        self.post("/login", {"email": USER["email"], "password": USER["password"]})

    # ----- helpers -----
    def user_id(self, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()["id"]

    def project_row(self, title):
        with self.app.app_context():
            return get_db().execute(
                "SELECT * FROM projects WHERE title = ?", (title,)
            ).fetchone()

    def project_id(self, title):
        row = self.project_row(title)
        return row["id"] if row else None

    def project_count(self):
        with self.app.app_context():
            return get_db().execute("SELECT COUNT(*) FROM projects").fetchone()[0]

    def create(self, client=None, follow_redirects=False, **overrides):
        data = {
            "title": "Student Result Portal",
            "description": "Teachers upload marks and students see their result.",
            "technologies": "Python, Flask, SQLite",
            "github_url": "https://github.com/asha/result-portal",
            "live_url": "https://result-portal.example.org",
            "status": "Planned",
        }
        data.update(overrides)
        return self.post(
            "/projects/new", data, client=client, follow_redirects=follow_redirects
        )

    def edit(self, project_id, client=None, follow_redirects=False, **overrides):
        data = {
            "title": "Student Result Portal",
            "description": "Updated description",
            "technologies": "Python, Flask",
            "github_url": "",
            "live_url": "",
            "status": "Planned",
        }
        data.update(overrides)
        return self.post(
            f"/projects/{project_id}/edit",
            data,
            client=client,
            follow_redirects=follow_redirects,
        )

    def second_user_client(self):
        client = self.new_client()
        self.post("/register", RAVI, client=client)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=client,
        )
        return client


class CreateProjectTests(PhaseEightTests):
    def test_projects_page_requires_login(self):
        response = self.new_client().get("/projects")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_empty_page_shows_an_empty_state(self):
        page = self.client.get("/projects")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Your projects", html)
        self.assertIn("No projects yet", html)
        self.assertIn("0 planned · 0 in progress · 0 completed", html)

    def test_create_project_saves_every_field(self):
        response = self.create(status="In Progress")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/projects")

        row = self.project_row("Student Result Portal")
        self.assertIsNotNone(row)
        self.assertEqual(row["description"], "Teachers upload marks and students see their result.")
        self.assertEqual(row["technologies"], "Python, Flask, SQLite")
        self.assertEqual(row["github_url"], "https://github.com/asha/result-portal")
        self.assertEqual(row["live_url"], "https://result-portal.example.org")
        self.assertEqual(row["status"], "In Progress")
        self.assertEqual(row["user_id"], self.user_id())

    def test_created_project_appears_with_links_and_tags(self):
        self.create()
        html = self.client.get("/projects").get_data(as_text=True)
        self.assertIn("Student Result Portal", html)
        self.assertIn("https://github.com/asha/result-portal", html)
        self.assertIn("https://result-portal.example.org", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn('<span class="tech-tag">Python</span>', html)
        self.assertIn('<span class="tech-tag">Flask</span>', html)
        self.assertIn('<span class="tech-tag">SQLite</span>', html)
        self.assertIn("Planned", html)

    def test_creating_is_logged_in_recent_activity(self):
        self.create()
        with self.app.app_context():
            count = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE user_id = ? AND description = ?",
                (self.user_id(), "Added a project: Student Result Portal"),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_status_defaults_to_planned_when_not_sent(self):
        self.create(status="")
        self.assertEqual(self.project_row("Student Result Portal")["status"], "Planned")

    def test_title_is_required(self):
        response = self.create(title="   ", follow_redirects=True)
        self.assertIn("Give your project a title.", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

    def test_title_length_is_checked(self):
        response = self.create(title="x" * 121, follow_redirects=True)
        self.assertIn("Titles can be up to 120 characters.", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

    def test_description_length_is_checked(self):
        response = self.create(description="x" * 1001, follow_redirects=True)
        self.assertIn("Descriptions can be up to 1000 characters.", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

    def test_javascript_url_is_rejected(self):
        response = self.create(github_url="javascript:alert(1)", follow_redirects=True)
        self.assertIn("must start with http:// or https://", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

    def test_url_without_scheme_is_rejected(self):
        response = self.create(live_url="github.com/asha/project", follow_redirects=True)
        self.assertIn("must start with http:// or https://", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

    def test_unknown_status_is_rejected(self):
        response = self.create(status="Archived", follow_redirects=True)
        self.assertIn("Choose a valid status", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

    def test_links_are_optional(self):
        self.create(github_url="", live_url="")
        row = self.project_row("Student Result Portal")
        self.assertEqual(row["github_url"], "")
        self.assertEqual(row["live_url"], "")

    def test_two_projects_share_one_user(self):
        self.create(title="First Project")
        self.create(title="Second Project")
        self.assertEqual(self.project_count(), 2)
        html = self.client.get("/projects").get_data(as_text=True)
        self.assertIn("2 projects saved", html)

    def test_project_title_is_escaped(self):
        self.create(title="<script>alert(1)</script>")
        html = self.client.get("/projects").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_create_requires_csrf_token(self):
        client = self.second_user_client()
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post("/projects/new", data={"title": "No token"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.project_count(), 0)

    def test_entered_values_survive_a_validation_error(self):
        response = self.create(title="", technologies="Django, PostgreSQL")
        html = response.get_data(as_text=True)
        self.assertIn("Give your project a title.", html)
        self.assertIn('value="Django, PostgreSQL"', html)


class UpdateProjectTests(PhaseEightTests):
    def test_status_moves_from_planned_to_in_progress(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        response = self.edit(project_id, status="In Progress")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.project_row("Student Result Portal")["status"], "In Progress")

        with self.app.app_context():
            activity = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE description = ?",
                ("Moved “Student Result Portal” to In Progress",),
            ).fetchone()[0]
        self.assertEqual(activity, 1)

    def test_status_moves_to_completed_and_is_grouped(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        self.edit(project_id, status="Completed")
        html = self.client.get("/projects").get_data(as_text=True)
        self.assertIn("Completed <span class=\"muted\">(1)</span>", html)
        self.assertIn("0 planned · 0 in progress · 1 completed", html)

    def test_edit_updates_all_fields(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        self.edit(
            project_id,
            title="Result Portal v2",
            description="Now with CSV import.",
            technologies="Python, Flask, SQLite, Bootstrap",
            github_url="https://github.com/asha/result-portal-v2",
            live_url="https://portal.example.org",
            status="In Progress",
        )
        row = self.project_row("Result Portal v2")
        self.assertEqual(row["description"], "Now with CSV import.")
        self.assertEqual(row["technologies"], "Python, Flask, SQLite, Bootstrap")
        self.assertEqual(row["github_url"], "https://github.com/asha/result-portal-v2")
        self.assertEqual(row["live_url"], "https://portal.example.org")
        self.assertEqual(row["status"], "In Progress")

    def test_edit_rejects_invalid_status(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        response = self.edit(project_id, status="Done", follow_redirects=True)
        self.assertIn("Choose a valid status", response.get_data(as_text=True))
        self.assertEqual(self.project_row("Student Result Portal")["status"], "Planned")

    def test_editing_an_unknown_project_is_handled(self):
        response = self.edit(99999, follow_redirects=True)
        self.assertIn("That project could not be found.", response.get_data(as_text=True))

    def test_another_users_project_cannot_be_edited(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        other = self.second_user_client()
        response = self.edit(
            project_id, client=other, title="Hijacked", status="Completed", follow_redirects=True
        )
        self.assertIn("That project could not be found.", response.get_data(as_text=True))
        row = self.project_row("Student Result Portal")
        self.assertEqual(row["status"], "Planned")
        self.assertEqual(row["user_id"], self.user_id())

    def test_edit_requires_csrf_token(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        client = self.second_user_client()
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post(f"/projects/{project_id}/edit", data={"title": "No token"})
        self.assertEqual(response.status_code, 400)


class DeleteProjectTests(PhaseEightTests):
    def test_delete_removes_the_project_and_logs_it(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        response = self.post(f"/projects/{project_id}/delete", {}, follow_redirects=True)
        self.assertIn("deleted", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 0)

        with self.app.app_context():
            activity = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE description = ?",
                ("Deleted a project: Student Result Portal",),
            ).fetchone()[0]
        self.assertEqual(activity, 1)

    def test_another_users_project_cannot_be_deleted(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        other = self.second_user_client()
        response = self.post(
            f"/projects/{project_id}/delete", {}, client=other, follow_redirects=True
        )
        self.assertIn("That project could not be found.", response.get_data(as_text=True))
        self.assertEqual(self.project_count(), 1)

    def test_deleting_an_unknown_project_is_handled(self):
        response = self.post("/projects/99999/delete", {}, follow_redirects=True)
        self.assertIn("That project could not be found.", response.get_data(as_text=True))

    def test_delete_requires_csrf_token(self):
        self.create()
        project_id = self.project_id("Student Result Portal")
        client = self.second_user_client()
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post(f"/projects/{project_id}/delete")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.project_count(), 1)


class ProjectPrivacyTests(PhaseEightTests):
    def test_other_users_projects_are_never_listed(self):
        self.create(title="Asha Private Project")
        other = self.second_user_client()
        html = other.get("/projects").get_data(as_text=True)
        self.assertNotIn("Asha Private Project", html)
        self.assertIn("No projects yet", html)

    def test_counts_are_per_user(self):
        self.create()
        other = self.second_user_client()
        html = other.get("/projects").get_data(as_text=True)
        self.assertIn("0 planned · 0 in progress · 0 completed", html)
        self.assertIn("0 projects saved", html)


class ProjectMigrationTests(unittest.TestCase):
    """The old 'Not Started' status must become 'Planned' without data loss."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        # Cleanups run last-in-first-out, so connections close before the
        # temporary folder is removed (Windows locks open SQLite files).
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "legacy.db"

    def _legacy_connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title        TEXT NOT NULL,
                description  TEXT NOT NULL DEFAULT '',
                technologies TEXT NOT NULL DEFAULT '',
                github_url   TEXT NOT NULL DEFAULT '',
                status       TEXT NOT NULL DEFAULT 'Not Started'
                             CHECK (status IN ('Not Started', 'In Progress', 'Completed')),
                created_at   TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO users (name, email, password_hash) VALUES ('Asha', 'asha@example.com', 'x');
            INSERT INTO projects (user_id, title, technologies, status)
                VALUES (1, 'Old Project', 'Python', 'Not Started');
            INSERT INTO projects (user_id, title, status)
                VALUES (1, 'Running Project', 'In Progress');
            INSERT INTO projects (user_id, title, status)
                VALUES (1, 'Done Project', 'Completed');
            """
        )
        connection.commit()
        self.addCleanup(connection.close)
        return connection

    def test_not_started_becomes_planned_and_ids_are_kept(self):
        connection = self._legacy_connection()
        before = [dict(row) for row in connection.execute("SELECT * FROM projects ORDER BY id")]
        migrate_projects_table(connection)

        columns = {row["name"] for row in connection.execute("PRAGMA table_info(projects)")}
        self.assertIn("live_url", columns)

        after = [dict(row) for row in connection.execute("SELECT * FROM projects ORDER BY id")]
        self.assertEqual([p["id"] for p in after], [p["id"] for p in before])
        self.assertEqual(
            [p["status"] for p in after], ["Planned", "In Progress", "Completed"]
        )
        self.assertEqual(after[0]["title"], "Old Project")
        self.assertEqual(after[0]["created_at"], before[0]["created_at"])

        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='projects'"
        ).fetchone()["sql"]
        self.assertIn("'Planned'", schema)
        self.assertNotIn("Not Started", schema)
        connection.close()

    def test_new_statuses_are_enforced_and_old_one_is_refused(self):
        connection = self._legacy_connection()
        migrate_projects_table(connection)
        connection.execute(
            "INSERT INTO projects (user_id, title, status) VALUES (1, 'Fresh', 'Planned')"
        )
        connection.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO projects (user_id, title, status) VALUES (1, 'Bad', 'Not Started')"
            )
        connection.close()

    def test_migration_is_safe_to_run_again(self):
        connection = self._legacy_connection()
        migrate_projects_table(connection)
        migrate_projects_table(connection)
        count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        self.assertEqual(count, 3)
        connection.close()

    def test_new_schema_is_left_alone(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                technologies TEXT NOT NULL DEFAULT '',
                github_url TEXT NOT NULL DEFAULT '',
                live_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Planned'
                       CHECK (status IN ('Planned', 'In Progress', 'Completed')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        migrate_projects_table(connection)  # must be a no-op
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(projects)")}
        self.assertIn("live_url", columns)
        connection.close()


if __name__ == "__main__":
    unittest.main()
