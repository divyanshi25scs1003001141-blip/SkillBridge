"""
utils/analyzer.py - the rule-based resume analyzer.

No AI service and no paid API is involved. The resume text is compared with a
curated skill vocabulary and with the words of the pasted job description:

    structure      25 points   contact details and the sections ATS expects
    skills match   25 points   job skills that also appear in the resume
    keywords       20 points   important job-description words found
    job relevance  15 points   job terms appearing in projects/experience
    content        15 points   length, bullets, action verbs, summary

The result is an ESTIMATE of ATS compatibility for this one document. It is not
any employer's real score and it does not predict hiring. Without a job
description the keyword and relevance parts are skipped and the score is
normalised over the remaining 65 points.
"""
import io
import re
from collections import Counter

# Words that say nothing about the job, so they are ignored in keyword counts.
STOPWORDS = set("""
a about above after again against all am an and any are aren as at be because been before being
below between both but by can cannot could couldn did didn do does doesn doing don down during each
few for from further had hadn has hasn have haven having he her here hers herself him himself his how
i if in into is isn it its itself just me more most mustn my myself no nor not now of off on once only
or other ought our ours ourselves out over own same shan she should shouldn so some such than that the
their theirs them themselves then there these they this those through to too under until up very was
wasn we were weren what when where which while who whom why with won would wouldn you your yours
yourself yourselves will shall may might must also using use used within across per etc including
work working works role roles company team teams job jobs candidate candidates ideal preferred plus
required requirements responsibilities responsibility skills skill experience experiences years year
good strong knowledge ability able new well like looking join apply position applicant applicants
hiring hired need needs want wants offer offers plus preferred bonus benefits culture growth
""".split())

