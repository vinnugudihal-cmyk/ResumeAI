# Redesign audit — what already existed vs. what was requested

Baseline recorded before edits, and re-checked after every test run:

- Production DB: `ai-service/resumeai.db`
  SHA-256 `2DFE524F27525A5C63E3062DC30DC9D2F505AAA9928E994EF2E85FC90164B989`
  size 942080, mtime 2026-10-20 01:30:04
  **Unchanged after all edits and all 35 backend suites.**

| Requirement | State before edits | State now |
| --- | --- | --- |
| 10 dashboard cards, fixed order | DONE — `features.js` `DASHBOARD_CARDS` | DONE (unchanged) |
| Two large hero cards side-by-side | DONE — `Landing.jsx` `.land-hero-row` | DONE (unchanged) |
| 8 compact cards in a 3-column grid | DONE — `.land-grid` | DONE (unchanged) |
| Shared card hover left accent | DONE — `cardHover.css` | DONE (unchanged) |
| Login: no "Back to Home" | NOT DONE — link present | **DONE** — link removed |
| Login: separate account box + Create Account | PARTIAL | **DONE** — `.login-account-box` under the card |
| Login: password show/hide, accessible | DONE | DONE — added `.eye-icon` sizing + focus ring |
| Cover letter: Back to Dashboard (dark blue) | NOT DONE — subdued link | **DONE** — dark-blue pill button |
| Education heading + "+ Add" in one box | NOT DONE | **DONE** — `.ed-head-box` |
| Education: category list with per-category Add | NOT DONE — hidden radio pills | **DONE** — `.ed-categories` list |
| Education: entries per category | DONE (7 kinds) | DONE (unchanged) |
| Auto percentage from marks | NOT DONE | **DONE** — `percentageFromMarks`, non-destructive |
| CGPA kept separate (no silent conversion) | DONE | DONE (unchanged, documented) |
| My Details persistence + isolation | DONE — `career_profiles` per user | DONE (unchanged) |
| Create My Resume → gallery → builder | DONE (details-first then gallery) | DONE (unchanged) |
| Template gallery real templates | DONE | DONE (unchanged) |
| Save resume / PDF / separate doc | DONE | DONE (unchanged) |
| Analyze resume real analysis | DONE | DONE (unchanged) |

## Verification performed

- Backend: all 35 suites pass, 0 failures (education suites 74 + 66 + 26 checks).
- Frontend: `npm run lint` clean; `npm run build` succeeds;
  `npm run verify:routes` → ALL ROUTE CHECKS PASSED (10 features, 20 routes).
- Production DB byte-identical after every run (hash above).

## Browser verification (done)

Ran against the throwaway sandbox (`run_isolated.py`, temp DB, port 8001)
with the app on the Vite dev server, in a real browser. Production DB was
byte-identical before and after (hash above).

Confirmed live:

- Login: no "Back to Home" link; separate `.login-account-box` under the
  card with "Don't have an account?" + a "Create Account" button that
  switches the page to its register view; password show/hide toggles the
  input between `password` and `text` and updates its aria-label.
- Dashboard: 2 hero cards (Create My Resume, Analyze My Resume) + the 8
  compact cards in the exact required order; 3-column grid at desktop
  width (CSS), 2-up hero (CSS).
- Education: heading + "+ Add" in one box; "+ Add" reveals the category
  list (SSLC/10th, PUC/12th or Diploma, Bachelor's, Master's, PhD, Other)
  with per-category Add; adding opens the right per-kind form; marks
  auto-fill the percentage (540/600 -> 90); a typed percentage is not
  overwritten; a "calculated from marks" note appears; 700/600 is refused
  on save; an entry saves and survives a full reload.
- Cover Letter: "Back to Dashboard" renders as a dark-blue pill
  (`rgb(49,85,217)`, white text, 999px radius) linking to /dashboard.
- Create My Resume: gallery loads real templates (24 shown, 124 total),
  "Select Template" creates a real resume and opens the builder; Save
  persists it; Download PDF returns `application/pdf` 200.
- Analyze My Resume: a real PDF produced "OVERALL RESUME SCORE 91/100";
  result saved to history; honest copy; no demo path.
