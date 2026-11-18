"""
Phase 2 tests: database, registration, login, logout and protected pages.

Run from the SkillBridge folder with:
    python -m unittest discover -s tests -v

Every test uses a temporary database, so your real data is never touched.
"""
import os
import re
import tempfile
import unittest

from app import create_app
from utils.database import get_db

USER = {
    "name": "Asha Verma",
    "email": "asha@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    # ----- helpers -----
    def post(self, url, data, client=None, **kwargs):
        """POST a form with a valid CSRF token (like a real browser would)."""
        client = client or self.client
        with client.session_transaction() as session:
            session["_csrf_token"] = "test-token"
        data = dict(data, csrf_token="test-token")
        return client.post(url, data=data, **kwargs)

    def register(self, client=None, **changes):
        return self.post("/register", dict(USER, **changes), client=client)

    def login(self, email=USER["email"], password=USER["password"], client=None, **kwargs):
        return self.post("/login", {"email": email, "password": password}, client=client, **kwargs)

    def new_client(self, app=None):
        return (app or self.app).test_client()


class DatabaseTests(AuthTestCase):
    def test_all_fourteen_tables_are_created(self):
        expected = {
            "users", "user_profiles", "skills", "user_skills", "assessments",
            "assessment_questions", "assessment_results", "roadmaps",
            "roadmap_steps", "resources", "favourites", "projects", "goals",
            "activities",
        }
        with self.app.app_context():
            rows = get_db().execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        self.assertTrue(expected.issubset({row["name"] for row in rows}))

    def test_foreign_keys_are_enforced(self):
        import sqlite3
        with self.app.app_context():
            with self.assertRaises(sqlite3.IntegrityError):
                get_db().execute("INSERT INTO user_profiles (user_id) VALUES (9999)")


class RegistrationTests(AuthTestCase):
    def test_register_page_loads_with_csrf_token(self):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="csrf_token"', response.data)

    def test_registration_works_and_creates_profile_row(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        with self.app.app_context():
            db = get_db()
            user = db.execute("SELECT * FROM users WHERE email = ?", (USER["email"],)).fetchone()
            self.assertIsNotNone(user)
            profile = db.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user["id"],)).fetchone()
            self.assertIsNotNone(profile)

    def test_password_is_stored_as_a_hash_not_plain_text(self):
        self.register()
        with self.app.app_context():
            stored = get_db().execute("SELECT password_hash FROM users").fetchone()["password_hash"]
        self.assertNotEqual(stored, USER["password"])
        self.assertNotIn(USER["password"], stored)
        self.assertTrue(stored.startswith(("scrypt:", "pbkdf2:")))

    def test_duplicate_email_is_rejected(self):
        self.register()
        response = self.register(name="Someone Else")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"already exists", response.data)
        with self.app.app_context():
            count = get_db().execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        self.assertEqual(count, 1)

    def test_duplicate_email_check_ignores_capital_letters(self):
        self.register()
        response = self.register(email="ASHA@Example.COM")
        self.assertIn(b"already exists", response.data)

    def test_weak_or_invalid_input_is_rejected(self):
        cases = [
            ({"password": "short1", "confirm_password": "short1"}, b"at least 8"),
            ({"password": "onlyletters", "confirm_password": "onlyletters"}, b"one letter and one number"),
            ({"password": "12345678", "confirm_password": "12345678"}, b"one letter and one number"),
            ({"confirm_password": "Different123"}, b"do not match"),
            ({"email": "not-an-email"}, b"valid email"),
            ({"name": "A"}, b"2 to 60"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                response = self.register(**changes)
                self.assertEqual(response.status_code, 200)
                self.assertIn(message, response.data)
        with self.app.app_context():
            count = get_db().execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        self.assertEqual(count, 0)

    def test_form_without_csrf_token_is_refused(self):
        response = self.client.post("/register", data=USER)
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            count = get_db().execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        self.assertEqual(count, 0)

    def test_real_form_flow_with_token_from_the_page(self):
        page = self.client.get("/register").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        response = self.client.post("/register", data=dict(USER, csrf_token=token))
        self.assertEqual(response.status_code, 302)

    def test_names_are_escaped_so_html_cannot_be_injected(self):
        self.register(name="<script>alert(1)</script>")
        self.login()
        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


class LoginLogoutTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.register()

    def test_login_works_and_opens_dashboard(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/dashboard"))
        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Asha Verma", page.data)

    def test_login_ignores_capital_letters_in_email(self):
        response = self.login(email="ASHA@example.com")
        self.assertEqual(response.status_code, 302)

    def test_wrong_password_is_rejected(self):
        response = self.login(password="WrongPass99")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"do not match", response.data)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_unknown_email_gets_the_same_message(self):
        wrong_password = self.login(password="WrongPass99").data
        unknown_email = self.login(email="nobody@example.com").data
        message = b"That email and password do not match"
        self.assertIn(message, wrong_password)
        self.assertIn(message, unknown_email)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertIn("next=", response.headers["Location"])

    def test_login_returns_to_the_page_the_visitor_wanted(self):
        response = self.login(query_string={"next": "/about"})
        self.assertTrue(response.headers["Location"].endswith("/about"))

    def test_login_refuses_to_redirect_to_other_websites(self):
        for bad in ["https://evil.example/", "//evil.example/", "/\\evil.example"]:
            with self.subTest(next=bad):
                client = self.new_client()
                response = self.login(client=client, query_string={"next": bad})
                self.assertEqual(response.status_code, 302)
                self.assertNotIn("evil", response.headers["Location"])

    def test_logged_in_user_is_sent_away_from_login_and_register(self):
        self.login()
        for url in ["/login", "/register"]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.headers["Location"].endswith("/dashboard"))

    def test_logout_ends_the_session(self):
        self.login()
        response = self.post("/logout", {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_logout_cannot_be_triggered_by_a_plain_link(self):
        self.login()
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_login_is_recorded_in_recent_activity(self):
        self.login()
        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Logged in to SkillBridge", page)
        self.assertIn("Created your SkillBridge account", page)


class PrivacyAndPersistenceTests(AuthTestCase):
    def test_two_users_only_see_their_own_details(self):
        client_a, client_b = self.new_client(), self.new_client()
        self.register(client=client_a)
        self.register(client=client_b, name="Ravi Kumar", email="ravi@example.com")
        self.login(client=client_a)
        self.login(email="ravi@example.com", client=client_b)

        page_a = client_a.get("/dashboard").get_data(as_text=True)
        page_b = client_b.get("/dashboard").get_data(as_text=True)
        self.assertIn("Asha Verma", page_a)
        self.assertNotIn("Ravi Kumar", page_a)
        self.assertNotIn("ravi@example.com", page_a)
        self.assertIn("Ravi Kumar", page_b)
        self.assertNotIn("Asha Verma", page_b)
        self.assertNotIn("asha@example.com", page_b)

    def test_data_survives_an_application_restart(self):
        self.register()
        # Create a brand-new application that uses the same database file.
        restarted = create_app({"TESTING": True, "DATABASE": self.db_path})
        client = self.new_client(restarted)
        response = self.login(client=client)
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"Asha Verma", client.get("/dashboard").data)


if __name__ == "__main__":
    unittest.main()
