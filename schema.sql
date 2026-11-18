-- =====================================================================
-- schema.sql - the structure of the SkillBridge database.
--
-- Every statement says "IF NOT EXISTS", so running this file again when the
-- app restarts is safe: existing tables and the data inside them are left
-- untouched. New tables can be added later in the same way.
--
-- Each person's private rows carry a user_id that points to the users table
-- (a "foreign key"). ON DELETE CASCADE means that deleting a user also deletes
-- that user's rows in the other tables.
-- =====================================================================

-- 1. users: one row per registered account
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,          -- stored in lower case
    password_hash TEXT    NOT NULL,                 -- never the real password
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Career paths and their learning steps (predefined data, shared by everyone)
-- 8. roadmaps
CREATE TABLE IF NOT EXISTS roadmaps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL UNIQUE,               -- e.g. Python Developer
    description TEXT NOT NULL DEFAULT ''
);

-- 9. roadmap_steps
CREATE TABLE IF NOT EXISTS roadmap_steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    roadmap_id  INTEGER NOT NULL REFERENCES roadmaps(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    UNIQUE (roadmap_id, step_number)
);

-- 2. user_profiles: extra details, exactly one row per user
CREATE TABLE IF NOT EXISTS user_profiles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    college_name        TEXT NOT NULL DEFAULT '',
    education_details   TEXT NOT NULL DEFAULT '',
    year_of_study       TEXT NOT NULL DEFAULT '',
    career_interests    TEXT NOT NULL DEFAULT '',
    preferred_fields    TEXT NOT NULL DEFAULT '',
    selected_roadmap_id INTEGER REFERENCES roadmaps(id) ON DELETE SET NULL,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. skills: the master list of skills (predefined data)
CREATE TABLE IF NOT EXISTS skills (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL
);

-- 4. user_skills: which skills a user has, and how far along they are
CREATE TABLE IF NOT EXISTS user_skills (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    status   TEXT NOT NULL DEFAULT 'Learning' CHECK (status IN ('Learning', 'Acquired')),
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, skill_id)
);

-- 5. assessments: the quizzes (Python, C++, ...)
CREATE TABLE IF NOT EXISTS assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);

-- 6. assessment_questions: multiple-choice questions for each quiz
CREATE TABLE IF NOT EXISTS assessment_questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    topic         TEXT NOT NULL DEFAULT 'General',
    question_text TEXT NOT NULL,
    option_a      TEXT NOT NULL,
    option_b      TEXT NOT NULL,
    option_c      TEXT NOT NULL,
    option_d      TEXT NOT NULL,
    correct_option TEXT NOT NULL CHECK (correct_option IN ('A', 'B', 'C', 'D')),
    explanation   TEXT NOT NULL DEFAULT ''
);

-- 7. assessment_results: one row each time a user completes a quiz
CREATE TABLE IF NOT EXISTS assessment_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id)       ON DELETE CASCADE,
    assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    score           INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    percentage      REAL    NOT NULL,
    weak_topics     TEXT    NOT NULL DEFAULT '',     -- topics answered wrongly
    answers_json    TEXT    NOT NULL DEFAULT '{}',   -- the answers the user chose
    taken_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 10. resources: learning links (predefined data)
CREATE TABLE IF NOT EXISTS resources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    category      TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    resource_type TEXT NOT NULL DEFAULT 'Documentation'
);

-- 11. favourites: the resources a user has saved
CREATE TABLE IF NOT EXISTS favourites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
    resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, resource_id)
);

-- Student-written notes and completed markers for learning resources (Phase 7).
-- One row per student per resource; deleting the student or the resource removes it.
CREATE TABLE IF NOT EXISTS resource_notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
    resource_id  INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    note         TEXT    NOT NULL DEFAULT '',
    is_completed INTEGER NOT NULL DEFAULT 0,          -- 0 = not yet, 1 = completed
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, resource_id)
);

-- 12. projects: a user's personal projects (Phase 8)
-- Older databases used the status 'Not Started'. migrate_db() rebuilds this
-- table once to move those rows to 'Planned' and add live_url.
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    technologies TEXT NOT NULL DEFAULT '',          -- comma-separated, shown as tags
    github_url   TEXT NOT NULL DEFAULT '',
    live_url     TEXT NOT NULL DEFAULT '',          -- deployed/demo link
    status       TEXT NOT NULL DEFAULT 'Planned'
                 CHECK (status IN ('Planned', 'In Progress', 'Completed')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 13. goals: weekly and monthly learning goals
CREATE TABLE IF NOT EXISTS goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    goal_type    TEXT NOT NULL CHECK (goal_type IN ('Weekly', 'Monthly')),
    target_date  TEXT NOT NULL,                      -- written as YYYY-MM-DD
    is_completed INTEGER NOT NULL DEFAULT 0 CHECK (is_completed IN (0, 1)),
    completed_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 14. activities: the "recent activity" feed on the dashboard
CREATE TABLE IF NOT EXISTS activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,
    description   TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 15. careers: the career paths a student can aim for (predefined data)
-- The table a user picks is remembered in user_profiles.selected_career_id.
-- That column is created by migrate_db() in utils/database.py, so databases
-- made before Phase 5 gain it without losing any existing rows.
CREATE TABLE IF NOT EXISTS careers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL UNIQUE,               -- e.g. Python Developer
    description TEXT NOT NULL DEFAULT ''
);

