"""
Phase 12 tests: Resume Analyzer.

Real PDFs (built with fpdf2) and real DOCX files (built with python-docx) are
extracted through the same code the app uses. Uploads go to a temporary folder
and are deleted by the route, so no document survives an analysis.
"""
import io
import os
import unittest

from docx import Document
from fpdf import FPDF

from test_phase11 import PDF_BYTES, StudioTestCase, RESUME_FORM
from utils.analyzer import (
    ExtractionError, analyze_resume, detect_sections, detected_skills, job_keywords,
)
from utils.database import get_db

RESUME_LINES = [
    "Divyanshi Sharma",
    "Email: divyanshi@example.com",
    "Phone: +91 98765 43210",
    "GitHub: github.com/divyanshi",
    "",
    "PROFESSIONAL SUMMARY",
    "Final year computer science student who builds web applications with Python and Flask.",
    "",
    "EDUCATION",
    "B.Tech Computer Science, SkillBridge Institute of Technology, 2026",
    "",
    "TECHNICAL SKILLS",
    "Python, Flask, SQL, HTML, CSS, Git, Docker",
    "",
    "PROJECTS",
    "Career Platform - Built a Flask web app with SQLite and REST APIs. Implemented login and unit testing.",
    "",
    "CERTIFICATIONS",
    "Python for Everybody - Coursera",
]

JOB_DESCRIPTION = (
    "We are hiring a Backend Developer to build services with Python and Flask. "
    "You will design REST APIs, write SQL queries, use Docker, and deploy on AWS. "
    "Experience with Kubernetes is a plus. You will write tests and review code."
)


def make_pdf(lines):
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(pdf.epw, 6, line or " ")
    return bytes(pdf.output())


def make_blank_pdf():
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    return bytes(pdf.output())


def make_docx(lines):
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class AnalyzerTestCase(StudioTestCase):
    def analyze(self, content=None, filename="resume.pdf", description=JOB_DESCRIPTION,
                client=None, **fields):
        data = {
            "job_title": "Backend Developer",
            "company": "Acme",
            "industry": "Software",
            "experience_level": "Fresher",
            "description": description,
            "resume_id": "",
        }
        data.update(fields)
        if content is not None:
            data["document"] = (io.BytesIO(content), filename)
        return self.post("/career-studio/analyzer/run", data, client=client)

    def analysis_count(self, email=None):
        email = email or "asha@example.com"
        with self.app.app_context():
            return get_db().execute(
                "SELECT COUNT(*) FROM resume_analyses WHERE user_id = ?",
                (self.student_id(email),),
            ).fetchone()[0]

    def student_id(self, email):
        with self.app.app_context():
            row = get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            return row["id"] if row else -1

    def latest_analysis(self):
        with self.app.app_context():
            return dict(get_db().execute(
                "SELECT * FROM resume_analyses ORDER BY id DESC LIMIT 1"
            ).fetchone())

    def pdf_uploads(self):
        folder = os.path.join(self.upload_dir, str(self.user_id()))
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class AnalyzerPageTests(AnalyzerTestCase):
    def test_page_requires_login(self):
        response = self.new_client().get("/career-studio/analyzer")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_form_shows_honest_scoring_explanation(self):
        page = self.client.get("/career-studio/analyzer")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("How the score is built", html)
        self.assertIn("not any employer", html)
        self.assertIn("not a hiring prediction", html)
        self.assertIn("Data Analyst", html)          # suggested roles
        self.assertIn("deleted immediately", html)   # no stored documents

    def test_history_page_requires_login_and_starts_empty(self):
        self.assertEqual(self.new_client().get("/career-studio/analyzer/history").status_code, 302)
        page = self.client.get("/career-studio/analyzer/history")
        self.assertIn("No analyses yet", page.get_data(as_text=True))


