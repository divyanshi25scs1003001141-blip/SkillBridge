# SkillBridge — Integrated Student Skill Development Platform

SkillBridge is a lightweight Flask and SQLite web application designed to help students manage skills, assess their knowledge and build career readiness.

## Current project status

- **Phases 1–3:** Foundation, authentication, dashboard and profile are integrated.
- **Phase 4:** Skill management and skill assessments are integrated. The assessment catalogue includes Python, C++, HTML and CSS, JavaScript, Basic Programming Concepts, Java, SQL and Web Development. Each assessment contains at least 10 multiple-choice questions with topic labels, explanations and saved results.
- **Phase 5:** Career selection and skill-gap analysis are integrated. A student picks one of five career paths (Python Developer, Web Developer, Data Analyst, AI/ML Engineer, Cybersecurity Analyst); SkillBridge compares that career's required skills with the student's own skills, shows the weighted gap, and lists suggested next steps. Latest assessment scores are shown as extra insight only and never change a skill's status.
- **Phase 6:** Career roadmaps are integrated. Each of the five careers has an ordered roadmap (Python Developer has the eight planned steps), students follow the roadmap for their selected career, mark steps complete or undo them, and see a real progress percentage on the roadmap page and the dashboard. Progress is per user and is kept when switching roadmaps.
- **Phase 7:** Learning resources are integrated. A seeded catalogue of free, real links is organised by skill category, difficulty and resource type, with keyword search, filters and private per-user favourites.
- **Phase 8:** The project tracker is integrated. Each student keeps a private list of projects with technologies, a GitHub link, an optional live link, and a Planned / In Progress / Completed status.
- **Phase 9:** Learning goals are integrated. Weekly and monthly goals carry a target date, can be completed and reopened, and the dashboard shows the real completion percentage and overdue count.
- **Phase 11:** Career Studio is integrated. The **Certificate Vault** keeps private PDF/image certificates with validation and owner-only downloads, and the **ATS Resume Builder** creates single-column resumes in four templates from the student's own data, with vault certificates, live preview, PDF and print output.
- **Phase 12:** The **Resume Analyzer** is integrated. It extracts the text of an uploaded PDF/DOCX or a saved resume, compares it with a pasted job description using fixed rules, and shows an estimated ATS compatibility score, matched/missing skills, keyword coverage, structure checks and an improvement checklist. Uploaded files are deleted immediately after the text is read.
- **Phase 10:** The Career Readiness Report is integrated. It combines skill coverage, roadmap progress, latest assessment scores, finished projects and completed goals into one weighted score, with every weight and piece of evidence shown on the page.

## Technology

- Python 3.10 or newer
- Flask and Jinja2
- SQLite
- HTML, CSS and JavaScript

## Run on Windows (VS Code)

1. Extract this ZIP to a normal folder (for example, `Documents\SkillBridge`).
2. Open that folder in VS Code (`File` → `Open Folder`).
3. Open the VS Code terminal (`Terminal` → `New Terminal`).
4. Create a virtual environment:
   ```powershell
   py -m venv .venv
   ```
5. Activate it:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, use Command Prompt and run:
   ```bat
   .venv\Scripts\activate.bat
   ```
6. Install dependencies:
   ```powershell
   py -m pip install -r requirements.txt
   ```
7. Start the app:
   ```powershell
   py app.py
   ```
8. Open `http://127.0.0.1:5000` in your browser.

The SQLite database is created automatically in the configured database folder on first run. Existing database records are not replaced by the Phase 4 starter-data seeder.

## Main routes

- `/` — public home page
- `/about` — about page
- `/features` — feature information
- `/register` — create an account
- `/login` — log in
- `/dashboard` — authenticated dashboard
- `/profile` — authenticated profile page
- `/skills` — manage personal skills
- `/assessments` — browse skill assessments
- `/assessments/<id>` — take an assessment
- `/career` — choose or change the target career
- `/skill-gap` — the skill gap for the selected career
- `/roadmap` — the career roadmap with step completion and progress
- `/roadmap/select` — choose which roadmap to follow (POST)
- `/roadmap/steps/<id>/toggle` — mark a step complete or undo it (POST)
- `/resources` — browse, search and filter learning resources
- `/resources/<id>/favourite` — save or remove a favourite (POST)
- `/resources/<id>/note` — save a private note and completed marker (POST)
- `/projects` — list your projects grouped by status
- `/projects/new` — add a project (POST)
- `/projects/<id>/edit` — update a project, including its status (POST)
- `/projects/<id>/delete` — delete one of your projects (POST)
- `/goals` — list your weekly and monthly goals
- `/goals/new` — add a goal with a target date (POST)
- `/goals/<id>/complete` — mark a goal complete (POST)
- `/goals/<id>/reopen` — reopen a completed goal (POST)
- `/goals/<id>/delete` — delete one of your own goals (POST)
- `/readiness` — the career readiness report
- `/assessment-history` — review previous attempts

