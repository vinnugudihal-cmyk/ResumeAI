# ResumeAI

AI-powered resume analyzer for students. Upload a resume PDF, get a
deterministic quality score, an ATS readability estimate, the technical
skills actually named in the document, and an honest gap analysis
against a target job role.

Every analysis is stored per user, so two people using the same browser
never see each other's resumes.

---

## Features

- **Career Mission** — pick a target role and ResumeAI builds an
  ordered, checkable plan from what is genuinely missing. Each skill
  task names a real exercise and the artefacts that prove the work.
  Essential requirements and preferred advantages are kept apart
  throughout. Tasks move through Not Started → In Progress →
  Completed, and progress is stored against your account.
  - Readiness is evidence-weighted: a skill you have only listed
    counts half of one the analyser found in your own work
  - Gaps are explained in words, each tied to something actually
    found in your profile or resumes
  - Rebuilding the plan keeps completed work, and drops tasks whose
    gap has since been closed
- **Find Jobs** — search by keyword, title, location, work mode and
  employment type. With a provider configured it returns live
  listings from that provider; with none it returns real search
  links on Naukri, LinkedIn, Indeed, Internshala, CutShort and
  Glassdoor, clearly labelled as links rather than listings. It
  never invents a job, employer, salary or application link.
- **Skill Passport** — record projects, repositories, demos,
  certificates and completed exercises, and the skills each one
  supports. Skills you have merely listed are shown separately from
  skills your recorded work actually demonstrates. Turns real work
  into editable resume bullet wording without inventing a number.
- **Application Tracker** — Interested, Preparing, Applied,
  Assessment, Interview, Offer, Rejected. Stores dates, private
  notes and next steps, logs every status change, and reports
  counts from the rows that exist rather than placeholders.
- **AI Career Assistant** — explain a pasted job description,
  practise interview questions, break a task into steps, scope a
  portfolio project, and get your next recommended action. Works
  without an API key; the offline path reads only your own records.
- **Resume template gallery** — 12 genuinely distinct designs across
  10 categories (ATS, modern/minimal, fresher, experienced, IT, data,
  business, creative, internship, career change), each with a real
  preview rendered from the same layout the exporter uses.
- **Guided resume editor** — personal details, summary, education,
  work experience, internships, projects, skills, certifications,
  achievements, languages, volunteering and custom sections. Add,
  edit, delete and reorder entries. Empty sections are never drawn.
- **Live preview** with desktop and mobile views that updates as you
  type, mirroring the exported PDF.
- **Customisation** — accent colour, professional font, spacing,
  section order, and showing or hiding optional sections. Switching
  template never touches your content.
- **Real PDF export** — selectable, searchable text drawn with
  PyMuPDF, which was already a dependency. No new package, and no
  rasterised images for a parser to choke on.
- **Save and manage** — multiple resumes, rename, duplicate, delete,
  reopen from the dashboard.
- **Writing assistance** — summary, bullets, skills and missing
  sections. Suggestions are read-only and are never written to your
  resume, and never invent a qualification or a number. Works with
  or without a Gemini key; the offline fallback reads only your own
  text and the role catalogue.
- **Career Profile** — one reusable place for contact details,
  education, projects, internships, volunteering, certifications and
  achievements. Nothing is ever filled in for you; a new account starts
  genuinely empty.
- **PDF resume upload** with validation (type, size, magic bytes, encryption)
- **Text and scanned PDF support** — text layers are read directly,
  scanned pages fall back to OCR
- **Genuine skill detection** — phone numbers, emails, names, usernames,
  URLs and addresses are rejected as skills; duplicates such as
  `Github.Com` / `GitHub` and `REST API` / `REST APIs` are normalised
- **Six-criteria scoring** out of 100, fully explainable
  - Structure & sections (20)
  - Technical skill breadth (20)
  - Projects & experience (20)
  - ATS keywords (20)
  - Formatting & readability (10)
  - Measurable achievements (10)
