"""
Phase 9 tests: weekly and monthly learning goals.

Each test uses a temporary database, so real data is never touched.
"""
import unittest
from datetime import date, timedelta

from test_auth import AuthTestCase, USER
from utils.database import get_db
from routes.goals import progress_percentage

RAVI = {
    "name": "Ravi Kumar",
    "email": "ravi@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}

TODAY = date.today()
FUTURE = (TODAY + timedelta(days=7)).isoformat()
PAST = (TODAY - timedelta(days=7)).isoformat()


class PhaseNineTests(AuthTestCase):
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

    def goal_row(self, title):
        with self.app.app_context():
            return get_db().execute(
                "SELECT * FROM goals WHERE title = ?", (title,)
            ).fetchone()

    def goal_id(self, title):
        row = self.goal_row(title)
        return row["id"] if row else None

    def goal_count(self):
        with self.app.app_context():
            return get_db().execute("SELECT COUNT(*) FROM goals").fetchone()[0]

    def create(self, client=None, follow_redirects=False, **overrides):
        data = {
            "title": "Finish Python functions",
            "description": "Read the chapter and solve three exercises.",
            "goal_type": "Weekly",
            "target_date": FUTURE,
        }
        data.update(overrides)
        return self.post(
            "/goals/new", data, client=client, follow_redirects=follow_redirects
        )

    def complete(self, goal_id, client=None, follow_redirects=False):
        return self.post(
            f"/goals/{goal_id}/complete",
            {},
            client=client,
            follow_redirects=follow_redirects,
        )

    def reopen(self, goal_id, client=None, follow_redirects=False):
        return self.post(
            f"/goals/{goal_id}/reopen",
            {},
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


class ProgressMathTests(unittest.TestCase):
    def test_percentage_rounds_half_up(self):
        self.assertEqual(progress_percentage(0, 0), 0)
        self.assertEqual(progress_percentage(1, 3), 33)
        self.assertEqual(progress_percentage(2, 3), 67)
        self.assertEqual(progress_percentage(1, 8), 13)
        self.assertEqual(progress_percentage(3, 3), 100)


class CreateGoalTests(PhaseNineTests):
    def test_goals_page_requires_login(self):
        response = self.new_client().get("/goals")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_empty_page_shows_an_empty_state(self):
        page = self.client.get("/goals")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Learning goals", html)
        self.assertIn("No goals yet", html)
        self.assertIn("0 of 0 complete", html)

    def test_create_weekly_goal_saves_and_lists_it(self):
        response = self.create()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/goals")

        row = self.goal_row("Finish Python functions")
        self.assertEqual(row["goal_type"], "Weekly")
        self.assertEqual(row["target_date"], FUTURE)
        self.assertEqual(row["is_completed"], 0)
        self.assertIsNone(row["completed_at"])
        self.assertEqual(row["user_id"], self.user_id())

        html = self.client.get("/goals").get_data(as_text=True)
        self.assertIn("Finish Python functions", html)
        self.assertIn("Weekly goals", html)
        self.assertIn("Mark complete", html)

    def test_create_monthly_goal_and_log_activity(self):
        self.create(title="Build a portfolio site", goal_type="Monthly")
        row = self.goal_row("Build a portfolio site")
        self.assertEqual(row["goal_type"], "Monthly")
        with self.app.app_context():
            logged = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE description = ?",
                ("Added a monthly goal: Build a portfolio site",),
            ).fetchone()[0]
        self.assertEqual(logged, 1)

    def test_title_is_required(self):
        response = self.create(title="  ", follow_redirects=True)
        self.assertIn("Give your goal a title.", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 0)

    def test_title_length_is_checked(self):
        response = self.create(title="x" * 121, follow_redirects=True)
        self.assertIn("Titles can be up to 120 characters.", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 0)

    def test_description_length_is_checked(self):
        response = self.create(description="x" * 501, follow_redirects=True)
        self.assertIn("Descriptions can be up to 500 characters.", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 0)

    def test_goal_type_must_be_weekly_or_monthly(self):
        response = self.create(goal_type="Yearly", follow_redirects=True)
        self.assertIn("Choose Weekly or Monthly", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 0)

    def test_invalid_target_date_is_rejected(self):
        for bad_date in ("2026-02-30", "31-12-2026", "", "next friday"):
            with self.subTest(bad_date=bad_date):
                response = self.create(target_date=bad_date, follow_redirects=True)
                self.assertIn("Choose a target date", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 0)

    def test_past_target_date_is_allowed_but_marked_overdue(self):
        self.create(target_date=PAST)
        html = self.client.get("/goals").get_data(as_text=True)
        self.assertIn("Overdue", html)
        self.assertIn('<span class="badge badge-overdue">Overdue</span>', html)

    def test_future_goal_is_not_overdue(self):
        self.create(target_date=FUTURE)
        html = self.client.get("/goals").get_data(as_text=True)
        self.assertNotIn("badge-overdue", html)

    def test_entered_values_survive_a_validation_error(self):
        response = self.create(title="", target_date=FUTURE, description="Keep this note")
        html = response.get_data(as_text=True)
        self.assertIn("Keep this note", html)
        self.assertIn(f'value="{FUTURE}"', html)

    def test_goal_title_is_escaped(self):
        self.create(title="<script>alert(1)</script>")
        html = self.client.get("/goals").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_create_requires_csrf_token(self):
        client = self.second_user_client()
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post(
            "/goals/new",
            data={"title": "No token", "goal_type": "Weekly", "target_date": FUTURE},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.goal_count(), 0)


class CompleteReopenTests(PhaseNineTests):
    def test_complete_marks_the_goal_finished(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        response = self.complete(goal_id)
        self.assertEqual(response.status_code, 302)

        row = self.goal_row("Finish Python functions")
        self.assertEqual(row["is_completed"], 1)
        self.assertIsNotNone(row["completed_at"])

        html = self.client.get("/goals").get_data(as_text=True)
        self.assertIn("Reopen", html)
        self.assertIn("1 of 1 complete", html)
        self.assertIn("100% of your goals are complete", html)

    def test_complete_is_logged_once(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        self.complete(goal_id)
        self.complete(goal_id)
        with self.app.app_context():
            logged = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE description = ?",
                ("Completed a goal: Finish Python functions",),
            ).fetchone()[0]
        self.assertEqual(logged, 1)

    def test_reopen_clears_the_completion(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        self.complete(goal_id)
        response = self.reopen(goal_id)
        self.assertEqual(response.status_code, 302)

        row = self.goal_row("Finish Python functions")
        self.assertEqual(row["is_completed"], 0)
        self.assertIsNone(row["completed_at"])

        html = self.client.get("/goals").get_data(as_text=True)
        self.assertIn("Mark complete", html)
        self.assertIn("0 of 1 complete", html)

    def test_reopening_an_open_goal_is_handled(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        response = self.reopen(goal_id, follow_redirects=True)
        self.assertIn("already open", response.get_data(as_text=True))

    def test_completing_an_already_finished_goal_is_handled(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        self.complete(goal_id)
        response = self.complete(goal_id, follow_redirects=True)
        self.assertIn("already complete", response.get_data(as_text=True))

    def test_unknown_goal_is_handled(self):
        response = self.complete(99999, follow_redirects=True)
        self.assertIn("That goal could not be found.", response.get_data(as_text=True))

    def test_another_users_goal_cannot_be_completed_or_reopened(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        other = self.second_user_client()

        response = self.complete(goal_id, client=other, follow_redirects=True)
        self.assertIn("That goal could not be found.", response.get_data(as_text=True))
        self.assertEqual(self.goal_row("Finish Python functions")["is_completed"], 0)

        self.complete(goal_id)  # owner completes it
        response = self.reopen(goal_id, client=other, follow_redirects=True)
        self.assertIn("That goal could not be found.", response.get_data(as_text=True))
        self.assertEqual(self.goal_row("Finish Python functions")["is_completed"], 1)

    def test_complete_and_reopen_require_csrf_token(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        client = self.second_user_client()
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        self.assertEqual(client.post(f"/goals/{goal_id}/complete").status_code, 400)
        self.assertEqual(client.post(f"/goals/{goal_id}/reopen").status_code, 400)
        self.assertEqual(self.goal_row("Finish Python functions")["is_completed"], 0)


class GoalDashboardTests(PhaseNineTests):
    def test_dashboard_shows_real_progress(self):
        self.create(title="Goal One")
        self.create(title="Goal Two", goal_type="Monthly")
        self.create(title="Goal Three")
        self.complete(self.goal_id("Goal One"))

        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("1 of 3 complete", html)
        self.assertIn("33% of your goals are complete", html)
        self.assertIn("of 3 weekly and monthly goals", html)

    def test_dashboard_counts_overdue_goals(self):
        self.create(title="Late Goal", target_date=PAST)
        self.create(title="On Time Goal", target_date=FUTURE)
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("0 of 2 complete · 2 open · 1 overdue", html)

    def test_dashboard_shows_zero_progress_without_goals(self):
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("of 0 weekly and monthly goals", html)
        self.assertIn("Set a weekly or monthly goal", html)

    def test_dashboard_updates_after_completing_everything(self):
        self.create(title="Only Goal")
        self.complete(self.goal_id("Only Goal"))
        html = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("1 of 1 complete", html)
        self.assertIn("100% of your goals are complete", html)


class GoalPrivacyTests(PhaseNineTests):
    def test_other_users_goals_are_never_listed(self):
        self.create(title="Asha Private Goal")
        other = self.second_user_client()
        html = other.get("/goals").get_data(as_text=True)
        self.assertNotIn("Asha Private Goal", html)
        self.assertIn("No goals yet", html)

    def test_counts_are_per_user(self):
        self.create(title="Asha Goal")
        other = self.second_user_client()
        html = other.get("/goals").get_data(as_text=True)
        self.assertIn("0 of 0 complete", html)


class GoalDeleteTests(PhaseNineTests):
    def test_delete_removes_own_goal_and_logs_it(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        response = self.post(f"/goals/{goal_id}/delete", {}, follow_redirects=True)
        self.assertIn("deleted", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 0)

        with self.app.app_context():
            logged = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE description = ?",
                ("Deleted a goal: Finish Python functions",),
            ).fetchone()[0]
        self.assertEqual(logged, 1)

    def test_delete_removes_a_completed_goal(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        self.complete(goal_id)
        self.post(f"/goals/{goal_id}/delete", {})
        self.assertEqual(self.goal_count(), 0)

    def test_deleting_an_unknown_goal_is_handled(self):
        response = self.post("/goals/99999/delete", {}, follow_redirects=True)
        self.assertIn("That goal could not be found.", response.get_data(as_text=True))

    def test_another_users_goal_cannot_be_deleted(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        other = self.second_user_client()
        response = self.post(
            f"/goals/{goal_id}/delete", {}, client=other, follow_redirects=True
        )
        self.assertIn("That goal could not be found.", response.get_data(as_text=True))
        self.assertEqual(self.goal_count(), 1)

    def test_delete_requires_csrf_token(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        client = self.second_user_client()
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post(f"/goals/{goal_id}/delete")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.goal_count(), 1)

    def test_page_offers_delete_with_a_confirmation_prompt(self):
        self.create()
        goal_id = self.goal_id("Finish Python functions")
        html = self.client.get("/goals").get_data(as_text=True)
        self.assertIn(f'action="/goals/{goal_id}/delete"', html)
        self.assertIn('data-confirm="Delete this goal? This cannot be undone."', html)


if __name__ == "__main__":
    unittest.main()
