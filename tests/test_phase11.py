"""
Phase 11 tests: Certificate Vault and Student Progress Reports.

Only real database rows and real files are used. Upload tests point the
storage folder at a temporary directory, so nothing in instance/ is touched.
"""
import io
import json
import os
import unittest
from datetime import date, timedelta

from test_auth import AuthTestCase, USER
from utils.database import get_db
from utils.storage import upload_root

OTHER = {
    "name": "Ravi Kumar",
    "email": "ravi@example.com",
    "password": "Learn1234",
    "confirm_password": "Learn1234",
}

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

CERTIFICATE = {
    "title": "Python for Everybody",
    "organization": "Coursera",
    "category": "Programming Courses",
    "issue_date": "2026-01-15",
    "expiry_date": "",
    "credential_id": "PY-1234",
    "credential_url": "https://coursera.org/verify/PY-1234",
    "skills": "Python, Programming",
    "description": "Completed the Python specialisation.",
}


class StudioTestCase(AuthTestCase):
    """A logged-in student whose uploads go to a temporary folder."""

    def setUp(self):
        super().setUp()
        self.upload_dir = os.path.join(self.temp_dir.name, "uploads")
        self.app.config["CAREER_STUDIO_UPLOAD_ROOT"] = self.upload_dir
        self.post("/register", USER)
        self.post("/login", {"email": USER["email"], "password": USER["password"]})

    # ----- helpers -----
    def user_id(self, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]

    def certificate_count(self, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute(
                "SELECT COUNT(*) FROM certificates WHERE user_id = ?", (self.user_id(email),)
            ).fetchone()[0]

    def upload(self, content=PDF_BYTES, filename="certificate.pdf", client=None, **overrides):
        data = dict(CERTIFICATE, **overrides)
        data["document"] = (io.BytesIO(content), filename)
        return self.post("/career-studio/certificates/new", data, client=client)

    def stored_files(self):
        folder = os.path.join(self.upload_dir, str(self.user_id()))
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def other_client(self):
        client = self.new_client()
        self.post("/register", OTHER, client=client)
        self.post("/login", {"email": OTHER["email"], "password": OTHER["password"]}, client=client)
        return client


class CertificateVaultAccessTests(StudioTestCase):
    def test_vault_requires_login(self):
        response = self.new_client().get("/career-studio/certificates")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_empty_vault_shows_honest_empty_state(self):
        page = self.client.get("/career-studio/certificates")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Your vault is empty", html)
        self.assertIn("Upload your first certificate", html)

    def test_upload_page_requires_login(self):
        self.assertEqual(self.new_client().get("/career-studio/certificates/new").status_code, 302)


class CertificateUploadTests(StudioTestCase):
    def test_upload_pdf_saves_row_and_private_file(self):
        response = self.upload()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.certificate_count(), 1)
        files = self.stored_files()
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].endswith(".pdf"))
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM certificates").fetchone()
        self.assertEqual(row["title"], CERTIFICATE["title"])
        self.assertEqual(row["mime_type"], "application/pdf")
        self.assertEqual(row["stored_filename"], files[0])
        # The file lives outside static/, so it has no public URL.
        self.assertFalse(os.path.exists(os.path.join("static", files[0])))

    def test_upload_png_is_detected_as_image(self):
        response = self.upload(content=PNG_BYTES, filename="badge.png")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = get_db().execute("SELECT mime_type FROM certificates").fetchone()
        self.assertEqual(row["mime_type"], "image/png")

    def test_wrong_extension_is_rejected(self):
        response = self.upload(filename="notes.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("not supported", response.get_data(as_text=True))
        self.assertEqual(self.certificate_count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_pdf_extension_with_wrong_content_is_rejected(self):
        response = self.upload(content=b"not really a pdf", filename="fake.pdf")
        self.assertIn("do not match its extension", response.get_data(as_text=True))
        self.assertEqual(self.certificate_count(), 0)

    def test_oversized_file_is_rejected(self):
        response = self.upload(content=b"%PDF-" + b"0" * (9 * 1024 * 1024), filename="big.pdf")
        self.assertIn("The limit is 8 MB", response.get_data(as_text=True))
        self.assertEqual(self.certificate_count(), 0)

    def test_missing_title_is_rejected(self):
        response = self.upload(title="")
        self.assertIn("Enter the certificate title", response.get_data(as_text=True))
        self.assertEqual(self.certificate_count(), 0)

    def test_bad_verification_link_is_rejected(self):
        response = self.upload(credential_url="javascript:alert(1)")
        self.assertIn("must start with http", response.get_data(as_text=True))
        self.assertEqual(self.certificate_count(), 0)

    def test_expiry_before_issue_is_rejected(self):
        response = self.upload(issue_date="2026-05-01", expiry_date="2026-01-01")
        self.assertIn("on or after the issue date", response.get_data(as_text=True))

    def test_future_issue_date_is_rejected(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        response = self.upload(issue_date=future)
        self.assertIn("cannot be in the future", response.get_data(as_text=True))

    def test_upload_is_recorded_in_activity(self):
        self.upload()
        with self.app.app_context():
            row = get_db().execute(
                "SELECT description FROM activities WHERE user_id = ? AND activity_type = 'certificate'",
                (self.user_id(),),
            ).fetchone()
        self.assertIn("Uploaded a certificate", row["description"])


class CertificateManagementTests(StudioTestCase):
    def setUp(self):
        super().setUp()
        self.upload()

    def certificate_id(self, email=USER["email"]):
        with self.app.app_context():
            return get_db().execute(
                "SELECT id FROM certificates WHERE user_id = ?", (self.user_id(email),)
            ).fetchone()["id"]

    def test_card_and_details_render(self):
        certificate_id = self.certificate_id()
        listing = self.client.get("/career-studio/certificates").get_data(as_text=True)
        self.assertIn("Python for Everybody", listing)
        self.assertIn("Programming Courses", listing)
        detail = self.client.get(f"/career-studio/certificates/{certificate_id}")
        self.assertEqual(detail.status_code, 200)
        html = detail.get_data(as_text=True)
        self.assertIn("Credential details", html)
        self.assertIn("PY-1234", html)
        self.assertIn("does not independently verify", html)

    def test_search_and_category_filter(self):
        self.upload(title="Networking Basics", category="Technical Certifications")
        found = self.client.get("/career-studio/certificates?q=network").get_data(as_text=True)
        self.assertIn("Networking Basics", found)
        self.assertNotIn("Python for Everybody", found)
        filtered = self.client.get("/career-studio/certificates?category=Technical+Certifications").get_data(as_text=True)
        self.assertIn("Networking Basics", filtered)
        self.assertNotIn("Python for Everybody", filtered)

    def test_edit_updates_details(self):
        certificate_id = self.certificate_id()
        response = self.post(
            f"/career-studio/certificates/{certificate_id}/edit",
            dict(CERTIFICATE, title="Python Specialisation", category="Technical Certifications"),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM certificates WHERE id = ?", (certificate_id,)).fetchone()
        self.assertEqual(row["title"], "Python Specialisation")
        self.assertEqual(row["category"], "Technical Certifications")

    def test_download_returns_owner_file(self):
        certificate_id = self.certificate_id()
        response = self.client.get(f"/career-studio/certificates/{certificate_id}/download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, PDF_BYTES)
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_preview_is_inline(self):
        self.upload(content=PNG_BYTES, filename="badge.png")
        with self.app.app_context():
            certificate_id = get_db().execute(
                "SELECT id FROM certificates WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (self.user_id(),),
            ).fetchone()["id"]
        response = self.client.get(f"/career-studio/certificates/{certificate_id}/file")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, PNG_BYTES)
        self.assertIn("inline", response.headers["Content-Disposition"])

    def test_delete_removes_row_and_file(self):
        certificate_id = self.certificate_id()
        response = self.post(f"/career-studio/certificates/{certificate_id}/delete", {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.certificate_count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_expiring_soon_is_flagged(self):
        soon = (date.today() + timedelta(days=10)).isoformat()
        self.upload(title="Cloud badge", expiry_date=soon, category="Technical Certifications")
        html = self.client.get("/career-studio/certificates").get_data(as_text=True)
        self.assertIn("Expires in", html)

    def test_other_students_cannot_reach_the_file(self):
        certificate_id = self.certificate_id()
        other = self.other_client()
        for path in (
            f"/career-studio/certificates/{certificate_id}",
            f"/career-studio/certificates/{certificate_id}/file",
            f"/career-studio/certificates/{certificate_id}/download",
        ):
            with self.subTest(path=path):
                self.assertEqual(other.get(path).status_code, 404)
        self.assertEqual(
            self.post(f"/career-studio/certificates/{certificate_id}/delete", {}, client=other).status_code,
            404,
        )
        self.assertEqual(self.certificate_count(), 1)

    def test_other_students_vault_is_empty(self):
        other = self.other_client()
        html = other.get("/career-studio/certificates").get_data(as_text=True)
        self.assertIn("Your vault is empty", html)
        self.assertNotIn("Python for Everybody", html)

    def test_delete_requires_csrf_token(self):
        certificate_id = self.certificate_id()
        response = self.client.post(f"/career-studio/certificates/{certificate_id}/delete", data={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.certificate_count(), 1)


if __name__ == "__main__":
    unittest.main()


RESUME_FORM = {
    "title": "Backend developer resume",
    "template": "modern",
    "full_name": "Asha Verma",
    "email": "asha@example.com",
    "phone": "9876543210",
    "location": "Pune, India",
    "linkedin": "https://linkedin.com/in/asha",
    "github": "https://github.com/asha",
    "portfolio": "",
    "summary": "Final-year computer science student building Flask applications.",
    "objective": "",
    "edu_institution": ["Pune Institute of Technology"],
    "edu_degree": ["B.Tech"],
    "edu_field": ["Computer Science"],
    "edu_start": ["2022"],
    "edu_end": ["2026"],
    "edu_grade": ["8.4 CGPA"],
    "edu_coursework": ["Databases, Operating Systems"],
    "skill_category": ["Languages", "Frameworks"],
    "skill_items": ["Python, SQL", "Flask"],
    "section_title": ["Hackathons"],
    "section_body": ["Runner-up, college coding sprint 2026."],
}


class ResumeBuilderTests(StudioTestCase):
    def create(self, client=None, **overrides):
        data = dict(RESUME_FORM, **overrides)
        return self.post("/career-studio/resumes/new", data, client=client)

    def resume_id(self, email=USER["email"]):
        with self.app.app_context():
            row = get_db().execute(
                "SELECT id FROM resumes WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (self.user_id(email),),
            ).fetchone()
        return row["id"] if row else None

    def items(self, kind=None):
        with self.app.app_context():
            if kind:
                rows = get_db().execute(
                    "SELECT * FROM resume_items WHERE resume_id = ? AND kind = ? ORDER BY position",
                    (self.resume_id(), kind),
                ).fetchall()
            else:
                rows = get_db().execute(
                    "SELECT * FROM resume_items WHERE resume_id = ? ORDER BY position",
                    (self.resume_id(),),
                ).fetchall()
        return [dict(row) for row in rows]

    def test_builder_pages_require_login(self):
        guest = self.new_client()
        self.assertEqual(guest.get("/career-studio/resumes").status_code, 302)
        self.assertEqual(guest.get("/career-studio/resumes/new").status_code, 302)

    def test_empty_list_shows_empty_state(self):
        html = self.client.get("/career-studio/resumes").get_data(as_text=True)
        self.assertIn("No resumes yet", html)
        self.assertIn("Create your first resume", html)

    def test_create_resume_saves_personal_items_and_template(self):
        response = self.create()
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.resume_id())
        with self.app.app_context():
            resume = get_db().execute("SELECT * FROM resumes WHERE id = ?", (self.resume_id(),)).fetchone()
        self.assertEqual(resume["full_name"], "Asha Verma")
        self.assertEqual(resume["template"], "modern")
        self.assertEqual(len(self.items("education")), 1)
        self.assertEqual(len(self.items("skill")), 2)
        self.assertEqual(len(self.items("section")), 1)
        listing = self.client.get("/career-studio/resumes").get_data(as_text=True)
        self.assertIn("Backend developer resume", listing)
        self.assertIn("Modern Minimal", listing)

    def test_missing_name_is_rejected(self):
        response = self.create(full_name="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Enter the name that should appear on the resume", response.get_data(as_text=True))
        self.assertIsNone(self.resume_id())

    def test_invalid_link_is_rejected(self):
        response = self.create(github="github.com/asha")
        self.assertIn("starts with http", response.get_data(as_text=True).lower())

    def test_edit_updates_resume_and_items(self):
        self.create()
        resume_id = self.resume_id()
        response = self.post(
            f"/career-studio/resumes/{resume_id}/edit",
            dict(RESUME_FORM, title="Updated title", template="technical", full_name="Asha V."),
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            resume = get_db().execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        self.assertEqual(resume["title"], "Updated title")
        self.assertEqual(resume["template"], "technical")
        self.assertEqual(resume["full_name"], "Asha V.")
        self.assertEqual(len(self.items("education")), 1)

    def test_preview_returns_rendered_resume(self):
        response = self.post("/career-studio/resumes/preview", RESUME_FORM)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Asha Verma", html)
        self.assertIn("Pune Institute of Technology", html)
        self.assertIn("template-modern", html)

    def test_pdf_download_returns_pdf(self):
        self.create()
        response = self.client.get(f"/career-studio/resumes/{self.resume_id()}/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF-"))
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_print_page_renders(self):
        self.create()
        response = self.client.get(f"/career-studio/resumes/{self.resume_id()}/print")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Pune Institute of Technology", response.get_data(as_text=True))

    def test_duplicate_copies_items(self):
        self.create()
        original = self.resume_id()
        response = self.post(f"/career-studio/resumes/{original}/duplicate", {})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            rows = get_db().execute("SELECT id, title FROM resumes ORDER BY id").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertIn("(copy)", rows[-1]["title"])
        with self.app.app_context():
            copied = get_db().execute(
                "SELECT COUNT(*) FROM resume_items WHERE resume_id = ?", (rows[-1]["id"],)
            ).fetchone()[0]
        self.assertEqual(copied, len(self.items()))

    def test_delete_removes_resume_and_items(self):
        self.create()
        resume_id = self.resume_id()
        response = self.post(f"/career-studio/resumes/{resume_id}/delete", {})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.resume_id())
        with self.app.app_context():
            remaining = get_db().execute(
                "SELECT COUNT(*) FROM resume_items WHERE resume_id = ?", (resume_id,)
            ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_delete_requires_csrf(self):
        self.create()
        resume_id = self.resume_id()
        response = self.client.post(f"/career-studio/resumes/{resume_id}/delete", data={})
        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(self.resume_id())

    def test_other_students_cannot_touch_a_resume(self):
        self.create()
        resume_id = self.resume_id()
        other = self.new_client()
        self.post("/register", OTHER, client=other)
        self.post("/login", {"email": OTHER["email"], "password": OTHER["password"]}, client=other)
        for path in (f"/career-studio/resumes/{resume_id}/edit",
                     f"/career-studio/resumes/{resume_id}/pdf",
                     f"/career-studio/resumes/{resume_id}/print"):
            with self.subTest(path=path):
                self.assertEqual(other.get(path).status_code, 404)
        self.assertEqual(
            self.post(f"/career-studio/resumes/{resume_id}/delete", {}, client=other).status_code, 404
        )
        self.assertIsNotNone(self.resume_id())

    def test_certificate_from_vault_can_be_selected(self):
        self.upload()
        with self.app.app_context():
            certificate_id = get_db().execute("SELECT id FROM certificates").fetchone()["id"]
        self.create(certificate_ids=[str(certificate_id)])
        certifications = self.items("certification")
        self.assertEqual(len(certifications), 1)
        self.assertEqual(certifications[0]["title"], "Python for Everybody")
        self.assertEqual(certifications[0]["source_id"], certificate_id)

    def test_unselecting_a_certificate_removes_it(self):
        self.upload()
        with self.app.app_context():
            certificate_id = get_db().execute("SELECT id FROM certificates").fetchone()["id"]
        self.create(certificate_ids=[str(certificate_id)])
        resume_id = self.resume_id()
        self.post(f"/career-studio/resumes/{resume_id}/edit", dict(RESUME_FORM))
        self.assertEqual(self.items("certification"), [])

    def test_import_skills_from_my_skills(self):
        self.create()
        resume_id = self.resume_id()
        with self.app.app_context():
            db = get_db()
            skill_id = db.execute("SELECT id FROM skills ORDER BY id LIMIT 1").fetchone()["id"]
            db.execute(
                "INSERT OR IGNORE INTO user_skills (user_id, skill_id, status) VALUES (?, ?, 'Learning')",
                (self.user_id(), skill_id),
            )
            db.commit()
        response = self.post(f"/career-studio/resumes/{resume_id}/import/skills", {})
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            categories = [
                row["subtitle"] for row in get_db().execute(
                    "SELECT subtitle FROM resume_items WHERE resume_id = ? AND kind = 'skill'",
                    (resume_id,),
                ).fetchall()
            ]
        self.assertTrue(any(category not in ("Languages", "Frameworks") for category in categories))

    def test_import_projects_copies_real_project(self):
        self.create()
        resume_id = self.resume_id()
        with self.app.app_context():
            db = get_db()
            db.execute(
                """INSERT INTO projects (user_id, title, description, technologies,
                                         github_url, status)
                   VALUES (?, 'Attendance tracker', 'Flask app for class attendance',
                           'Flask, SQLite', 'https://github.com/asha/attendance', 'Completed')""",
                (self.user_id(),),
            )
            db.commit()
        self.post(f"/career-studio/resumes/{resume_id}/import/projects", {})
        projects = self.items("project")
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Attendance tracker")
        self.assertEqual(projects[0]["link"], "https://github.com/asha/attendance")
        self.assertIsNotNone(projects[0]["source_id"])

    def test_import_profile_adds_college(self):
        self.create()
        resume_id = self.resume_id()
        with self.app.app_context():
            db = get_db()
            db.execute(
                """UPDATE user_profiles
                   SET college_name = 'Pune Institute of Technology',
                       education_details = 'B.Tech Computer Science'
                   WHERE user_id = ?""",
                (self.user_id(),),
            )
            db.commit()
        self.post(f"/career-studio/resumes/{resume_id}/import/profile", {})
        with self.app.app_context():
            resume = get_db().execute(
                "SELECT full_name FROM resumes WHERE id = ?", (resume_id,)
            ).fetchone()
        self.assertEqual(resume["full_name"], "Asha Verma")


if __name__ == "__main__":
    unittest.main()