## Phase 4 assessment catalogue

1. Python
2. C++
3. HTML and CSS
4. JavaScript
5. Basic Programming Concepts
6. Java
7. SQL
8. Web Development

Assessment answers are checked on the server. Correct answers are not sent to the quiz page before submission. Results and weak-topic summaries are saved per signed-in user.

## Phase 5 skill-gap scoring

Each required skill of the selected career is scored from the student's own skill list:

- **Acquired** = 100% of the skill's weight
- **Learning** = 50%
- **Not in the student's list** = 0%

Core skills count twice as much as supporting skills. The gap percentage is `earned points / possible points`, rounded to a whole number, and it is calculated in `routes/career.py` from database rows — never from values sent by the browser. A skill's latest matching assessment score and weak topics are displayed next to it as insight only.

## Visual design

The interface is a bright, colourful system built on the tokens in `static/css/style.css`. A final layer, `static/css/refresh.css`, is loaded last on every page and refines colours and surfaces without changing markup or layout: a light lavender canvas with soft pink, blue and amber glows, a violet-to-pink gradient hero heading, gradient buttons and progress bars, white cards with soft coloured shadows, and a different accent colour per skill card, roadmap step, sidebar icon and feature row.

Everything stays self-contained: the two fonts are served from `static/fonts`, there is no CSS framework, no icon package and no network request. Motion is limited to hover transitions and the landing progress bar, and the `prefers-reduced-motion` block in `style.css` turns all of it off.

## Phase 10 career readiness report

The report scores five parts of the student's own data with fixed weights that are displayed on the page: skill coverage against the chosen career (35%), roadmap completion (25%), the average of each assessment's latest score (20%), finished projects (10%, capped at three) and completed goals (10%).

`build_readiness()` in `routes/readiness.py` reads everything for the signed-in user only. The overall number is `(sum of score × weight + 50) // 100`, so it can always be recomputed from the rows shown beside it. Sections that have no data score zero and say so instead of being hidden, and the page ends with a plain statement that the score estimates preparation rather than predicting job outcomes.

## Phase 9 learning goals

Goals live in the `goals` table with a `goal_type` of `Weekly` or `Monthly`, a required `target_date` written `YYYY-MM-DD`, and the `is_completed` / `completed_at` pair. Completing a goal sets both columns; reopening clears `completed_at` again, so a goal never looks half-finished in the data.

Only the owner's rows are ever read or updated. A goal whose target date has passed while still open is shown with an Overdue badge, and the dashboard counts those separately.

The dashboard percentages are computed from real rows, never stored: `(completed * 100 + total // 2) // total` rounds .5 up, so 1 of 3 is 33% and 1 of 8 is 13%. When there are no goals the dashboard says so instead of showing 0%.

## Phase 8 project tracker

Projects are stored in the `projects` table, always filtered by `user_id`, so every list, edit and delete is scoped to the signed-in student. Status is limited to `Planned`, `In Progress` and `Completed`; the page groups projects by status with live counts.

Titles are required (120 characters), descriptions are limited to 1000 and technologies to 300, split on commas into tags on the card. Both links are optional, but a supplied link must be an `http://` or `https://` URL with a host, so `javascript:` URLs and bare `github.com/...` text are refused. Validation errors re-render the page with the submitted values instead of silently dropping them.

Older databases stored the status `Not Started` inside a CHECK constraint. Appendix: `migrate_projects_table()` in `utils/database.py` rebuilds the table once, converts those rows to `Planned`, copies every id and timestamp, adds the `live_url` column and recreates the user index; running it again does nothing.

## Phase 7 learning resources

Resources are predefined free links to real public sites: official documentation, free books and courses, practice sites, and free video tutorials on public YouTube channels and playlists. The URL is the stable key for seeding, so `ensure_resource_seed_data()` runs at startup and updates titles, descriptions and difficulty in place without creating duplicates or breaking a student's favourites.

