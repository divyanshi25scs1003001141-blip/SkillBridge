"""
Phase 7 tests: learning resources, search/filters and private favourites.

Each test uses a temporary database, so real data is never touched.
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


class PhaseSevenTests(AuthTestCase):
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

    def resource_id(self, title):
        with self.app.app_context():
            row = get_db().execute(
                "SELECT id FROM resources WHERE title = ?", (title,)
            ).fetchone()
        return row["id"]

    def favourite_count(self, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute(
                "SELECT COUNT(*) FROM favourites WHERE user_id = ?",
                (self.user_id(email),),
            ).fetchone()[0]

    def save(self, title, client=None, **data):
        return self.post(
            f"/resources/{self.resource_id(title)}/favourite", data, client=client
        )


class ResourceTypeTests(PhaseSevenTests):
    """Documentation, Tutorial and Course must be visible and filterable."""

    def test_types_are_normalised_to_the_known_list(self):
        from routes.resources import RESOURCE_TYPES

        with self.app.app_context():
            types = {
                row["resource_type"]
                for row in get_db().execute("SELECT DISTINCT resource_type FROM resources")
            }
        self.assertTrue(types <= set(RESOURCE_TYPES))
        self.assertIn("Documentation", types)
        self.assertIn("Tutorial", types)
        self.assertIn("Course", types)
        self.assertIn("Video", types)

    def test_video_tutorials_are_real_youtube_links(self):
        with self.app.app_context():
            rows = get_db().execute(
                "SELECT url FROM resources WHERE resource_type = 'Video'"
            ).fetchall()
        self.assertGreaterEqual(len(rows), 12)
        for row in rows:
            with self.subTest(url=row["url"]):
                self.assertTrue(row["url"].startswith("https://www.youtube.com/"))

    def test_type_counts_are_real(self):
        with self.app.app_context():
            db = get_db()
            total = db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            summed = db.execute(
                "SELECT SUM(count) FROM (SELECT COUNT(*) AS count FROM resources GROUP BY resource_type)"
            ).fetchone()[0]
        self.assertEqual(total, summed)

    def test_page_shows_type_chips_with_counts(self):
        html = self.client.get("/resources").get_data(as_text=True)
        for label in ("All types", "Documentation (", "Tutorial (", "Course (", "Book ("):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_filter_by_documentation(self):
        html = self.client.get(
            "/resources", query_string={"resource_type": "Documentation"}
        ).get_data(as_text=True)
        self.assertIn("The Python Tutorial (official)", html)
        self.assertIn("MDN JavaScript Guide", html)
        self.assertNotIn("SQLBolt", html)          # Tutorial
        self.assertNotIn("Introduction to Programming with Python", html)  # Course

    def test_filter_by_course(self):
        html = self.client.get(
            "/resources", query_string={"resource_type": "Course"}
        ).get_data(as_text=True)
        self.assertIn("Introduction to Programming with Python", html)
        self.assertNotIn("SQLBolt", html)

    def test_filter_by_tutorial(self):
        html = self.client.get(
            "/resources", query_string={"resource_type": "Tutorial"}
        ).get_data(as_text=True)
        self.assertIn("SQLBolt", html)
        self.assertIn("javascript.info", html)
        self.assertNotIn("Pro Git (free book)", html)  # Book

    def test_type_filter_combines_with_difficulty(self):
        html = self.client.get(
            "/resources",
            query_string={"resource_type": "Documentation", "difficulty": "Beginner"},
        ).get_data(as_text=True)
        self.assertIn("The Python Tutorial (official)", html)
        self.assertNotIn("scikit-learn: Getting started", html)  # Intermediate docs

    def test_unknown_type_falls_back_to_everything(self):
        html = self.client.get(
            "/resources", query_string={"resource_type": "Podcast"}
        ).get_data(as_text=True)
        self.assertIn("SQLBolt", html)

    def test_type_is_kept_after_saving_a_favourite(self):
        response = self.save("SQLBolt", resource_type="Tutorial")
        self.assertEqual(response.status_code, 302)
        self.assertIn("resource_type=Tutorial", response.headers["Location"])

    def test_selected_type_stays_selected(self):
        html = self.client.get(
            "/resources", query_string={"resource_type": "Course"}
        ).get_data(as_text=True)
        self.assertIn('<option value="Course" selected>', html)


class ResourceCatalogueTests(PhaseSevenTests):
    def test_catalogue_is_seeded_across_many_skills(self):
        with self.app.app_context():
            rows = get_db().execute(
                "SELECT title, url, category, difficulty FROM resources"
            ).fetchall()
        self.assertGreaterEqual(len(rows), 50)
        self.assertGreaterEqual(len({row["category"] for row in rows}), 12)
        self.assertTrue({row["difficulty"] for row in rows} <= {"Beginner", "Intermediate", "Advanced"})
        self.assertEqual(len({row["url"] for row in rows}), len(rows))  # no duplicates

    def test_every_link_is_a_real_public_https_site(self):
        with self.app.app_context():
            urls = [row["url"] for row in get_db().execute("SELECT url FROM resources")]
        self.assertTrue(urls)
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(url.startswith("https://"))
                host = url.split("/")[2]
                self.assertIn(".", host)
                for placeholder in ("example.com", "localhost", "127.0.0.1", "your-"):
                    self.assertNotIn(placeholder, url.lower())

    def test_resource_seeding_repeats_without_duplicates(self):
        from routes.resources import ensure_resource_seed_data

        with self.app.app_context():
            db = get_db()
            before = db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            ensure_resource_seed_data(db)
            after = db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        self.assertEqual(before, after)

    def test_resources_page_requires_login(self):
        response = self.new_client().get("/resources")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_page_lists_resources_with_safe_external_links(self):
        page = self.client.get("/resources")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Learning resources", html)
        self.assertIn("SQLBolt", html)
        self.assertIn('href="https://sqlbolt.com/"', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn("Beginner", html)

    def test_filter_by_category(self):
        html = self.client.get(
            "/resources", query_string={"category": "Python"}
        ).get_data(as_text=True)
        self.assertIn("The Python Tutorial (official)", html)
        self.assertNotIn("SQLBolt", html)

    def test_filter_by_difficulty(self):
        html = self.client.get(
            "/resources", query_string={"difficulty": "Advanced"}
        ).get_data(as_text=True)
        self.assertIn("cp-algorithms", html)
        self.assertNotIn("The Python Tutorial (official)", html)

    def test_search_by_keyword(self):
        html = self.client.get(
            "/resources", query_string={"q": "sql"}
        ).get_data(as_text=True)
        self.assertIn("SQLBolt", html)
        self.assertNotIn("The Odin Project", html)

    def test_combined_filters(self):
        html = self.client.get(
            "/resources",
            query_string={"q": "python", "category": "Python", "difficulty": "Beginner"},
        ).get_data(as_text=True)
        self.assertIn("Automate the Boring Stuff with Python", html)
        self.assertNotIn("Real Python tutorials", html)   # Intermediate
        self.assertNotIn("SQLBolt", html)

    def test_no_match_shows_an_empty_state(self):
        html = self.client.get(
            "/resources", query_string={"q": "quantum-widgets"}
        ).get_data(as_text=True)
        self.assertIn("No resources match those filters", html)

    def test_saved_filter_starts_empty(self):
        html = self.client.get(
            "/resources", query_string={"saved": "1"}
        ).get_data(as_text=True)
        self.assertIn("My saved resources", html)
        self.assertIn("No resources match those filters", html)

    def test_saved_view_explains_that_the_catalogue_is_filtered(self):
        html = self.client.get(
            "/resources", query_string={"saved": "1"}
        ).get_data(as_text=True)
        self.assertIn("You are viewing only your saved resources", html)
        self.assertIn("Browse all 56 resources", html)

    def test_no_saved_callout_in_the_full_catalogue(self):
        html = self.client.get("/resources").get_data(as_text=True)
        self.assertNotIn("You are viewing only your saved resources", html)


class FavouriteTests(PhaseSevenTests):
    def test_saving_a_resource_adds_it_to_favourites(self):
        response = self.save("SQLBolt")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.favourite_count(), 1)

        saved_page = self.client.get(
            "/resources", query_string={"saved": "1"}
        ).get_data(as_text=True)
        self.assertIn("SQLBolt", saved_page)
        self.assertIn("Saved — remove", saved_page)
        self.assertNotIn("The Odin Project", saved_page)

        with self.app.app_context():
            activity = get_db().execute(
                """SELECT COUNT(*) AS c FROM activities
                   WHERE user_id = ? AND description = ?""",
                (self.user_id(), "Saved a learning resource: SQLBolt"),
            ).fetchone()["c"]
        self.assertEqual(activity, 1)

    def test_saving_again_removes_the_favourite(self):
        self.save("SQLBolt")
        self.save("SQLBolt")
        self.assertEqual(self.favourite_count(), 0)
        saved_page = self.client.get(
            "/resources", query_string={"saved": "1"}
        ).get_data(as_text=True)
        self.assertIn("No resources match those filters", saved_page)

    def test_saving_does_not_delete_or_change_the_resource(self):
        with self.app.app_context():
            db = get_db()
            before = db.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        self.save("SQLBolt")
        with self.app.app_context():
            after = get_db().execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        self.assertEqual(before, after)

    def test_unknown_resource_is_rejected(self):
        response = self.post("/resources/99999/favourite", {}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("not available", response.get_data(as_text=True))
        self.assertEqual(self.favourite_count(), 0)

    def test_favourites_are_private_to_each_user(self):
        second = self.new_client()
        self.post("/register", RAVI, client=second)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=second,
        )
        self.save("SQLBolt")

        second_saved = second.get(
            "/resources", query_string={"saved": "1"}
        ).get_data(as_text=True)
        self.assertIn("No resources match those filters", second_saved)
        self.assertEqual(self.favourite_count(RAVI["email"]), 0)

        second_page = second.get("/resources").get_data(as_text=True)
        self.assertIn("Save to favourites", second_page)
        self.assertEqual(self.favourite_count(), 1)

    def test_favourite_post_without_csrf_token_is_refused(self):
        client = self.new_client()
        self.post("/register", RAVI, client=client)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=client,
        )
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post(
            f"/resources/{self.resource_id('SQLBolt')}/favourite"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.favourite_count(RAVI["email"]), 0)

    def test_filters_are_kept_after_saving(self):
        response = self.save("SQLBolt", q="sql", difficulty="Beginner")
        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        self.assertIn("q=sql", location)
        self.assertIn("difficulty=Beginner", location)

    def test_filter_choices_survive_on_the_page(self):
        html = self.client.get(
            "/resources", query_string={"category": "Python", "difficulty": "Beginner"}
        ).get_data(as_text=True)
        self.assertIn('<option value="Python" selected>', html)
        self.assertIn('<option value="Beginner" selected>', html)


class FilterFeedbackTests(PhaseSevenTests):
    """Applying filters must produce a visible change above the results."""

    def test_form_lands_on_the_catalogue_section(self):
        html = self.client.get("/resources").get_data(as_text=True)
        self.assertIn('action="/resources#catalogue"', html)
        self.assertIn('id="catalogue"', html)

    def test_count_line_says_match(self):
        with self.app.app_context():
            total = get_db().execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        html = self.client.get("/resources").get_data(as_text=True)
        self.assertIn(f"of {total} resources match", html)

    def test_active_filters_are_listed(self):
        html = self.client.get(
            "/resources", query_string={"q": "sql", "category": "SQL"}
        ).get_data(as_text=True)
        self.assertIn("Showing only:", html)
        self.assertIn("search “sql”", html)
        self.assertIn("Clear all filters", html)

    def test_no_filter_summary_when_nothing_is_set(self):
        html = self.client.get("/resources").get_data(as_text=True)
        self.assertNotIn("Showing only:", html)

    def test_saved_filter_is_named_in_the_summary(self):
        self.save("SQLBolt")
        html = self.client.get(
            "/resources", query_string={"saved": "1"}
        ).get_data(as_text=True)
        self.assertIn("saved only", html)


class ResourceNoteTests(PhaseSevenTests):
    """Private notes and completed markers on resource cards."""

    def note_for(self, title, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute(
                """SELECT note, is_completed FROM resource_notes
                   WHERE user_id = ? AND resource_id = ?""",
                (self.user_id(email), self.resource_id(title)),
            ).fetchone()

    def note_rows(self):
        with self.app.app_context():
            return get_db().execute("SELECT COUNT(*) FROM resource_notes").fetchone()[0]

    def save_note(self, title, client=None, follow_redirects=False, **data):
        return self.post(
            f"/resources/{self.resource_id(title)}/note",
            data,
            client=client,
            follow_redirects=follow_redirects,
        )

    def test_saving_a_note_shows_it_on_the_card(self):
        response = self.save_note("SQLBolt", note="Finished lessons 1-3. JOINS still tricky.")
        self.assertEqual(response.status_code, 302)
        row = self.note_for("SQLBolt")
        self.assertEqual(row["note"], "Finished lessons 1-3. JOINS still tricky.")
        self.assertEqual(row["is_completed"], 0)

        html = self.client.get("/resources").get_data(as_text=True)
        self.assertIn("Finished lessons 1-3. JOINS still tricky.", html)
        self.assertIn("Your note", html)
        self.assertNotIn("✓ Completed", html)

    def test_completed_marker_adds_a_badge_and_an_activity_line(self):
        self.save_note("SQLBolt", note="Done", is_completed="1")
        self.assertEqual(self.note_for("SQLBolt")["is_completed"], 1)

        html = self.client.get("/resources").get_data(as_text=True)
        self.assertIn("✓ Completed", html)
        self.assertIn("1 completed", html)

        with self.app.app_context():
            count = get_db().execute(
                """SELECT COUNT(*) FROM activities
                   WHERE user_id = ? AND description = ?""",
                (self.user_id(), "Completed a learning resource: SQLBolt"),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_completing_twice_logs_only_once(self):
        self.save_note("SQLBolt", note="Done", is_completed="1")
        self.save_note("SQLBolt", note="Done again", is_completed="1")
        with self.app.app_context():
            count = get_db().execute(
                "SELECT COUNT(*) FROM activities WHERE description = ?",
                ("Completed a learning resource: SQLBolt",),
            ).fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(self.note_for("SQLBolt")["note"], "Done again")

    def test_notes_are_private_between_users(self):
        second = self.new_client()
        self.post("/register", RAVI, client=second)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=second,
        )
        self.save_note("SQLBolt", note="My private revision plan", is_completed="1")

        second_html = second.get("/resources").get_data(as_text=True)
        self.assertNotIn("My private revision plan", second_html)
        self.assertNotIn("✓ Completed", second_html)
        self.assertIsNone(self.note_for("SQLBolt", RAVI["email"]))

    def test_saving_twice_updates_one_row(self):
        self.save_note("SQLBolt", note="First")
        self.save_note("SQLBolt", note="Second")
        self.assertEqual(self.note_rows(), 1)
        self.assertEqual(self.note_for("SQLBolt")["note"], "Second")

    def test_clearing_the_note_removes_the_row(self):
        self.save_note("SQLBolt", note="Temporary")
        self.save_note("SQLBolt", note="   ")
        self.assertEqual(self.note_rows(), 0)
        self.assertIsNone(self.note_for("SQLBolt"))

    def test_empty_note_without_completed_saves_nothing(self):
        response = self.save_note("SQLBolt", note="", follow_redirects=True)
        self.assertIn("Add a note or tick completed", response.get_data(as_text=True))
        self.assertEqual(self.note_rows(), 0)

    def test_note_longer_than_the_limit_is_rejected(self):
        response = self.save_note("SQLBolt", note="x" * 501, follow_redirects=True)
        self.assertIn("up to 500 characters", response.get_data(as_text=True))
        self.assertEqual(self.note_rows(), 0)

    def test_note_is_saved_at_the_limit(self):
        self.save_note("SQLBolt", note="y" * 500)
        self.assertEqual(len(self.note_for("SQLBolt")["note"]), 500)

    def test_note_html_is_escaped(self):
        self.save_note("SQLBolt", note="<script>alert(1)</script>")
        html = self.client.get("/resources").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_note_post_requires_csrf_token(self):
        client = self.new_client()
        self.post("/register", RAVI, client=client)
        self.post(
            "/login",
            {"email": RAVI["email"], "password": RAVI["password"]},
            client=client,
        )
        with client.session_transaction() as session:
            session.pop("_csrf_token", None)
        response = client.post(
            f"/resources/{self.resource_id('SQLBolt')}/note", data={"note": "sneaky"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.note_rows(), 0)

    def test_note_on_unknown_resource_is_rejected(self):
        response = self.post(
            "/resources/99999/note", {"note": "ghost"}, follow_redirects=True
        )
        self.assertIn("not available", response.get_data(as_text=True))
        self.assertEqual(self.note_rows(), 0)

    def test_filters_are_kept_after_saving_a_note(self):
        response = self.save_note("SQLBolt", note="kept", category="SQL")
        self.assertEqual(response.status_code, 302)
        self.assertIn("category=SQL", response.headers["Location"])

    def test_notes_survive_resource_reseeding(self):
        from routes.resources import ensure_resource_seed_data

        self.save_note("SQLBolt", note="Still here", is_completed="1")
        with self.app.app_context():
            ensure_resource_seed_data(get_db())
        row = self.note_for("SQLBolt")
        self.assertEqual(row["note"], "Still here")
        self.assertEqual(row["is_completed"], 1)


if __name__ == "__main__":
    unittest.main()
