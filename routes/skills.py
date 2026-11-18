"""Skill management and interactive assessments for the signed-in user."""
import json
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from utils.database import get_db
from utils.helpers import log_activity

skills_bp = Blueprint("skills", __name__)

# Starter catalogue. Entries are inserted once and never replace user data.
SKILL_CATALOGUE = [
    ("Python", "Programming"), ("C++", "Programming"), ("Java", "Programming"),
    ("HTML", "Web Development"), ("CSS", "Web Development"),
    ("JavaScript", "Web Development"), ("SQL", "Database"),
    ("Git & GitHub", "Tools"), ("Machine Learning", "AI & Data"),
    ("Data Structures", "Computer Science"), ("Cybersecurity", "Security"),
    ("Basic Programming Concepts", "Computer Science"),
    # Phase 5: the skills the five career paths ask for, so a student can add
    # any missing skill to their own list instead of only seeing it listed.
    ("Flask", "Web Development"), ("REST APIs", "Web Development"),
    ("Unit Testing", "Tools"), ("Linux", "Tools"),
    ("Excel", "Data & Analytics"), ("Statistics", "Data & Analytics"),
    ("Data Visualisation", "Data & Analytics"),
    ("NumPy & Pandas", "AI & Data"), ("Deep Learning", "AI & Data"),
    ("Networking", "Security"), ("Security Basics", "Security"),
]

# Each question is (topic, question, option A, option B, option C, option D,
# correct option, explanation). Question text is used as a stable seed key so
# new questions can be added without deleting attempts or replacing old rows.

def Q(topic, prompt, a, b, c, d, answer, explanation):
    return (topic, prompt, a, b, c, d, answer, explanation)