Filtering happens in SQL: keyword search matches the title, description or category, and the category, resource-type (Documentation, Tutorial, Course, Book, Practice, Reference, Guide, Visualisation), difficulty and favourites filters can be combined. Type chips above the list show the real number of resources in each type. Favourites are rows in the existing `favourites` table scoped by `user_id`, so one student's saved list is never visible to another; removing a favourite deletes only that row and never the resource itself.

Each card also carries a private note (up to 500 characters) and a "Completed" tick, stored in `resource_notes` with one row per student per resource (`UNIQUE (user_id, resource_id)`). Saving an empty note with the tick cleared deletes the row, so clearing a note leaves nothing behind. Completing a resource for the first time is written to recent activity; re-saving an already completed note does not duplicate it. The table is created by `schema.sql`, so existing databases gain it on the next start without losing data.

## Phase 6 roadmap progress

Roadmaps and their ordered steps are predefined data seeded by `ensure_roadmap_seed_data()` at startup (idempotent; existing roadmaps and steps are updated in place, never deleted). A row in `user_roadmap_steps` means that student completed that step, so progress is always `completed steps ÷ total steps` — never a stored or fake percentage. Percentages round half up, so 1 of 8 steps shows 13%.

Only a step that belongs to the student's current roadmap can be toggled: the route checks `roadmap_steps.roadmap_id` against the student's own selection before writing anything. Steps are shared catalogue data, but completion rows are scoped by `user_id`, so one student's progress is never visible to another. Switching roadmaps keeps every completed step, so returning to a roadmap restores its progress.

Choosing a career on `/career` also selects the roadmap with the same title, and choosing a roadmap on `/roadmap` selects the matching career, so the two pages always agree. A Phase 5 account that only has a career saved falls back to the roadmap with the same title, so no one loses their roadmap by upgrading.