- **ATS readability estimate** shown as three weighted components with an
  explicit disclaimer — no promise of selection or interviews
- **Target role matching** (Software Developer, Web Developer, Data
  Analyst, Java Developer) with matched skills, missing skills, missing
  keywords and written reasons
- **Optional job description comparison** — matched and missing keywords
- **Analysis history** with per-user ownership enforced in SQL
- **Register / login / logout** with scrypt password hashing and
  HttpOnly session cookies
- **Optional Gemini suggestions** — the analysis works fully without it

---

## Architecture

```
frontend (React + Vite, :5173)
      |  fetch, credentials included
      v
ai-service (Flask, :8000)  <-- owns the SQLite database
      |  proxy (optional)
      v
backend (Express, :5000)
```

The frontend calls the Flask service directly and only falls back to the
Express proxy. **Express is optional** and adds no features — it exists
as a thin proxy. Both paths reach the same database, so there is exactly
one source of truth.

### Request flow

```
1. Browser picks a PDF
2. POST /analyze  (multipart: resume, job_description?, target_role?)
3. Flask saves the upload under a random UUID name
4. PDF magic bytes are verified
5. extractor.py -> pypdf -> PyMuPDF -> OCR (RapidOCR, Tesseract optional)
6. skills.py    -> genuine skills only, normalised and de-duplicated
7. scorer.py    -> six deterministic criteria
8. roles.py     -> optional target-role match
9. analyzer.py  -> Gemini suggestions (optional) + composite scores
10. database.py -> resumes + resume_analyses rows for the session user
11. JSON response -> dashboard
```

The session cookie identifies the user. **No user id is ever read from
the request body**, so a client cannot write into another account.

---

## Database

SQLite file: `ai-service/resumeai.db` (created automatically on start).

```
users
  id            INTEGER PRIMARY KEY
  name          TEXT
  email         TEXT UNIQUE          -- login identity, lowercased
  password_hash TEXT                 -- scrypt hash, NULL only for the
                                       local demo row, never plain text
  created_at    TEXT

resumes                         (1 user -> N resumes)
  id           INTEGER PRIMARY KEY
  user_id      INTEGER -> users.id  ON DELETE CASCADE
  filename     TEXT                 -- sanitised original name
  stored_path  TEXT                 -- random UUID on disk, never the
                                     client filename
  file_size    INTEGER
  mime_type    TEXT
  text_length  INTEGER
  text_excerpt TEXT                 -- first 20 000 chars
  uploaded_at  TEXT

career_profiles                 (1 user -> 1 profile)
  id                  INTEGER PRIMARY KEY
  user_id             INTEGER -> users.id  ON DELETE CASCADE, UNIQUE
  full_name, headline, email, phone, location
  preferred_locations, work_arrangement
  portfolio_url, linkedin_url, github_url
  summary, interests, preferred_roles
  willing_to_relocate INTEGER           -- 0/1, defaults to 0
  open_to_internship  INTEGER           -- 0/1, defaults to 0
  created_at, updated_at

career_profile_items             (1 user -> N entries)
  id           INTEGER PRIMARY KEY
  user_id      INTEGER -> users.id            ON DELETE CASCADE
  profile_id   INTEGER -> career_profiles.id  ON DELETE CASCADE
  item_type    TEXT     -- education | project | experience |
                         -- volunteering | certification | achievement
  title        TEXT     -- the only required field
  organisation, location, start_date, end_date, url, description
  is_current   INTEGER
  sort_order   INTEGER
  created_at, updated_at

career_missions                  (1 user -> N missions, one per role)
  id             INTEGER PRIMARY KEY
  user_id        INTEGER -> users.id  ON DELETE CASCADE
  role_key       TEXT     -- software_developer | web_developer |
                             -- data_analyst | java_developer
  role_title     TEXT
  job_title      TEXT     -- optional, typed by the user
  job_reference  TEXT     -- optional link to a real listing
  status         TEXT     -- active | completed
  readiness_json TEXT     -- the assessment made at build time
  created_at, updated_at
  UNIQUE(user_id, role_key)  -- never two of the same role

mission_tasks                   (1 mission -> N tasks)
  id           INTEGER PRIMARY KEY
  mission_id   INTEGER -> career_missions.id  ON DELETE CASCADE
  user_id      INTEGER -> users.id             ON DELETE CASCADE
  task_key     TEXT     -- stable key, so rebuilding the plan keeps
                          -- progress instead of resetting it
  title        TEXT
  detail       TEXT     -- the exercise and the proof to keep
  category     TEXT     -- profile | skill | evidence | resume |
                          -- applications
  skill        TEXT     -- the role skill this addresses
  importance   TEXT     -- essential | preferred
  status       TEXT     -- not_started | in_progress | completed
  sort_order   INTEGER
  completed_at TEXT
  created_at, updated_at

resume_analyses                 (1 resume -> N analyses)
  id                    INTEGER PRIMARY KEY
  resume_id             INTEGER -> resumes.id  ON DELETE CASCADE
  user_id               INTEGER -> users.id    ON DELETE CASCADE
  score                 INTEGER
  ats_score             INTEGER
  skills_json           TEXT
  matched_keywords_json TEXT
  missing_keywords_json TEXT
  suggestions_json      TEXT
  weaknesses_json       TEXT
  missing_sections_json TEXT
  criteria_json         TEXT
  breakdown_json        TEXT
  improvement_plan_json TEXT
  job_description      TEXT
  result_json           TEXT          -- full replayable analysis
  created_at            TEXT
```

