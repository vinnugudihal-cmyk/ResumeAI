import SpecPreview from "./SpecPreview";
import "./ResumePreview.css";

/**
 * Live resume preview.
 *
 * Mirrors the layout the server will draw in the PDF so what the
 * user sees while editing matches what they download. It is a
 * preview, not the export: the PDF is produced by PyMuPDF and is
 * the authoritative file.
 *
 * Nothing is invented here. An empty section is simply not drawn,
 * exactly as the exporter does.
 *
 * Two kinds of template reach this component. The original twelve
 * carry `spec: null` and are drawn below, unchanged. Everything
 * newer carries a declarative specification and is handed to
 * SpecPreview, which walks the same axes the server's layout engine
 * does.
 */

const SECTION_TITLES = {
  summary: "Professional Summary",
  education: "Education",
  experience: "Work Experience",
  projects: "Projects",
  skills: "Skills",
  certifications: "Certifications",
  achievements: "Achievements",
  volunteering: "Volunteering",
  languages: "Languages",
  internships: "Internships",
  custom: "Additional Information",
};

function dateRange(entry) {
  const start = (entry.start || "").trim();
  const end = entry.current ? "Present" : (entry.end || "").trim();

  if (start && end) return `${start} – ${end}`;
  return start || end;
}

function Bullets({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <ul className="rp-bullets">
      {/* Bullets are plain text with no stable id, so the index is
          the honest key. */}
      {items.map((bullet, index) => (
        <li key={index}>{bullet}</li>
      ))}
    </ul>
  );
}

function Section({ name, entries, render }) {
  const list = entries || [];
  if (list.length === 0) return null;

  return (
    <section className="rp-section">
      <h3 className="rp-h">{SECTION_TITLES[name] || name}</h3>
      {list.map((entry, index) => render(entry, index))}
    </section>
  );
}

function Entry({ title, subtitle, meta, date, bullets, url }) {
  return (
    <div className="rp-entry">
      <div className="rp-entry-top">
        <strong className="rp-entry-title">{title}</strong>
        {date && <span className="rp-date">{date}</span>}
      </div>
      {subtitle && <div className="rp-entry-sub">{subtitle}</div>}
      {meta && <div className="rp-entry-meta">{meta}</div>}
      <Bullets items={bullets} />
      {url && <div className="rp-entry-url">{url}</div>}
    </div>
  );
}