- Isolation: a second fresh account saw 0 resumes, 0 analyses and 0
  education entries while the first account's data stayed intact.
- No console errors during the whole session.

---

# Session 2 — Career Gap-to-Action engine + follow-up verification

## What was added

| Feature | Where |
| --- | --- |
| Evidence-based job match engine (extract → match → actions → persist) | `ai-service/job_match.py` |
| Job-match DB tables (additive migration 12) | `ai-service/migrations.py` |
| Flask routes `/job-match`, `/job-matches`, `/job-matches/<id>`, `/job-match-actions/<id>`, `/dashboard-summary` | `ai-service/app.py` |
| Job Match page (report, essential/preferred split, action tracking, history, score caveat) | `frontend/src/pages/JobMatch.jsx` + `.css` |
| Career snapshot on the dashboard (real latest score, match, gap, plan, jobs, applications) | `frontend/src/components/CareerSnapshot.jsx` + `.css` |
| Sidebar + dashboard links to Job Match / Career Mission; legacy JD matcher now routes to `/job-match` | `Dashboard.jsx`, `App.jsx` |
| Saved-job form now has an optional job-description field so saved jobs can be matched without re-pasting | `FindJobs.jsx` |
| `/interview-practice` route restored (honest "question generation unavailable" banner) | `App.jsx` |
| `compareAnalyses` enriched with improved/declined criteria, remaining gaps, added/removed skills | `services/api.js` |

## Bugs found and fixed during testing

1. **All-caps short skill lines were swallowed as section headings.** A bare
   `SQL` line inside an *Essential* block was read as a heading and dropped,
   so SQL fell back to `unspecified`. Fixed by treating any line that names a
   known skill as a requirement, not a heading.
2. **Three-character skills were dropped by the `<4` noise filter.** `SQL`,
   `Git`, `AWS`, `CSS`, `R` disappeared. The filter now keeps a short line
   when it contains a recognised skill.
3. **Ambiguous skills were invisible in job adverts.** A bare `React` (the
   verb vs. the library) was rejected by the resume-strict rule. Added
   `find_skills(text, allow_ambiguous=True)`; resumes still use the strict
   default, job descriptions can read a bare `React` as the skill.
4. **Action "why" text repeated the bare skill** ("…marked essential. Docker").
   It now explains the evidence state, quotes the advert only when the line
   says more than the skill, and never says the student lacks the skill.
5. **Match history was unreachable after a reload.** It rendered *inside* the
   active-match branch, so with no active match the saved matches could not be
   opened. Moved outside the branch so history always renders.
6. **Low-contrast small text** in the new snapshot and job-match CSS
   (`#98a2b3`, ratio 2.57) darkened to `#5b6472`.
7. **The application History panel always read "History (0)" after a
   reload.** Status changes *were* being written to `application_events`, and
   the update response returned them, but the list endpoint the tracker reloads
   from (`GET /applications`) did not. `tracker.list_all` now loads the
   timeline for every application in one owner-scoped query, so history
   survives a reload and cannot expose another account's events.

## Score transparency added

- Amber caveat on `/job-match` when essential/preferred requirement lines did
  **not** name a skill the analyser recognises, linking to "Requirements to
  read yourself". The estimate only covers recognised skills; the caveat stops
  a 100/100 from reading as "fully job-ready".
- "No evidence found" is labelled as missing *evidence*, never a missing skill.

## Verification performed

- Backend `test_job_match.py`: **87/87 pass** (added 7 regression checks for
  bugs 1–4). `test_skill_detection.py`: 93/93. `test_api_contract.py`: 117/117.
- Full backend suite re-run at the end of the session: **36 suites, all
  exited 0, 0 failed** (`SUITES=36 FAILED=0`). Suite totals include
  `test_api_contract` 117, `test_auth` 55,
  `test_auth_privacy` 56, `test_career_mission` 137, `test_career_profile` 78,
  `test_cover_letters` 108, `test_education_entries` 74, `test_feature_integration`
  133, `test_job_match` 87, `test_pdf_extraction` 47, `test_pdf_layout_quality`
  12, `test_pdf_layout_regressions` 48, `test_preview_parity` 345,
  `test_resume_builder` 192, `test_roles` 73, `test_skill_detection` 93,
  `test_template_library` 149, `test_template_thumbnails` 29.
  (`test_career_platform` recorded 167 in that run because it preceded the two
  new regression checks below.)
