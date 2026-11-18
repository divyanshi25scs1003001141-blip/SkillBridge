"""
Tests for the public pages (Home, About, Features) and error pages.

Run from the SkillBridge folder with:
    python -m unittest discover -s tests -v
"""
import os
import tempfile
import unittest

from app import create_app


class PublicPagesTest(unittest.TestCase):
    def setUp(self):
        # A temporary database, so the tests never touch your real data.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "DATABASE": os.path.join(self.temp_dir.name, "test.db"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Know where you stand", response.data)

    def test_home_page_links_to_registration_and_login_when_logged_out(self):
        response = self.client.get("/")
        self.assertIn(b'href="/register"', response.data)
        self.assertIn(b'href="/login"', response.data)

    def test_about_page_loads(self):
        response = self.client.get("/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"About SkillBridge", response.data)

    def test_features_page_lists_every_feature(self):
        response = self.client.get("/features")
        self.assertEqual(response.status_code, 200)
        for name in [
            b"Skill assessments",
            b"Career roadmaps",
            b"Skill gap analysis",
            b"Learning resources",
            b"Project tracker",
            b"Goals and progress",
            b"Career readiness report",
        ]:
            self.assertIn(name, response.data)

    def test_site_never_promises_a_job(self):
        response = self.client.get("/")
        self.assertIn(b"does not predict or guarantee job selection", response.data)

    def test_unknown_page_shows_custom_404(self):
        response = self.client.get("/this-page-does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"find that page", response.data)

    def test_stylesheets_script_and_fonts_are_served(self):
        for path in [
            "/static/css/style.css",
            "/static/css/forms.css",
            "/static/css/auth.css",
            "/static/css/dashboard.css",
            "/static/js/main.js",
            "/static/images/favicon.svg",
            "/static/fonts/bricolage-grotesque-latin-700-normal.woff2",
            "/static/fonts/instrument-sans-latin-400-normal.woff2",
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            response.close()


if __name__ == "__main__":
    unittest.main()