QUESTION_BANK = {
    "Python": ("Python programming: syntax, data types, control flow and functions", [
        Q("Functions", "Which keyword defines a function in Python?", "func", "def", "function", "lambda", "B", "The def keyword begins a function definition."),
        Q("Data types", "Which data type stores key-value pairs?", "list", "tuple", "dictionary", "set", "C", "A dictionary stores values under unique keys."),
        Q("Built-in functions", "What does len([2, 4, 6]) return?", "2", "3", "4", "6", "B", "The list contains three elements."),
        Q("Syntax", "Which symbol starts a single-line comment?", "//", "<!--", "#", "/*", "C", "Python comments begin with #."),
        Q("Operators", "What is the result of 7 // 2?", "3.5", "4", "3", "2", "C", "The // operator performs floor division."),
        Q("Collections", "Which collection is ordered and mutable?", "tuple", "list", "frozenset", "string", "B", "Lists preserve order and can be changed."),
        Q("Control flow", "Which keyword skips to the next loop iteration?", "stop", "pass", "continue", "break", "C", "continue skips the remaining body and starts the next iteration."),
        Q("Strings", "What is the result of 'Py' + 'thon'?", "Py thon", "Python", "Py+thon", "Error", "B", "The + operator concatenates strings."),
        Q("Exceptions", "Which block handles an exception?", "catch", "except", "error", "final", "B", "Python uses except to handle raised exceptions."),
        Q("Modules", "Which statement imports the math module?", "include math", "using math", "import math", "load(math)", "C", "The import statement makes a module available."),
    ]),
    "C++": ("C++ programming: syntax, input/output, control flow and OOP", [
        Q("Input and output", "Which header is commonly used for cout and cin?", "<stdio.h>", "<iostream>", "<string>", "<fstream>", "B", "iostream provides standard input and output streams."),
        Q("Operators", "Which operator accesses a member through an object?", "::", "->", ".", "&", "C", "The dot operator accesses members through an object."),
        Q("Loops", "Which loop checks its condition before each iteration?", "do-while", "while", "Both always", "Neither", "B", "A while loop checks its condition before the body."),
        Q("Classes", "Which keyword declares a class?", "struct", "object", "class", "define", "C", "The class keyword declares a class."),
        Q("Functions", "What does return 5; return from an int function?", "5", "'5'", "5.0", "true", "A", "The integer literal 5 is returned."),
        Q("Variables", "Which type is commonly used to store a whole number?", "int", "bool", "char", "void", "A", "int represents integer values."),
        Q("Arrays", "What is the index of the first element in a C++ array?", "1", "-1", "0", "Depends on size", "C", "C++ arrays use zero-based indexing."),
        Q("Functions", "Which keyword sends a value back from a function?", "break", "return", "continue", "using", "B", "return ends the function and can provide a value."),
        Q("OOP", "Which OOP concept bundles data and methods in one unit?", "Encapsulation", "Compilation", "Iteration", "Recursion", "A", "Encapsulation combines data and related operations in a class."),
        Q("Pointers", "Which symbol is used to declare a pointer variable?", "&", "*", "%", "#", "B", "The asterisk indicates a pointer declarator in a declaration."),
    ]),
    "Java": ("Java syntax, data types and object-oriented basics", [
        Q("Program structure", "Which method is the usual Java program entry point?", "start()", "main()", "run()", "init()", "B", "Java applications commonly start at public static void main."),
        Q("Objects", "Which keyword creates an object?", "this", "new", "class", "make", "B", "The new keyword creates an object."),
        Q("Data types", "Which type stores true or false?", "int", "char", "boolean", "String", "C", "boolean represents true or false."),
        Q("Inheritance", "Which keyword supports inheritance between classes?", "implements", "extends", "inherits", "superclass", "B", "A Java class extends another class."),
        Q("Collections", "Which collection stores unique elements?", "ArrayList", "HashSet", "Array", "LinkedList", "B", "HashSet does not allow duplicate elements."),
        Q("Strings", "Which class represents text as an immutable sequence?", "String", "StringBuilder", "Scanner", "File", "A", "String objects are immutable in Java."),
        Q("Access modifiers", "Which access modifier makes a member accessible from any class?", "private", "protected", "public", "default only", "C", "public gives the widest access."),
        Q("Exceptions", "Which block is used to handle an exception?", "try", "catch", "throw", "throws", "B", "A catch block handles a matching exception from a try block."),
        Q("Interfaces", "Which keyword indicates that a class uses an interface?", "extends", "implements", "interface", "instanceof", "B", "A class implements an interface."),
        Q("Loops", "Which loop is guaranteed to execute its body at least once?", "for", "while", "do-while", "enhanced for", "C", "A do-while loop checks its condition after the body."),
    ]),
    "HTML and CSS": ("HTML structure, semantic elements, selectors and styling", [
        Q("HTML elements", "Which HTML element creates a hyperlink?", "<link>", "<a>", "<href>", "<url>", "B", "The anchor element creates links."),
        Q("CSS properties", "Which CSS property changes text colour?", "font-style", "background", "color", "text-decoration", "C", "The color property sets foreground text colour."),
        Q("HTML attributes", "Which attribute provides alternative text for an image?", "title", "alt", "src", "href", "B", "The alt attribute describes an image for accessibility."),
        Q("CSS layout", "Which CSS layout system is one-dimensional?", "Grid", "Flexbox", "Table", "Float", "B", "Flexbox lays out items along one main axis."),
        Q("HTML forms", "Which element creates a user input field?", "<input>", "<section>", "<label>", "<meta>", "A", "The input element accepts user-entered data."),
        Q("Semantic HTML", "Which element represents the main content of a page?", "<main>", "<aside>", "<small>", "<footer>", "A", "The main element identifies the dominant page content."),
        Q("CSS selectors", "Which selector targets an element with id='header'?", ".header", "#header", "header*", "@header", "B", "An ID selector starts with #."),
        Q("CSS box model", "Which property adds space inside an element's border?", "margin", "padding", "outline", "gap", "B", "Padding is the space between content and border."),
        Q("CSS units", "Which unit is relative to the root element's font size?", "px", "em", "rem", "vh", "C", "rem is based on the root element's font size."),
        Q("Responsive design", "Which CSS rule is commonly used for responsive breakpoints?", "@font-face", "@media", "@import", "@keyframes", "B", "Media queries apply styles based on viewport or device conditions."),
    ]),
    "JavaScript": ("JavaScript fundamentals: variables, functions, arrays and DOM", [
        Q("Variables", "Which keyword declares a block-scoped variable that can be reassigned?", "const", "let", "static", "define", "B", "let declares a block-scoped variable that can be reassigned."),
        Q("Data types", "Which value represents an intentional absence of a value?", "undefined", "null", "NaN", "false", "B", "null is commonly used to represent an intentional empty value."),
        Q("Functions", "Which syntax creates an arrow function?", "function =>", "() => {}", "-> {}", "func() {}", "B", "Arrow functions use the => operator."),
        Q("Arrays", "Which method adds an item to the end of an array?", "pop()", "shift()", "push()", "slice()", "C", "push appends one or more items to an array."),
        Q("DOM", "Which method selects an element by its ID?", "getElementById()", "queryAllId()", "selectId()", "findClass()", "A", "document.getElementById selects an element by its id."),
        Q("Comparisons", "Which operator checks value and type equality?", "=", "==", "===", "!=", "C", "=== performs strict equality without type coercion."),
        Q("Conditions", "Which keyword runs a block when an if condition is false?", "otherwise", "else", "then", "default", "B", "else provides the alternative branch of an if statement."),
        Q("Objects", "How do you access the name property of object user?", "user->name", "user.name", "user::name", "user/name", "B", "Dot notation accesses an object's property."),
        Q("Events", "Which event commonly fires when a user clicks an element?", "change", "submit", "click", "load", "C", "The click event is dispatched when an element is clicked."),
        Q("JSON", "Which method converts a JSON string into a JavaScript value?", "JSON.parse()", "JSON.stringify()", "JSON.convert()", "parse.JSON()", "A", "JSON.parse parses a JSON string into a value."),
    ]),
    "Basic Programming Concepts": ("Core programming logic, algorithms, variables and control flow", [
        Q("Variables", "What is a variable used for?", "Store a value", "Draw a screen", "Connect to Wi-Fi", "Compile a file", "A", "A variable names a storage location or value used by a program."),
        Q("Data types", "Which data type is best suited to a true/false value?", "Integer", "Boolean", "String", "Float", "B", "A Boolean represents true or false."),
        Q("Operators", "What is the result of 10 % 3?", "0", "1", "3", "3.3", "B", "The modulo operator returns the remainder, which is 1."),
        Q("Conditions", "Which structure chooses between alternative paths?", "Loop", "Conditional statement", "Comment", "Variable", "B", "An if/else conditional selects a path based on a condition."),
        Q("Loops", "What is a loop mainly used for?", "Repeat instructions", "Rename variables", "Delete a program", "Create a database", "A", "Loops repeat a block while a condition or iteration requires it."),
        Q("Algorithms", "What is an algorithm?", "A programming language", "A step-by-step procedure", "A computer brand", "A data cable", "B", "An algorithm is a finite sequence of steps to solve a problem."),
        Q("Debugging", "What does debugging mean?", "Finding and fixing errors", "Designing a logo", "Installing hardware", "Writing comments only", "A", "Debugging identifies, diagnoses and fixes defects in code."),
        Q("Functions", "Why are functions useful?", "They reuse grouped instructions", "They remove all variables", "They replace the operating system", "They always make code slower", "A", "Functions package reusable logic and can accept inputs and return outputs."),
        Q("Input and output", "What is input in a program?", "Data provided to a program", "Only the final result", "A syntax error", "A loop ending", "A", "Input is information supplied to a program for processing."),
        Q("Logic", "Which logical operator is true only when both conditions are true?", "OR", "NOT", "AND", "XOR", "C", "AND is true only if both operands are true."),
    ]),
    "SQL": ("Relational database fundamentals and SQL queries", [
        Q("Queries", "Which SQL command retrieves rows?", "GET", "FETCH", "SELECT", "OPEN", "C", "SELECT queries data from tables or views."),
        Q("Filtering", "Which clause filters rows before grouping?", "ORDER BY", "WHERE", "HAVING", "LIMIT", "B", "WHERE filters individual rows before grouping."),
        Q("Keys", "Which key uniquely identifies a row?", "Foreign key", "Candidate text", "Primary key", "Index only", "C", "A primary key uniquely identifies each row."),
        Q("Data modification", "Which command adds a new row?", "INSERT", "UPDATE", "ALTER", "CREATE", "A", "INSERT adds records to a table."),
        Q("Aggregate functions", "What does COUNT(*) return?", "Sum of values", "Number of rows", "Largest value", "Column names", "B", "COUNT(*) counts rows in the result set."),
        Q("Sorting", "Which clause sorts query results?", "GROUP BY", "ORDER BY", "SORT", "ARRANGE", "B", "ORDER BY sorts rows by one or more expressions."),
        Q("Grouping", "Which clause groups rows with matching values?", "GROUP BY", "WHERE", "VALUES", "JOIN", "A", "GROUP BY forms groups for aggregate calculations."),
        Q("Joins", "Which join returns only matching rows from both tables?", "LEFT JOIN", "FULL JOIN", "INNER JOIN", "CROSS JOIN", "C", "INNER JOIN returns rows where the join condition matches."),
        Q("Data modification", "Which command changes existing rows?", "INSERT", "UPDATE", "SELECT", "CREATE", "B", "UPDATE modifies values in existing records."),
        Q("Table structure", "Which command creates a new table?", "MAKE TABLE", "NEW TABLE", "CREATE TABLE", "ADD TABLE", "C", "CREATE TABLE defines a new database table."),
    ]),
    "Web Development": ("Web development concepts: browser, HTTP, forms and accessibility", [
        Q("HTML", "Which language provides the structure of a web page?", "CSS", "HTML", "SQL", "Python only", "B", "HTML describes the structure and content of web pages."),
        Q("CSS", "Which language is mainly used to style web pages?", "CSS", "HTTP", "JSON", "SQL", "A", "CSS controls presentation and layout."),
        Q("JavaScript", "Which language commonly adds interactivity in the browser?", "JavaScript", "SQL", "XML only", "Bash", "A", "JavaScript can respond to events and update page content."),
        Q("HTTP", "Which HTTP method is commonly used to retrieve a resource?", "POST", "GET", "PATCH", "DELETE", "B", "GET requests a representation of a resource."),
        Q("HTTP", "What does HTTP status code 404 mean?", "Success", "Server redirected", "Not Found", "Unauthorized", "C", "404 indicates that the requested resource was not found."),
        Q("Forms", "Which HTML attribute names the form field sent to a server?", "name", "colour", "font", "target-size", "A", "The name attribute identifies a submitted form control."),
        Q("Responsive design", "What does responsive web design aim to do?", "Adapt layouts to screen sizes", "Disable mobile browsers", "Use only images", "Prevent scrolling", "A", "Responsive layouts adapt to different viewport sizes."),
        Q("Accessibility", "Why should form inputs have labels?", "To improve usability and accessibility", "To increase file size", "To hide errors", "To replace validation", "A", "Labels help users understand controls and support assistive technology."),
        Q("Client and server", "Where does client-side JavaScript commonly run?", "In the user's browser", "Only in SQLite", "Inside CSS", "Only on a DNS server", "A", "Browser JavaScript executes on the client device."),
        Q("Web security", "What does HTTPS add to HTTP?", "Encrypted transport using TLS", "Automatic backups", "A database", "Faster HTML parsing", "A", "HTTPS protects data in transit using TLS."),
    ]),
}


