import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  fetchResumeTemplates,
  createMyResume,
  fetchAiStatus,
  fetchCareerProfile,
} from "../services/api";
import { readForUser, writeForUser } from "../services/sessionCache";
import ResumePreview from "../components/ResumePreview";
import TemplateThumbnail from "../components/TemplateThumbnail";
import "./TemplateGallery.css";

/**
 * The template library.
 *
 * One page serves both "Resume Templates" and "CV Templates". How
 * many templates exist is decided by the server and reported here;
 * this page never counts cards in the DOM, because that would be the
 * number it happens to have drawn rather than the number there are.
 * Searching and paging happen server-side for the same reason: two
 * browsers must not get different answers to "how many are there".
 *
 * The filter bar is deliberately gone.
 *
 * It used to be a row of column chips, a row of category chips, four
 * selects (header, section style, experience, sort) and two toggles
 * (ATS-only, favourites-only) - eleven controls in front of the
 * thing the page is for. Every one of them had to be understood
 * before a single design could be seen, most of them were read as
 * required rather than optional, and "Clear filters" appeared on an
 * untouched gallery because the default state counted as a filter.
 *
 * What is left is a search box, the templates, and Load More. That
 * is enough to find a design by name, style or role, which is what
 * people actually arrive wanting.
 *
 * Sorting is not a control either: the server's own "featured" order
 * is used, which is the curated order the registry produced. Asking
 * for it by name would only reintroduce a dropdown that most people
 * never touch.
 *
 * Favourites are kept. The star on a card is not a filter - it is
 * per-template state, and removing it would throw away something
 * people had already built. Only the "favourites only" toggle is
 * gone.
 */

const PAGE_SIZE = 24;

/**
 * Favourites are a per-account UI preference, not resume content.
 *
 * They live in the session cache under this name, which is already
 * namespaced per user id, so one person on a shared machine does not
 * inherit another's shortlist. Nothing is sent to the server: the
 * catalogue is public, so a favourite list is not worth a table.
 */
const FAVOURITES = "template_favourites";

/**
 * The two things this page can be opened as.
 *
 * There is no CV-only template in the registry: every design in the
 * catalogue is a general document layout that suits a resume or a CV,
 * and the data does not say which. Inventing a CV category to fill
 * the gap would mean presenting the same 124 layouts under a name
 * that implies they are different documents, so both entries open the
 * one real catalogue and say plainly that they share it.
 */
const VIEWS = [
  {
    key: "resume",
    path: "/resume-templates",
    label: "Resume Templates",
    title: "Resume Templates",
    lede:
      "Choose a design, see it filled with the details you saved in My "
      + "Details, edit it, then download a PDF with selectable text.",
  },
  {
    key: "cv",
    path: "/cv-templates",
    label: "CV Templates",
    title: "CV Templates",
    lede:
      "The same design library, opened as a CV. Every design here is "
      + "a general document layout that suits either document.",
  },
];

function viewFor(pathname) {
  return VIEWS.find((view) => view.path === pathname) || VIEWS[0];
}

function readFavourites(userId) {
  const stored = readForUser(FAVOURITES, userId, []);
  return Array.isArray(stored) ? stored : [];
}

