"""
Phase 3 tests: the dashboard (real database numbers), the profile page,
and the friendly date helpers.

Run from the SkillBridge folder with:
    python -m unittest discover -s tests -v
"""
import re
import unittest
from datetime import date, datetime, timedelta, timezone

from test_auth import USER, AuthTestCase   # shared setup from the Phase 2 tests

from utils.database import get_db
from utils.helpers import date_label, time_ago

RAVI = {
    "name": "Ravi Kumar",
    "email": "ravi@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}


class DashboardProfileCase(AuthTestCase):
    """Adds helpers for logging in and for putting test rows in the database."""

    def make_user(self, details=USER, client=None):
        client = client or self.client
        self.post("/register", details, client=client)
        self.post("/login", {"email": details["email"], "password": details["password"]}, client=client)
        with self.app.app_context():
            row = get_db().execute("SELECT id FROM users WHERE email = ?", (details["email"],)).fetchone()
        return row["id"]

    def run_sql(self, sql, params=()):
        with self.app.app_context():
            db = get_db()
            cursor = db.execute(sql, params)
            db.commit()
            return cursor.lastrowid

    def stat(self, html, name):
        """Read one number from the summary strip, e.g. stat(page, 'skills')."""
        return int(re.search(rf'data-stat="{name}">(\d+)<', html).group(1))

    def save_profile(self, client=None, **changes):
        data = {
            "name": "Asha Verma",
            "college_name": "ABC Institute of Technology",
            "education_details": "B.Tech in Computer Science",
            "year_of_study": "2nd year",
            "career_interests": "Backend development and data analysis",
            "preferred_fields": ["Web development", "Cybersecurity"],
        }
        data.update(changes)
        return self.post("/profile", data, client=client)


class DashboardTests(DashboardProfileCase):
    def test_dashboard_welcomes_user_by_first_name(self):
        self.make_user()
        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Welcome back, Asha.", page)

    def test_dashboard_has_sidebar_with_working_links(self):
        self.make_user()
        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('class="sidebar"', page)
        self.assertIn('href="/profile"', page)
        self.assertIn('action="/logout"', page)

    def test_new_user_sees_zeros_and_empty_states(self):
        self.make_user()
        page = self.client.get("/dashboard").get_data(as_text=True)
        for name in ["skills", "learning", "goals-completed"]:
            self.assertEqual(self.stat(page, name), 0)
        self.assertIn("No assessments taken yet", page)
        self.assertIn("No upcoming goals", page)
        self.assertIn("Created your SkillBridge account", page)

    def test_numbers_and_lists_come_from_the_database(self):
        user_id = self.make_user()
        today = date.today()

        # 3 skills: 2 learning, 1 acquired
        for index, status in enumerate(["Learning", "Learning", "Acquired"]):
            skill_id = self.run_sql("INSERT INTO skills (name, category) VALUES (?, ?)", (f"Skill {index}", "Test"))
            self.run_sql("INSERT INTO user_skills (user_id, skill_id, status) VALUES (?, ?, ?)", (user_id, skill_id, status))

        # goals: 2 completed, 1 upcoming, 1 overdue
        goal_sql = "INSERT INTO goals (user_id, title, goal_type, target_date, is_completed) VALUES (?, ?, ?, ?, ?)"
        self.run_sql(goal_sql, (user_id, "Finished goal one", "Weekly", str(today), 1))
        self.run_sql(goal_sql, (user_id, "Finished goal two", "Monthly", str(today), 1))
        self.run_sql(goal_sql, (user_id, "Read the Flask docs", "Weekly", str(today + timedelta(days=5)), 0))
        self.run_sql(goal_sql, (user_id, "Overdue goal", "Weekly", str(today - timedelta(days=3)), 0))

        # one assessment taken twice: the older result is 50%, the newer is 80%
        # The Phase 4 seeder already creates a "Python" assessment, so a
        # clearly separate title avoids a UNIQUE constraint clash.
        assessment_id = self.run_sql("INSERT INTO assessments (title) VALUES (?)", ("Dashboard Test Assessment",))
        result_sql = ("INSERT INTO assessment_results (user_id, assessment_id, score, total_questions, percentage, taken_at) "
                      "VALUES (?, ?, ?, ?, ?, ?)")
        self.run_sql(result_sql, (user_id, assessment_id, 5, 10, 50.0, "2026-01-01 10:00:00"))
        self.run_sql(result_sql, (user_id, assessment_id, 8, 10, 80.0, "2026-01-02 10:00:00"))

        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertEqual(self.stat(page, "skills"), 3)
        self.assertEqual(self.stat(page, "learning"), 2)
        self.assertEqual(self.stat(page, "goals-completed"), 2)

        # latest score only
        self.assertIn("80%", page)
        self.assertIn("8 of 10 correct", page)
        self.assertNotIn("5 of 10 correct", page)

        # upcoming goals: the future one only
        self.assertIn("Read the Flask docs", page)
        self.assertNotIn("Overdue goal", page)
        self.assertNotIn("Finished goal one", page)
        self.assertNotIn("No upcoming goals", page)

    def test_dashboard_never_shows_another_users_records(self):
        client_a, client_b = self.new_client(), self.new_client()
        user_a = self.make_user(USER, client_a)
        self.make_user(RAVI, client_b)

        # "Python" already exists in the seeded catalogue, so use a new name.
        skill_id = self.run_sql("INSERT INTO skills (name, category) VALUES (?, ?)", ("Privacy Test Skill", "Test"))
        self.run_sql("INSERT INTO user_skills (user_id, skill_id, status) VALUES (?, ?, 'Learning')", (user_a, skill_id))
        self.run_sql(
            "INSERT INTO goals (user_id, title, goal_type, target_date) VALUES (?, ?, 'Weekly', ?)",
            (user_a, "Asha private goal", str(date.today() + timedelta(days=2))),
        )

        page_a = client_a.get("/dashboard").get_data(as_text=True)
        page_b = client_b.get("/dashboard").get_data(as_text=True)
        self.assertEqual(self.stat(page_a, "skills"), 1)
        self.assertIn("Asha private goal", page_a)
        self.assertEqual(self.stat(page_b, "skills"), 0)
        self.assertNotIn("Asha private goal", page_b)

    def test_profile_reminder_shows_until_college_and_year_are_saved(self):
        self.make_user()
        self.assertIn("finish setting up your profile", self.client.get("/dashboard").get_data(as_text=True))
        self.save_profile()
        self.assertNotIn("finish setting up your profile", self.client.get("/dashboard").get_data(as_text=True))

    def test_recent_activity_uses_friendly_times(self):
        self.make_user()
        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Just now", page)


class ProfileTests(DashboardProfileCase):
    def test_profile_requires_login(self):
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_profile_page_shows_the_form(self):
        self.make_user()
        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('name="csrf_token"', page)
        self.assertIn('name="college_name"', page)
        self.assertIn('name="year_of_study"', page)
        self.assertIn('name="preferred_fields"', page)
        self.assertIn("Not added yet", page)

    def test_saving_the_profile_stores_every_field(self):
        user_id = self.make_user()
        response = self.save_profile(name="Asha  K  Verma")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/profile"))

        with self.app.app_context():
            db = get_db()
            user = db.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
            profile = db.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
            activity = db.execute(
                "SELECT COUNT(*) AS c FROM activities WHERE user_id = ? AND description = 'Updated your profile'",
                (user_id,),
            ).fetchone()
        self.assertEqual(user["name"], "Asha K Verma")          # extra spaces tidied
        self.assertEqual(profile["college_name"], "ABC Institute of Technology")
        self.assertEqual(profile["education_details"], "B.Tech in Computer Science")
        self.assertEqual(profile["year_of_study"], "2nd year")
        self.assertEqual(profile["career_interests"], "Backend development and data analysis")
        self.assertEqual(profile["preferred_fields"], "Web development, Cybersecurity")
        self.assertEqual(activity["c"], 1)

    def test_saved_values_come_back_in_the_form_and_summary(self):
        self.make_user()
        self.save_profile()
        page = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("ABC Institute of Technology", page)
        self.assertIn("B.Tech in Computer Science", page)
        self.assertIn('<option value="2nd year" selected>', page)
        # the two chosen fields are ticked, the others are not
        self.assertRegex(page, r'value="Web development"\s+checked')
        self.assertRegex(page, r'value="Cybersecurity"\s+checked')
        self.assertNotRegex(page, r'value="Cloud computing"\s+checked')
        self.assertNotIn("Not added yet", page)

    def test_name_change_shows_in_the_sidebar(self):
        self.make_user()
        self.save_profile(name="Asha Sharma")
        page = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Welcome back, Asha.", page)
        self.assertIn("Asha Sharma", page)

    def test_profile_can_be_cleared_again(self):
        self.make_user()
        self.save_profile()
        self.save_profile(college_name="", year_of_study="", preferred_fields=[], education_details="", career_interests="")
        page = self.client.get("/profile").get_data(as_text=True)
        self.assertIn("Not added yet", page)

    def test_invalid_profile_is_rejected_and_nothing_is_saved(self):
        user_id = self.make_user()
        cases = [
            ({"name": "A"}, "2 to 60"),
            ({"year_of_study": "9th year"}, "Choose one of the options"),
            ({"preferred_fields": ["Web development", "Time travel"]}, "Choose only from the fields shown"),
            ({"college_name": "x" * 121}, "120 characters"),
            ({"education_details": "x" * 151}, "150 characters"),
            ({"career_interests": "x" * 301}, "300 characters"),
        ]
        for changes, message in cases:
            with self.subTest(changes=list(changes)):
                response = self.save_profile(**changes)
                self.assertEqual(response.status_code, 200)
                self.assertIn(message, response.get_data(as_text=True))
        with self.app.app_context():
            profile = get_db().execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        self.assertEqual(profile["college_name"], "")
        self.assertEqual(profile["preferred_fields"], "")

    def test_rejected_form_keeps_what_the_user_typed(self):
        self.make_user()
        response = self.save_profile(year_of_study="9th year", college_name="My College")
        self.assertIn("My College", response.get_data(as_text=True))

    def test_profile_form_without_csrf_token_is_refused(self):
        self.make_user()
        response = self.client.post("/profile", data={"name": "Hacker", "college_name": "Evil U"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Evil U", self.client.get("/profile").get_data(as_text=True))

    def test_email_cannot_be_changed_through_the_profile_form(self):
        user_id = self.make_user()
        self.save_profile(email="someone-else@example.com")
        with self.app.app_context():
            row = get_db().execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        self.assertEqual(row["email"], USER["email"])

    def test_one_user_cannot_see_or_change_another_users_profile(self):
        client_a, client_b = self.new_client(), self.new_client()
        self.make_user(USER, client_a)
        user_b = self.make_user(RAVI, client_b)

        self.save_profile(client=client_a, college_name="Asha's Private College")
        page_b = client_b.get("/profile").get_data(as_text=True)
        self.assertNotIn("Asha's Private College", page_b)

        with self.app.app_context():
            profile_b = get_db().execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_b,)).fetchone()
        self.assertEqual(profile_b["college_name"], "")

    def test_html_typed_into_the_profile_is_escaped(self):
        self.make_user()
        self.save_profile(college_name="<script>alert(1)</script>")
        page = self.client.get("/profile").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_dashboard_script_and_styles_are_served(self):
        for path in ["/static/js/dashboard.js", "/static/css/dashboard.css", "/static/css/forms.css"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            response.close()


class FriendlyDateTests(unittest.TestCase):
    @staticmethod
    def ago(**delta):
        moment = datetime.now(timezone.utc) - timedelta(**delta)
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    def test_time_ago(self):
        self.assertEqual(time_ago(self.ago(seconds=5)), "Just now")
        self.assertEqual(time_ago(self.ago(minutes=1, seconds=5)), "1 minute ago")
        self.assertEqual(time_ago(self.ago(minutes=5, seconds=5)), "5 minutes ago")
        self.assertEqual(time_ago(self.ago(hours=1, seconds=5)), "1 hour ago")
        self.assertEqual(time_ago(self.ago(hours=3, seconds=5)), "3 hours ago")
        self.assertEqual(time_ago(self.ago(days=2, seconds=5)), "2 days ago")

    def test_old_times_show_a_date(self):
        self.assertEqual(time_ago("2026-01-02 10:00:00"), "02 Jan 2026")

    def test_bad_input_does_not_crash(self):
        self.assertEqual(time_ago(None), "")
        self.assertEqual(time_ago("not a date"), "not a date")
        self.assertEqual(date_label(None), "")

    def test_date_label(self):
        self.assertEqual(date_label("2026-11-10"), "10 Nov 2026")
        self.assertEqual(date_label("2026-11-10 14:30:00"), "10 Nov 2026")


if __name__ == "__main__":
    unittest.main()