Relationships: `users 1─N resumes 1─N resume_analyses`, plus
`users 1─1 career_profiles 1─N career_profile_items` and
`users 1─N career_missions 1─N mission_tasks`. Foreign keys are
enforced (`PRAGMA foreign_keys = ON`), so deleting a user cascades.

Every read and write filters on `user_id` taken from the session. No
endpoint accepts a user id from the client.

No secrets, API keys or passwords are ever written to the database.

### Migrations

Schema changes are numbered steps in `migrations.py`, recorded in
SQLite's own `PRAGMA user_version`. They run automatically at start-up.

```powershell
# Check which version is applied
python -c "import migrations; print(migrations.run(verbose=False))"
```

- Steps are **append only**. Editing a released step breaks databases
  that already ran it.
- A consistent backup is written to `ai-service/backups/` before the
  first pending step, using `VACUUM INTO` so committed WAL data is
  included. A plain file copy would silently miss rows.
- Migrations are idempotent: running twice applies nothing the second
  time.

| Version | Name | Adds |
|---|---|---|
| 1 | `baseline_resume_analysis` | `users`, `resumes`, `resume_analyses` |
| 2 | `career_profile` | `career_profiles`, `career_profile_items` |
| 3 | `career_mission` | `career_missions`, `mission_tasks`, `career_profiles.skills` |
| 4 | `resume_builder` | `saved_resumes` |
| 5 | `jobs_passport_tracker` | `saved_jobs`, `skill_evidence`, `applications`, `application_events` |
| 6 | `session_revocation` | `users.session_version` |

### The template library

`GET /resume-templates` serves **122 templates**: ten curated designs,
the twelve original hand-built layouts, and a hundred generated from a
declarative layout space.

The ten curated designs are the names people search for, each pinned to
a fixed specification, accent and typography: Premium Professional,
Minimal Elegant, Modern Corporate, Student & Fresher, Software
Developer, Creative Designer, Executive, Classic ATS, Academic &
Research, Contemporary Two-Column.

The rest come from a specification space of roughly 1.2 million
combinations (8 header styles x 7 section styles x 6 entry styles x 4
skill styles x 3 rails x 3 rail widths x 2 rail fills x 4 section
orders x 3 densities x 3 fonts). One renderer draws all of them, so
adding templates is publishing more of that space rather than writing
more code.

