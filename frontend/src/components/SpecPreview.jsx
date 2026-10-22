import "./SpecPreview.css";

/**
 * Declarative preview.
 *
 * The server draws generated templates from a small specification
 * rather than from a hand-written function per design
 * (`ai-service/layout_engine.py`). This component is the browser
 * half of that engine: one renderer that walks the same
 * specification, so a card in the gallery shows the layout the
 * exporter will actually produce.
 *
 * Every vocabulary value below mirrors the one in layout_engine.py.
 * If a value is added there, it must be added here too, otherwise a
 * generated template silently falls back to the default and the
 * preview lies.
 *
 * The original twelve designs carry `spec: null` and are rendered by
 * ResumePreview instead. Nothing in this file touches them.
 */

/* Section wording is fixed, not invented, so a parser recognises it.
   Mirrors templates_catalog.SECTION_LABELS. */
const SECTION_LABELS = {
  summary: "Professional Summary",
  education: "Education",
  experience: "Work Experience",
  internships: "Internships",
  projects: "Projects",
  skills: "Skills",
  certifications: "Certifications",
  achievements: "Achievements",
  volunteering: "Volunteering",
  languages: "Languages",
  custom: "Additional Information",
};

/* layout_engine._draw_heading numbers a section by its position in
   SECTION_LABELS, not by its position on the page. A resume that
   leads with education still numbers Education 02. */
const SECTION_NUMBER = {
  summary: 1,
  education: 2,
  experience: 3,
  internships: 4,
  projects: 5,
  skills: 6,
  certifications: 7,
  achievements: 8,
  volunteering: 9,
  languages: 10,
  custom: 11,
};

/* layout_engine.order_for. */
const SECTION_ORDERS = {
  summary_first: [
    "summary", "experience", "projects", "skills", "education",
    "internships", "certifications", "achievements", "volunteering",
    "languages", "custom",
  ],
  experience_first: [
    "summary", "experience", "internships", "projects", "skills",
    "education", "certifications", "achievements", "volunteering",
    "languages", "custom",
  ],
  education_first: [
    "summary", "education", "skills", "experience", "internships",
    "projects", "certifications", "achievements", "volunteering",
    "languages", "custom",
  ],
  skills_last: [
    "summary", "experience", "internships", "projects", "education",
    "certifications", "achievements", "volunteering", "skills",
    "languages", "custom",
  ],
};

/* layout_engine.RAIL_FITTED minus achievements: the engine skips
   achievements in the body column but sidebar_sections never draws
   them in the rail, so following both rules exactly would drop the
   section from the preview entirely. They are kept in the body here
   instead, which is what a reader expects to find. */
const RAIL_SECTIONS = [
  "skills",
  "education",
  "certifications",
  "languages",
];

/* layout_engine.default_spec. An unknown or missing axis falls back
   to the same default the exporter would use. */
const DEFAULT_SPEC = {
  header: "ruled",
  section_style: "ruled",
  entry_style: "plain",
  skill_style: "labelled",
  rail: "none",
  rail_width: 0.34,
  rail_fill: false,
  section_order: "summary_first",
  density: "normal",
  font: "classic",
};

/* layout_engine.validate: the axes it is willing to draw. */
const ALLOWED = {
  header: [
    "plain", "centred", "ruled", "banded", "stacked", "boxed",
    "banner", "split",
  ],
  section_style: [
    "ruled", "underlined", "accent_bar", "boxed", "plain",
    "centred_rule", "numbered",
  ],
  entry_style: [
    "plain", "timeline", "dotted", "boxed", "underline", "tight",
  ],
  skill_style: ["labelled", "inline", "bullets", "columns"],
  rail: ["none", "left", "right"],
  section_order: [
    "summary_first", "experience_first", "education_first", "skills_last",
  ],
  density: ["compact", "normal", "relaxed"],
  font: ["classic", "modern", "serif"],
};

/* resume_pdf.Theme: spacing metrics per density, as multiples of the
   11pt page text the PDF draws them at. */
const DENSITY_TIGHT_GAP = {
  compact: "0.18em",
  normal: "0.36em",
  relaxed: "0.55em",
};

function cleanSpec(spec) {
  const clean = { ...DEFAULT_SPEC };

  if (!spec || typeof spec !== "object") return clean;

  Object.keys(ALLOWED).forEach((key) => {
    if (ALLOWED[key].includes(spec[key])) {
      clean[key] = spec[key];
    }
  });

  if (clean.rail !== "none") {
    const width = Number(spec.rail_width);

    if (Number.isFinite(width) && width >= 0.25 && width <= 0.42) {
      clean.rail_width = Math.round(width * 1000) / 1000;
    }
  }

  clean.rail_fill = Boolean(spec.rail_fill);

  return clean;
}