def ensure_phase4_seed_data(db):
    """Seed missing catalogue/questions safely; never replace existing attempts.

    BEGIN IMMEDIATE serializes concurrent seeders. Question text acts as the
    idempotency key because the original schema has no unique question index.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        for name, category in SKILL_CATALOGUE:
            db.execute(
                "INSERT OR IGNORE INTO skills (name, category) VALUES (?, ?)",
                (name, category),
            )

        for title, (description, questions) in QUESTION_BANK.items():
            db.execute(
                "INSERT OR IGNORE INTO assessments (title, description) VALUES (?, ?)",
                (title, description),
            )
            assessment = db.execute(
                "SELECT id FROM assessments WHERE title = ?", (title,)
            ).fetchone()
            assessment_id = assessment["id"]

            for topic, prompt, a, b, c, d, answer, explanation in questions:
                # Correct the generic topic on older starter questions only.
                db.execute(
                    "UPDATE assessment_questions SET topic = ? "
                    "WHERE assessment_id = ? AND question_text = ? AND topic = 'Fundamentals'",
                    (topic, assessment_id, prompt),
                )
                exists = db.execute(
                    "SELECT 1 FROM assessment_questions "
                    "WHERE assessment_id = ? AND question_text = ? LIMIT 1",
                    (assessment_id, prompt),
                ).fetchone()
                if not exists:
                    db.execute(
                        """INSERT INTO assessment_questions
                        (assessment_id, topic, question_text, option_a, option_b,
                         option_c, option_d, correct_option, explanation)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (assessment_id, topic, prompt, a, b, c, d, answer, explanation),
                    )
        db.commit()
    except Exception:
        db.rollback()
        raise