export default function ResumePreview({
  content,
  template,
  settings,
  emptyLabel = "Your resume will appear here as you fill it in.",
  readable = false,
}) {
  // A specification is the exporter's own description of the
  // layout, so it is drawn by the engine that understands it. The
  // hand-built designs below never carry one and are untouched.
  if (template?.spec) {
    return (
      <SpecPreview
        content={content}
        template={template}
        spec={template.spec}
        settings={settings}
        emptyLabel={emptyLabel}
        readable={readable}
      />
    );
  }

  const data = content || {};
  const basics = data.basics || {};
  const skills = data.skills || {};

  const order =
    settings?.section_order?.length
      ? settings.section_order
      : Object.keys(SECTION_TITLES);

  const hidden = settings?.hidden_sections || [];
  const accent = settings?.accent || template?.default_accent || "#3155d9";
  const layout = template?.layout || "classic_single";

  const visible = order.filter((key) => !hidden.includes(key));

  const hasAnything =
    (basics.full_name || "").trim() ||
    (data.summary || "").trim() ||
    (skills.technical || []).length ||
    visible.some(
      (key) => (data[key] || []).length > 0
    );

  const renderers = {
    summary: () => {
      if (!(data.summary || "").trim()) return null;
      return (
        <section className="rp-section">
          <h3 className="rp-h">{SECTION_TITLES.summary}</h3>
          <p className="rp-summary">{data.summary}</p>
        </section>
      );
    },

    skills: () => {
      if (
        !(skills.technical || []).length &&
        !(skills.soft || []).length
      ) {
        return null;
      }
      return (
        <section className="rp-section">
          <h3 className="rp-h">{SECTION_TITLES.skills}</h3>
          {(skills.technical || []).length > 0 && (
            <p className="rp-skill-line">
              <span className="rp-skill-label">Technical</span>
              {skills.technical.join(" · ")}
            </p>
          )}
          {(skills.soft || []).length > 0 && (
            <p className="rp-skill-line">
              <span className="rp-skill-label">Soft</span>
              {skills.soft.join(" · ")}
            </p>
          )}
        </section>
      );
    },

    experience: () => (
      <Section
        name="experience"
        entries={data.experience}
        render={(entry) => (
          <Entry
            key={`${entry.role}-${entry.organisation}`}
            title={entry.role}
            subtitle={[entry.organisation, entry.location]
              .filter(Boolean)
              .join(" · ")}
            date={dateRange(entry)}
            bullets={entry.bullets}
          />
        )}
      />
    ),

    internships: () => (
      <Section
        name="internships"
        entries={data.internships}
        render={(entry) => (
          <Entry
            key={`${entry.role}-${entry.organisation}`}
            title={entry.role}
            subtitle={[entry.organisation, entry.location]
              .filter(Boolean)
              .join(" · ")}
            date={dateRange(entry)}
            bullets={entry.bullets}
          />
        )}
      />
    ),

    volunteering: () => (
      <Section
        name="volunteering"
        entries={data.volunteering}
        render={(entry) => (
          <Entry
            key={`${entry.role}-${entry.organisation}`}
            title={entry.role}
            subtitle={entry.organisation}
            date={dateRange(entry)}
            bullets={entry.bullets}
          />
        )}
      />
    ),

    education: () => (
      <Section
        name="education"
        entries={data.education}
        render={(entry) => (
          <Entry
            key={`${entry.degree}-${entry.organisation}`}
            title={entry.degree}
            subtitle={entry.organisation}
            meta={entry.location}
            date={dateRange(entry)}
          />
        )}
      />
    ),

    projects: () => (
      <Section
        name="projects"
        entries={data.projects}
        render={(entry) => (
          <Entry
            key={`${entry.name}-${entry.organisation}`}
            title={entry.name}
            subtitle={entry.organisation}
            date={dateRange(entry)}
            bullets={entry.bullets}
            url={entry.url}
          />
        )}
      />
    ),

    certifications: () => (
      <Section
        name="certifications"
        entries={data.certifications}
        render={(entry) => (
          <Entry
            key={`${entry.name}-${entry.organisation}`}
            title={entry.name}
            subtitle={entry.organisation}
            date={entry.date}
          />
        )}
      />
    ),

    achievements: () => (
      <Section
        name="achievements"
        entries={data.achievements}
        render={(entry) => (
          <Entry
            key={`${entry.title}-${entry.date}`}
            title={entry.title}
            meta={entry.detail}
            date={entry.date}
          />
        )}
      />
    ),

    languages: () => (
      <Section
        name="languages"
        entries={data.languages}
        render={(entry) => (
          <p className="rp-skill-line" key={`${entry.name}`}>
            <strong>{entry.name}</strong>
            {entry.level ? ` · ${entry.level}` : ""}
          </p>
        )}
      />
    ),

    custom: () => {
      const blocks = data.custom || [];
      if (blocks.length === 0) return null;
      return blocks.map((block) => (
        <section className="rp-section" key={block.heading}>
          <h3 className="rp-h">{block.heading}</h3>
          <Bullets items={block.lines} />
        </section>
      ));
    },
  };

  const railKeys = ["skills", "education", "certifications", "languages"];

  const mainBlocks = visible
    .filter((key) => renderers[key])
    .map((key) => {
      const node = renderers[key]();

      if (!node) return null;

      // A side rail carries the short sections; the main column
      // must not repeat them.
      if (
        (layout === "sidebar_left" || layout === "sidebar_right") &&
        railKeys.includes(key)
      ) {
        return null;
      }

      return (
        <div key={key} className={`rp-block rp-block-${key}`}>
          {node}
        </div>
      );
    });

  const railBlocks =
    layout === "sidebar_left" || layout === "sidebar_right"
      ? visible
          .filter((key) => railKeys.includes(key) && renderers[key])
          .map((key) => {
            const node = renderers[key]();
            return node ? (
              <div key={`rail-${key}`} className={`rp-block rp-block-${key}`}>
                {node}
              </div>
            ) : null;
          })
      : null;

  const contact = [
    basics.email,
    basics.phone,
    basics.location,
    basics.linkedin,
    basics.github,
    basics.website,
  ]
    .filter(Boolean)
    .join("  ·  ");

  const railContact = [
    basics.email,
    basics.phone,
    basics.location,
    basics.linkedin,
    basics.github,
    basics.website,
  ]
    .filter(Boolean);

  const centredHeader = layout === "minimal_centered";
  const banner =
    layout === "header_band" || layout === "executive_banner";

  const body = (
    <>
      {railBlocks && railBlocks.length > 0 && (
        <aside
          className={`rp-rail ${
            layout === "sidebar_right" ? "rp-rail-right" : "rp-rail-left"
          }`}
        >
          {railBlocks}
        </aside>
      )}

      <div className="rp-main">
        {!banner && (
          <header className={`rp-head ${centredHeader ? "rp-centre" : ""}`}>
            {centredHeader ? (
              <>
                <h1 className="rp-name">{basics.full_name || "Your Name"}</h1>
                {basics.headline && (
                  <p className="rp-headline">{basics.headline}</p>
                )}
              </>
            ) : (
              <>
                <h1 className="rp-name">{basics.full_name || "Your Name"}</h1>
                {basics.headline && (
                  <p className="rp-headline">{basics.headline}</p>
                )}
              </>
            )}
            {contact && <p className="rp-contact">{contact}</p>}
          </header>
        )}

        {banner && (
          <header className="rp-banner">
            {layout === "executive_banner" && basics.headline && (
              <p className="rp-banner-kicker">{basics.headline}</p>
            )}
            <h1 className="rp-banner-name">
              {basics.full_name || "Your Name"}
            </h1>
            {contact && <p className="rp-banner-contact">{contact}</p>}
          </header>
        )}

        {mainBlocks}

        {!hasAnything && (
          <p className="rp-empty">{emptyLabel}</p>
        )}
      </div>
    </>
  );

  const railContactBlock =
    railContact.length > 0 && railBlocks ? (
      <div className="rp-rail-contact">
        {railContact.map((item) => (
          <div key={item}>{item}</div>
        ))}
      </div>
    ) : null;

  return (
    <div
      className={`rp-sheet rp-${layout} rp-font-${settings?.font || "classic"}`}
      style={{ "--rp-accent": accent }}
    >
      {layout === "sidebar_left" && railContactBlock && railContactBlock}
      {body}
      {layout === "sidebar_right" && railContactBlock && railContactBlock}
    </div>
  );
}
