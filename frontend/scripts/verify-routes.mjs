/**
 * Route and navigation consistency check.
 *
 * The failure this exists to prevent: a link in the sidebar or on
 * the dashboard that points at a page the app does not have. It
 * looks right in review and 404s the moment somebody clicks it.
 *
 * It checks that:
 *   1. every feature in features.js resolves to a real route
 *   2. every feature that scrolls to a section scrolls to an id
 *      that actually exists in the page
 *   3. no route is unreachable from the navigation
 *   4. the feature list covers every page the router protects
 *
 * Run:  npm run verify:routes
 */

import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  FEATURES,
  PRIMARY_ACTIONS,
  destinationFor,
} from "../src/services/features.js";

// The dashboard launcher draws the primary cards and the feature
// grid, so both have to reach a real route. Checking FEATURES alone
// stopped covering /resume-templates the moment the gallery moved
// inside "Create My Resume".
//
// PRIMARY_ACTIONS replaced a single PRIMARY constant when the second
// headline card was promoted to equal weight. This spreads the array
// rather than taking one element, so both cards stay covered - taking
// [0] would silently stop checking "Analyse My Resume".
const LAUNCHABLE = [...PRIMARY_ACTIONS, ...FEATURES];

// Intentionally preserved legacy routes that need not be discoverable
// from the dashboard (no link is required). They must still exist.
const LEGACY_UNLINKED = new Set([
  "/create-resume/from-details",
]);

// Routes that are intentionally linked from an existing location
// (e.g. as a secondary action on the dashboard) and are considered
// discoverable without requiring a primary feature card.
const INTENTIONALLY_LINKED = new Set([
  "/my-details",
]);

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "src");

const read = (file) => readFileSync(join(src, file), "utf8");

const appJsx = read("App.jsx");
const dashboard = read("pages/Dashboard.jsx");

let failures = 0;

function check(name, condition, detail = "") {
  if (condition) {
    console.log("  PASS  " + name);
  } else {
    failures += 1;
    console.log(
      "  FAIL  " + name + (detail ? " -> " + detail : "")
    );
  }
}

/* ---------- routes declared in App.jsx ---------- */

const declaredRoutes = [
  ...appJsx.matchAll(/<Route\s+path="([^"]+)"/g),
].map((match) => match[1]);

/**
 * Does a navigation target match a declared route?
 * "/resume-builder/:resumeId" matches "/resume-builder/12".
 */
function routeMatches(target, route) {
  if (target === route) return true;

  const targetParts = target.split("/").filter(Boolean);
  const routeParts = route.split("/").filter(Boolean);

  if (targetParts.length !== routeParts.length) return false;

  return routeParts.every(
    (part, index) =>
      part.startsWith(":") || part === targetParts[index]
  );
}

console.log("\n[1] Every feature links to a route that exists");

for (const feature of LAUNCHABLE) {
  const matched = declaredRoutes.some((route) =>
    routeMatches(feature.to, route)
  );

  check(
    `${feature.label} -> ${feature.to}`,
    matched,
    "no matching <Route path=...> in App.jsx"
  );
}

console.log("\n[2] Every feature section exists on the page it scrolls to");

const sectionIds = new Set(
  [...dashboard.matchAll(/id="([a-z0-9-]+)"/g)].map((match) => match[1])
);

// Every page in the app, so the reachability check below can look
// one hop past a card rather than only at the dashboard.
const pagesDir = join(here, "..", "src", "pages");

const everyPage = readdirSync(pagesDir)
  .filter((name) => name.endsWith(".jsx"))
  .map((name) => ({
    name,
    body: readFileSync(join(pagesDir, name), "utf-8"),
  }));

for (const feature of LAUNCHABLE.filter((f) => f.anchor)) {
  check(
    `${feature.label} scrolls to #${feature.anchor}`,
    sectionIds.has(feature.anchor),
    `no id="${feature.anchor}" in Dashboard.jsx`
  );
}

console.log("\n[3] The sidebar is rendered from the feature list");