# A compact vocabulary of skills seen in student and fresher job descriptions.
# canonical name -> searchable aliases (all lower case).
SKILL_VOCABULARY = {
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"],
    "C": ["c language"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "c sharp"],
    "SQL": ["sql"],
    "HTML": ["html"],
    "CSS": ["css"],
    "React": ["react", "react.js", "reactjs"],
    "Angular": ["angular"],
    "Vue": ["vue", "vue.js"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "Flask": ["flask"],
    "Django": ["django"],
    "FastAPI": ["fastapi"],
    "Spring Boot": ["spring boot", "springboot"],
    "REST APIs": ["rest api", "restful", "rest apis"],
    "GraphQL": ["graphql"],
    "MongoDB": ["mongodb", "mongo"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "SQLite": ["sqlite"],
    "Redis": ["redis"],
    "Git": ["git"],
    "GitHub": ["github"],
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Linux": ["linux", "unix"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "Google Cloud": ["gcp", "google cloud"],
    "Firebase": ["firebase"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib"],
    "Scikit-learn": ["scikit-learn", "sklearn"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"],
    "Data Analysis": ["data analysis", "data analytics"],
    "Data Visualisation": ["data visualization", "data visualisation", "tableau", "power bi"],
    "Excel": ["excel", "spreadsheet"],
    "Statistics": ["statistics", "statistical"],
    "Cybersecurity": ["cybersecurity", "cyber security", "information security"],
    "Networking": ["networking", "tcp/ip", "dns"],
    "Penetration Testing": ["penetration testing", "pentesting"],
    "Unit Testing": ["unit testing", "pytest", "unittest", "jest"],
    "CI/CD": ["ci/cd", "continuous integration", "github actions"],
    "Agile": ["agile", "scrum"],
    "Jira": ["jira"],
    "Figma": ["figma"],
    "UI/UX": ["ui/ux", "user experience", "user interface"],
    "Android": ["android"],
    "Flutter": ["flutter"],
    "React Native": ["react native"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "PHP": ["php"],
    "Laravel": ["laravel"],
    "Ruby": ["ruby"],
    "Go": ["golang", "go language"],
    "Rust": ["rust"],
    "Bash": ["bash", "shell scripting"],
    "GitHub Actions": ["github actions"],
    "OpenCV": ["opencv"],
    "Computer Vision": ["computer vision"],
    "Big Data": ["big data", "hadoop", "spark"],
    "System Design": ["system design"],
    "OOP": ["oop", "object-oriented", "object oriented"],
    "Data Structures": ["data structures"],
    "Algorithms": ["algorithms"],
    "Debugging": ["debugging"],
    "Testing": ["testing"],
    "Documentation": ["documentation"],
    "Communication": ["communication"],
    "Teamwork": ["teamwork", "team player", "collaboration"],
    "Problem Solving": ["problem solving", "problem-solving"],
    "Leadership": ["leadership"],
    "Time Management": ["time management"],
    "Presentation": ["presentation", "public speaking"],
    "SEO": ["seo", "search engine optimisation", "search engine optimization"],
    "WordPress": ["wordpress"],
    "SAP": ["sap"],
}

ACTION_VERBS = {
    "built", "build", "developed", "develop", "designed", "design", "created", "create",
    "implemented", "implement", "led", "lead", "managed", "manage", "improved", "improve",
    "automated", "automate", "launched", "launch", "analysed", "analyzed", "analyse", "analyze",
    "deployed", "deploy", "tested", "test", "optimised", "optimized", "optimise", "optimize",
    "integrated", "integrate", "wrote", "write", "documented", "document", "coordinated",
    "maintained", "maintain", "delivered", "deliver", "architected", "migrated", "migrate",
}

SECTION_PATTERNS = {
    "summary": r"(professional\s+summary|summary|profile|career\s+objective|objective)",
    "education": r"(education|academic\s+background|qualifications)",
    "skills": r"(technical\s+skills|skills|core\s+competencies|technologies)",
    "projects": r"(projects|academic\s+projects|personal\s+projects)",
    "experience": r"(experience|work\s+experience|internship|employment)",
    "certifications": r"(certifications?|licenses?|courses?)",
    "achievements": r"(achievements?|awards?|honours?|honors?)",
}

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
LINK_PATTERN = re.compile(r"(https?://[^\s]+|linkedin\.com/[^\s]+|github\.com/[^\s]+)", re.IGNORECASE)


class ExtractionError(Exception):
    """Raised when a file cannot be turned into text."""


# ------------------------------------------------------------------ extraction
def extract_pdf_text(data):
    """Read the text layer of a PDF with PyMuPDF."""
    import pymupdf

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as problem:  # damaged or not really a PDF
        raise ExtractionError("That PDF could not be opened. Try exporting it again.") from problem

    try:
        pages = [page.get_text("text") for page in document]
    finally:
        document.close()
    return "\n".join(pages)


def extract_docx_text(data):
    """Read the paragraph text of a DOCX file with python-docx."""
    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except Exception as problem:
        raise ExtractionError("That DOCX file could not be opened. Try saving it again.") from problem

    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return "\n".join(parts)


def extract_text(data, extension):
    extension = (extension or "").lower()
    if extension == "pdf":
        return extract_pdf_text(data)
    if extension == "docx":
        return extract_docx_text(data)
    raise ExtractionError("Only PDF and DOCX files can be analysed.")


def clean_text(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def words(text):
    """Lower-case words with trailing punctuation removed ('Flask.' -> 'flask')."""
    found = re.findall(r"[A-Za-z][A-Za-z+#./-]*", (text or "").lower())
    return [word.strip("./-+") for word in found if word.strip("./-+")]


# ------------------------------------------------------------------ sections
def detect_sections(text):
    """Look for standard resume headings, line by line."""
    lines = [line.strip() for line in (text or "").splitlines()]
    found = {}
    order = []
    for index, line in enumerate(lines):
        if not line or len(line) > 60:
            continue
        lowered = line.lower().strip(" :•-")
        for name, pattern in SECTION_PATTERNS.items():
            if re.fullmatch(pattern, lowered) or re.match(pattern + r"\b", lowered):
                if name not in found:
                    found[name] = index
                    order.append(name)
                break

    sections = {}
    for position, name in enumerate(order):
        start = found[name] + 1
        end = found[order[position + 1]] if position + 1 < len(order) else len(lines)
        sections[name] = "\n".join(lines[start:end]).strip()
    return sections


def detected_skills(text):
    """All vocabulary skills that appear in the text, with their evidence."""
    lowered = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    hits = []
    for canonical, aliases in SKILL_VOCABULARY.items():
        for alias in aliases:
            pattern = r"(?<![a-z0-9+#.])" + re.escape(alias.lower()) + r"(?![a-z0-9+#])"
            if re.search(pattern, lowered):
                hits.append(canonical)
                break
    return hits


# ------------------------------------------------------------------ job side
def job_keywords(description, limit=25):
    """The most repeated meaningful words in the job description."""
    counts = Counter(
        word for word in words(description)
        if len(word) > 2 and word not in STOPWORDS and not word.isdigit()
    )
    return [word for word, _count in counts.most_common(limit)]


def contact_details(text):
    return {
        "email": bool(EMAIL_PATTERN.search(text or "")),
        "phone": bool(PHONE_PATTERN.search(text or "")),
        "link": bool(LINK_PATTERN.search(text or "")),
    }


# ------------------------------------------------------------------ scoring
def _structure_score(text, sections):
    contact = contact_details(text)
    checks = [
        ("Email address", contact["email"], 4,
         "Add a professional email address near the top."),
        ("Phone number", contact["phone"], 3,
         "Add a phone number with the country code."),
        ("Professional summary", "summary" in sections, 4,
         "Add a two or three line professional summary."),
        ("Education section", "education" in sections, 4,
         "Add an Education section with your institution and degree."),
        ("Skills section", "skills" in sections, 4,
         "Add a Skills section so ATS software can read your technologies."),
        ("Projects or experience", ("projects" in sections) or ("experience" in sections), 3,
         "Add a Projects section describing what you built."),
        ("Profile links", contact["link"], 3,
         "Add GitHub, LinkedIn or a portfolio link."),
    ]
    score = sum(points for _label, passed, points, _hint in checks if passed)
    return score, checks


def _skills_score(resume_skills, jd_skills):
    if jd_skills:
        matched = [skill for skill in jd_skills if skill in resume_skills]
        return round(len(matched) * 25 / len(jd_skills)), matched
    # Without a job description, reward a reasonable, focused skills list.
    return min(25, len(resume_skills) * 2), []


def _keyword_score(resume_text, keywords):
    if not keywords:
        return None, [], []
    lowered = (resume_text or "").lower()
    found = [word for word in keywords if re.search(r"\b" + re.escape(word) + r"\b", lowered)]
    missing = [word for word in keywords if word not in found]
    return round(len(found) * 20 / len(keywords)), found, missing


def _relevance_score(sections, jd_terms, jd_title):
    """Do the job's terms appear in the project/experience evidence?"""
    evidence = " ".join(
        sections.get(name, "") for name in ("projects", "experience")
    ).lower()
    title_words = [word for word in words(jd_title) if len(word) > 2 and word not in STOPWORDS]
    terms = list(dict.fromkeys([*jd_terms, *title_words]))[:20]
    if not terms:
        return None
    hits = sum(1 for term in terms if re.search(r"\b" + re.escape(term) + r"\b", evidence))
    return round(hits * 15 / len(terms))


def _content_score(text, sections):
    total_words = len(words(text))
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    bullets = sum(1 for line in lines if re.match(r"^[•\-*·▪◦]", line))
    verbs = {word for word in words(text) if word in ACTION_VERBS}
    score = 0
    notes = []

    if 180 <= total_words <= 900:
        score += 5
        notes.append("Length is in a readable range for one or two pages.")
    elif total_words > 0:
        notes.append(
            "The resume has about %d words; 180-900 reads best for a fresher." % total_words
        )

    if bullets >= 3:
        score += 4
        notes.append("%d bullet points make the document easy to scan." % bullets)
    elif bullets:
        notes.append("Only %d bullet point(s) found; short bullets read better than paragraphs." % bullets)
    else:
        notes.append("No bullet points were detected; use short bullets for achievements.")

    if len(verbs) >= 3:
        score += 3
        notes.append("Action verbs detected: " + ", ".join(sorted(verbs)[:5]) + ".")
    elif verbs:
        notes.append("Add more action verbs (built, implemented, analysed) at the start of bullets.")
    else:
        notes.append("No common action verbs were detected in the text.")

    if sections.get("summary") and len(words(sections["summary"])) >= 12:
        score += 3
        notes.append("The summary is present and specific enough to read as a summary.")

    return score, notes


# ------------------------------------------------------------------ main entry
def analyze_resume(text, job_title="", description="", company="", industry="",
                   experience_level="", source_name=""):
    """Return the full analysis dictionary for one resume text."""
    text = clean_text(text)
    if len(words(text)) < 40:
        raise ExtractionError(
            "There is almost no readable text in that file. If it is a scanned image, "
            "OCR software is needed before it can be analysed."
        )

    sections = detect_sections(text)
    resume_skills = detected_skills(text)
    jd_text = " ".join(part for part in (job_title, description) if part).strip()
    jd_skills = detected_skills(jd_text) if jd_text else []
    keywords = job_keywords(description) if description.strip() else []

    structure, structure_checks = _structure_score(text, sections)
    skills_score, matched = _skills_score(resume_skills, jd_skills)
    keyword_score, found_keywords, missing_keywords = _keyword_score(text, keywords)
    job_terms = job_keywords(description, limit=40) if description.strip() else []
    relevance = _relevance_score(sections, job_terms, job_title) if description.strip() else None
    content, content_notes = _content_score(text, sections)

    missing = [skill for skill in jd_skills if skill not in resume_skills]
    extra_skills = [skill for skill in resume_skills if skill not in jd_skills]

    # Skills written in the skills section but never demonstrated below it.
    evidence = " ".join(
        sections.get(name, "") for name in ("projects", "experience", "education")
    ).lower()
    unsupported = [
        skill for skill in resume_skills
        if skill.lower() in (sections.get("skills", "").lower())
        and not any(
            re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", evidence)
            for alias in SKILL_VOCABULARY.get(skill, [skill.lower()])
        )
    ]

    scores = {
        "structure": structure,
        "skills": skills_score,
        "keywords": keyword_score,
        "relevance": relevance,
        "content": content,
    }

    available = 25 + 15  # structure and content always apply
    earned = structure + content
    if skills_score is not None:
        available += 25
        earned += skills_score
    if keyword_score is not None:
        available += 20
        earned += keyword_score
    if relevance is not None:
        available += 15
        earned += relevance
    overall = round(earned * 100 / available) if available else 0
    overall = max(0, min(100, overall))

    strengths = []
    for label, passed, _points, _hint in structure_checks:
        if passed:
            strengths.append(f"{label} detected.")
    if len(resume_skills) >= 5:
        strengths.append(f"{len(resume_skills)} recognised skills found in the document.")
    if bullets := sum(1 for line in text.splitlines() if re.match(r"^[•\-*·▪◦]", line.strip())):
        strengths.append(f"Uses {bullets} bullet points, which ATS software reads line by line.")
    if matched:
        strengths.append("Job skills also found in the resume: " + ", ".join(matched[:8]) + ".")
    if sections.get("projects") and ("github" in text.lower() or "http" in text.lower()):
        strengths.append("Project section includes a link that a recruiter can open.")

    improvements = []
    for label, passed, _points, hint in structure_checks:
        if not passed:
            improvements.append({"title": f"Missing: {label.lower()}", "detail": hint})
    if missing:
        improvements.append({
            "title": "Job skills not found in this resume",
            "detail": "Only add a skill you can actually discuss: " + ", ".join(missing[:8]) + ".",
        })
    if missing_keywords:
        improvements.append({
            "title": "Job words not found in the document",
            "detail": "Consider covering these naturally, never as a keyword list: "
                      + ", ".join(missing_keywords[:10]) + ".",
        })
    if unsupported:
        improvements.append({
            "title": "Skills without an example",
            "detail": "These appear in your skills list but not in a project or job: "
                      + ", ".join(unsupported[:8]) + ". Add one line of evidence if you have it.",
        })
    if keyword_score is not None and keyword_score < 12:
        improvements.append({
            "title": "Low overlap with the job description",
            "detail": "Mirror the real responsibilities you have done, using the same vocabulary as the advert.",
        })
    for note in content_notes:
        if "No " in note or "Only" in note or "Add " in note or "about" in note:
            improvements.append({"title": "Content quality", "detail": note})

    # A stable, ordered checklist for the results page.
    checklist = [
        {"title": item["title"], "detail": item["detail"]}
        for item in improvements[:8]
    ]
    checklist.append({
        "title": "Re-read the document after editing",
        "detail": "Make sure every line is still true and nothing was invented.",
    })

    return {
        "overall": overall,
        "scores": scores,
        "score_maxima": {"structure": 25, "skills": 25, "keywords": 20, "relevance": 15, "content": 15},
        "normalised": keyword_score is None or relevance is None,
        "resume_skills": resume_skills,
        "job_skills": jd_skills,
        "matched": matched,
        "missing": missing,
        "extra_skills": extra_skills,
        "unsupported": unsupported,
        "keywords_found": found_keywords,
        "keywords_missing": missing_keywords,
        "structure_checks": [
            {"label": label, "passed": passed, "hint": hint}
            for label, passed, _points, hint in structure_checks
        ],
        "sections_present": sorted(sections.keys()),
        "strengths": strengths,
        "improvements": improvements,
        "checklist": checklist,
        "content_notes": content_notes,
        "word_count": len(words(text)),
        "source_name": source_name,
        "job_title": job_title,
        "company": company,
        "industry": industry,
        "experience_level": experience_level,
        "has_job": bool(description.strip()),
    }
