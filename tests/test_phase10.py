"""
Phase 10 tests: the career readiness report.

The report must be computed from real rows with fixed, visible weights.
"""
import unittest
from datetime import date, timedelta

from test_auth import AuthTestCase, USER
from utils.database import get_db
from routes.readiness import WEIGHTS, build_readiness, readiness_band

RAVI = {
    "name": "Ravi Kumar",
    "email": "ravi@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}

FUTURE = (date.today() + timedelta(days=10)).isoformat()


class ReadinessTests(AuthTestCase):
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

    def choose_first_career(self):
        with self.app.app_context():
            db = get_db()
            career = db.execute(
                "SELECT id, title FROM careers ORDER BY id LIMIT 1"
            ).fetchone()
            roadmap = db.execute(
                "SELECT id FROM roadmaps WHERE title = ?", (career["title"],)
            ).fetchone()
            db.execute(
                """INSERT INTO user_profiles (user_id, selected_career_id, selected_roadmap_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       selected_career_id = excluded.selected_career_id,
                       selected_roadmap_id = excluded.selected_roadmap_id""",
                (self.user_id(), career["id"], roadmap["id"] if roadmap else None),
            )
            db.commit()
        return dict(career)

    def acquire_all_career_skills(self):
        with self.app.app_context():
            db = get_db()
            user_id = self.user_id()
            career = db.execute(
                "SELECT selected_career_id FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            skills = db.execute(
                "SELECT skill_id FROM career_skills WHERE career_id = ?",
                (career["selected_career_id"],),
            ).fetchall()
            for row in skills:
                db.execute(
                    """INSERT INTO user_skills (user_id, skill_id, status)
                       VALUES (?, ?, 'Acquired')
                       ON CONFLICT(user_id, skill_id) DO UPDATE SET status = 'Acquired'""",
                    (user_id, row["skill_id"]),
                )
            db.commit()

    def complete_all_roadmap_steps(self):
        with self.app.app_context():
            db = get_db()
            user_id = self.user_id()
            profile = db.execute(
                "SELECT selected_roadmap_id FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            steps = db.execute(
                "SELECT id FROM roadmap_steps WHERE roadmap_id = ?",
                (profile["selected_roadmap_id"],),
            ).fetchall()
            for row in steps:
                db.execute(
                    """INSERT OR IGNORE INTO user_roadmap_steps (user_id, step_id)
                       VALUES (?, ?)""",
                    (user_id, row["id"]),
                )
            db.commit()

    def add_assessment_results(self, *percentages):
        with self.app.app_context():
            db = get_db()
            assessment_id = db.execute(
                "SELECT id FROM assessments ORDER BY id LIMIT 1"
            ).fetchone()["id"]
            for percentage in percentages:
                db.execute(
                    """INSERT INTO assessment_results
                       (user_id, assessment_id, score, total_questions, percentage,
                        weak_topics, answers_json)
                       VALUES (?, ?, ?, 10, ?, '', '{}')""",
                    (self.user_id(), assessment_id, int(percentage / 10), percentage),
                )
            db.commit()

    def add_projects(self, completed=0, planned=0):
        with self.app.app_context():
            db = get_db()
            for index in range(completed):
                db.execute(
                    "INSERT INTO projects (user_id, title, status) VALUES (?, ?, 'Completed')",
                    (self.user_id(), f"Done project {index}"),
                )
            for index in range(planned):
                db.execute(
                    "INSERT INTO projects (user_id, title, status) VALUES (?, ?, 'Planned')",
                    (self.user_id(), f"Planned project {index}"),
                )
            db.commit()

    def add_goals(self, completed=0, open_goals=0):
        with self.app.app_context():
            db = get_db()
            for index in range(completed):
                db.execute(
                    """INSERT INTO goals
                       (user_id, title, goal_type, target_date, is_completed, completed_at)
                       VALUES (?, ?, 'Weekly', ?, 1, datetime('now'))""",
                    (self.user_id(), f"Done goal {index}", FUTURE),
                )
            for index in range(open_goals):
                db.execute(
                    """INSERT INTO goals (user_id, title, goal_type, target_date)
                       VALUES (?, ?, 'Weekly', ?)""",
                    (self.user_id(), f"Open goal {index}", FUTURE),
                )
            db.commit()

    def report(self):
        with self.app.app_context():
            return build_readiness(get_db(), self.user_id())

    def expected_overall(self, components):
        return (sum(c["score"] * c["weight"] for c in components) + 50) // 100

    def second_user_client(self):
        client = self.new_client()
        self.post("/register", RAVI, client=client)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=client,
        )
        return client