Filters are `category`, `columns`, `header`, `section_style`,
`experience`, `ats`, `q`, `sort`, `offset` and `limit`. The composed
`layout_label` is for display only: there are 95 of them, which is not
a menu anybody can use.

**ATS-friendly is derived, never declared.** A template is marked
ATS-friendly only when its structure has no side rail, and every
template in the catalogue is rendered and checked for extractable text
by `test_template_library.py`.

Migration 6 exists because Flask's session is a client-side signed
cookie. `session.clear()` only asks the browser to replace that cookie;
a copy taken beforehand stays valid until it expires. The version
stored in the cookie is compared against the account's current one on
every request, and logout increments it, so signing out genuinely
revokes every session issued before it.

`ALTER TABLE ... ADD COLUMN` is the one statement shape SQLite cannot
repeat, so the migration runner checks `PRAGMA table_info` first and
skips a column that is already present. That keeps a database whose
recorded version lags its actual schema (interrupted upgrade, partial
restore) from aborting on `duplicate column name`.

### Jobs, passport and tracker

```
saved_jobs                     (1 user -> N saved jobs)
  id           INTEGER PRIMARY KEY
  user_id      INTEGER -> users.id  ON DELETE CASCADE
  title, company, location, work_mode, employment, salary
  source       TEXT     -- 'api' or 'external_link'; where it really came from
  url, description, posted_on, search_query, notes
  created_at, updated_at

skill_evidence                  (1 user -> N pieces of evidence)
  id            INTEGER PRIMARY KEY
  user_id       INTEGER -> users.id  ON DELETE CASCADE
  kind          TEXT     -- project | repository | demonstration |
                             -- certificate | exercise | other
  title, description, url, organisation, started_on, completed_on
  skills_json   TEXT
  evidence_type TEXT     -- 'self_reported' or 'submitted'
  verified      INTEGER  -- always 0; not editable through any API
  sort_order, created_at, updated_at

applications                   (1 user -> N applications)
  id           INTEGER PRIMARY KEY
  user_id      INTEGER -> users.id  ON DELETE CASCADE
  saved_job_id INTEGER -> saved_jobs(id)        ON DELETE SET NULL
  resume_id    INTEGER -> saved_resumes(id)     ON DELETE SET NULL
  mission_id   INTEGER -> career_missions(id)   ON DELETE SET NULL
  job_title, company, location, work_mode, employment, salary, apply_url
  status       TEXT     -- interested | preparing | applied | assessment |
                         -- interview | offer | rejected
  applied_on, next_step, notes
  created_at, updated_at

application_events             (1 application -> N status changes)
  id             INTEGER PRIMARY KEY
  application_id INTEGER -> applications(id)  ON DELETE CASCADE
  user_id        INTEGER -> users(id)         ON DELETE CASCADE
  status, note, event_date, created_at
```

### Built resumes

`saved_resumes` is deliberately separate from `resumes`, which holds
uploaded PDFs for analysis. The analyser and its history are
completely untouched by the builder.

```
saved_resumes                  (1 user -> N resumes)
  id            INTEGER PRIMARY KEY
  user_id       INTEGER -> users.id  ON DELETE CASCADE
  title         TEXT     -- the name shown on the dashboard
  template_key  TEXT     -- which template is selected
  target_role   TEXT     -- optional, used for skill suggestions
  content_json  TEXT     -- the validated resume body
  settings_json TEXT     -- accent, font, spacing, order, hidden
  created_at, updated_at
```

To add one, append a `(version, name, [sql, ...])` tuple to
`MIGRATIONS`. Never use a lower or reused version number.

### ATS and template honesty

A template is marked `ats_friendly` when its layout uses standard
headings, a single reading order and selectable text. That is a
property of the layout, not a promise: ATS behaviour depends on the
employer's system, and nothing in ResumeAI claims a template will
"pass" anything. Creative templates say so in the gallery.

