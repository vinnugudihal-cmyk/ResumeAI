# ResumeAI — Project Progress

Last updated: after the Job Discovery, Skill Passport, Application
Tracker and AI Career Assistant work.

**Status: all planned phases complete.** Nothing is stubbed, and no
button is wired to nothing.

---

## How to run

```powershell
# 1. AI service (required) — port 8000
cd "C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\ai-service"
python app.py

# 2. Frontend — port 5173
cd ..\frontend
npm run dev
```

Open **http://localhost:5173**. Keep the hostname `localhost`.
`127.0.0.1` is a different site to the browser, so the session
cookie is dropped and sign-in silently fails.

If a stale server holds the port:

```powershell
Stop-Process -Name node -Force
Stop-Process -Name python -Force
```

---

## Completed

| # | Phase | State |
|---|---|---|
| 1 | Versioned migrations with automatic backup | Complete |
| 2 | Career Profile | Complete |
| 3 | Career Mission with persistent progress | Complete |
| 4 | Job Discovery with honest fallback | Complete |
| 5 | Skill Passport and project evidence | Complete |
| 6 | Resume Studio: 12 templates, editor, PDF export | Complete |
| 7 | Application Tracker | Complete |
| 8 | AI Career Assistant | Complete |
| 9 | Unified dashboard and navigation | Complete |
| 10 | Testing, isolation and regression | Complete |

---

## Database

SQLite through Python's `sqlite3`, file at
`ai-service/resumeai.db`. Current version **5**.

| Version | Name | Adds |
|---|---|---|
| 1 | `baseline_resume_analysis` | `users`, `resumes`, `resume_analyses` |
| 2 | `career_profile` | `career_profiles`, `career_profile_items` |
| 3 | `career_mission` | `career_missions`, `mission_tasks`, `career_profiles.skills` |
| 4 | `resume_builder` | `saved_resumes` |
| 5 | `jobs_passport_tracker` | `saved_jobs`, `skill_evidence`, `applications`, `application_events` |

Migrations run automatically on start-up, on every start path
(`python app.py`, `flask run`, gunicorn). A consistent backup is
written to `ai-service/backups/` before any pending step, using
`VACUUM INTO` so committed WAL data is included.

Append only. Never edit or reuse a version number.

---

## The honesty rules this project follows

These are enforced in code and covered by tests, not just
documented:

1. **No invented jobs.** Without a configured provider, job search
   returns real search *links* and says so. Never a listing.
2. **No invented qualifications.** Career Profile, Skill Passport
   and the resume builder store only what the user typed.
3. **Listed is not demonstrated.** A skill the user merely declared
   is reported separately and earns half credit in Career Mission
   readiness.
4. **Nothing is auto-verified.** `skill_evidence.verified` is not
   editable through any API, because nothing here performs a real
   check.
5. **Suggestions are read-only.** Every AI suggestion returns to the
   browser. The user's records change only when they save.
6. **No ATS guarantees.** Templates are labelled by layout property.
   Nothing claims a template will "pass" a parser.
7. **Match scores are estimates**, calculated by a documented method
   from real data, and labelled as such.

---

## Test results

15 suites, **1040 assertions**, all passing:

```
test_skill_detection.py      93    test_migrations.py         19
test_database.py             43    test_account_isolation.py  40
test_auth.py                 55    test_career_profile.py     76
test_isolation.py            73    test_career_mission.py    137
test_roles.py                73    test_resume_builder.py    152
test_api_contract.py        117    test_career_platform.py   115
test_pdf_extraction.py       47    (+ 2 diagnostic suites)
```

Frontend: `npm run lint` clean, `npm run build` succeeds.

Every suite uses a throwaway database via `RESUMEAI_DB`, so running
tests never touches real data.

---

## Environment variables

All optional. Nothing is required to run the app.

| Variable | Effect if unset |
|---|---|
| `GEMINI_API_KEY` | Writing help falls back to reading your own text |
| `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` | Find Jobs shows external search links |
| `JOOBLE_API_KEY` | Same as above |
| `RESUMEAI_DB` | Uses `ai-service/resumeai.db` |
| `RESUMEAI_UPLOADS` | Uses `ai-service/backend/uploads` |
| `RESUMEAI_SECRET_KEY` | Generated into `ai-service/.secret_key` |

To enable live features, edit `ai-service/.env` and restart.

---

## Known limitations

1. **Gemini is not configured.** `.env` still holds the
   `PASTE_YOUR_API_KEY_HERE` placeholder. Every AI feature has a
   tested offline fallback, but the model-written path has not been
   exercised against a real key.
2. **No job provider is configured.** Find Jobs returns external
   search links by design. The Adzuna adapter is implemented and
   handles auth failures, rate limits and unreachable providers,
   but has never run against the live API.
3. **OCR misses "Power BI"** on one two-column template at 200/300/400
   DPI. This is a RapidOCR detector limit, not a bug in the code.
4. **`creative_split` splits the name** into separate spans. That is
   why it is marked non-ATS.

---

## If work continues

The natural next steps, in order:

1. Configure a Gemini key and exercise the model paths.
2. Configure a job provider and verify the live listing path.
3. Job-match scoring that combines a saved job with a saved resume
   in one view (the matcher exists per-feature; the cross-link
   between Find Jobs and Resume Studio is not built).
4. Cover letter generation from real profile and mission data.