class WeightsAndBandsTests(unittest.TestCase):
    def test_weights_add_up_to_one_hundred(self):
        self.assertEqual(sum(WEIGHTS.values()), 100)

    def test_bands_have_no_gaps(self):
        self.assertEqual(readiness_band(0), "First steps")
        self.assertEqual(readiness_band(24), "First steps")
        self.assertEqual(readiness_band(25), "Getting started")
        self.assertEqual(readiness_band(49), "Getting started")
        self.assertEqual(readiness_band(50), "Building momentum")
        self.assertEqual(readiness_band(74), "Building momentum")
        self.assertEqual(readiness_band(75), "Interview-ready foundations")
        self.assertEqual(readiness_band(100), "Interview-ready foundations")


class ReadinessReportTests(ReadinessTests):
    def test_report_requires_login(self):
        response = self.new_client().get("/readiness")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_empty_report_is_honest(self):
        report = self.report()
        self.assertEqual(report["overall"], 0)
        self.assertEqual(report["band"], "First steps")
        self.assertEqual([c["score"] for c in report["components"]], [0, 0, 0, 0, 0])
        self.assertIn(
            "Choose a career path", [action["title"] for action in report["next_actions"]]
        )

    def test_page_renders_the_breakdown(self):
        page = self.client.get("/readiness")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Career readiness report", html)
        self.assertIn("How the score is built", html)
        for label in ("Skill coverage", "Roadmap progress", "Assessment results",
                      "Finished projects", "Goals completed"):
            with self.subTest(label=label):
                self.assertIn(label, html)
        self.assertIn("estimates preparation, not job outcomes", html)

    def test_skill_coverage_drives_the_score(self):
        self.choose_first_career()
        self.acquire_all_career_skills()
        report = self.report()
        components = {c["key"]: c for c in report["components"]}
        self.assertEqual(components["skills"]["score"], 100)
        self.assertEqual(components["skills"]["weight"], 35)
        self.assertEqual(report["overall"], 35)
        self.assertEqual(report["overall"], self.expected_overall(report["components"]))

    def test_full_evidence_gives_ninety_six(self):
        self.choose_first_career()
        self.acquire_all_career_skills()
        self.complete_all_roadmap_steps()
        self.add_assessment_results(80)
        self.add_projects(completed=3)
        self.add_goals(completed=2)
        report = self.report()
        scores = {c["key"]: c["score"] for c in report["components"]}
        self.assertEqual(scores, {
            "skills": 100, "roadmap": 100, "assessments": 80,
            "projects": 100, "goals": 100,
        })
        self.assertEqual(report["overall"], 96)
        self.assertEqual(report["band"], "Interview-ready foundations")

    def test_only_the_latest_assessment_attempt_counts(self):
        self.choose_first_career()
        self.add_assessment_results(50, 90)
        report = self.report()
        self.assertEqual(
            {c["key"]: c for c in report["components"]}["assessments"]["score"], 90
        )

    def test_projects_score_caps_at_three_completed(self):
        self.add_projects(completed=5)
        report = self.report()
        component = {c["key"]: c for c in report["components"]}["projects"]
        self.assertEqual(component["score"], 100)
        self.assertIn("5 completed", component["detail"])

    def test_planned_projects_do_not_count(self):
        self.add_projects(completed=0, planned=4)
        spec = self.report()
        component = {c["key"]: c for c in spec["components"]}["projects"]
        self.assertEqual(component["score"], 0)
        self.assertEqual(spec["supporting"]["projects_planned"], 4)

    def test_goals_percentage_is_real(self):
        self.add_goals(completed=1, open_goals=2)
        report = self.report()
        component = {c["key"]: c for c in report["components"]}["goals"]
        self.assertEqual(component["score"], 33)
        self.assertEqual(component["detail"], "1 of 3 goals complete")

    def test_next_actions_point_at_real_gaps(self):
        self.choose_first_career()
        report = self.report()
        actions = " ".join(action["title"] for action in report["next_actions"])
        self.assertIn("core skill", actions)
        self.assertIn("Next roadmap step", actions)
        self.assertIn("Take a skill assessment", actions)

    def test_report_is_private_to_the_student(self):
        self.choose_first_career()
        self.acquire_all_career_skills()
        self.add_projects(completed=3)
        self.assertEqual(self.report()["overall"], 45)

        other = self.second_user_client()
        other_html = other.get("/readiness").get_data(as_text=True)
        self.assertIn("0% ready", other_html)
        self.assertIn("First steps", other_html)
        with self.app.app_context():
            other_report = build_readiness(get_db(), self.user_id(RAVI["email"]))
        self.assertEqual(other_report["overall"], 0)


if __name__ == "__main__":
    unittest.main()