/* resume_pdf._hex_to_rgb / _shade. The Python multiplies each channel
   and clamps, rather than blending towards white, so a very saturated
   accent washes out to near-white exactly as it does in the PDF. */
function shade(hex, factor) {
  const fallback = [0.19, 0.33, 0.85];
  const channels =
    typeof hex === "string" && hex.startsWith("#")
      ? [1, 3, 5].map((i) => {
          const value = parseInt(hex.slice(i, i + 2), 16);
          return Number.isNaN(value) ? fallback[(i - 1) / 2] : value / 255;
        })
      : fallback;

  const scaled = channels
    .map((c) => Math.round(Math.min(1, Math.max(0, c * factor)) * 255))
    .join(", ");

  return `rgb(${scaled})`;
}

function dateRange(entry) {
  const start = (entry.start || "").trim();
  const end = entry.current ? "Present" : (entry.end || "").trim();

  if (start && end) return `${start} – ${end}`;
  return start || end;
}

/* layout_engine._entry_parts. One stored entry, four drawing slots. */
function entryParts(key, entry) {
  if (key === "languages") {
    return {
      title: entry.name,
      subtitle: entry.level,
      meta: "",
      bullets: [],
      dates: "",
    };
  }

  if (key === "certifications") {
    return {
      title: entry.name,
      subtitle: entry.organisation,
      meta: entry.date,
      bullets: [],
      dates: "",
    };
  }

  if (key === "achievements") {
    return {
      title: entry.title,
      subtitle: entry.organisation,
      meta: entry.date,
      bullets: entry.detail ? [entry.detail] : [],
      dates: "",
    };
  }

  if (key === "projects") {
    return {
      title: entry.name,
      subtitle: entry.organisation,
      meta: "",
      bullets: entry.bullets || [],
      dates: dateRange(entry),
    };
  }

  if (key === "education") {
    return {
      title: entry.degree,
      subtitle: entry.organisation,
      meta: entry.location,
      bullets: [],
      dates: dateRange(entry),
    };
  }

  return {
    title: entry.role || entry.title,
    subtitle: entry.organisation,
    meta: entry.location,
    bullets: entry.bullets || [],
    dates: dateRange(entry),
  };
}

/* resume_pdf.section_has_content. An empty section is never drawn. */
function sectionHasContent(key, content) {
  if (key === "summary") return Boolean((content.summary || "").trim());

  if (key === "skills") {
    const skills = content.skills || {};
    return Boolean(
      (skills.technical || []).length || (skills.soft || []).length
    );
  }

  return Boolean((content[key] || []).length);
}

function SectionHeading({ spec, sectionKey, title }) {
  const text = (title || "").toUpperCase();
  const style = spec.section_style;

  if (style === "centred_rule") {
    return <h3 className="sp-h sp-h-centred">{text}</h3>;
  }

  if (style === "numbered") {
    // A block with no section key (a custom block) numbers as 01,
    // which is what the engine does for a key it cannot place.
    const index = SECTION_NUMBER[sectionKey] || 1;

    return (
      <h3 className="sp-h sp-h-numbered">
        <span className="sp-h-num">{String(index).padStart(2, "0")}</span>
        <span className="sp-h-text">{text}</span>
      </h3>
    );
  }

  if (style === "accent_bar") {
    return (
      <h3 className="sp-h sp-h-bar">
        <span className="sp-h-bar-mark" aria-hidden="true" />
        <span className="sp-h-text">{text}</span>
      </h3>
    );
  }

  if (style === "boxed") {
    return (
      <div className="sp-h-box">
        <h3 className="sp-h sp-h-bare">{text}</h3>
      </div>
    );
  }

  if (style === "underlined") {
    return <h3 className="sp-h sp-h-underline">{text}</h3>;
  }

  if (style === "plain") {
    return <h3 className="sp-h sp-h-bare">{text}</h3>;
  }

  return <h3 className="sp-h">{text}</h3>;
}

function SkillLines({ skills }) {
  const technical = skills.technical || [];
  const soft = skills.soft || [];

  if (!technical.length && !soft.length) return null;

  return (
    <div className="sp-skills">
      {technical.length > 0 && (
        <p className="sp-skill-line">
          <span className="sp-skill-items">{technical.join(" • ")}</span>
          <b className="sp-skill-label">Technical</b>
        </p>
      )}
      {soft.length > 0 && (
        <p className="sp-skill-line">
          <span className="sp-skill-items">{soft.join(" • ")}</span>
          <b className="sp-skill-label">Soft</b>
        </p>
      )}
    </div>
  );
}

