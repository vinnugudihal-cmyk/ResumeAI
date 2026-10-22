"""
Learning tracks and application checklists.

Each track answers one honest question: "the role names this skill
and the student has not shown it yet, so what do they actually do
next?" Every entry names a real exercise and the artefacts that
prove the work happened.

Two rules apply throughout:

* Nothing here claims a skill was verified. A track is a
  suggestion, never a certificate.
* No entry invents a qualification. If a student has not done the
  exercise, the mission still shows it as not started.
"""

# ============================================================
# LEARNING TRACKS
#
# key    exact role skill name
# why    why a listing asks for it
# do     the exercise to carry out
# done   artefacts that demonstrate the work
# ============================================================

LEARNING_TRACKS = {
    # ---------- shared across roles ----------
    "python": {
        "why": "Almost every back-end and data role lists it first.",
        "do": "Build one small command-line tool that reads a CSV, "
              "validates each row, and writes a cleaned copy plus a "
              "summary of what was wrong.",
        "done": [
            "Working script committed to a public repository",
            "A README explaining the input format and how to run it",
            "Three example input files, including one with bad rows",
        ],
    },
    "java": {
        "why": "Common in enterprise and backend listings.",
        "do": "Write a console application that models a small "
              "library: books, members and loans, with classes for "
              "each and a text menu to drive it.",
        "done": [
            "Source files with clear classes and packages",
            "Sample console transcript showing the menu working",
            "A short note explaining your object-oriented choices",
        ],
    },
    "sql": {
        "why": "Asked for in nearly every data and back-end role, "
               "and it is the fastest skill to prove on paper.",
        "do": "Take a public dataset, load it into SQLite or "
              "PostgreSQL, then answer ten real business questions "
              "with queries rather than by eye.",
        "done": [
            "The .sql file containing all ten queries",
            "One screenshot or table of results per question",
            "A short write-up naming the questions and what each "
            "query revealed",
        ],
    },
    "git": {
        "why": "Assumed everywhere; a missing repository history is "
               "noticed immediately by reviewers.",
        "do": "Set up a repository for one of your projects and make "
              "it a genuine history: small commits, meaningful "
              "messages, branches for at least one feature.",
        "done": [
            "Public repository with a readable commit history",
            "At least one merged branch showing real branching",
            "A .gitignore and a README at the repository root",
        ],
    },
    "github": {
        "why": "Where reviewers look first, and where your projects "
               "are found.",
        "do": "Publish one finished project properly: clear name, "
              "description, screenshots, setup steps and a licence.",
        "done": [
            "Repository that another person can clone and run",
            "Screenshots in the README showing it working",
            "A pinned repository on your profile",
        ],
    },
    "linux": {
        "why": "Expected wherever deployments or servers are involved.",
        "do": "Deploy one of your existing projects on a free Linux "
              "host or a local virtual machine, then serve it there.",
        "done": [
            "A running web address you can share",
            "The commands you used, written down as a short guide",
            "A screenshot of the terminal output",
        ],
    },
    "rest api": {
        "why": "How front-end and back-end work is joined together.",
        "do": "Add an API layer to an existing project: at least four "
              "endpoints, real request validation, and errors "
              "returned as meaningful status codes.",
        "done": [
            "An endpoint list with a method and path for each route",
            "Example requests and responses committed as a document",
            "Error cases that return the correct status code",
        ],
    },
    "data structures": {
        "why": "The most common screening question after core skills.",
        "do": "Implement arrays, linked lists, stacks, queues, binary "
              "search trees and hash maps in one language, each in "
              "its own file with a small runnable example.",
        "done": [
            "One file per data structure with a runnable example",
            "A README comparing when each structure is the right "
            "choice",
            "Your own working implementation, not a copied library",
        ],
    },
    "algorithms": {
        "why": "Asked for directly in most developer listings.",
        "do": "Work through the common patterns: two pointers, "
              "sliding window, BFS and DFS, basic dynamic "
              "programming, then write each solution yourself.",
        "done": [
            "Solutions written from scratch, each with a short "
            "explanation of the approach and its complexity",
            "A few small tests proving each solution works",
            "A README grouping the problems by pattern",
        ],
    },
    "oop": {
        "why": "Explicitly expected wherever Java or a large codebase "
               "appears.",
        "do": "Refactor one procedural program into classes using "
              "encapsulation, inheritance and at least one interface.",
        "done": [
            "Before-and-after code showing the same behaviour",
            "A note explaining each abstraction and why it exists",
            "An interface implemented by two different classes",
        ],
    },
    "statistics": {
        "why": "Separates a data analyst from someone who only writes "
               "queries.",
        "do": "Take a dataset, ask a real question, and report the "
              "result with the distribution, spread and a stated "
              "limitation.",
        "done": [
            "Charts showing the distribution you measured",
            "A written conclusion that names what the data can and "
            "cannot show",
            "The queries used, kept in one script",
        ],
    },
    # ---------- software developer ----------
    "docker": {
        "why": "Standard in back-end roles and useful for showing "
               "your work is reproducible.",
        "do": "Containerise one project of yours: write a Dockerfile, "
              "build the image, run it, and confirm it works with no "
              "local setup.",
        "done": [
            "A Dockerfile and a working build",
            "A short README section on building and running",
            "Evidence that the container runs on its own",
        ],
    },
    "aws": {
        "why": "Named in most cloud-adjacent developer listings.",
        "do": "Use the AWS free tier to host one of your projects, "
              "then add one managed service such as a database or "
              "file storage.",
        "done": [
            "A public address for the deployed project",
            "A diagram or note listing the services you used and why",
            "Screenshots of the running service",
        ],
    },
    "mysql": {
        "why": "The database most often named in Indian listings.",
        "do": "Design a schema for a real problem you care about, "
              "then implement it in MySQL with foreign keys and a "
              "few reports.",
        "done": [
            "An ER diagram or a written schema description",
            "The .sql file that creates the database",
            "Three example queries that answer real questions",
        ],
    },
    "mongodb": {
        "why": "Common where listings mention NoSQL.",
        "do": "Rebuild the data layer of one small project in "
              "MongoDB, then compare it with the relational version "
              "you already had.",
        "done": [
            "Working data layer with schema validation in place",
            "A note on what changed and why",
            "Example documents showing your structure",
        ],
    },
    "postgresql": {
        "why": "Widely used in production back ends.",
        "do": "Move one project's data layer to PostgreSQL and use "
              "two features SQLite lacks, such as proper indexing "
              "or JSON columns.",
        "done": [
            "A migration script from your old database",
            "An index with a note on what it speeds up",
            "Evidence the app still runs correctly afterwards",
        ],
    },
    # ---------- web developer ----------
    "html": {
        "why": "The base of every front-end role.",
        "do": "Build one page with semantic elements used correctly, "
              "then check the markup with a validator until it is "
              "clean.",
        "done": [
            "Markup that passes the W3C validator with no errors",
            "A short note on why each element was chosen",
            "The page working with images and links",
        ],
    },
    "css": {
        "why": "Front-end listings ask for layout and responsive "
               "design more often than for any framework.",
        "do": "Build a responsive layout that works from a 320px "
              "phone to a wide desktop, without a framework.",
        "done": [
            "Screenshots at phone, tablet and desktop widths",
            "No horizontal scrolling at the narrowest width",
            "Layout using flexbox or grid, explained briefly",
        ],
    },
    "react": {
        "why": "The most requested front-end skill in listings.",
        "do": "Build one small application with components, state "
              "and at least one data fetch, then deploy it.",
        "done": [
            "A deployed URL anyone can open",
            "Components split sensibly rather than one large file",
            "Loading and error states that actually work",
        ],
    },
    "node.js": {
        "why": "Usual back-end choice in JavaScript listings.",
        "do": "Write a small server that reads and writes data, with "
              "routes, validation and real error handling.",
        "done": [
            "Server source committed to a repository",
            "Example requests and responses",
            "A note on the route structure you chose",
        ],
    },
    "express": {
        "why": "The framework almost always named with Node.js.",
        "do": "Build an Express app with REST routes, middleware for "
              "errors and a simple JSON data store.",
        "done": [
            "Working routes for create, read, update and delete",
            "One piece of custom middleware",
            "A README showing how to start and test it",
        ],
    },
    "typescript": {
        "why": "Increasingly listed as expected rather than optional.",
        "do": "Add TypeScript types to one existing JavaScript project "
              "rather than starting a new one.",
        "done": [
            "The project running with types enabled",
            "Interfaces or types for your main data shapes",
            "No remaining implicit any in your own code",
        ],
    },
    "tailwind css": {
        "why": "Frequently named in front-end listings.",
        "do": "Rebuild the styling of one existing page with "
              "Tailwind instead of writing custom CSS.",
        "done": [
            "Before and after screenshots",
            "Responsive behaviour preserved",
            "A note on which utilities replaced which custom CSS",
        ],
    },
    "figma": {
        "why": "Design collaboration is expected in UI-facing roles.",
        "do": "Take an existing screen and rebuild it in Figma as a "
              "component set, then share the file link.",
        "done": [
            "A shareable Figma link",
            "Reusable components rather than one flat frame",
            "Auto-layout used for spacing consistency",
        ],
    },
    # ---------- data analyst ----------
    "excel": {
        "why": "Still the everyday tool of most analyst roles.",
        "do": "Load a real dataset and answer questions using "
              "pivot tables, lookups and conditional formatting.",
        "done": [
            "A working spreadsheet committed as a file",
            "Pivot tables summarising the dataset",
            "Formulas rather than typed numbers wherever possible",
        ],
    },
    "data analysis": {
        "why": "The core of the role and the part listed first.",
        "do": "Take one dataset, clean it, and write a short "
              "analysis answering a question you chose.",
        "done": [
            "A written report with a clear question and answer",
            "Charts that support the conclusion",
            "The cleaning steps documented, not hidden",
        ],
    },
    "pandas": {
        "why": "The standard library for handling data in Python.",
        "do": "Load a messy real dataset, clean it, and produce a "
              "summary table plus two charts from a script.",
        "done": [
            "A notebook or script that runs end to end",
            "A summary of what was cleaned and why",
            "Two charts saved as images",
        ],
    },
    "numpy": {
        "why": "Underpins most data work in Python.",
        "do": "Complete a few numerical exercises: arrays, indexing, "
              "reshaping and basic statistics, then apply one to a "
              "real dataset.",
        "done": [
            "Your own solutions with explanations",
            "One worked example on real data",
            "Results checked against a second method",
        ],
    },
    "power bi": {
        "why": "Named in business-facing analyst listings.",
        "do": "Build a two-page report from a public dataset with a "
              "chart, a KPI and a filter that works.",
        "done": [
            "A published report link",
            "Measurements written as DAX, not defaults only",
            "An interactive filter that genuinely changes the view",
        ],
    },
    "tableau": {
        "why": "Common in analyst roles that value dashboards.",
        "do": "Connect a public dataset and build a dashboard with at "
              "least three coordinated views.",
        "done": [
            "A published dashboard link",
            "Views connected by filters or actions",
            "A note on the question each view answers",
        ],
    },
    # ---------- java developer ----------
    "spring boot": {
        "why": "The framework almost always paired with Java back-end "
               "listings.",
        "do": "Build a small REST service with Spring Boot, including "
              "a database connection and input validation.",
        "done": [
            "A running service with at least three endpoints",
            "A schema file and sample data",
            "Validation that rejects bad input with a clear message",
        ],
    },
    "hibernate": {
        "why": "The default ORM in most Java back-end work.",
        "do": "Map an existing database schema to entity classes and "
              "run real queries through the ORM.",
        "done": [
            "Entity classes with correct relationships",
            "Queries working against real data",
            "A note on how you chose the mappings",
        ],
    },
    "maven": {
        "why": "Expected build tooling for Java projects.",
        "do": "Convert a manual Java project into a Maven build, then "
              "add one dependency and one test.",
        "done": [
            "A working pom.xml",
            "One automated test that runs in the build",
            "A README with the build command",
        ],
    },
    "microservices": {
        "why": "Appears in senior-leaning Java listings.",
        "do": "Split an existing single application into two services "
              "that communicate over HTTP, both deployable alone.",
        "done": [
            "Two services with their own start commands",
            "Working communication between them",
            "A short note on where you drew the boundary and why",
        ],
    },
}


