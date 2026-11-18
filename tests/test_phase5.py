"""
Phase 5 tests: career selection, skill-gap analysis and the dashboard summary.

The expected gap is calculated by hand in each test so the maths is checked,
not just the page. Every test uses a temporary database.
"""
import unittest

from test_auth import AuthTestCase, USER
from utils.database import get_db

RAVI = {
    "name": "Ravi Kumar",
    "email": "ravi@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}

CAREERS = {
    "Python Developer",
    "Web Developer",
    "Data Analyst",
    "AI/ML Engineer",
    "Cybersecurity Analyst",
}


class PhaseFiveTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.post("/register", USER)
        self.post("/login", {"email": USER["email"], "password": USER["password"]})

    # ----- helpers -----
    def user_id(self, email=USER["email"]):
        with self.app.app_context():
            row = get_db().execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
        return row["id"]

    def career_id(self, title):
        with self.app.app_context():
            row = get_db().execute(
                "SELECT id FROM careers WHERE title = ?", (title,)
            ).fetchone()
        return row["id"]

    def selected_career(self, email=USER["email"]):
        with self.app.app_context():
            row = get_db().execute(
                """SELECT p.selected_career_id
                   FROM user_profiles p JOIN users u ON u.id = p.user_id
                   WHERE u.email = ?""",
                (email,),
            ).fetchone()
        return row["selected_career_id"] if row else None

    def add_skill(self, name, status, email=USER["email"]):
        with self.app.app_context():
            db = get_db()
            user_id = db.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()["id"]
            skill_id = db.execute(
                "SELECT id FROM skills WHERE name = ?", (name,)
            ).fetchone()["id"]
            db.execute(
                """INSERT INTO user_skills (user_id, skill_id, status) VALUES (?, ?, ?)
                   ON CONFLICT (user_id, skill_id) DO UPDATE SET status = excluded.status""",
                (user_id, skill_id, status),
            )
            db.commit()

    def choose(self, title):
        return self.post("/career", {"career_id": self.career_id(title)})

    def gap_percentage(self, email=USER["email"]):
        """Reads the saved gap the same way the page builds it."""
        from routes.career import build_skill_gap

        with self.app.app_context():
            db = get_db()
            user_id = db.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()["id"]
            career_id = db.execute(
                """SELECT selected_career_id FROM user_profiles WHERE user_id = ?""",
                (user_id,),
            ).fetchone()["selected_career_id"]
            return build_skill_gap(db, user_id, career_id)["percentage"]


class CareerCatalogueTests(PhaseFiveTests):
    def test_five_careers_are_seeded_with_required_skills(self):
        with self.app.app_context():
            rows = get_db().execute(
                """SELECT c.title, COUNT(cs.id) AS skills,
                          SUM(CASE WHEN cs.is_core = 1 THEN 1 ELSE 0 END) AS core
                   FROM careers c LEFT JOIN career_skills cs ON cs.career_id = c.id
                   GROUP BY c.id"""
            ).fetchall()
        self.assertEqual({row["title"] for row in rows}, CAREERS)
        for row in rows:
            with self.subTest(career=row["title"]):
                self.assertGreaterEqual(row["skills"], 4)
                self.assertGreaterEqual(row["core"], 1)

    def test_every_required_skill_exists_in_the_skill_catalogue(self):
        with self.app.app_context():
            orphans = get_db().execute(
                """SELECT cs.id FROM career_skills cs
                   LEFT JOIN skills s ON s.id = cs.skill_id
                   WHERE s.id IS NULL"""
            ).fetchall()
        self.assertEqual(orphans, [])

    def test_career_seeding_repeats_without_creating_duplicates(self):
        from routes.career import ensure_career_seed_data

        with self.app.app_context():
            db = get_db()

            def counts():
                return tuple(
                    db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("careers", "career_skills", "skills")
                )

            before = counts()
            ensure_career_seed_data(db)
            after = counts()
        self.assertEqual(before, after)

    def test_career_page_requires_login(self):
        response = self.new_client().get("/career")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_career_page_lists_every_career(self):
        page = self.client.get("/career")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Choose a career path", html)
        self.assertIn("No career path chosen yet", html)
        for title in CAREERS:
            self.assertIn(title, html)


class CareerSelectionTests(PhaseFiveTests):
    def test_selecting_a_career_saves_it_and_opens_the_gap(self):
        response = self.choose("Python Developer")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/skill-gap"))
        self.assertEqual(self.selected_career(), self.career_id("Python Developer"))

        with self.app.app_context():
            activity = get_db().execute(
                """SELECT COUNT(*) AS c FROM activities
                   WHERE user_id = ? AND description = ?""",
                (self.user_id(), "Selected Python Developer as the target career"),
            ).fetchone()["c"]
        self.assertEqual(activity, 1)

    def test_career_page_shows_the_selection_and_its_gap(self):
        self.choose("Python Developer")
        html = self.client.get("/career").get_data(as_text=True)
        self.assertIn("Your selected career", html)
        self.assertIn("0%", html)
        self.assertNotIn("No career path chosen yet", html)

    def test_invalid_career_is_rejected(self):
        response = self.post("/career", {"career_id": 99999})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Choose one of the careers", response.get_data(as_text=True))
        self.assertIsNone(self.selected_career())

    def test_non_numeric_career_is_rejected(self):
        response = self.post("/career", {"career_id": "python"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.selected_career())

    def test_career_form_without_csrf_token_is_refused(self):
        response = self.new_client().post(
            "/career", data={"career_id": self.career_id("Web Developer")}
        )
        self.assertEqual(response.status_code, 400)

    def test_switching_career_updates_the_saved_choice(self):
        self.choose("Web Developer")
        self.assertEqual(self.selected_career(), self.career_id("Web Developer"))
        self.choose("Data Analyst")
        self.assertEqual(self.selected_career(), self.career_id("Data Analyst"))
        self.assertEqual(self.client.get("/skill-gap").status_code, 200)


class SkillGapTests(PhaseFiveTests):
    def test_skill_gap_page_requires_login(self):
        response = self.new_client().get("/skill-gap")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_skill_gap_without_a_career_sends_user_to_the_career_page(self):
        response = self.client.get("/skill-gap")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/career"))

    def test_empty_skill_list_shows_zero_percent_and_every_gap(self):
        self.choose("Web Developer")
        page = self.client.get("/skill-gap")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("0%", html)
        self.assertIn("Required skills", html)
        self.assertIn(">6<", html)
        self.assertNotIn('class="status-pill is-acquired"', html)
        self.assertIn("Not started", html)

    def test_core_skills_weigh_twice_and_learning_counts_half(self):
        # Web Developer weights: HTML, CSS, JavaScript, REST APIs are core (2),
        # Git & GitHub and SQL are supporting (1) -> 10 possible points.
        # HTML acquired (2) + CSS learning (1) + JavaScript learning (1)
        # + Git acquired (1) + SQL acquired (1) = 6 -> 60%.
        self.choose("Web Developer")
        for name, status in [
            ("HTML", "Acquired"),
            ("CSS", "Learning"),
            ("JavaScript", "Learning"),
            ("Git & GitHub", "Acquired"),
            ("SQL", "Acquired"),
        ]:
            self.add_skill(name, status)

        self.assertEqual(self.gap_percentage(), 60)
        html = self.client.get("/skill-gap").get_data(as_text=True)
        self.assertIn("60%", html)
        self.assertIn("3 acquired · 2 learning · 1 not started", html)
        self.assertIn("REST APIs", html)

    def test_all_skills_acquired_is_one_hundred_percent(self):
        self.choose("Cybersecurity Analyst")
        for name in ["Networking", "Linux", "Security Basics", "Cybersecurity", "Python", "SQL"]:
            self.add_skill(name, "Acquired")
        self.assertEqual(self.gap_percentage(), 100)
        self.assertIn("100%", self.client.get("/skill-gap").get_data(as_text=True))

    def test_assessment_score_is_insight_and_never_changes_a_skill(self):
        with self.app.app_context():
            db = get_db()
            assessment = db.execute(
                "SELECT id FROM assessments WHERE title = 'Python'"
            ).fetchone()
            questions = db.execute(
                "SELECT id, correct_option FROM assessment_questions WHERE assessment_id = ?",
                (assessment["id"],),
            ).fetchall()
        answers = {f"question_{q['id']}": q["correct_option"] for q in questions}
        self.post(f"/assessments/{assessment['id']}/submit", answers)

        self.choose("Python Developer")
        html = self.client.get("/skill-gap").get_data(as_text=True)
        self.assertIn("Latest Python assessment: 100%", html)
        # The 100% score must not fill in the gap by itself.
        self.assertEqual(self.gap_percentage(), 0)
        with self.app.app_context():
            count = get_db().execute(
                "SELECT COUNT(*) FROM user_skills WHERE user_id = ?", (self.user_id(),)
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_recommendations_name_the_missing_core_skills(self):
        self.choose("Python Developer")
        html = self.client.get("/skill-gap").get_data(as_text=True)
        self.assertIn("core skills your career needs", html)
        self.assertIn("Python", html)

    def test_two_users_have_private_career_choices_and_gaps(self):
        second = self.new_client()
        self.post("/register", RAVI, client=second)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=second,
        )

        self.choose("Web Developer")
        self.add_skill("HTML", "Acquired")

        page = second.get("/career").get_data(as_text=True)
        self.assertIn("No career path chosen yet", page)
        self.assertIsNone(self.selected_career(RAVI["email"]))
        self.assertEqual(second.get("/skill-gap").status_code, 302)

        # The first user's choice is untouched by the second user's page visits.
        self.assertEqual(self.selected_career(), self.career_id("Web Developer"))
        self.assertEqual(self.gap_percentage(), 20)


class DashboardCareerTests(PhaseFiveTests):
    def test_dashboard_asks_for_a_career_when_none_is_chosen(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Career goal", html)
        self.assertIn('href="/career"', html)

    def test_dashboard_shows_the_selected_career_and_real_percentage(self):
        self.choose("Web Developer")
        self.add_skill("HTML", "Acquired")  # core skill: 2 of 10 points
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Web Developer", html)
        self.assertIn("20% of its required skills covered", html)
        self.assertIn("1 acquired · 0 learning · 5 not started", html)

    def test_sidebar_links_to_the_new_pages(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('href="/career"', html)
        self.assertIn('href="/skill-gap"', html)


if __name__ == "__main__":
    unittest.main()
