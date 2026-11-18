"""Phase 4 tests: private skill management and skill assessments."""
from test_auth import AuthTestCase, USER
from utils.database import get_db


class PhaseFourTests(AuthTestCase):
    def setUp(self):
        super().setUp()
        self.post("/register", USER)
        self.post("/login", {"email": USER["email"], "password": USER["password"]})

    def test_skill_catalogue_loads_and_user_can_add_skill(self):
        page = self.client.get("/skills")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Skill Management", page.data)
        with self.app.app_context():
            skill = get_db().execute("SELECT id FROM skills WHERE name = 'Python'").fetchone()
        response = self.post("/skills", {"action": "add", "skill_id": skill["id"]})
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/skills").get_data(as_text=True)
        self.assertIn("Python", page)

    def test_user_can_update_and_remove_only_their_own_skill(self):
        self.client.get("/skills")
        with self.app.app_context():
            db = get_db()
            skill_id = db.execute("SELECT id FROM skills WHERE name = 'Python'").fetchone()["id"]
            user_id = db.execute("SELECT id FROM users WHERE email = ?", (USER["email"],)).fetchone()["id"]
            row_id = db.execute("INSERT INTO user_skills (user_id, skill_id) VALUES (?, ?)", (user_id, skill_id)).lastrowid
            db.commit()
        self.post("/skills", {"action": "update", "user_skill_id": row_id, "status": "Acquired"})
        with self.app.app_context():
            status = get_db().execute("SELECT status FROM user_skills WHERE id = ?", (row_id,)).fetchone()["status"]
        self.assertEqual(status, "Acquired")
        self.post("/skills", {"action": "delete", "user_skill_id": row_id})
        with self.app.app_context():
            self.assertIsNone(get_db().execute("SELECT id FROM user_skills WHERE id = ?", (row_id,)).fetchone())

    def test_assessment_is_scored_and_saved_to_history(self):
        page = self.client.get("/assessments")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Skill Assessments", page.data)
        with self.app.app_context():
            db = get_db()
            assessment = db.execute("SELECT id FROM assessments WHERE title = 'Python'").fetchone()
            questions = db.execute("SELECT id, correct_option FROM assessment_questions WHERE assessment_id = ?", (assessment["id"],)).fetchall()
        answers = {f"question_{q['id']}": q["correct_option"] for q in questions}
        response = self.post(f"/assessments/{assessment['id']}/submit", answers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"100%", response.data)
        history = self.client.get("/assessment-history").get_data(as_text=True)
        self.assertIn("Python", history)
        self.assertIn("10/10 correct", history)
    def test_all_eight_assessments_have_at_least_ten_questions_and_real_topics(self):
        response = self.client.get("/assessments")
        self.assertEqual(response.status_code, 200)
        expected = {
            "Python", "C++", "HTML and CSS", "JavaScript",
            "Basic Programming Concepts", "Java", "SQL", "Web Development",
        }
        with self.app.app_context():
            db = get_db()
            rows = db.execute(
                """SELECT a.title, COUNT(q.id) AS total, COUNT(DISTINCT q.topic) AS topics
                   FROM assessments a LEFT JOIN assessment_questions q
                   ON q.assessment_id = a.id GROUP BY a.id"""
            ).fetchall()
        actual = {row["title"] for row in rows}
        self.assertTrue(expected.issubset(actual))
        for row in rows:
            self.assertGreaterEqual(row["total"], 10, row["title"])
            self.assertGreaterEqual(row["topics"], 3, row["title"])

    def test_seeding_is_idempotent_and_preserves_existing_attempts(self):
        self.client.get("/assessments")
        with self.app.app_context():
            db = get_db()
            assessment = db.execute("SELECT id FROM assessments WHERE title = 'Python'").fetchone()
            before = db.execute(
                "SELECT COUNT(*) FROM assessment_questions WHERE assessment_id = ?",
                (assessment["id"],),
            ).fetchone()[0]
            user_id = db.execute("SELECT id FROM users WHERE email = ?", (USER["email"],)).fetchone()["id"]
            db.execute(
                """INSERT INTO assessment_results
                   (user_id, assessment_id, score, total_questions, percentage, weak_topics, answers_json)
                   VALUES (?, ?, 3, 10, 30, 'Loops', '{}')""",
                (user_id, assessment["id"]),
            )
            db.commit()
            from routes.skills import ensure_phase4_seed_data
            ensure_phase4_seed_data(db)
            after = db.execute(
                "SELECT COUNT(*) FROM assessment_questions WHERE assessment_id = ?",
                (assessment["id"],),
            ).fetchone()[0]
            attempts = db.execute(
                "SELECT COUNT(*) FROM assessment_results WHERE user_id = ? AND assessment_id = ?",
                (user_id, assessment["id"]),
            ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(attempts, 1)

    def test_second_user_cannot_update_or_delete_first_users_skill(self):
        self.client.get("/skills")
        with self.app.app_context():
            db = get_db()
            skill_id = db.execute("SELECT id FROM skills WHERE name = 'Python'").fetchone()["id"]
            first_user_id = db.execute("SELECT id FROM users WHERE email = ?", (USER["email"],)).fetchone()["id"]
            row_id = db.execute(
                "INSERT INTO user_skills (user_id, skill_id, status) VALUES (?, ?, 'Learning')",
                (first_user_id, skill_id),
            ).lastrowid
            db.commit()

        second = self.new_client()
        second_user = dict(USER, name="Second User", email="second@example.com")
        self.post("/register", second_user, client=second)
        self.post("/login", {"email": second_user["email"], "password": second_user["password"]}, client=second)
        self.post("/skills", {"action": "update", "user_skill_id": row_id, "status": "Acquired"}, client=second)
        self.post("/skills", {"action": "delete", "user_skill_id": row_id}, client=second)

        with self.app.app_context():
            row = get_db().execute("SELECT status FROM user_skills WHERE id = ?", (row_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "Learning")
        with self.app.app_context():
            second_id = get_db().execute("SELECT id FROM users WHERE email = ?", (second_user["email"],)).fetchone()["id"]
            second_skill_count = get_db().execute("SELECT COUNT(*) FROM user_skills WHERE user_id = ?", (second_id,)).fetchone()[0]
        self.assertEqual(second_skill_count, 0)

