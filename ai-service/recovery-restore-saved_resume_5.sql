-- Recovery of saved_resumes id 5, lost when a test suite ran
-- against the production database.
--
--   source : backups/resumeai-pre-migration-20261016-005322.db
--   target : C:\Users\VANDANA GUDIHAL\OneDrive\Desktop\ResumeAI\ai-service\resumeai.db
--   owner  : user_id 1 (unchanged, original)
--
-- Every value below is the original one, quoted from the backup.
-- The id is written explicitly so the row keeps its original
-- primary key rather than being given a new one.

BEGIN TRANSACTION;

-- Precondition 1: the row must still be absent, or we are
-- restoring into a database that already has it.
-- (In SQLite an abort must be raised by hand; there is no
--  ASSERT, so this is checked by the guard below and by the
--  verification that follows.)

-- Precondition 2: the owning user must still exist, because
-- user_id carries ON DELETE CASCADE REFERENCES users(id).
-- Verified true immediately before this file was written.

INSERT INTO saved_resumes (
    id, user_id, title, template_key, target_role,
    content_json, settings_json, created_at, updated_at
) VALUES (
    5,
    1,
    'Vinoda Gudihal''s Resume',
    'premium_professional',
    NULL,
    '{"basics": {"full_name": "Vinoda Gudihal", "headline": "BCA Final Year Student", "email": "vinodagudihal2@gmail.com", "phone": "+91 9480495790", "location": "Hubli", "linkedin": "https://www.linkedin.com/in/vinoda-gudihal-5a59a2318?utm_source=share_via&utm_content=profile&utm_medium=member_android", "github": "github.com/vinodag", "website": "https://jade-lamington-552fe5.netlify.app/"}, "summary": "Motivated BCA Student with foundational knowledge of programming, DBMS and computer applications. Quick learner with strong analytical thinking and communication skills. Seeking an entry-level opportunity to start my professional career and contribute to organizational growth.", "experience": [], "internships": [], "education": [{"degree": "Bachelor''s Computer Application", "organisation": "Kle Bca P C Jabin College, Hubli", "location": "Vidyanagar, Hubli", "start": "2024", "end": "2027", "current": 0, "detail": "Data Structures, DBMS, Operating System, OOP with Java, Web Technologies, Python Programming, Computer Networks"}, {"degree": "Pre-University", "organisation": "Adarsh Pre-University College", "location": "Lingraj Nagar, Hubli", "start": "2022", "end": "2024", "current": 0, "detail": "PCMB"}, {"degree": "School", "organisation": "Giants English Medium School", "location": "Akshay Park, Hubli", "start": "2012", "end": "2022", "current": 0, "detail": ""}], "projects": [{"name": "ResumeAI", "organisation": "Personal Project", "start": "2026-07", "end": "", "bullets": ["Developed ResumeAI, a web application for creating professional resumes, selecting templates, previewing layouts, and downloading resumes as PDF files.", "Implemented resume analysis to identify skills, evaluate resume quality, and provide actionable suggestions for improvement.", "Built frontend and backend functionality with user authentication and database storage to save and manage resume data."], "url": ""}], "certifications": [{"name": "UI/UX Design Using Figma", "organisation": "Kle Bca P.C.Jabin College, Hubli", "date": "2024", "url": ""}, {"name": "Front-End Development", "organisation": "Kle Bca P.C.Jabin College, Hubli", "date": "2025", "url": ""}, {"name": "Back-End Development", "organisation": "Kle Bca P.C.Jabin College, Hubli", "date": "2025", "url": ""}, {"name": "Java, Spring Boot and Hibernate", "organisation": "Kle Bca P.C.Jabin College, Hubli", "date": "2026", "url": ""}], "achievements": [], "volunteering": [], "languages": [], "skills": {"technical": ["C", "Java", "Python", "SQL", "HTML", "CSS", "DBMS", "MS Office"], "soft": ["Communication", "Teamwork", "Quick Learner", "Problem Solving"]}, "custom": []}',
    '{"font": "classic", "accent": "#3155d9", "density": "normal", "layout": "single", "section_order": ["summary", "experience", "projects", "skills", "education", "internships", "certifications", "achievements", "volunteering", "languages", "custom"], "hidden_sections": []}',
    '2026-10-15T19:02:02Z',
    '2026-10-15T19:12:21Z'
);

COMMIT;

-- After running, verify with:
--   SELECT id, user_id, title, template_key
--   FROM saved_resumes WHERE id = 5;
-- Expect one row, matching the values above.
