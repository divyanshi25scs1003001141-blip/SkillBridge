"""
utils/resume_pdf.py - turns a saved resume into an ATS-friendly PDF.

All four templates share one single-column structure and only vary the accent
colour, name size and section order. No tables, columns, icons or images are
used, so text extraction by an applicant tracking system stays clean.
"""
import re
from urllib.parse import urlparse

from fpdf import FPDF

TEMPLATES = {
    "classic": {"label": "Classic Professional", "accent": (31, 58, 95), "name": 22},
    "modern": {"label": "Modern Minimal", "accent": (109, 40, 217), "name": 21},
    "technical": {"label": "Technical Fresher", "accent": (13, 104, 96), "name": 20},
    "corporate": {"label": "Corporate Professional", "accent": (30, 64, 124), "name": 23},
}

SECTION_ORDER = {
    "classic": ["education", "skills", "projects", "experience", "certification", "section"],
    "modern": ["education", "skills", "projects", "experience", "certification", "section"],
    "technical": ["skills", "projects", "education", "experience", "certification", "section"],
    "corporate": ["experience", "education", "skills", "projects", "certification", "section"],
}

HEADINGS = {
    "education": "EDUCATION",
    "skills": "TECHNICAL SKILLS",
    "projects": "PROJECTS",
    "experience": "INTERNSHIP AND WORK EXPERIENCE",
    "certification": "CERTIFICATIONS",
}

LINK_PATTERN = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)


def safe_url(value):
    """Only complete http(s) links are written into the document."""
    value = (value or "").strip()
    if not value or not LINK_PATTERN.match(value):
        return ""
    parsed = urlparse(value)
    return value if parsed.scheme in ("http", "https") and parsed.netloc else ""


def _plain(text):
    """Core PDF fonts are Latin-1, so unsupported characters are replaced."""
    return (text or "").encode("latin-1", "replace").decode("latin-1")


class ResumePDF(FPDF):
    def __init__(self, resume, accent):
        super().__init__(format="A4", unit="mm")
        self.resume = resume
        self.accent = accent
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(16, 14, 16)
        self.set_title(_plain(f"{resume['full_name'] or 'Resume'} - Resume"))
        self.set_author(_plain(resume["full_name"] or "SkillBridge student"))

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 130)
        self.cell(0, 6, _plain(f"Page {self.page_no()}"), align="C")


def _heading(pdf, title):
    pdf.ln(2.5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*pdf.accent)
    pdf.cell(0, 6, _plain(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*pdf.accent)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    pdf.set_text_color(30, 30, 40)


def _body(pdf, text, size=9.5, style="", color=(45, 45, 55)):
    if not (text or "").strip():
        return
    pdf.set_font("Helvetica", style, size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, 4.8, _plain(text), new_x="LMARGIN", new_y="NEXT")


def _link_line(pdf, links):
    links = [link for link in links if safe_url(link)]
    if not links:
        return
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*pdf.accent)
    for index, link in enumerate(links):
        label = link.replace("https://", "").replace("http://", "").rstrip("/")
        pdf.cell(pdf.get_string_width(_plain(label)) + 2, 4.6, _plain(label), link=link)
        if index < len(links) - 1:
            pdf.set_text_color(120, 120, 130)
            pdf.cell(4, 4.6, "|")
            pdf.set_text_color(*pdf.accent)
    pdf.ln(5)
    pdf.set_text_color(30, 30, 40)


def _education(pdf, item):
    _body(pdf, item["title"], size=10, style="B", color=(25, 25, 35))
    _body(pdf, " | ".join(part for part in (item["subtitle"], item["meta"]) if part), size=9)
    _body(pdf, item["detail"], size=9)
    pdf.ln(1.2)


def _skill(pdf, item):
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(25, 25, 35)
    pdf.write(4.8, _plain(f"{(item['subtitle'] or 'Skills').strip()}: "))
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(55, 55, 65)
    pdf.write(4.8, _plain(item["title"]))
    pdf.ln(5.4)


def _project(pdf, item):
    _body(pdf, item["title"], size=10, style="B", color=(25, 25, 35))
    _body(pdf, item["meta"], size=9, color=(90, 90, 105))
    _body(pdf, item["detail"], size=9)
    _body(pdf, item["extra"], size=9)
    _link_line(pdf, [item["link"], item["link2"]])
    pdf.ln(1.2)


def _experience(pdf, item):
    heading = item["title"]
    if item["subtitle"]:
        heading = f"{heading} - {item['subtitle']}" if heading else item["subtitle"]
    _body(pdf, heading, size=10, style="B", color=(25, 25, 35))
    _body(pdf, item["meta"], size=9, color=(90, 90, 105))
    _body(pdf, item["detail"], size=9)
    _body(pdf, item["extra"], size=9)
    pdf.ln(1.2)


def _certification(pdf, item):
    _body(pdf, item["title"], size=9.5, style="B", color=(25, 25, 35))
    _body(pdf, " | ".join(part for part in (item["subtitle"], item["meta"]) if part), size=9)
    _link_line(pdf, [item["link"]])
    pdf.ln(0.8)


def _extra_section(pdf, items):
    for item in items:
        _heading(pdf, item["title"] or "ADDITIONAL INFORMATION")
        _body(pdf, item["detail"], size=9)
        pdf.ln(1)


def build_resume_pdf(resume, items, grouped=None):
    """Return the finished PDF as bytes."""
    template = resume["template"] if resume["template"] in TEMPLATES else "classic"
    accent = TEMPLATES[template]["accent"]

    pdf = ResumePDF(resume, accent)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", TEMPLATES[template]["name"])
    pdf.set_text_color(*accent)
    pdf.multi_cell(0, 9, _plain(resume["full_name"] or "Your name"), new_x="LMARGIN", new_y="NEXT")

    contact = "  |  ".join(part for part in (resume["email"], resume["phone"], resume["location"]) if part)
    if contact:
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(60, 60, 75)
        pdf.multi_cell(0, 4.8, _plain(contact), new_x="LMARGIN", new_y="NEXT")
    _link_line(pdf, [resume["linkedin"], resume["github"], resume["portfolio"]])

    if (resume["summary"] or "").strip():
        _heading(pdf, "PROFESSIONAL SUMMARY")
        _body(pdf, resume["summary"])
    if (resume["objective"] or "").strip():
        _heading(pdf, "CAREER OBJECTIVE")
        _body(pdf, resume["objective"])

    if grouped is None:
        grouped = {}
        for item in items:
            grouped.setdefault(item["kind"], []).append(item)
        grouped.setdefault("section", [])

    builders = {
        "education": _education,
        "skill": _skill,
        "project": _project,
        "experience": _experience,
        "certification": _certification,
    }
    kind_for = {
        "education": "education", "skills": "skill", "projects": "project",
        "experience": "experience", "certification": "certification",
    }

    for block in SECTION_ORDER.get(template, SECTION_ORDER["classic"]):
        if block == "section":
            _extra_section(pdf, grouped.get("section", []))
            continue
        rows = grouped.get(kind_for[block], [])
        if not rows:
            continue
        _heading(pdf, HEADINGS[block])
        for item in rows:
            builders[kind_for[block]](pdf, item)

    return bytes(pdf.output())