export default function TemplateGallery() {
  const navigate = useNavigate();
  const location = useLocation();

  // Which of the two entries the current URL is. Read from the route
  // rather than stored, so a bookmark or the Back button lands on the
  // view the address bar says it does.
  const view = viewFor(location.pathname);

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ai, setAi] = useState(null);

  // Search and the broad category the reader is browsing. Everything
  // else that used to live here (column, header, section-style chips,
  // four selects, two checkboxes) is still gone.
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState("all");

  const [shown, setShown] = useState([]);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [preview, setPreview] = useState(null);
  const [creating, setCreating] = useState("");

  // Lazy initialiser: read the account id once, the same way the
  // rest of the app does, rather than from an effect.
  const [userId] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("resumeai_user") || "{}").id
        ?? null;
    } catch {
      return null;
    }
  });

  const [favourites, setFavourites] = useState(() =>
    readFavourites(userId)
  );

  /*
   * A prompt, never a redirect.
   *
   * The gallery has to stay open to somebody with no profile at all:
   * browsing designs is the first step, and being thrown into a long
   * form before seeing anything is the thing this replaces. So an
   * empty profile produces one dismissible line with a link to My
   * Details, and the gallery carries on working either way.
   *
   * Only checked when signed in: an anonymous visitor has no profile
   * to be incomplete about.
   */
  const [profileHint, setProfileHint] = useState(null);

  useEffect(() => {
    // userId is read once when the component mounts and never
    // changes, so the signed-out case needs no state reset: the hint
    // starts as null and stays that way.
    if (!userId) return undefined;

    let cancelled = false;

    fetchCareerProfile()
      .then((data) => {
        if (cancelled) return;

        const profile = (data && data.profile) || {};
        const has = ["full_name", "email", "phone", "location", "skills"]
          .some((field) => profile[field]);

        if (has) {
          setProfileHint(null);
        } else {
          setProfileHint({
            kind: "empty",
            message:
              "Complete your profile to personalise your resume.",
          });
        }
      })
      .catch(() => {
        // Failing to read the profile must never stop the gallery.
        if (!cancelled) setProfileHint(null);
      });

    return () => {
      cancelled = true;
    };
  }, [userId]);

  // Debounce so typing does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);

  // Pure: builds the query, fetches, returns the payload. It sets no
  // state, so it can be called from an effect body without a
  // cascading render.
  const fetchPage = useCallback(
    async (offset) => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });

      if (debounced.trim()) params.set("q", debounced.trim());

      // The server filters by category, so the count line stays the
      // number that actually matches rather than a browser-side guess.
      if (category !== "all") params.set("category", category);

      return fetchResumeTemplates(params);
    },
    [debounced, category]
  );

  const applyPage = useCallback((payload, append) => {
    setData(payload);
    setTotal(payload.total);
    setShown((previous) =>
      append ? [...previous, ...payload.templates]
             : payload.templates
    );
    setError("");
  }, []);

  const reportError = useCallback((requestError) => {
    setError(
      requestError?.message || "Could not load the template library."
    );
  }, []);

  // Any change to the search or the category resets paging to the
  // first page.
  useEffect(() => {
    let cancelled = false;

    fetchPage(0)
      .then((payload) => {
        if (cancelled) return;
        applyPage(payload, false);
      })
      .catch((requestError) => {
        if (cancelled) return;
        reportError(requestError);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fetchPage, applyPage, reportError]);

  async function loadMore() {
    setLoadingMore(true);

    try {
      const payload = await fetchPage(shown.length);
      applyPage(payload, true);
    } catch (requestError) {
      reportError(requestError);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    fetchAiStatus()
      .then(setAi)
      .catch(() => {
        /* the gallery works without the AI badge */
      });
  }, []);

  const favouritesSet = useMemo(
    () => new Set(favourites),
    [favourites]
  );

  function toggleFavourite(key) {
    setFavourites((previous) => {
      const next = previous.includes(key)
        ? previous.filter((k) => k !== key)
        : [...previous, key];

      writeForUser(FAVOURITES, userId, next, []);

      return next;
    });
  }

  async function handleUse(template) {
    setCreating(template.key);

    try {
      const created = await createMyResume({
        title: `${template.name} ${view.key === "cv" ? "CV" : "Resume"}`,
        templateKey: template.key,
        // Seeded from the user's own Details when there is one. This
        // used to always send startEmpty, which opened a blank editor
        // even for somebody who had already filled in My Details -
        // the whole point of choosing a template is to see their own
        // details laid out in it.
        //
        // An anonymous visitor still gets the empty start: this route
        // is deliberately not behind the auth guard, so there is no
        // profile to read and from_profile would only produce the
        // same blank page. The server treats the two as exclusive -
        // from_profile is ignored when start_empty is also sent.
        fromProfile: Boolean(userId),
        startEmpty: !userId,
      });

      if (created) navigate(`/resume-builder/${created.id}`);
    } catch (requestError) {
      setError(
        requestError?.message || "Could not start that resume."
      );
    } finally {
      setCreating("");
    }
  }

  const facets = data?.facets;
  const categories = facets?.categories || data?.categories || [];
  const activeCategory =
    categories.find((entry) => entry.key === category) || null;
  const searching = Boolean(debounced.trim());

  if (loading && !data) {
    return (
      <div className="tg-page">
        <div className="tg-card tg-state">
          <div className="spinner" />
          <p>Loading the template library…</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="tg-page">
        <div className="tg-card tg-state">
          <h2>Could not load the library</h2>
          <p className="tg-error">{error}</p>
          <div className="tg-state-actions">
            <button
              type="button"
              className="tg-btn"
              onClick={() => window.location.reload()}
            >
              Try again
            </button>
            <Link to="/dashboard" className="tg-btn tg-btn-ghost">
              Back to dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="tg-page">
      <header className="tg-header">
        <div>
          <Link to="/dashboard" className="tg-back">
            ← Back to dashboard
          </Link>
          <h1>{view.title}</h1>
          <p className="tg-sub">
            {view.lede} Nothing here is a picture of a resume - every
            preview is drawn from the same layout the PDF uses.
          </p>
        </div>

        <div className="tg-header-actions">
          <Link to="/career-profile" className="tg-btn tg-btn-ghost">
            My Details
          </Link>
          <Link to="/my-resumes" className="tg-btn tg-btn-ghost">
            My Saved Resumes
          </Link>
        </div>
      </header>

      {/*
        A prompt, not a redirect. Browsing designs is the first thing
        anybody does here, and a visitor with no profile must still
        be able to do it.
      */}
      {profileHint && (
        <div className="tg-hint" role="status">
          <span>{profileHint.message}</span>
          <Link to="/career-profile" className="tg-hint-link">
            Edit Profile
          </Link>
          <button
            type="button"
            className="tg-hint-dismiss"
            onClick={() => setProfileHint(null)}
            aria-label="Dismiss this reminder"
          >
            ×
          </button>
        </div>
      )}

      <div className="tg-flow" aria-label="How this works">
        {/*
          Details come first everywhere else in the app: the details
          form and the resume editor both say "1 Enter Details". This
          page used to announce "1 Choose Template", so someone landing
          here was told to pick a design before they had written a word
          of the thing the design is for - and the two pages
          contradicted each other about the order.

          This is the gallery, so choosing is what happens *here*, but
          it is step two of the journey, not the whole of it.
        */}
        <span className="tg-flow-step">1 Enter Details</span>
        <span className="tg-flow-arrow">→</span>
        <span className="tg-flow-step is-current">2 Choose Template</span>
        <span className="tg-flow-arrow">→</span>
        <span className="tg-flow-step">3 Customise</span>
        <span className="tg-flow-arrow">→</span>
        <span className="tg-flow-step">4 Preview</span>
        <span className="tg-flow-arrow">→</span>
        <span className="tg-flow-step">5 Download PDF</span>
      </div>

      {/*
        The count is the server's `total` for whatever is currently
        being asked for - the whole catalogue with no filter, the
        category's own count when one is chosen, or the search
        result. `facets.total` is the catalogue-wide figure and is
        deliberately not used here: showing 124 while twelve cards
        are on screen was the one thing this line got wrong.
      */}
      <p className="tg-count-line" aria-live="polite">
        <strong>{total}</strong>{" "}
        {total === 1 ? "template" : "templates"}
        {activeCategory && <> in {activeCategory.label}</>}
        {!activeCategory && !searching && (
          <>{" · "}{facets?.ats_count ?? 0} ATS-friendly</>
        )}
        {searching && <> matching “{debounced.trim()}”</>}
      </p>

      {/* The broad categories the catalogue is organised into. The
          counts come from the server's facet list, so they describe
          the whole library rather than the current page. */}
      {categories.length > 0 && (
        <div
          className="tg-categories"
          role="group"
          aria-label="Template categories"
        >
          <button
            type="button"
            className={
              "tg-category" + (category === "all" ? " is-active" : "")
            }
            aria-pressed={category === "all"}
            onClick={() => setCategory("all")}
          >
            All
            <span>{facets?.total ?? total}</span>
          </button>

          {categories.map((entry) => (
            <button
              key={entry.key}
              type="button"
              className={
                "tg-category" +
                (category === entry.key ? " is-active" : "")
              }
              aria-pressed={category === entry.key}
              title={entry.blurb || entry.label}
              onClick={() => setCategory(entry.key)}
            >
              {entry.label}
              <span>{entry.count}</span>
            </button>
          ))}
        </div>
      )}

      {/*
        Resume / CV.

        Both open the one real catalogue, because the registry has no
        CV-only designs - every layout is a general document layout.
        Two links into the same page rather than one link pretending
        there are two sets, and the note below says so out loud
        instead of letting the reader assume otherwise.
      */}
      <div className="tg-views" role="tablist" aria-label="Template type">
        {VIEWS.map((entry) => {
          const current = entry.key === view.key;

          return (
            <Link
              key={entry.key}
              to={entry.path}
              role="tab"
              aria-selected={current}
              className={`tg-view ${current ? "is-current" : ""}`}
            >
              {entry.label}
            </Link>
          );
        })}
      </div>

      <p className="tg-shared-note">
        Resume and CV templates come from the same design library -
        every layout here suits either document. The two pages stay
        separate so you can bookmark the one you use.
      </p>

      {/*
        Search, and then the templates.

        This used to be followed by eleven filter controls: a row of
        column chips, a row of category chips, four selects and two
        checkboxes. They are gone. What remains searches the server's
        own `searchable` field, which covers each template's name,
        style, description, best-for and category - so "ats",
        "minimal" and "software" all find what they should.
      */}
      <div className="tg-toolbar">
        <input
          type="search"
          className="tg-search"
          placeholder="Search templates by name, style, or role..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search templates"
        />

        {searching && (
          <button
            type="button"
            className="tg-btn tg-btn-small tg-btn-ghost"
            onClick={() => setQuery("")}
          >
            Clear search
          </button>
        )}
      </div>

      {error && <p className="tg-error tg-error-inline">{error}</p>}

      <div className="tg-grid">
        {shown.map((template) => {
          const isFavourite = favouritesSet.has(template.key);

          return (
            <article
              key={template.key}
              className={`tg-card tg-tile ${
                preview?.key === template.key ? "selected" : ""
              }`}
            >
              <div className="tg-tile-frame">
                <button
                  type="button"
                  className="tg-tile-preview"
                  onClick={() => setPreview(template)}
                  aria-label={`Preview ${template.name}`}
                >
                  {/*
                    The real export, rasterised server-side.

                    This was a <ResumePreview> miniature - a third
                    implementation of a design whose actual renderer
                    is PyMuPDF. Nothing could catch the two
                    disagreeing, so the gallery could promise a layout
                    the download never produced. The image is page one
                    of the PDF itself: if a template looks wrong here,
                    it is wrong in the download too.
                  */}
                  <TemplateThumbnail
                    key={template.key}
                    template={template}
                  />
                </button>

                <button
                  type="button"
                  className={`tg-fav ${isFavourite ? "active" : ""}`}
                  onClick={() => toggleFavourite(template.key)}
                  aria-pressed={isFavourite}
                  aria-label={
                    isFavourite
                      ? `Remove ${template.name} from favourites`
                      : `Add ${template.name} to favourites`
                  }
                  title={
                    isFavourite ? "Remove from favourites"
                                : "Add to favourites"
                  }
                >
                  {isFavourite ? "★" : "☆"}
                </button>
              </div>

              <div className="tg-tile-body">
                <div className="tg-tile-head">
                  <h2 className="tg-tile-name">{template.name}</h2>
                  {/*
                    Only shown when the registry says so. This is a
                    worked-out property of the layout - single reading
                    order, standard headings, selectable text - not a
                    marketing label, which is why it is not a filter
                    and not on every card.
                  */}
                  {template.ats_friendly && (
                    <span className="tg-badge tg-badge-ats">ATS</span>
                  )}
                </div>

                <p className="tg-tile-desc">{template.description}</p>

                {template.category_label && (
                  <p className="tg-tile-cat">{template.category_label}</p>
                )}

                {template.best_for && (
                  <p className="tg-tile-best">
                    <strong>Best for:</strong> {template.best_for}
                  </p>
                )}

                <div className="tg-tile-actions">
                  <button
                    type="button"
                    className="tg-btn tg-btn-small"
                    onClick={() => handleUse(template)}
                    disabled={creating === template.key}
                  >
                    {creating === template.key
                      ? "Starting…"
                      : "Select Template"}
                  </button>
                  <button
                    type="button"
                    className="tg-btn tg-btn-small tg-btn-ghost"
                    onClick={() => setPreview(template)}
                  >
                    Preview
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {shown.length === 0 && (
        <div className="tg-card tg-empty">
          <h2>
            {searching
              ? <>No templates match “{debounced.trim()}”</>
              : <>No templates in this category</>}
          </h2>
          <p>
            {searching
              ? `Nothing in the ${total} registered templates matches that. Try a shorter word - a style such as "minimal", a role such as "software", or part of a template's name.`
              : "This category has no templates registered yet. Try another category, or show the whole catalogue."}
          </p>

          {searching ? (
            <button
              type="button"
              className="tg-btn"
              onClick={() => setQuery("")}
            >
              Clear search
            </button>
          ) : (
            <button
              type="button"
              className="tg-btn"
              onClick={() => setCategory("all")}
            >
              Show all templates
            </button>
          )}
        </div>
      )}

      {shown.length < total && (
        <div className="tg-more">
          <button
            type="button"
            className="tg-btn"
            onClick={() => loadMore()}
            disabled={loadingMore}
          >
            {loadingMore
              ? "Loading…"
              : `Load More (${shown.length} of ${total})`}
          </button>
        </div>
      )}

      {facets && data.disclaimer && (
        <p className="tg-disclaimer">{data.disclaimer}</p>
      )}

      {ai && !ai.configured && (
        <p className="tg-disclaimer">
          Writing suggestions are currently generated from your own
          resume text. Adding a Gemini API key enables richer{" "}
          <Link to="/dashboard">model-written suggestions</Link>.
        </p>
      )}

      {/*
        The modal renders only when the user asked for a specific
        preview. It used to fall back to the first template in the
        list, which meant it covered the entire gallery on page load
        and could never be dismissed.
      */}
      {preview && (
        <div
          className="tg-modal"
          role="dialog"
          aria-modal="true"
          aria-label={`${preview.name} preview`}
          onClick={() => setPreview(null)}
        >
          <div
            className="tg-modal-inner"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="tg-modal-head">
              <div>
                <h2 className="tg-modal-name">{preview.name}</h2>
                <p className="tg-modal-cat">
                  {preview.category_label} · {preview.layout_label}
                  {preview.ats_friendly ? " · ATS-friendly layout" : ""}
                </p>
              </div>
              <button
                type="button"
                className="tg-btn tg-btn-small tg-btn-ghost"
                onClick={() => setPreview(null)}
                aria-label="Close preview"
              >
                Close
              </button>
            </div>

            <div className="tg-modal-preview">
              <ResumePreview
                content={preview.sample}
                template={preview}
                settings={{
                  accent: preview.default_accent,
                  font: preview.default_font,
                }}
                emptyLabel=""
              />
            </div>

            <p className="tg-disclaimer">
              This preview uses fictional sample data so you can see
              the layout. It is never merged into your own resume.
            </p>

            <div className="tg-modal-actions">
              <button
                type="button"
                className="tg-btn"
                onClick={() => handleUse(preview)}
                disabled={creating === preview.key}
              >
                Select Template
              </button>
              <button
                type="button"
                className={`tg-btn tg-btn-ghost ${
                  favouritesSet.has(preview.key) ? "is-fav" : ""
                }`}
                onClick={() => toggleFavourite(preview.key)}
              >
                {favouritesSet.has(preview.key)
                  ? "★ Favourited"
                  : "☆ Add to favourites"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}