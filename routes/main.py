"""
routes/main.py - the public pages anyone can visit: Home, About, Features.
"""
from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)

# The features are stored once here and shown on both the Home page
# and the Features page. Edit the text here to change it everywhere.
FEATURES = [
    {
        "icon": "clipboard",
        "title": "Skill assessments",
        "summary": (
            "Multiple-choice quizzes in Python, C++, HTML and CSS, JavaScript and "
            "programming basics. You get a score, the correct answers and the "
            "topics to revisit."
        ),
        "points": [
            "At least 10 questions per subject, one clear quiz screen at a time",
            "Scores are calculated automatically and saved to your account",
            "Review which answers were right or wrong",
            "See the topics that need more practice",
        ],
    },
    {
        "icon": "route",
        "title": "Career roadmaps",
        "summary": (
            "Pick a career path and follow its learning steps in order. Tick off "
            "each step and watch your completion percentage grow."
        ),
        "points": [
            "Python Developer, Web Developer, AI/ML Engineer, Data Analyst and Cybersecurity Analyst",
            "Every path has predefined, ordered learning steps",
            "Your progress is saved per account",
        ],
    },
    {
        "icon": "target",
        "title": "Skill gap analysis",
        "summary": (
            "Compare the skills you have with what your chosen career asks for. "
            "See what you know, what you are learning and what is missing."
        ),
        "points": [
            "Skills already acquired and skills you are still learning",
            "Missing skills for your selected career",
            "Suggested learning priorities, worked out with simple, readable rules",
        ],
    },
    {
        "icon": "book",
        "title": "Learning resources",
        "summary": (
            "Browse free documentation and tutorials by skill. Search, filter and "
            "save the ones you want to come back to."
        ),
        "points": [
            "Resources organised by skill category",
            "Search by keyword and filter by category",
            "Save and remove favourites",
            "Every link opens a real, publicly available resource",
        ],
    },
    {
        "icon": "folder",
        "title": "Project tracker",
        "summary": (
            "Keep every project in one place: what it uses, where its code lives "
            "on GitHub and whether it is finished."
        ),
        "points": [
            "Add, edit and delete your own projects",
            "Record the technologies and the GitHub repository link",
            "Mark each project as Not Started, In Progress or Completed",
        ],
    },
    {
        "icon": "flag",
        "title": "Goals and progress",
        "summary": (
            "Set weekly and monthly learning goals with target dates. See what is "
            "done, what is pending and what is overdue."
        ),
        "points": [
            "Weekly and monthly goals with task descriptions",
            "Mark goals complete, edit them or delete them",
            "Progress statistics and overdue goals at a glance",
        ],
    },
    {
        "icon": "file",
        "title": "Career readiness report",
        "summary": (
            "Get a summary of your skills, assessment scores, roadmap progress "
            "and suggested next steps, and download it as a PDF."
        ),
        "points": [
            "Built from your own saved data",
            "Shows learning progress and career preparation",
            "It never predicts or guarantees a job",
        ],
    },
]

# Career paths shown on the Home page, with a few key skills each.
CAREERS = [
    {"title": "Python Developer", "skills": ["Python", "SQL", "Flask"]},
    {"title": "Web Developer", "skills": ["HTML and CSS", "JavaScript", "Git"]},
    {"title": "AI/ML Engineer", "skills": ["Python", "Statistics", "Machine learning"]},
    {"title": "Data Analyst", "skills": ["SQL", "Excel", "Data visualisation"]},
    {"title": "Cybersecurity Analyst", "skills": ["Networking", "Linux", "Security basics"]},
]


@main_bp.route("/")
def index():
    return render_template("index.html", features=FEATURES, careers=CAREERS)


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/features")
def features():
    return render_template("features.html", features=FEATURES)


@main_bp.route("/design-system")
def design_system():
    """The Phase 2 design specimen: tokens, components and charts.

    This is a review page for the design system, not a product feature. It has
    no database access and no private data, so it does not require a login.
    """
    return render_template("design_system.html")