Exported PDFs contain real text. `test_resume_builder.py` asserts
that every template produces selectable text, keeps a sensible
reading order, and prints nothing twice or off the page edge.

---

## Requirements

- Python 3.10+ (developed on 3.14)
- Node.js 18+ (developed on 24)

### Python dependencies

```powershell
cd ai-service
pip install -r requirements.txt
```

Includes `PyMuPDF` and `rapidocr-onnxruntime`. RapidOCR ships its models
inside the wheel, so OCR needs **no separate installer and no admin
rights**. `pytesseract` is kept as an optional second engine and is used
automatically if a Tesseract binary is present.

The production WSGI server is deliberately separate, so development
does not install a serving stack it never uses:

```powershell
pip install -r requirements-prod.txt   # Waitress (Windows)
```

### Node dependencies

```powershell
cd backend  ; npm install
cd frontend ; npm install
```

---

## Running the application

Three terminals, or two if you skip the Express proxy.

```powershell
# 1. AI service — required
cd ai-service
python app.py                    # http://127.0.0.1:8000

# 2. Express proxy — optional
cd ..\backend
npm run dev                      # http://localhost:5000

# 3. Frontend
cd ..\frontend
npm run dev                      # http://localhost:5173
```

Open **http://localhost:5173**. You will be sent to the login page.
Create an account, upload a resume, and results appear on the dashboard.

> Use `localhost`, not `127.0.0.1`. The browser treats them as different
> sites, so a session cookie set on one is not sent to the other.

`python app.py` uses Flask's development server and prints its
"development server" warning. That is expected: the backend is running,
the `/health` endpoint answers `200`, and local work should keep using
this command.

### Production server (optional)

`wsgi.py` exposes the same Flask `app` to a real WSGI server. Nothing
in the application is duplicated or reconfigured; importing it still
runs the database bootstrap and every existing environment variable.

**Windows — Waitress:**

```powershell
cd ai-service
pip install -r requirements-prod.txt
python wsgi.py                        # 127.0.0.1:8000
python wsgi.py --host 0.0.0.0 --port 8000
```

**Linux / macOS — Gunicorn:**

```bash
pip install gunicorn
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app
```

`HOST` and `PORT` are used as defaults when the flags are omitted. This
does not by itself make the deployment production-ready: HTTPS, CORS and
the SQLite file still need real thought. See `RUNNING.md`.

### Environment variables

All optional. Put them in `ai-service/.env`.

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | no | Enables AI-written suggestions. Everything else works without it. |
| `ADZUNA_APP_ID` | no | Public half of the Adzuna credential. **Both halves are required** — setting only this one leaves Find Jobs on real search links, deliberately. |
| `ADZUNA_APP_KEY` | no | Secret half of the Adzuna credential. Get both from <https://developer.adzuna.com/>. |
| `JOOBLE_API_KEY` | no | Declared but **not implemented** — there is no request code for Jooble, so setting it changes nothing. Listed so the intent is recorded. |
| `RESUMEAI_SECRET_KEY` | no | Session signing key. A random one is generated into `ai-service/.secret_key`. |
| `RESUMEAI_DB` | no | SQLite path. Defaults to `ai-service/resumeai.db`. |
| `RESUMEAI_UPLOADS` | no | Where uploads are stored. |
| `RESUMEAI_HTTPS` | no | Set to `1` behind TLS so the session cookie is marked `Secure`. Leave unset on `http://localhost`. |
| `RESUMEAI_SESSION_HOURS` | no | Absolute session lifetime, default `12`. |
| `RESUMEAI_IDLE_MINUTES` | no | Idle timeout reported to the client, default `15`. |
| `HOST` | no | Bind interface for `python wsgi.py`, default `127.0.0.1`. |
| `PORT` | no | Bind port for `python wsgi.py`, default `8000`. |
| `RESUMEAI_OCR_DPI` | no | OCR render resolution, default `300`. |
| `RESUMEAI_MAX_OCR_PAGES` | no | OCR page cap, default `10`. |
| `AI_SERVICE_URL` | no | Express proxy target, default `http://127.0.0.1:8000`. |