# ============================================================
# APPLICATION CHECKLIST
#
# Shown once the skills are in place. Ordered, so the next action
# is always the first unfinished item.
# ============================================================

APPLICATION_CHECKLIST = [
    (
        "check-role",
        "Read a real listing for this role and note every "
        "requirement it names",
        "applications",
        "Copy the listing text into the matcher on the Resume "
        "Analysis page and compare it with your resume. Look for "
        "requirements you genuinely cannot evidence yet.",
    ),
    (
        "check-timeline",
        "List every date you will write on your resume",
        "applications",
        "Check that your education, project and internship dates "
        "are consistent and in the right order. Gaps and "
        "overlaps get noticed.",
    ),
    (
        "check-evidence",
        "Pick the two strongest projects and write one honest line "
        "for each",
        "applications",
        "Each line should say what you built, what you used and "
        "what it did. Only state numbers you can point to.",
    ),
    (
        "check-resume",
        "Re-run the resume analyser and work through the top "
        "improvement",
        "resume",
        "Open Resume Analysis, upload your current resume and "
        "follow the single highest-value action it lists.",
    ),
    (
        "check-tailor",
        "Tailor your resume to one specific role",
        "resume",
        "Reorder and reword for that role. Remove anything you "
        "would not want to discuss in an interview.",
    ),
    (
        "check-questions",
        "Prepare three questions to ask at the end",
        "applications",
        "Questions about the team's current work show genuine "
        "interest far better than a generic question.",
    ),
    (
        "check-apply",
        "Apply, then record it in the tracker",
        "applications",
        "Apply and log the date so you can follow up if you hear "
        "nothing within a week.",
    ),
]