function SkillBlock({ spec, skills }) {
  const technical = skills.technical || [];
  const soft = skills.soft || [];
  const everything = [...technical, ...soft];

  if (!everything.length) return null;

  if (spec.skill_style === "inline") {
    return <p className="sp-skill-inline">{everything.join(" · ")}</p>;
  }

  if (spec.skill_style === "bullets") {
    return (
      <ul className="sp-bullets">
        {everything.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    );
  }

  if (spec.skill_style === "columns") {
    // The engine alternates skill by skill into two columns. Stored
    // content has no named groups, so there is nothing to repeat as
    // a column label.
    const left = everything.filter((_, i) => i % 2 === 0);
    const right = everything.filter((_, i) => i % 2 === 1);

    return (
      <div className="sp-skill-columns">
        <ul className="sp-bullets">
          {left.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
        <ul className="sp-bullets">
          {right.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </div>
    );
  }

  return <SkillLines skills={skills} />;
}

// `showTitle` is not a detail. Five entry styles call this, and
// three of them - underline, dotted and the default - already draw
// the title in their own header row so it can sit on the same line
// as the dates. Drawing it here as well put a second copy of the
// title into the middle of every one of those entries: in the
// gallery thumbnails it read as two different resumes side by side.
function EntryBody({ parts, italicMeta, showTitle = false }) {
  return (
    <>
      {showTitle && parts.title && (
        <strong className="sp-entry-title">{parts.title}</strong>
      )}
      {parts.subtitle && (
        <div className="sp-entry-sub">{parts.subtitle}</div>
      )}
      {parts.meta && (
        <div
          className={`sp-entry-meta ${
            italicMeta ? "sp-entry-meta-italic" : ""
          }`}
        >
          {parts.meta}
        </div>
      )}
      {parts.bullets.length > 0 && (
        <ul className="sp-bullets">
          {parts.bullets.map((bullet, index) => (
            <li key={index}>{bullet}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function Entry({ spec, parts, showDates = true }) {
  const style = spec.entry_style;
  const dates = showDates ? parts.dates : "";

  if (style === "timeline") {
    return (
      <div className="sp-entry sp-entry-timeline">
        <div className="sp-tl-side">
          {dates && <span className="sp-tl-date">{dates}</span>}
          <span className="sp-tl-dot" aria-hidden="true" />
        </div>
        <div className="sp-tl-body">
          <EntryBody parts={parts} showTitle />
        </div>
      </div>
    );
  }

  if (style === "dotted") {
    return (
      <div className="sp-entry sp-entry-dotted">
        <div className="sp-dot-head">
          {parts.title && (
            <strong className="sp-entry-title">{parts.title}</strong>
          )}
          {dates && (
            <>
              <span className="sp-dot-leader" aria-hidden="true" />
              <span className="sp-date">{dates}</span>
            </>
          )}
        </div>
        <EntryBody parts={parts} italicMeta />
      </div>
    );
  }

  if (style === "boxed") {
    return (
      <div className="sp-entry sp-entry-boxed">
        <EntryBody parts={{ ...parts, dates: "" }} showTitle />
        {parts.dates && <span className="sp-date">{parts.dates}</span>}
      </div>
    );
  }

  if (style === "underline") {
    return (
      <div className="sp-entry sp-entry-underline">
        <div className="sp-entry-head">
          {parts.title && (
            <strong className="sp-entry-title">{parts.title}</strong>
          )}
          {dates && <span className="sp-date">{dates}</span>}
        </div>
        <EntryBody parts={parts} />
      </div>
    );
  }

  const tight = style === "tight" ? " sp-entry-tight" : "";

  return (
    <div className={`sp-entry${tight}`}>
      <div className="sp-entry-head">
        {parts.title && (
          <strong className="sp-entry-title">{parts.title}</strong>
        )}
        {dates && <span className="sp-date">{dates}</span>}
      </div>
      <EntryBody parts={parts} />
    </div>
  );
}

function SpecHeader({ spec, basics }) {
  const name = basics.full_name || "Your Name";
  const headline = (basics.headline || "").trim();

  const contactParts = [
    basics.email,
    basics.phone,
    basics.location,
    basics.linkedin,
    basics.github,
    basics.website,
  ].filter(Boolean);

  const contact = contactParts.join("  ·  ");

  if (spec.header === "banner") {
    return (
      <header className="sp-head sp-head-banner">
        <h1 className="sp-banner-name">{name}</h1>
        {contact && <p className="sp-banner-contact">{contact}</p>}
      </header>
    );
  }

  if (spec.header === "banded") {
    return (
      <>
        <header className="sp-head sp-head-banded">
          <h1 className="sp-name">{name}</h1>
          {headline && <p className="sp-headline sp-headline-muted">{headline}</p>}
        </header>
        {contact && <p className="sp-contact sp-contact-below">{contact}</p>}
      </>
    );
  }

  if (spec.header === "boxed") {
    return (
      <header className="sp-head sp-head-boxed">
        <h1 className="sp-name sp-name-centre">{name}</h1>
        {headline && <p className="sp-headline sp-headline-centre">{headline}</p>}
        {contact && <p className="sp-contact sp-contact-centre">{contact}</p>}
      </header>
    );
  }

  if (spec.header === "centred") {
    return (
      <header className="sp-head sp-head-centred">
        <h1 className="sp-name sp-name-centre">{name}</h1>
        {headline && <p className="sp-headline sp-headline-centre">{headline}</p>}
        {contact && <p className="sp-contact sp-contact-centre">{contact}</p>}
      </header>
    );
  }

  if (spec.header === "split") {
    return (
      <header className="sp-head sp-head-split">
        <h1 className="sp-name">{name}</h1>
        <div className="sp-split-contact">
          {contactParts.slice(0, 4).map((item, index) => (
            <span key={index}>{item}</span>
          ))}
        </div>
      </header>
    );
  }

  if (spec.header === "stacked") {
    return (
      <header className="sp-head sp-head-stacked">
        <h1 className="sp-name sp-name-small">{name}</h1>
        {headline && <p className="sp-headline">{headline}</p>}
        {contact && <p className="sp-contact">{contact}</p>}
      </header>
    );
  }

  if (spec.header === "ruled") {
    return (
      <header className="sp-head sp-head-ruled">
        <h1 className="sp-name">{name}</h1>
        {headline && <p className="sp-headline sp-headline-muted">{headline}</p>}
        {contact && <p className="sp-contact">{contact}</p>}
        <div className="sp-accent-rule" aria-hidden="true" />
      </header>
    );
  }

  return (
    <header className="sp-head sp-head-plain">
      <h1 className="sp-name sp-name-small">{name}</h1>
      {headline && <p className="sp-headline sp-headline-muted">{headline}</p>}
      {contact && <p className="sp-contact">{contact}</p>}
    </header>
  );
}

function RailHeader({ basics }) {
  const contactParts = [
    basics.email,
    basics.phone,
    basics.location,
    basics.linkedin,
    basics.github,
    basics.website,
  ].filter(Boolean);

  return (
    <div className="sp-rail-head">
      <h1 className="sp-rail-name">{basics.full_name || "Your Name"}</h1>
      {(basics.headline || "").trim() && (
        <p className="sp-rail-headline">{basics.headline.trim()}</p>
      )}
      {contactParts.map((item, index) => (
        <p className="sp-rail-contact-line" key={index}>
          {item}
        </p>
      ))}
    </div>
  );
}

/* layout_engine._draw_body_header: with a rail, the name already sits
   in the rail, so the body gets only the headline. */
function BodyHeader({ spec, basics }) {
  const headline = (basics.headline || "").trim();

  if (!headline) return null;

  const ruled = ["ruled", "banded", "boxed"].includes(spec.header);

  return (
    <div className="sp-body-head">
      <p className="sp-body-headline">{headline}</p>
      {ruled && <div className="sp-accent-rule" aria-hidden="true" />}
    </div>
  );
}

export default function SpecPreview({
  content,
  template,
  spec,
  settings,
  emptyLabel = "Your resume will appear here as you fill it in.",
  readable = false,
}) {
  const data = content || {};
  const basics = data.basics || {};
  const skills = data.skills || {};

  const clean = cleanSpec(spec);

  // The exporter builds its theme from the resume's settings and only
  // then walks the spec, so a chosen font or density still wins.
  const accent = settings?.accent || template?.default_accent || "#3155d9";
  const font = settings?.font || template?.default_font || clean.font;
  const density = settings?.density || clean.density;

  // layout_engine.order_for: the spec decides the order, and anything
  // the spec omits is appended so a section cannot disappear.
  const order = [...(SECTION_ORDERS[clean.section_order] ||
    SECTION_ORDERS.summary_first)];
  const hidden = settings?.hidden_sections || [];

  (settings?.section_order || []).forEach((key) => {
    if (!order.includes(key)) order.push(key);
  });

  const visible = order.filter(
    (key) =>
      SECTION_LABELS[key] && !hidden.includes(key)
  );

  const hasRail = clean.rail !== "none";

  const railKeys = hasRail
    ? visible.filter(
        (key) =>
          RAIL_SECTIONS.includes(key) && sectionHasContent(key, data)
      )
    : [];

  const bodyKeys = visible.filter(
    (key) => !railKeys.includes(key) && sectionHasContent(key, data)
  );

  const renderSection = (key, inRail) => {
    if (key === "summary") {
      return (
        <section className="sp-section" key={key}>
          <SectionHeading
            spec={clean}
            sectionKey="summary"
            title={SECTION_LABELS.summary}
          />
          <p className="sp-summary">{data.summary}</p>
        </section>
      );
    }

    if (key === "skills") {
      return (
        <section className="sp-section" key={key}>
          <SectionHeading
            spec={clean}
            sectionKey="skills"
            title={SECTION_LABELS.skills}
          />
          {inRail ? (
            <SkillLines skills={skills} />
          ) : (
            <SkillBlock spec={clean} skills={skills} />
          )}
        </section>
      );
    }

    if (key === "custom") {
      return (data.custom || []).map((block, index) => (
        <section className="sp-section" key={`custom-${index}`}>
          <SectionHeading spec={clean} sectionKey={null} title={block.heading} />
          <ul className="sp-bullets">
            {(block.lines || []).map((line, lineIndex) => (
              <li key={lineIndex}>{line}</li>
            ))}
          </ul>
        </section>
      ));
    }

    if (key === "languages" && inRail) {
      // The rail prints a language as one run-on line rather than as
      // a bold entry with an accent subtitle.
      return (
        <section className="sp-section" key={key}>
          <SectionHeading
            spec={clean}
            sectionKey="languages"
            title={SECTION_LABELS.languages}
          />
          {(data.languages || []).map((entry, index) => (
            <p className="sp-rail-line" key={index}>
              {[entry.name, entry.level].filter(Boolean).join(" • ")}
            </p>
          ))}
        </section>
      );
    }

    const entries = data[key] || [];

    if (!entries.length) return null;

    return (
      <section className="sp-section" key={key}>
        <SectionHeading
          spec={clean}
          sectionKey={key}
          title={SECTION_LABELS[key]}
        />
        {entries.map((entry, index) => {
          const parts = entryParts(key, entry);

          if (inRail && key === "education") {
            return (
              <div className="sp-entry sp-entry-tight" key={index}>
                <strong className="sp-entry-title">{parts.title}</strong>
                <div className="sp-entry-meta">
                  {[parts.subtitle, parts.dates].filter(Boolean).join(" • ")}
                </div>
              </div>
            );
          }

          if (inRail && key === "certifications") {
            return (
              <div className="sp-entry sp-entry-tight" key={index}>
                <div className="sp-rail-body">{parts.title}</div>
                {parts.meta && (
                  <div className="sp-entry-meta">{parts.meta}</div>
                )}
              </div>
            );
          }

          return (
            <Entry
              key={index}
              spec={clean}
              parts={parts}
              showDates={!inRail}
            />
          );
        })}
      </section>
    );
  };

  const hasAnything =
    (basics.full_name || "").trim() ||
    (data.summary || "").trim() ||
    (skills.technical || []).length ||
    (skills.soft || []).length ||
    bodyKeys.length > 0;

  const railClass = [
    "sp-rail",
    clean.rail === "right" ? "sp-rail-right" : "sp-rail-left",
    clean.rail_fill ? "sp-rail-fill" : "sp-rail-line",
  ].join(" ");

  return (
    <div
      className={[
        "sp-sheet",
        `sp-font-${font}`,
        `sp-density-${density}`,
        `sp-header-${clean.header}`,
        hasRail ? "sp-has-rail" : "",
        readable ? "sp-readable" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{
        "--sp-accent": accent,
        "--sp-accent-soft": shade(accent, 1.9),
        "--sp-rail-faded": shade(accent, 1.75),
        "--sp-rail-width": `${Math.round(clean.rail_width * 100)}%`,
        "--sp-tight-gap": DENSITY_TIGHT_GAP[density] ||
          DENSITY_TIGHT_GAP.normal,
      }}
    >
      {hasRail && (
        <aside className={railClass}>
          <RailHeader basics={basics} />
          {railKeys.map((key) => renderSection(key, true))}
        </aside>
      )}

      <div className="sp-main">
        {hasRail ? (
          <BodyHeader spec={clean} basics={basics} />
        ) : (
          <SpecHeader spec={clean} basics={basics} />
        )}

        {bodyKeys.map((key) => renderSection(key, false))}

        {!hasAnything && <p className="sp-empty">{emptyLabel}</p>}
      </div>
    </div>
  );
}