Career data is seeded once at application startup by `ensure_career_seed_data()` (idempotent, never deletes students' skills, career choices or assessment attempts). The selected career is stored in `user_profiles.selected_career_id`; `utils/database.py` adds that column to an existing database automatically, so no data is lost. The Phase 5 feature adds the supporting skills its careers need (Flask, REST APIs, Unit Testing, Linux, Excel, Statistics, Data Visualisation, NumPy & Pandas, Deep Learning, Networking, Security Basics) to the shared skill catalogue, so a student can add any of them to their own list.

## Career Studio: Certificate Vault

The first Career Studio tool stores a student's certificates, badges and course records. Open it from the sidebar (`Certificate Vault`) or at `/career-studio/certificates`.

- **What you can do:** upload a PDF, PNG or JPG certificate with its details (title, organisation, category, issue and expiry dates, credential ID, verification link, skills, description); search and filter by category; sort by upload date, issue date or expiry; preview the document, download it, edit its details and delete it together with the file.
- **What is stored where:** the details go in the new `certificates` table (one row per document, tied to `user_id`), and the file goes to `instance/career_studio/<user_id>/<random>.<ext>`. That folder is already excluded by `.gitignore`, is outside `static/`, and is only reachable through routes that check the signed-in owner, so documents have no guessable public URL.
- **Upload checks:** extension allow-list (PDF, PNG, JPG), a 16-byte signature check on the file contents, an empty-file check and an 8 MB limit. `MAX_CONTENT_LENGTH` is now 10 MB so the upload itself reaches those checks. Errors are shown next to the field that failed.
- **Honest labelling:** a stored certificate counts as *uploaded*, not independently verified. When a verification link is present the page says so and opens it in a new tab; SkillBridge never claims to have verified the certificate itself.
- **Expiry:** certificates expiring within 60 days, and expired ones, are counted on the dashboard and flagged on the card and detail page from the stored expiry date.
- **Activity:** uploads, edits and deletions are written to the existing `activities` feed with the `certificate` type.

## Career Studio: Resume Builder

`/career-studio/resumes` builds ATS-friendly resumes from the student's own information.

- **What you can do:** create several resumes; edit personal details, summary, objective, education, skill groups, projects, experience, certifications and extra sections; add, remove and reorder repeating rows; switch between four templates without losing anything; import real data from My Skills, the project tracker and the profile; select certificates stored in the vault; download a PDF or open a print view.
- **Templates:** Classic Professional, Modern Minimal, Technical Fresher and Corporate Professional. All four are single-column with standard headings, real text links and no tables, images or icons, so text extraction stays clean. Only the accent colour, name size and section order differ.
- **Certificate selection:** certificate titles, organisations, dates, credential IDs and verification links are copied from the vault when the student ticks them. The certificate file itself is never attached or embedded. Unticking removes the entry on the next save.
- **Live preview:** the right-hand pane is rendered by the server from the same form the save button posts to, so the preview, the PDF and the print view can never disagree. `static/js/resume_editor.js` refreshes it after a short pause and handles add/remove/reorder, with plain DOM APIs only.
- **Data model:** one row in `resumes` for the personal block and template, plus ordered rows in `resume_items` (`education`, `skill`, `project`, `experience`, `certification`, `section`). `source_id` remembers which project or certificate an imported item came from, while the copy itself stays independent.
- **Privacy:** every resume list, edit, preview, PDF, print, duplicate and delete query is scoped to `current_user.id`; another account gets 404. All POSTs (including preview fetch calls) need the CSRF token.

### Test the resume builder locally

```powershell
py -m unittest discover -s tests -p "test_phase11.py" -v
```

Then open **Career Studio → Resume Builder**, create a resume, add a row in each section, switch templates, import your skills or projects, tick a certificate from the vault, and download the PDF.

## Career Studio: Resume Analyzer

`/career-studio/analyzer` checks one resume against one job description. Everything runs inside SkillBridge with fixed rules — there is no AI service, no paid API and no data leaving the computer.

- **Two sources:** upload a PDF (limited to 5 MB, extension and file signature checked) or pick a resume saved in the builder. An uploaded document is written to the private Career Studio folder only long enough to extract its text, then deleted; only the results are stored.
- **Extraction:** PDFs are read with PyMuPDF, DOCX with python-docx. A scanned PDF with no text layer is reported as needing OCR instead of being scored from guesswork.
- **Scoring (100 points):** structure 25 (email, phone, summary, education, skills, projects/experience, profile link), skills match 25 (job skills that also appear), keyword coverage 20 (repeated meaningful words from the advert), job relevance 15 (those words inside projects/experience) and content quality 15 (length, bullets, action verbs, summary). Without a job description the keyword and relevance parts are skipped and the score is normalised over the remaining parts; the page says so.
- **Skill vocabulary:** a curated list of about 90 student/junior skills (languages, frameworks, databases, cloud, data, security, soft skills) with alias matching, so “Node.js” and “nodejs” count once.
- **Results page:** score ring, per-part bars, matched and missing skills, keyword columns, structure checklist, strengths, practical improvements and a checklist whose ticks are kept in the browser only.
- **Honesty:** the page states that the score is an estimate from these rules, not any employer's real applicant tracking system and not a hiring prediction. A missing skill is labelled as “not found in this document”, never as “you lack this skill”.
- **Privacy:** every analysis, result, history entry and delete is scoped to `current_user.id`; another account gets 404. History keeps the target role, the score and the source document name, never the document itself.

### Test the resume analyzer locally

```powershell
py -m unittest discover -s tests -p "test_phase12.py" -v
```

The tests build real PDFs and DOCX files, upload them through the app, and check extraction, scoring, matched/missing skills, keyword coverage, saved-resume analysis, rejections (wrong type, damaged file, scanned file, oversized file), owner-only results, deletion and CSRF.

### Test the vault locally

```powershell
py -m unittest discover -s tests -p "test_phase11.py" -v
```

Then log in, open **Certificate Vault**, upload a certificate and try the preview, download, edit and delete actions. Erase a record from another account and it returns 404, because every query is scoped to the signed-in user.

## Run automated tests

From the project root, with the virtual environment activated:

```powershell
py -m unittest discover -s tests -v
```

The tests use temporary SQLite databases and do not modify your normal application database.

## Notes

- Starter skills, questions and careers are seeded once during app creation. The seeders are idempotent, use a write lock while inserting, and do not delete existing users, skills, career choices, questions or assessment attempts.
- Upgrading from Phase 4 is safe: `init_db()` runs `migrate_db()`, which adds missing columns with `ALTER TABLE` instead of recreating a table. Back up `database/skillbridge.db` before any upgrade, as always.
- Keep a backup of your project and database before future development.
- For deployment, set a strong `SECRET_KEY`, use HTTPS, and turn off Flask debug mode.
