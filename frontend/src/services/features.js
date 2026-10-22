/**
 * The features this app has, in one place.
 *
 * The sidebar, the dashboard launch grid and the "coming soon"
 * list all read from here. They used to be written out separately,
 * which is how a button ends up pointing at a page that does not
 * exist: the link looked fine in the sidebar and 404'd when it
 * was clicked.
 *
 * Every entry here is backed by a real route in App.jsx and a real
 * backend feature. Nothing is listed that the app cannot do.
 *
 * `DASHBOARD_CARDS` is the order the dashboard draws those ten in:
 * five rows of two, flat, with no headings between them.
 * `PRIMARY_ACTIONS` is the first row on its own, because the route
 * verifier reads it.
 */

export const FEATURES = [
  {
    key: "create_resume",
    label: "Create My Resume",
    action: "Create Resume",
    icon: "create",
    blurb:
      "Pick a design, see it filled with your details, then edit and "
      + "download. Your details come from My Details.",
    to: "/create-resume",
    kind: "page",
  },
  {
    key: "resume_analysis",
    label: "Analyze My Resume",
    action: "Analyze Resume",
    icon: "analyse",
    blurb:
      "Upload your existing resume to review its content, skills, "
      + "formatting, and ATS compatibility.",
    to: "/analyse",
    kind: "page",
  },
  {
    key: "career_profile",
    label: "My Details",
    action: "View My Details",
    icon: "profile",
    blurb:
      "Your education, projects, experience and skills in one "
      + "reusable place. Every resume and letter starts from this.",
    to: "/career-profile",
    kind: "page",
  },
  {
    key: "resume_templates",
    label: "Resume Templates",
    action: "Browse Resume Templates",
    icon: "create",
    blurb:
      "Search real, selectable-text resume designs and start building "
      + "from the one you pick.",
    to: "/resume-templates",
    kind: "page",
  },
  {
    key: "cv_templates",
    label: "CV Templates",
    action: "Browse CV Templates",
    icon: "create",
    blurb:
      "The same design library, opened on the CV view so the two "
      + "entry points stay separate.",
    to: "/cv-templates",
    kind: "page",
  },
  {
    key: "cover_letter",
    label: "Cover Letter Generator",
    action: "Write a Cover Letter",
    icon: "letter",
    blurb:
      "Write one letter per role from the details you have saved, "
      + "keep them separately, and download any of them as a PDF.",
    to: "/cover-letter",
    kind: "page",
  },
  {
    key: "find_jobs",
    label: "Find Jobs",
    action: "Find Jobs",
    icon: "jobs",
    blurb:
      "Search real job sites by role, city, experience level and "
      + "work arrangement.",
    to: "/find-jobs",
    kind: "page",
  },
  {
    key: "saved_jobs",
    label: "Saved Jobs",
    action: "Open Saved Jobs",
    icon: "saved",
    blurb:
      "The jobs you kept, ready to track or tailor a resume for.",
    to: "/saved-jobs",
    kind: "page",
  },
  {
    key: "apply_for_job",
    label: "Apply for a Job",
    action: "Find a Job to Apply For",
    icon: "jobs",
    blurb:
      "Open the employer application link, then confirm you submitted "
      + "it. Nothing is recorded until you say so.",
    to: "/find-jobs",
    kind: "page",
  },
  {
    key: "applications",
    label: "Track Your Applications",
    action: "Track Applications",
    icon: "applications",
    blurb:
      "See where every application you sent actually stands, and "
      + "what to chase.",
    to: "/applications",
    kind: "page",
  },
];

/**
 * The order the dashboard draws its ten cards in.
 *
 * A single flat list: five rows of two, read left to right. It used to
 * be seven numbered sections, which put a heading and a rule between
 * every pair of related tools and made the page taller than the ten
 * things on it warranted. There are no headings now and no numbers -
 * a "1 of 7" badge would claim the app has an order it does not have,
 * since every card is reachable from anywhere on the page.
 *
 * This is a drawing order only. `FEATURES` remains the single list of
 * what exists and where it goes; the sidebar still walks FEATURES, and
 * neither list can drift from a route because both resolve through
 * `destinationFor`.
 */
export const DASHBOARD_CARDS = [
  // Row 1
  "create_resume",
  "resume_analysis",

  // Row 2
  "career_profile",
  "cover_letter",

  // Row 3
  "resume_templates",
  "cv_templates",

  // Row 4
  "find_jobs",
  "saved_jobs",

  // Row 5
  "apply_for_job",
  "applications",
];

/**
 * The two things people come here to do.
 *
 * The first row of the dashboard, kept as its own export because the
 * route verifier reads it. They are equal: nothing here marks one as
 * more important than the other, and every card is now drawn by the
 * same map with the same class, so the top row is not a different
 * kind of thing from the rest.
 */
export const PRIMARY_ACTIONS = FEATURES.filter((feature) =>
  DASHBOARD_CARDS.slice(0, 2).includes(feature.key)
);

/**
 * Short labels for the sidebar.
 *
 * The full label is what the dashboard card needs. In a 216px rail
 * "Match a Job Description" wrapped onto two lines and left the
 * menu looking ragged, so the menu gets its own word where the two
 * differ. Where they are the same, `navLabel` is simply not set and
 * the sidebar falls back to `label`.
 *
 * These are the ten features in the order the dashboard groups them,
 * so the rail reads as the same seven sections without repeating the
 * section headings.
 */
export const NAV_LABELS = {
  create_resume: "Create My Resume",
  resume_analysis: "Analyze My Resume",
  career_profile: "My Details",
  resume_templates: "Resume Templates",
  cv_templates: "CV Templates",
  cover_letter: "Cover Letter Generator",
  find_jobs: "Find Jobs",
  saved_jobs: "Saved Jobs",
  apply_for_job: "Apply for a Job",
  applications: "Track Your Applications",
};

export function navLabelFor(feature) {
  return NAV_LABELS[feature.key] || feature.label;
}

export const FEATURE_BY_KEY = FEATURES.reduce((all, feature) => {
  all[feature.key] = feature;

  return all;
}, {});

/**
 * Where a card goes, anchor included.
 *
 * Two cards share the analysis section on purpose: uploading a
 * resume to score it and pasting a job description to match against
 * it are two different jobs done in one panel. They are not given
 * separate destinations because there is only one place they are
 * actually done.
 */
export function destinationFor(feature) {
  if (!feature.anchor) return feature.to;

  return `${feature.to}#${feature.anchor}`;
}

/**
 * Things the app deliberately does not do yet.
 *
 * Listed as disabled and labelled "Coming soon" rather than
 * rendered as a button, because a button that leads nowhere is
 * worse than an honest gap.
 */
export const COMING_SOON = [
  {
    label: "Salary negotiation coach",
    note: "Not built yet. Would need real market data first, "
      + "which we do not have.",
  },
];