class AnalyzerUploadTests(AnalyzerTestCase):
    def test_pdf_with_job_description_is_scored_and_file_deleted(self):
        response = self.analyze(make_pdf(RESUME_LINES))
        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.headers["Location"], r"/career-studio/analyzer/\d+$")
        self.assertEqual(self.analysis_count(), 1)
        # The upload is read and then removed: nothing stays on disk.
        self.assertEqual(self.pdf_uploads(), [])

        row = self.latest_analysis()
        self.assertGreaterEqual(row["overall_score"], 40)
        self.assertIn("python", row["matched_json"].lower())
        self.assertIn("kubernetes", row["missing_json"].lower())
        self.assertEqual(row["word_count"] > 50, True)
        self.assertEqual(row["job_title"], "Backend Developer")
        self.assertEqual(row["company"], "Acme")

        page = self.client.get(response.headers["Location"])
        html = page.get_data(as_text=True)
        self.assertIn("Estimated ATS compatibility", html)
        self.assertIn("Matched skills", html)
        self.assertIn("Kubernetes", html)
        self.assertIn("Keyword coverage", html)
        self.assertIn("Improvement checklist", html)
        self.assertIn("not the score of any real applicant tracking system", html)

    def test_analysis_without_job_description_is_normalised(self):
        response = self.analyze(make_pdf(RESUME_LINES), description="", job_title="")
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.headers["Location"])
        html = page.get_data(as_text=True)
        self.assertIn("No job description was provided", html)
        self.assertIn("Not scored", html)
        self.assertNotIn("Keyword coverage</h2>", html)
        row = self.latest_analysis()
        self.assertGreaterEqual(row["overall_score"], 40)
        self.assertLessEqual(row["overall_score"], 100)

    def test_docx_resume_is_extracted(self):
        response = self.analyze(make_docx(RESUME_LINES), filename="resume.docx")
        self.assertEqual(response.status_code, 302)
        row = self.latest_analysis()
        self.assertIn("python", row["matched_json"].lower())
        self.assertTrue(row["source_name"].endswith(".docx"))

    def test_unsupported_extension_is_rejected_without_touching_disk(self):
        response = self.analyze(b"plain text resume", filename="resume.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("not supported", response.get_data(as_text=True))
        self.assertEqual(self.analysis_count(), 0)

    def test_damaged_pdf_reports_instead_of_guessing(self):
        response = self.analyze(b"%PDF-1.4\nthis is not a real pdf body\n", filename="broken.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("could not be opened", response.get_data(as_text=True))
        self.assertEqual(self.analysis_count(), 0)

    def test_scanned_pdf_without_text_is_explained(self):
        response = self.analyze(make_blank_pdf(), filename="scan.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("OCR", response.get_data(as_text=True))
        self.assertEqual(self.analysis_count(), 0)

    def test_no_source_is_rejected(self):
        response = self.analyze(None)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Upload a PDF or DOCX file", response.get_data(as_text=True))

    def test_oversized_upload_is_rejected(self):
        big = b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024) + b"\n%%EOF\n"
        response = self.analyze(big, filename="big.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("The limit is 5 MB", response.get_data(as_text=True))
        self.assertEqual(self.analysis_count(), 0)

    def test_missing_csrf_token_is_refused(self):
        response = self.client.post("/career-studio/analyzer/run", data={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.analysis_count(), 0)

    def test_activity_is_recorded(self):
        self.analyze(make_pdf(RESUME_LINES))
        with self.app.app_context():
            row = get_db().execute(
                "SELECT description FROM activities WHERE activity_type = 'analysis'"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("Backend Developer", row["description"])


class AnalyzerSavedResumeTests(AnalyzerTestCase):
    def create_resume(self):
        response = self.post("/career-studio/resumes/new", dict(RESUME_FORM))
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            return get_db().execute(
                "SELECT id FROM resumes ORDER BY id DESC LIMIT 1"
            ).fetchone()["id"]

    def test_saved_resume_can_be_analysed_without_uploading(self):
        resume_id = self.create_resume()
        response = self.analyze(None, resume_id=str(resume_id))
        self.assertEqual(response.status_code, 302)
        row = self.latest_analysis()
        self.assertEqual(row["resume_id"], resume_id)
        self.assertIn("SkillBridge resume", row["source_name"])
        self.assertIn("python", row["matched_json"].lower())
        self.assertIn("flask", row["matched_json"].lower())

    def test_another_users_resume_cannot_be_analysed(self):
        resume_id = self.create_resume()
        other = self.new_client()
        self.post("/register", {
            "name": "Ravi Kumar", "email": "ravi2@example.com",
            "password": "Learn1234", "confirm_password": "Learn1234",
        }, client=other)
        self.post("/login", {"email": "ravi2@example.com", "password": "Learn1234"}, client=other)
        response = self.analyze(None, resume_id=str(resume_id), client=other)
        self.assertEqual(response.status_code, 200)
        self.assertIn("could not be found", response.get_data(as_text=True))
        self.assertEqual(self.analysis_count("ravi2@example.com"), 0)


class AnalyzerPrivacyTests(AnalyzerTestCase):
    def run_one(self):
        response = self.analyze(make_pdf(RESUME_LINES))
        self.assertEqual(response.status_code, 302)
        return int(response.headers["Location"].rstrip("/").split("/")[-1])

    def other_client(self):
        client = self.new_client()
        self.post("/register", {
            "name": "Ravi Kumar", "email": "ravi3@example.com",
            "password": "Learn1234", "confirm_password": "Learn1234",
        }, client=client)
        self.post("/login", {"email": "ravi3@example.com", "password": "Learn1234"}, client=client)
        return client

    def test_result_is_owner_only(self):
        analysis_id = self.run_one()
        other = self.other_client()
        self.assertEqual(other.get(f"/career-studio/analyzer/{analysis_id}").status_code, 404)
        self.assertEqual(
            other.post(f"/career-studio/analyzer/{analysis_id}/delete",
                       data={"csrf_token": "x"}).status_code, 400,
        )
        # A valid token still cannot delete someone else's analysis.
        with other.session_transaction() as session:
            session["_csrf_token"] = "test-token"
        self.assertEqual(
            other.post(f"/career-studio/analyzer/{analysis_id}/delete",
                       data={"csrf_token": "test-token"}).status_code, 404,
        )
        self.assertEqual(self.analysis_count(), 1)

    def test_owner_can_delete_analysis(self):
        analysis_id = self.run_one()
        response = self.post(f"/career-studio/analyzer/{analysis_id}/delete", {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.analysis_count(), 0)
        self.assertEqual(
            self.client.get(f"/career-studio/analyzer/{analysis_id}").status_code, 404
        )

    def test_history_lists_only_own_analyses(self):
        self.run_one()
        other = self.other_client()
        page = other.get("/career-studio/analyzer/history")
        self.assertIn("No analyses yet", page.get_data(as_text=True))


class AnalyzerRuleTests(unittest.TestCase):
    """The scoring rules themselves, without the web layer."""

    def text(self):
        return "\n".join(RESUME_LINES)

    def test_structure_and_contact_checks(self):
        result = analyze_resume(self.text(), job_title="Backend Developer",
                                description=JOB_DESCRIPTION)
        passed = {check["label"] for check in result["structure_checks"] if check["passed"]}
        self.assertEqual(
            passed,
            {"Email address", "Phone number", "Professional summary", "Education section",
             "Skills section", "Projects or experience", "Profile links"},
        )
        self.assertEqual(result["scores"]["structure"], 25)

    def test_skills_are_matched_and_missing_reported(self):
        result = analyze_resume(self.text(), job_title="Backend Developer",
                                description=JOB_DESCRIPTION)
        for skill in ("Python", "Flask", "SQL", "Docker", "REST APIs"):
            self.assertIn(skill, result["matched"])
        for skill in ("AWS", "Kubernetes"):
            self.assertIn(skill, result["missing"])
        self.assertNotIn("AWS", result["matched"])

    def test_keywords_come_from_the_job_description(self):
        keywords = job_keywords(JOB_DESCRIPTION)
        self.assertIn("apis", keywords)
        self.assertNotIn("the", keywords)
        self.assertNotIn("hiring", keywords)

    def test_sections_and_skills_are_detected_from_text(self):
        sections = detect_sections(self.text())
        for name in ("summary", "education", "skills", "projects", "certifications"):
            self.assertIn(name, sections)
        skills = detected_skills(self.text())
        self.assertIn("Python", skills)
        self.assertIn("Git", skills)
        self.assertNotIn("Kubernetes", skills)

    def test_scores_are_bounded_and_explained(self):
        result = analyze_resume(self.text(), job_title="Backend Developer",
                                description=JOB_DESCRIPTION)
        self.assertGreaterEqual(result["overall"], 0)
        self.assertLessEqual(result["overall"], 100)
        self.assertFalse(result["normalised"])
        self.assertTrue(result["improvements"])
        self.assertTrue(result["checklist"])
        self.assertTrue(result["strengths"])

    def test_missing_parts_lower_the_score_honestly(self):
        thin = ("Ravi Kumar\nravi@example.com\n\nSKILLS\nPython\n\n"
                "PROJECTS\nBuilt a small command line tool that renames files and "
                "reports each change in the terminal window.\n\nEDUCATION\n"
                "B.Sc Computer Science, 2026\n\nCOURSEWORK\n"
                "Databases and operating systems were studied with weekly practical "
                "assignments and a final project.\n")
        result = analyze_resume(thin, job_title="Backend Developer",
                                description=JOB_DESCRIPTION)
        self.assertLess(result["scores"]["structure"], 25)
        self.assertIn("AWS", result["missing"])
        self.assertTrue(any("Missing" in item["title"] for item in result["improvements"]))

    def test_empty_or_unreadable_text_raises(self):
        with self.assertRaises(ExtractionError):
            analyze_resume("   \n  \n")

    def test_normalised_score_without_job_description(self):
        result = analyze_resume(self.text())
        self.assertTrue(result["normalised"])
        self.assertIsNone(result["scores"]["keywords"])
        self.assertFalse(result["has_job"])
        self.assertGreater(result["overall"], 0)


if __name__ == "__main__":
    unittest.main()