-- 16. career_skills: which skills each career asks for
-- is_core = 1 means the skill is central to that career, so it counts twice
-- when the skill gap is calculated. is_core = 0 is a supporting skill.
CREATE TABLE IF NOT EXISTS career_skills (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    career_id INTEGER NOT NULL REFERENCES careers(id) ON DELETE CASCADE,
    skill_id  INTEGER NOT NULL REFERENCES skills(id)  ON DELETE CASCADE,
    is_core   INTEGER NOT NULL DEFAULT 0 CHECK (is_core IN (0, 1)),
    UNIQUE (career_id, skill_id)
);

-- 17. user_roadmap_steps: which roadmap steps a student has completed
-- (Phase 6). A row exists only for a completed step, so deleting the row
-- marks the step as pending again. Progress is private to each user.
CREATE TABLE IF NOT EXISTS user_roadmap_steps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
    step_id      INTEGER NOT NULL REFERENCES roadmap_steps(id) ON DELETE CASCADE,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, step_id)
);

-- Indexes make "show me this user's rows" lookups fast
CREATE INDEX IF NOT EXISTS idx_user_skills_user         ON user_skills(user_id);
CREATE INDEX IF NOT EXISTS idx_assessment_results_user  ON assessment_results(user_id);
CREATE INDEX IF NOT EXISTS idx_assessment_questions_set ON assessment_questions(assessment_id);
CREATE INDEX IF NOT EXISTS idx_favourites_user          ON favourites(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_user            ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user               ON goals(user_id);
CREATE INDEX IF NOT EXISTS idx_activities_user          ON activities(user_id);
CREATE INDEX IF NOT EXISTS idx_career_skills_career     ON career_skills(career_id);
CREATE INDEX IF NOT EXISTS idx_user_roadmap_steps_user  ON user_roadmap_steps(user_id);

-- =====================================================================
-- Career Studio and Student Progress Reports (added together as one
-- additive step). Every table carries user_id and is only ever queried
-- with the signed-in student's id. Nothing above this line was changed.
-- =====================================================================

-- 18. certificates: metadata for files in the private vault folder.
CREATE TABLE IF NOT EXISTS certificates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    organization      TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT 'Other',
    issue_date        TEXT NOT NULL DEFAULT '',
    expiry_date       TEXT NOT NULL DEFAULT '',
    credential_id     TEXT NOT NULL DEFAULT '',
    credential_url    TEXT NOT NULL DEFAULT '',
    skills            TEXT NOT NULL DEFAULT '',
    description       TEXT NOT NULL DEFAULT '',
    stored_filename   TEXT NOT NULL,
    original_filename TEXT NOT NULL DEFAULT '',
    mime_type         TEXT NOT NULL DEFAULT '',
    file_size         INTEGER NOT NULL DEFAULT 0,
    uploaded_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_certificates_user ON certificates(user_id);

-- 19. resumes: one row per saved resume. Personal details live here so a
-- student can keep a different version for each role.
CREATE TABLE IF NOT EXISTS resumes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT 'My resume',
    template   TEXT NOT NULL DEFAULT 'classic',
    full_name  TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',
    location   TEXT NOT NULL DEFAULT '',
    linkedin   TEXT NOT NULL DEFAULT '',
    github     TEXT NOT NULL DEFAULT '',
    portfolio  TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    objective  TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 20. resume_items: each repeating block of a resume as one ordered row.
-- kind separates education, skills, projects, experience, certifications and
-- free-form extra sections, so only two tables are needed for the builder.
CREATE TABLE IF NOT EXISTS resume_items (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL CHECK (kind IN (
                  'education', 'skill', 'project', 'experience',
                  'certification', 'section')),
    position  INTEGER NOT NULL DEFAULT 0,
    title     TEXT NOT NULL DEFAULT '',
    subtitle  TEXT NOT NULL DEFAULT '',
    meta      TEXT NOT NULL DEFAULT '',
    detail    TEXT NOT NULL DEFAULT '',
    link      TEXT NOT NULL DEFAULT '',
    link2     TEXT NOT NULL DEFAULT '',
    extra     TEXT NOT NULL DEFAULT '',
    source_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_resumes_user        ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_resume_items_resume ON resume_items(resume_id);

-- 21. resume_analyses: one row per analysis. The job details and the results
-- are stored so the history shows what the resume looked like that day.
-- Uploaded files are NOT kept: only the extracted text statistics.
CREATE TABLE IF NOT EXISTS resume_analyses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id        INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
    source_name      TEXT NOT NULL DEFAULT '',
    job_title        TEXT NOT NULL DEFAULT '',
    company          TEXT NOT NULL DEFAULT '',
    industry         TEXT NOT NULL DEFAULT '',
    experience_level TEXT NOT NULL DEFAULT '',
    overall_score    INTEGER NOT NULL DEFAULT 0,
    scores_json      TEXT NOT NULL DEFAULT '{}',
    matched_json     TEXT NOT NULL DEFAULT '[]',
    missing_json     TEXT NOT NULL DEFAULT '[]',
    keywords_json    TEXT NOT NULL DEFAULT '[]',
    strengths_json   TEXT NOT NULL DEFAULT '[]',
    improvements_json TEXT NOT NULL DEFAULT '[]',
    sections_json    TEXT NOT NULL DEFAULT '{}',
    word_count       INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_analyses_user ON resume_analyses(user_id);