---

## API

| Method | Route | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | no | Service and database readiness |
| GET | `/roles` | no | Target role catalogue |
| POST | `/auth/register` | no | Create account, starts a session |
| POST | `/auth/login` | no | Sign in |
| POST | `/auth/logout` | no | Clear session |
| GET | `/auth/me` | no | Current session user |
| GET | `/missions` | **yes** | Missions the signed-in user owns |
| POST | `/missions` | **yes** | Create or rebuild a mission for a role |
| POST | `/missions/preview` | **yes** | Build a plan without saving |
| GET | `/missions/<id>` | **yes** | One mission: tasks, progress, next action |
| DELETE | `/missions/<id>` | **yes** | Delete a mission and its tasks |
| PUT | `/missions/tasks/<id>` | **yes** | Set a task to not_started / in_progress / completed |
| GET | `/resume-templates` | no | Template catalogue, categories, fonts, accents |
| GET | `/ai-status` | no | Whether writing assistance is live |
| GET | `/my-resumes` | **yes** | Built resumes this user owns |
| POST | `/my-resumes` | **yes** | Create a resume (`start_empty` for a blank one) |
| GET | `/my-resumes/<id>` | **yes** | One resume: content, settings, completeness |
| PUT | `/my-resumes/<id>` | **yes** | Save edits, rename, or switch template |
| POST | `/my-resumes/<id>/duplicate` | **yes** | Copy a resume |
| DELETE | `/my-resumes/<id>` | **yes** | Delete a resume |
| GET | `/my-resumes/<id>/pdf` | **yes** | Export a selectable-text PDF |
| POST | `/my-resumes/<id>/suggest` | **yes** | Read-only writing suggestions |
| POST | `/jobs/search` | **yes** | Job search: live listings, or real search links |
| GET | `/jobs/meta` | **yes** | Filters, cities, configured providers |
| GET | `/saved-jobs` | **yes** | Saved jobs |
| POST | `/saved-jobs` | **yes** | Save a job found on a real site |
| PUT | `/saved-jobs/<id>` | **yes** | Update a saved job |
| DELETE | `/saved-jobs/<id>` | **yes** | Delete a saved job |
| GET | `/skill-passport` | **yes** | Evidence entries and the skill map |
| POST | `/skill-passport` | **yes** | Record evidence |
| PUT | `/skill-passport/<id>` | **yes** | Update evidence |
| DELETE | `/skill-passport/<id>` | **yes** | Delete evidence |
| POST | `/skill-passport/bullets` | **yes** | Bullet wording from recorded work |
| GET | `/applications` | **yes** | Applications, summary and statuses |
| POST | `/applications` | **yes** | Track an application |
| PUT | `/applications/<id>` | **yes** | Update status, dates or notes |
| DELETE | `/applications/<id>` | **yes** | Delete an application |
| GET | `/assistant/status` | no | Whether the assistant is live |
| POST | `/assistant/ask` | **yes** | Ask the assistant something |
| GET | `/career-profile` | **yes** | Whole profile: details, entries, counts, `is_empty` |
| PUT | `/career-profile` | **yes** | Create or update own details |
| POST | `/career-profile/items` | **yes** | Add an entry |
| PUT | `/career-profile/items/<id>` | **yes** | Update an owned entry |
| DELETE | `/career-profile/items/<id>` | **yes** | Delete an owned entry |
| POST | `/analyze` | **yes** | Upload PDF, optional `job_description` and `target_role` |
| GET | `/analyses` | **yes** | Stored analyses for the signed-in user |
| GET | `/analyses/<id>` | **yes** | One analysis, full result |
| DELETE | `/analyses/<id>` | **yes** | Delete an analysis |