@skills_bp.route("/skills", methods=["GET", "POST"])
@login_required
def manage_skills():
    db = get_db()
    user_id = current_user.id

    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "add":
            try:
                skill_id = int(request.form.get("skill_id", ""))
            except (TypeError, ValueError):
                skill_id = 0
            skill = db.execute("SELECT id FROM skills WHERE id = ?", (skill_id,)).fetchone()
            if not skill:
                flash("Please choose a skill from the list.", "error")
            else:
                try:
                    db.execute("INSERT INTO user_skills (user_id, skill_id, status) VALUES (?, ?, 'Learning')", (user_id, skill_id))
                    db.commit()
                    log_activity(user_id, "skill", "Added a skill to your learning list")
                    flash("Skill added to your learning list.", "success")
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That skill is already in your list.", "info")
        elif action == "update":
            try:
                row_id = int(request.form.get("user_skill_id", ""))
            except (TypeError, ValueError):
                row_id = 0
            status = request.form.get("status", "")
            if status not in ("Learning", "Acquired"):
                flash("Choose a valid skill status.", "error")
            else:
                cursor = db.execute("UPDATE user_skills SET status = ? WHERE id = ? AND user_id = ?", (status, row_id, user_id))
                db.commit()
                if cursor.rowcount:
                    log_activity(user_id, "skill", "Updated a skill's progress")
                    flash("Skill progress updated.", "success")
                else:
                    flash("That skill could not be found.", "error")
        elif action == "delete":
            try:
                row_id = int(request.form.get("user_skill_id", ""))
            except (TypeError, ValueError):
                row_id = 0
            cursor = db.execute("DELETE FROM user_skills WHERE id = ? AND user_id = ?", (row_id, user_id))
            db.commit()
            if cursor.rowcount:
                log_activity(user_id, "skill", "Removed a skill from your list")
                flash("Skill removed.", "success")
            else:
                flash("That skill could not be found.", "error")
        return redirect(url_for("skills.manage_skills"))

    user_skills = db.execute(
        """SELECT us.id AS user_skill_id, us.status, us.added_at, s.id AS skill_id, s.name, s.category
        FROM user_skills us JOIN skills s ON s.id = us.skill_id
        WHERE us.user_id = ? ORDER BY s.category, s.name""", (user_id,)
    ).fetchall()
    available = db.execute(
        """SELECT id, name, category FROM skills WHERE id NOT IN
        (SELECT skill_id FROM user_skills WHERE user_id = ?) ORDER BY category, name""", (user_id,)
    ).fetchall()
    acquired = sum(1 for item in user_skills if item["status"] == "Acquired")
    return render_template("dashboard/skills.html", user_skills=user_skills, available=available, acquired=acquired)


