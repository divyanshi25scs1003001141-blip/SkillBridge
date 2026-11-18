"""
Phase 6 tests: career roadmaps, step completion and real progress.

Every expected percentage is worked out by hand in the test, so the maths is
checked and not just the page. Each test uses a temporary database.
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

ROADMAPS = {
    "Python Developer",
    "Web Developer",
    "Data Analyst",
    "AI/ML Engineer",
    "Cybersecurity Analyst",
}

PYTHON_STEPS = [
    "Python Fundamentals",
    "Object-Oriented Programming",
    "Data Structures and Algorithms",
    "SQL and Database Management",
    "Flask or Django",
    "Practical Projects",
    "Git and GitHub",
    "Deployment",
]


class PhaseSixTests(AuthTestCase):
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

    def roadmap_id(self, title):
        with self.app.app_context():
            row = get_db().execute(
                "SELECT id FROM roadmaps WHERE title = ?", (title,)
            ).fetchone()
        return row["id"]

    def steps(self, title):
        with self.app.app_context():
            return get_db().execute(
                """SELECT id, step_number, title FROM roadmap_steps
                   WHERE roadmap_id = ? ORDER BY step_number""",
                (self.roadmap_id(title),),
            ).fetchall()

    def select_roadmap(self, title):
        return self.post("/roadmap/select", {"roadmap_id": self.roadmap_id(title)})

    def toggle(self, step_id, client=None, **kwargs):
        return self.post(f"/roadmap/steps/{step_id}/toggle", {}, client=client, **kwargs)

    def selected_roadmap(self, email=USER["email"]):
        with self.app.app_context():
            row = get_db().execute(
                """SELECT p.selected_roadmap_id
                   FROM user_profiles p JOIN users u ON u.id = p.user_id
                   WHERE u.email = ?""",
                (email,),
            ).fetchone()
        return row["selected_roadmap_id"] if row else None

    def completed_steps(self, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute(
                "SELECT COUNT(*) FROM user_roadmap_steps WHERE user_id = ?",
                (self.user_id(email),),
            ).fetchone()[0]


class RoadmapSeedTests(PhaseSixTests):
    def test_five_roadmaps_are_seeded_with_steps(self):
        with self.app.app_context():
            rows = get_db().execute(
                """SELECT r.title, COUNT(rs.id) AS steps
                   FROM roadmaps r LEFT JOIN roadmap_steps rs ON rs.roadmap_id = r.id
                   GROUP BY r.id"""
            ).fetchall()
        self.assertEqual({row["title"] for row in rows}, ROADMAPS)
        for row in rows:
            with self.subTest(roadmap=row["title"]):
                self.assertGreaterEqual(row["steps"], 6)

    def test_python_developer_roadmap_has_the_expected_eight_steps_in_order(self):
        steps = self.steps("Python Developer")
        self.assertEqual([step["title"] for step in steps], PYTHON_STEPS)

    def test_step_numbers_start_at_one_and_have_no_gaps(self):
        for title in ROADMAPS:
            numbers = [step["step_number"] for step in self.steps(title)]
            self.assertEqual(numbers, list(range(1, len(numbers) + 1)), title)

    def test_roadmap_seeding_repeats_without_creating_duplicates(self):
        from routes.roadmap import ensure_roadmap_seed_data

        with self.app.app_context():
            db = get_db()

            def counts():
                return tuple(
                    db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("roadmaps", "roadmap_steps")
                )

            before = counts()
            ensure_roadmap_seed_data(db)
            after = counts()
        self.assertEqual(before, after)

    def test_roadmap_page_requires_login(self):
        response = self.new_client().get("/roadmap")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


class RoadmapSelectionTests(PhaseSixTests):
    def test_roadmap_page_lists_every_roadmap_before_a_choice(self):
        page = self.client.get("/roadmap")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("No career path chosen yet", html)
        self.assertIn('href="/roadmap"', html)
        for title in ROADMAPS:
            self.assertIn(title, html)

    def test_choosing_a_roadmap_saves_it_and_shows_the_steps(self):
        response = self.select_roadmap("Python Developer")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/roadmap"))
        self.assertEqual(self.selected_roadmap(), self.roadmap_id("Python Developer"))

        html = self.client.get("/roadmap").get_data(as_text=True)
        self.assertIn("Your selected career", html)
        self.assertIn(PYTHON_STEPS[0], html)
        self.assertIn("0 of 8 steps complete", html)

        with self.app.app_context():
            activity = get_db().execute(
                """SELECT COUNT(*) AS c FROM activities
                   WHERE user_id = ? AND description = ?""",
                (self.user_id(), "Started the Python Developer roadmap"),
            ).fetchone()["c"]
        self.assertEqual(activity, 1)

    def test_invalid_roadmap_is_rejected(self):
        response = self.post("/roadmap/select", {"roadmap_id": 99999}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Choose one of the roadmaps", response.get_data(as_text=True))
        self.assertIsNone(self.selected_roadmap())

    def test_choosing_a_career_also_chooses_the_matching_roadmap(self):
        with self.app.app_context():
            career_id = get_db().execute(
                "SELECT id FROM careers WHERE title = 'Python Developer'"
            ).fetchone()["id"]
        self.post("/career", {"career_id": career_id})
        self.assertEqual(self.selected_roadmap(), self.roadmap_id("Python Developer"))
        self.assertIn(
            "8 steps", self.client.get("/roadmap").get_data(as_text=True)
        )


class RoadmapProgressTests(PhaseSixTests):
    def test_marking_a_step_complete_updates_the_percentage(self):
        self.select_roadmap("Python Developer")
        first_step = self.steps("Python Developer")[0]
        response = self.toggle(first_step["id"])
        self.assertEqual(response.status_code, 302)

        self.assertEqual(self.completed_steps(), 1)
        html = self.client.get("/roadmap").get_data(as_text=True)
        self.assertIn("1 of 8 steps complete", html)
        self.assertIn("13%", html)   # 1 of 8 rounds up from 12.5
        with self.app.app_context():
            activity = get_db().execute(
                """SELECT COUNT(*) AS c FROM activities
                   WHERE user_id = ? AND description = ?""",
                (self.user_id(), "Completed roadmap step: Python Fundamentals"),
            ).fetchone()["c"]
        self.assertEqual(activity, 1)

    def test_marking_the_same_step_again_undoes_it(self):
        self.select_roadmap("Python Developer")
        step_id = self.steps("Python Developer")[0]["id"]
        self.toggle(step_id)
        self.toggle(step_id)
        self.assertEqual(self.completed_steps(), 0)
        html = self.client.get("/roadmap").get_data(as_text=True)
        self.assertIn("0 of 8 steps complete", html)

    def test_four_of_eight_steps_is_fifty_percent(self):
        self.select_roadmap("Python Developer")
        for step in self.steps("Python Developer")[:4]:
            self.toggle(step["id"])
        html = self.client.get("/roadmap").get_data(as_text=True)
        self.assertIn("50%", html)
        self.assertIn("4 of 8 steps complete", html)

    def test_all_steps_complete_is_one_hundred_percent(self):
        self.select_roadmap("Python Developer")
        for step in self.steps("Python Developer"):
            self.toggle(step["id"])
        html = self.client.get("/roadmap").get_data(as_text=True)
        self.assertIn("100%", html)
        self.assertIn("8 of 8 steps complete", html)
        self.assertEqual(self.completed_steps(), 8)

    def test_a_step_from_another_roadmap_cannot_be_changed(self):
        self.select_roadmap("Python Developer")
        other_step = self.steps("Web Developer")[0]
        response = self.toggle(other_step["id"], follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "not part of your current roadmap", response.get_data(as_text=True)
        )
        self.assertEqual(self.completed_steps(), 0)

    def test_progress_is_private_to_each_user(self):
        second = self.new_client()
        self.post("/register", RAVI, client=second)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=second,
        )
        self.select_roadmap("Python Developer")
        self.toggle(self.steps("Python Developer")[0]["id"])

        # The second user follows the same roadmap but starts at zero.
        self.post(
            "/roadmap/select",
            {"roadmap_id": self.roadmap_id("Python Developer")},
            client=second,
        )
        html = second.get("/roadmap").get_data(as_text=True)
        self.assertIn("0 of 8 steps complete", html)
        self.assertNotIn("1 of 8 steps complete", html)
        self.assertEqual(self.completed_steps(RAVI["email"]), 0)
        self.assertEqual(self.completed_steps(), 1)

    def test_progress_is_kept_when_switching_roadmaps(self):
        self.select_roadmap("Python Developer")
        self.toggle(self.steps("Python Developer")[0]["id"])

        self.select_roadmap("Web Developer")
        self.assertIn(
            "0 of 7 steps complete", self.client.get("/roadmap").get_data(as_text=True)
        )
        self.assertEqual(self.completed_steps(), 1)  # the Python step is still saved

        self.select_roadmap("Python Developer")
        html = self.client.get("/roadmap").get_data(as_text=True)
        self.assertIn("1 of 8 steps complete", html)
        self.assertIn("13%", html)

    def test_toggle_without_csrf_token_is_refused(self):
        self.select_roadmap("Python Developer")
        step_id = self.steps("Python Developer")[0]["id"]

        client = self.new_client()
        self.post("/register", RAVI, client=client)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=client,
        )
        self.post(
            "/roadmap/select",
            {"roadmap_id": self.roadmap_id("Python Developer")},
            client=client,
        )
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)

        response = client.post(f"/roadmap/steps/{step_id}/toggle")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.completed_steps(RAVI["email"]), 0)


class DashboardRoadmapTests(PhaseSixTests):
    def test_dashboard_has_a_roadmap_panel(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Career roadmap", html)
        self.assertIn("Open roadmap", html)
        self.assertIn('href="/roadmap"', html)

    def test_dashboard_shows_real_roadmap_progress(self):
        self.select_roadmap("Python Developer")
        self.toggle(self.steps("Python Developer")[0]["id"])
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("1 of 8 steps complete", html)
        self.assertIn("13%", html)
        self.assertIn("Next step: Object-Oriented Programming", html)


if __name__ == "__main__":
    unittest.main()