The Express proxy exposes the same routes under `/api/*` and forwards the
session cookie.

`POST /analyze` accepts:

- `resume` — PDF, 5 MB maximum, magic bytes verified
- `job_description` — optional, 20 000 characters
- `target_role` — optional role key

and returns `score`, `ats_score`, `ats_breakdown`, `skills`,
`criteria`, `matched_keywords`, `missing_keywords`, `role_match`,
`suggestions`, `weaknesses`, `missing_sections`, `improvement_plan`,
`breakdown` and `analysis_id`.

Failures use real status codes: `400` invalid input, `401` not signed in,
`404` not found or not yours, `413` too large, `422` unreadable PDF. The
`422` body includes an `extraction.reason` such as `encrypted`,
`damaged`, `no_text` or `ocr_unavailable`, with a specific message.

---

## Scoring

Total score is the sum of six transparent criteria. Every criterion
returns its score, max, feedback, what was detected, what was missing,
each deduction with its points, and concrete actions.

Skill breadth uses a **saturating curve** rather than a threshold, so
eight skills is strong but not flawless. This stops a thin resume from
looking perfect.

The ATS estimate is a weighted sum of keyword coverage (40%), skill
breadth (30%) and formatting (30%). The three components are returned
with their weights and points so the number can be checked, and the API
returns a disclaimer: it is an estimate of machine readability and cannot
predict whether an employer will shortlist anyone.

---

## Tests

```powershell
cd ai-service
python test_skill_detection.py     # skills, formats, personal data
python test_database.py            # schema, CRUD, cascades
python test_auth.py                # hashing, sessions, protection
python test_isolation.py           # cross-account ownership
python test_api_contract.py        # response shape, errors, uploads
python test_roles.py               # role matching, score honesty
python test_pdf_extraction.py      # text PDFs, scanned PDFs, OCR
python test_template_library.py   # ids, render, page breaks, layout quality
python test_diagnostic.py          # end-to-end scoring on a real PDF
python test_jd_passthrough.py      # job description plumbing
python test_career_profile.py      # profile CRUD, validation, isolation
python test_career_mission.py      # plan generation, progress, isolation
python test_resume_builder.py      # templates, validation, isolation, PDF
python test_career_platform.py     # jobs, passport, tracker, assistant
python test_migrations.py          # migration safety and data preservation
python test_account_isolation.py   # profile + history isolation, two accounts
python test_logout_flow.py         # logout revokes, replay refused, data kept
```

Every suite that touches data sets `RESUMEAI_DB` to a throwaway file
before importing the app, so running the tests cannot modify the real
database.

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```

All suites run against a temporary database and never touch real data.

---

## Technologies

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 19, Vite | Component UI, fast dev server, production build |
| Styling | Plain CSS | Matches the existing design tokens; no extra dependency |
| API | Flask | Small, clear request handling for file uploads |
| Proxy | Express + Multer | Optional upload proxy with cookie relay |
| Database | SQLite | Zero setup, single file, real relational constraints |
| PDF text | pypdf, PyMuPDF | Two independent text-layer readers |
| OCR | RapidOCR (ONNX) | Bundled models, no system install |
| Hashing | Werkzeug scrypt | Salted, memory-hard, no extra dependency |
| Sessions | Flask signed cookie | HttpOnly, SameSite=Lax, server-side identity |
| AI | Google Gemini | Optional natural-language suggestions |

---

## Security notes

- Passwords are scrypt-hashed with a per-user salt. Plain text is never
  stored or logged.
- Session cookies are `HttpOnly` and `SameSite=Lax`.
- Uploads are verified by PDF magic bytes, size-capped, and stored under
  random UUID filenames. The client filename is never used to build a
  path.
- Ownership is enforced in SQL on every analysis query.
- The Gemini key is read from the environment and never sent to the
  browser.