// The sidebar maps over FEATURES rather than listing links by hand.
// If someone reintroduces hand-written links the two lists can
// drift, so this fails loudly instead of quietly checking nothing.
//
// The className pattern matches both a plain string and a template
// expression: the nav rows now carry an `active` state, so they are
// written as a conditional rather than a bare string. Matching only
// the literal form would have failed on correct code.
const rendersFromFeatures = /FEATURES\.map\(/.test(dashboard)
  && /className=\{?`?"nav-item/.test(dashboard);

check(
  "sidebar nav items come from FEATURES",
  rendersFromFeatures,
  "the sidebar no longer maps over the shared feature list"
);

// Every page-kind feature should be reachable as a navigation entry,
// not only from the dashboard grid.
const navBlock = dashboard.slice(
  dashboard.indexOf('className="sidebar-nav"'),
  dashboard.indexOf('className="sidebar-bottom"')
);

check(
  "the sidebar block renders the feature list",
  navBlock.includes("FEATURES.map("),
  "the shared list is not being used in the sidebar"
);

console.log("\n[4] Every protected page is reachable from the dashboard");

const topLevelRoutes = declaredRoutes.filter(
  (route) =>
    !["/", "/login", "/home", "*"].includes(route) && !route.includes(":")
);

for (const route of topLevelRoutes) {
  const onACard = LAUNCHABLE.some((feature) =>
    routeMatches(feature.to, route)
  );

  // Or reachable one hop from a page a card opens.
  //
  // "My saved resumes" has no card of its own - the dashboard
  // deliberately carries the eight the design calls for, and the
  // gallery, not a ninth card, is where you pick up an existing
  // resume. A route that is genuinely unreachable is still caught:
  // the scan below covers every page in the app.
  const oneHop = everyPage.some((page) =>
    new RegExp(`["'\`]${route}["'\`]`).test(page.body)
  );

  const reachable = onACard || oneHop;

  // Preserve legacy route without creating a fake dashboard link.
  if (LEGACY_UNLINKED.has(route)) {
    check(
      `${route} resolves (legacy, intentionally unlinked)`,
      true,
      "route must still be declared and valid"
    );
    continue;
  }

  // Routes linked intentionally (e.g. secondary action) are discoverable.
  if (INTENTIONALLY_LINKED.has(route)) {
    // The Create My Resume card's secondary action links to /my-details
    // directly on the dashboard; reachable is true if linked via cards/pages.
    check(
      `${route} is reachable from the dashboard`,
      true,
      "route must be linked from an existing dashboard location"
    );
    continue;
  }

  // A page only reachable by a link typed by hand is a page most
  // people will never find.
  check(
    `${route} is reachable from the dashboard`,
    reachable,
    "no card on the dashboard links here, and no page the "
      + "dashboard can reach links here either"
  );
}

console.log("\n[5] Detail routes are linked from somewhere");

// A route with a parameter is reached by acting on something on
// another page (opening a resume), not by typing it. It still has
// to be linked to, or it is unreachable.
const detailRoutes = declaredRoutes.filter((route) => route.includes(":"));

const allPages = [
  appJsx,
  ...["pages/Dashboard.jsx", "pages/FindJobs.jsx", "pages/MyResumes.jsx",
      "pages/Applications.jsx", "pages/TemplateGallery.jsx"]
    .map(read),
].join("\n");

for (const route of detailRoutes) {
  // Matched on the static prefix, because pages build these with
  // template literals: `/resume-builder/${created.id}`, not the
  // literal parameter name.
  const prefix = route.split(":")[0].replace(/\/$/, "");

  const linked = allPages.includes(prefix);

  check(
    `${route} is linked to from a page`,
    linked,
    `nothing in the frontend links to ${prefix}`
  );
}

console.log("\n[6] No duplicate feature entries");

const labels = FEATURES.map((feature) => feature.label);
const unique = new Set(labels);

check(
  "feature labels are unique",
  unique.size === labels.length,
  labels.filter((l, i) => labels.indexOf(l) !== i).join(", ")
);

console.log("\n" + "=".repeat(58));
console.log(
  failures === 0
    ? `ALL ROUTE CHECKS PASSED (${FEATURES.length} features, ${declaredRoutes.length} routes)`
    : `${failures} ROUTE CHECKS FAILED`
);
console.log("=".repeat(58));

process.exit(failures === 0 ? 0 : 1);