@skills_bp.route("/assessments")
@login_required
def assessment_list():
    db = get_db()
    assessments = db.execute(
        """SELECT a.id, a.title, a.description, COUNT(q.id) AS question_count,
        (SELECT ROUND(r.percentage) FROM assessment_results r WHERE r.assessment_id = a.id AND r.user_id = ? ORDER BY r.id DESC LIMIT 1) AS latest_score,
        (SELECT COUNT(*) FROM assessment_results r2 WHERE r2.assessment_id = a.id AND r2.user_id = ?) AS attempts
        FROM assessments a LEFT JOIN assessment_questions q ON q.assessment_id = a.id
        GROUP BY a.id ORDER BY a.title""", (current_user.id, current_user.id)
    ).fetchall()
    return render_template("dashboard/assessments.html", assessments=assessments)


@skills_bp.route("/assessments/<int:assessment_id>")
@login_required
def take_assessment(assessment_id):
    db = get_db()
    assessment = db.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
    if not assessment:
        flash("That assessment is not available.", "error")
        return redirect(url_for("skills.assessment_list"))
    questions = db.execute(
        "SELECT id, topic, question_text, option_a, option_b, option_c, option_d FROM assessment_questions WHERE assessment_id = ? ORDER BY id",
        (assessment_id,),
    ).fetchall()
    if not questions:
        flash("Questions for this assessment are being prepared.", "info")
        return redirect(url_for("skills.assessment_list"))
    return render_template("dashboard/take_assessment.html", assessment=assessment, questions=questions)