- `test_career_platform.py` raised to **169/169** with two new regression
  checks that the application list endpoint keeps the real status timeline
  across a reload (see bug 7).
- Frontend `npm run verify`: lint clean, route checks pass (10 features,
  22 routes incl. `/job-match` and `/interview-practice`), Vite build succeeds
  (only the known >500 kB chunk warning).
- Lighthouse on the dashboard: accessibility 0.96, best-practices 1.0, no
  console errors, no horizontal overflow at 800px. The two contrast failures
  that came from `CareerSnapshot` were fixed; remaining contrast notes are
  pre-existing dashboard/sidebar styles outside this work.
- Responsive review: `JobMatch.css` (900px / 560px breakpoints) and
  `CareerSnapshot.css` (1100px / 760px breakpoints) collapse the multi-column
  grids to one column; verified no overflow.

## End-to-end browser evidence (sandbox, real behaviour)

- Real PDF uploaded and analysed: 65/100, estimated ATS 66, 12 skills.
- Saved a job with a real pasted description; "Match my skills" prefilled
  `/job-match` including the description.
- Job match with a **demonstrated** skill (Python/SQL/Power BI/React/Git), a
  **reported-only** skill (Docker), and a **not-found** skill (Kubernetes):
  score 67/100 "Partial alignment", 2/4 essential demonstrated, 1 reported,
  1 no-evidence.
- Action status set to *In progress*, persisted across a **re-match** and
  across a **full reload** (loaded back from history, status intact).
- Dashboard snapshot showed the same real values: latest score 65, latest
  match 67, top open gap "Add evidence for Docker", plan 0 of 2 (1 in progress),
  1 saved job, "1 of 1 active · 1 interview · 0 offers".
- Application created from the saved job, status moved `applied → interview`,
  persisted across reload, and the dashboard updated to "1 interview · 0 offers".
- The application History panel now shows the real timeline after a reload:
  `History (2)` with "Applied — Created" and "Interview — Status changed"
  (bug 7 fixed; verified in the browser against the sandbox).
- `/interview-practice` loads and honestly states no AI key is configured.

## Production database — honest status