@skills_bp.route("/assessments/<int:assessment_id>/submit", methods=["POST"])
@login_required
def submit_assessment(assessment_id):
    db = get_db()
    assessment = db.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
    if not assessment:
        flash("That assessment is not available.", "error")
        return redirect(url_for("skills.assessment_list"))
    questions = db.execute("SELECT * FROM assessment_questions WHERE assessment_id = ? ORDER BY id", (assessment_id,)).fetchall()
    if not questions:
        flash("This assessment has no questions yet.", "error")
        return redirect(url_for("skills.assessment_list"))

    score = 0
    weak_topics = set()
    answers = {}
    review = []
    for question in questions:
        chosen = request.form.get(f"question_{question['id']}", "").upper()
        if chosen not in ("A", "B", "C", "D"):
            chosen = ""
        correct = chosen == question["correct_option"]
        score += int(correct)
        answers[str(question["id"])] = chosen
        if not correct:
            weak_topics.add(question["topic"])
        review.append({"question": question, "chosen": chosen, "correct": correct})
    total = len(questions)
    percentage = round((score / total) * 100, 2)
    cursor = db.execute(
        """INSERT INTO assessment_results
        (user_id, assessment_id, score, total_questions, percentage, weak_topics, answers_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (current_user.id, assessment_id, score, total, percentage, ", ".join(sorted(weak_topics)), json.dumps(answers)),
    )
    db.commit()
    log_activity(current_user.id, "assessment", f"Completed the {assessment['title']} assessment ({score}/{total})")
    return render_template("dashboard/assessment_result.html", assessment=assessment, score=score, total=total, percentage=percentage, review=review, weak_topics=sorted(weak_topics))


@skills_bp.route("/assessment-history")
@login_required
def assessment_history():
    results = get_db().execute(
        """SELECT r.id, r.score, r.total_questions, r.percentage, r.weak_topics, r.taken_at, a.title
        FROM assessment_results r JOIN assessments a ON a.id = r.assessment_id
        WHERE r.user_id = ? ORDER BY r.id DESC LIMIT 50""", (current_user.id,)
    ).fetchall()
    return render_template("dashboard/assessment_history.html", results=results)