- `ai-service/resumeai.db` was **never opened by the app during this session**.
  All tests and browser checks ran against throwaway databases (`db_guard`
  temp files and `run_isolated.py`'s temp sandbox).
- Current state, read-only: size 942080, mtime `2026-10-21 00:54:34`,
  SHA-256 `16A55D26E1B7BC5813488ACFDF4BC577E3AFA86A589CC9D3FBB9485669945B05`,
  `PRAGMA user_version = 11`, and it does **not** contain the
  `job_matches` / `job_match_actions` tables.
- This hash differs from the original audit baseline
  (`2DFE524F…`, mtime `2026-10-20 01:30:04`). The difference predates this
  session: the file's mtime is older than any work here, and it was only ever
  read. Migration 12 has **not** been applied to the production database, so
  the user's real data is untouched and no schema change has shipped to it.
  When the app is next started against the real database, the startup guard
  will back it up and apply migration 12 deliberately (that is by design).

## Remaining limitations / manual configuration

- Interview question generation needs an AI key; without it the page says so
  and only manual practice is available.
- Existing saved jobs created before this change have no description; they can
  still be matched by pasting the description on `/job-match`.
- Application status changes persist, and the per-application status timeline
  now reloads with the list (bug 7 fixed and covered by a regression test).
- Lighthouse notes a few low-contrast muted texts in pre-existing dashboard
  components, outside the scope of this work.

---

# Session 3 — final brief pass

This pass closed the remaining gaps between the built app and the last brief.
Nothing was rebuilt; every change extends what was already there.

## 1. Education shows classifications, never numbers

- Migration **13 `education_classification`** adds `classification TEXT` to
  `career_profile_education`. It is additive and nullable, so every existing
  entry keeps working and simply omits the line until the student picks one.
  The startup guard backed the sandbox database up and applied it deliberately
  (`resumeai-pre-migration-20261021-160536.db`).
- `profile_education.CLASSIFICATIONS` = Distinction / First Class / Second
  Class / Pass. The value is **chosen, never calculated**: the percentage that
  earns a class differs by board and university, so deriving it would invent a
  rule the institution never applied. Input is normalised (`first class` →
  `First Class`); anything outside the four is refused with a 400.
- The classification dropdown is rendered from the server's own field spec
  (`rules.choices`), so the form cannot drift from the backend. Verified in the
  browser: `Not stated / Distinction / First Class / Second Class / Pass`
  inside the Bachelor's add form.
- `resume_pdf.education_grade` and `profile_education.grade_summary` now return
  the classification **only**. Percentage, marks-out-of-maximum and CGPA stay
  in the private profile but are no longer printed on a generated document.
- A qualification still **Pursuing** prints "Pursuing" and no class, because no
  result has been awarded yet. Covered by a new check.
- The resume builder's Education section gained a Classification dropdown, and
  `resume_builder.EDUCATION_FIELDS` carries the field so it survives
  profile → resume.
- End-to-end proof on the live sandbox: set the degree's classification to
  *First Class* (CGPA 8.7 still stored), created a resume from the profile,
  downloaded the PDF and extracted its text —
  `… Bangalore University Computer Science · First Class`, with `%` absent and
  `8.7` absent.

## 2. Login page is sign-in only — superseded in Session 5

- Removed the "Don't have an account? Create Account" panel and the in-form
  "New to ResumeAI?" switch, plus their CSS. The page is email, password and
  Sign In.
- **Superseded in Session 5:** the client asked for the in-form prompt back.
  See the Session 5 section at the end; this entry is kept as written rather
  than rewritten.
- Registration is still reachable: the Home page's "No account yet? Create
  one" opens `/login` with `mode: "register"`, and the register view keeps an
  "Already have an account? Sign in" switch so nobody is trapped on it.
- Browser check: `.login-account-box` absent, no "Don't have an account" text,
  email + password + Sign In present, login still lands on `/dashboard`.

## 3. "Back to dashboard" is a text link

- `.ar-back` is now an inline-flex blue link (`rgb(49, 85, 217)`, weight 600)
  with a `←`, at the top of **and** after the analysis, replacing the ghost
  pill. Measured in the browser.

## 4. Card hover

- **Corrected in Session 4.** Removing the accent from the two hero cards first
  was only half the job: the brief asks for the blue vertical line gone
  *everywhere*. The shared stylesheet `src/cardHover.css` was then rewritten so
  the `::before` strip is deleted outright from **all twelve** card classes it
  covers (dashboard hero and grid cards, both galleries, the builder's design
  picker, saved resumes, saved jobs, job results, applications, cover letters
  and the saved qualification cards on My Details). Nothing is left to hover -
  the pseudo-element does not exist, rather than being hidden or made
  transparent.
- What replaced it is the same smooth motion on every card: a `-5px` lift
  (`--card-hover-lift`, 1.01 scale on roomy cards), a soft light-blue border
  (`rgb(199, 210, 254)`), a layered shadow with a faint inset glass highlight,
  over ~0.24s, with `prefers-reduced-motion` and `hover: none` handled.
- Browser proof in Session 4: a full-DOM scan of the dashboard and of the
  resume-template gallery found **zero** elements with a `::before` that has
  content. A real `.land-hero-card` under the cursor measured `border-left:
  0.8px` (its uniform border, not a 4px accent), the layered shadow above, and
  `::before`/`::after` content `none`.

## 5. Naming

- `/job-match` now presents as **Career Readiness Roadmap** in its H1 and in
  the dashboard sidebar. Route, API contracts and stored data are unchanged.
- The analysis page heading is **Analyze My Resume**, matching the dashboard
  card the brief names.

## 6. Verification actually run

- Full backend suite: **37 files, ~2,710 checks, 0 failures** once
  `test_migration_11.py` was updated (see below). `test_diagnostic.py` and
  `test_jd_passthrough.py` are scripts that print no `RESULT:` line; both
  exited 0.
- `test_profile_education.py` **70/70**, `test_education_entries.py`
  **75/75** (updated to assert classifications and to assert that `%`,
  `528/600`, `8.8 on 10`, `8.9 on 10` never reach the PDF).
- `test_preview_parity.py` **345/345** — preview and PDF still agree after the
  grade change, because both read the same `education_detail`.
- `test_migration_11.py` **33/33**. Its "no existing table gained or lost a
  column" check was tightened rather than deleted: it now forbids any lost or
  retyped column and allows only the additions a migration declares
  (`career_profile_education.classification` from migration 13).
- `test_pdf_layout_quality.py` **12/12**, `test_pdf_layout_regressions.py`
  **48/48**, `test_resume_builder.py` **192/192**, `test_api_contract.py`
  **117/117**, `test_career_platform.py` **169/169**,
  `test_migrations.py` **19/19**, `test_database.py` **43/43**.
- Frontend `npm run verify`: lint clean, route checks pass (10 features,
  22 routes), production build succeeds (only the known >500 kB chunk warning).
- Browser, against the sandbox: classification dropdown renders; job-match H1
  and sidebar label read "Career Readiness Roadmap"; no horizontal overflow on
  the dashboard; login and back-link checks as above.

## 7. Database status after this pass

- The status written here in Session 3 was true when it was written and is now
  **superseded**; see Section 9 below for the current truth.
- Production `ai-service/resumeai.db` was not opened *by this pass's own work*.
  It remained at `user_version 11` with the hash recorded above for the whole
  of Session 3. Migration 13 was applied to the sandbox copy only, and the
  startup guard was expected to back production up and apply 13 on first real
  use.
- The sandbox copy is at `user_version 13` and its backup sits in
  `%TEMP%\resumeai_browser_sandbox\backups\`.

## 8. Still manual

- Interview question generation still needs an AI key; the page says so.
- The sandbox job data is sample data and is labelled as such in the UI.


# Session 4 — templates, PDF page flow, and cover-letter framing

The closing pass on the last brief. Nothing was rebuilt and no page was
duplicated; every change below extends code that was already there. Two of the
three PDF fixes were found by exporting real documents and reading the pages,
not by reading the code.

## 1. Template gallery exposes its categories

- `templates_catalog.py` already knew the eleven categories but the legacy
  branch of `_as_gallery_entry` mislabelled them; it now goes through
  `CATEGORY_LABELS` so a tile's category strip and the filter agree.
- The gallery reads the server's own `categories` (name + count) rather than a
  hardcoded list, adds a horizontally scrollable chip row (`All` plus the
  eleven), and passes the chosen category back as the existing `category`
  query parameter. Counts come from the server, so they cannot drift.
- Tiles carry a `.tg-tile-cat` label. The result line is honest about the
  filter: `All` reads `124 templates · 67 ATS-friendly`, and a chosen category
  reads `12 templates in Student, Fresher & Internship` using the *filtered*
  total, not the catalogue-wide `facets.total`. The empty state distinguishes
  "no results for this search" from "nothing in this category".
- Browser proof (sandbox, signed in): twelve chips rendered with counts
  (`All 124`, `ATS-Friendly & Traditional 14`, … `Career Change & Returning to
  Work 10`); clicking **Student, Fresher & Internship** produced exactly **12**
  `.tg-card`s, every one labelled `STUDENT, FRESHER & INTERNSHIP`, with the
  count line above reading `12 templates in Student, Fresher & Internship`.
- The gallery is browsable before the profile is complete, as asked: nothing on
  the page requires saved details to render.

## 2. Section headings never orphan (resume PDF)

- A section heading could land as the last line of a page with its first entry
  overleaf. `resume_pdf.HEADING_KEEP_WITH_NEXT = 66.0` now reserves
  `30 + 66` pt for a heading plus its first row, and `layout_engine._render_body`
  reserves `max(section_height_estimate, 30 + rp.HEADING_KEEP_WITH_NEXT)`.
  The reservation is applied on every render path — `render_sections`, custom
  blocks, and the minimal / ruled / timeline / executive / summary layouts.
- Verified on the oversized fixture resume-12: `INTERNSHIPS` now begins page 4
  together with its entry instead of stranding the heading at the foot of
  page 3.

## 3. A cover letter prints its frame once (cover-letter PDF)

- `build_pdf` supplies the letter's own `Dear …` and `Kind regards, Name`. A
  body that already carried them — pasted from another tool, or written that
  way out of habit — was printed **twice**, opening with two greetings and
  closing with two sign-offs.
- `cover_letter_pdf._strip_own_frame()` now removes only the frame from the
  body before layout: a leading greeting line, and a trailing sign-off with or
  without the printed name (`Kind regards,\nAsha Rao` in one block, or as two).
  Content is left alone — a closing paragraph such as "Thank you for reading my
  application." is not a sign-off and stays.
- Verified by export: a body containing `Dear Hiring Manager,` and
  `Kind regards,\nVerification Student` now produces exactly **one** greeting,
  **one** sign-off, and the name twice (letterhead + signature), on one page.

## 4. A long letter keeps a readable size

- `_fit_size` compared the body against the whole page with a flat 160pt
  allowance. That under-counted both the letterhead and the gaps between
  paragraphs, so it reported "fits" at a size that then produced a second page
  anyway: a long letter came out **smaller and over two pages**, which is the
  opposite of the file's own stated rule ("readability first; if it needs a
  second page it runs to a second page").
- It now measures from the cursor the caller is actually at (letterhead and
  greeting already drawn), includes the inter-paragraph gap, and reserves the
  150pt the sign-off block uses. If nothing at or above the 9pt floor fits on
  one page it returns the preferred 10.5pt, because shrinking any further buys
  no page and costs legibility.
- Verified on a real 430-word letter: body now renders at **10.5pt** over two
  pages with the last two paragraphs and the closing together on page 2, rather
  than at 10.0pt with a single stranded paragraph.

## 5. Verification actually run this pass

- **Backend:** every `test_*.py` (36 files) exited 0. Notable totals:
  `test_preview_parity.py` **345/345**, `test_resume_builder.py` **192/192**,
  `test_career_platform.py` **169/169**, `test_template_library.py`
  **149/149**, `test_career_mission.py` **137/137**,
  `test_feature_integration.py` **133/133**, `test_api_contract.py`
  **117/117**, `test_cover_letters.py` **112/112** (up from 108: the new
  `test_pdf_does_not_repeat_a_greeting_in_the_body` adds four checks),
  `test_education_entries.py` **75/75**, `test_profile_education.py` **70/70**,
  `test_pdf_layout_regressions.py` **48/48**, `test_pdf_layout_quality.py`
  **12/12**, `test_migrations.py` **19/19**, `test_migration_11.py` **33/33**,
  `test_database.py` **43/43**, `test_db_guard.py` **24/24**.
  `test_diagnostic.py` and `test_jd_passthrough.py` print no `RESULT:` line by
  design; both exited 0.
- **Frontend:** `npm run lint` clean; `npm run verify:routes` passes (10
  features, 22 routes); `npm run build` succeeds with only the known
  ">500 kB chunk" warning.
- **Documents exported and inspected** (real files, Flask test client, sandbox
  database): `resume-11` (short — prints "First Class", no percentage, marks or
  CGPA), `resume-12` (long — headings travel with their entries), a plain cover
  letter, the 430-word cover letter, and a cover letter whose body carries its
  own greeting and sign-off. For each: `U+FFFD` count 0, no placeholder
  brackets, no out-of-bounds text blocks, no blank pages, every section heading
  exactly once.
- **Browser:** dashboard and gallery full-DOM scans found **zero** elements with
  a content-bearing `::before`; a hovered `.land-hero-card` measured the new
  lift/shadow border treatment with no accent strip; the cover-letter "Back to
  Dashboard" link measured `rgb(49, 85, 217)`, 13px, weight 600, no padding,
  no background, no border, `href="/dashboard"`, and navigated there; the login
  page rendered as sign-in only.

## 6. Production database — current truth

- **`ai-service/resumeai.db` is now at `user_version 13`.** This supersedes the
  Session 3 note above. It was applied by a real application start, not by any
  test: a `python app.py` process started at 13:49:29/13:49:33, and the guarded
  startup took the designed path — it wrote the automatic backup
  `ai-service/backups/resumeai-pre-migration-20261022-134933.db` (a
  `user_version 11` copy) **first**, then applied migrations 12 and 13.
- The pre-migration backup and the live file hold **identical record counts**:
  users 26, resumes 26, cover letters 1, resume analyses 26, career profiles 2,
  applications 0. `PRAGMA integrity_check` returns `ok` on both. The only
  schema difference is the additive `career_profile_education.classification`
  column and migration 12's additions; nothing was dropped or retyped.
- Current production file: size **942080**, SHA-256
  `F6A1B199B46EF6108C520C981D4099D669B6FC8CBB8AFF1E0597B9393F3BB1F5`, mtime
  `22-10-2026 13:49:33`.
- The test suites themselves remain walled off from production: `db_guard`
  refuses the production path when the running script is a test, and
  `test_db_guard.py` (24/24) fingerprints the production file and asserts the
  hardest-opening suites leave it byte-identical. Re-running the suite after
  the migration left the hash unchanged.
- **Honest note:** migrating production during this session was not the
  intended sequence — the plan was to introduce migration 13 to the sandbox
  only and let the first real start apply it. The first real start happened
  now. No data was lost and the guard did exactly what it was built to do, but
  the change was not requested in advance and is recorded here rather than
  glossed over.

## 7. Still manual / not automated

- A true ~390px mobile viewport could not be set — the browser tooling exposes
  no resize/emulation. Checked instead at 800px: the chip row is
  `overflow-x: auto` with `flex-wrap: nowrap` (scrolls within itself) and the
  page has **no** horizontal overflow (`scrollWidth − clientWidth = 0`). A
  hand check on a phone is still worthwhile.
- Interview question generation and AI cover-letter drafting still require a
  provider key; both pages say so rather than faking output.
- The long resume fixture is deliberately oversized; page 5 holds only its last
  language entry. That is content length, not clipping, and is documented in
  the tests.

---

# Session 5 — registration prompt restored on the login card

## 1. "New to ResumeAI? Create Account"

- Reinstated below the Sign In button at the client's request. This reverses
  Session 3 §2 above; that entry is marked superseded rather than deleted.
- Markup in `Login.jsx`: a `<p class="login-register-prompt">` with a grey
  `<span>` and a `type="button"` styled as a link. It is a button, not an
  `<a>`: registration is the same `/login` component in `mode: "register"`
  (no `/register` route, no second page), so the click calls the same
  `setMode("register")` the landing page's links already trigger. A `Link` to
  the same path would leave the component mounted and the form would not
  switch.
- Shown only while `!isRegister`, so it cannot appear on top of the
  registration form. The register view keeps "Already have an account? Sign
  in", which sets the mode back and clears the same fields.
- Styling in `Login.css`: question `#64748b`; link `#2563eb`, weight 600,
  13.5px; `margin-top: 14px`; centred. Hover changes the colour to `#1d4ed8`
  and adds an underline. No background, no border, no pseudo-element — in
  particular no vertical accent line. `:focus-visible` gets a 2px outline.
- Logo, heading, subtitle, both fields, the eye toggle and the Sign In button
  are untouched. The card's existing `width: 430px; max-width: 90%` and the
  `max-width: 500px` padding rule are unchanged, and the prompt has no fixed
  width, so it wraps inside the card on narrow screens.

## 2. Verification actually run

- `npm run lint` clean; `npm run verify:routes` passes (10 features, 22
  routes); `npm run build` succeeds with only the known ">500 kB chunk"
  warning.
- Browser against the real sandbox (`localhost:5173` → `localhost:8001`,
  throwaway database):
  - prompt text exactly `New to ResumeAI? Create Account`;
  - grey `rgb(100, 116, 139)`; blue `rgb(37, 99, 235)`; 14px between the Sign
    In button and the prompt;
  - hover: `rgb(29, 78, 216)` and underline; `border-left: 0px`,
    `::before` `content: none`, transparent background;
  - "Create Account" opens the register view (heading "Create Account", Full
    Name and Confirm Password present);
  - "Already have an account? Sign in" returns to the login card and the
    prompt;
  - Sign In with an existing sandbox account → `/dashboard`;
  - registered a fresh throwaway account in the sandbox database → `/dashboard`,
    then signed out and signed in with that new account → `/dashboard`.
- No backend file, route, migration, authentication rule or database was
  changed by this pass, so the backend suites were not re-run.


