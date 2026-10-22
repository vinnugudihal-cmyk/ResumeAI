/**
 * The dashboard you land on after signing in.
 *
 * A launcher, not a second home page: it says what the app can do,
 * and every card goes to the place that does it. The analysis panel
 * stays below it on the same route, so nothing that used to live at
 * /dashboard has moved.
 *
 * Ten features in a fixed order, laid out the way the reference
 * dashboard is: two large cards side by side at the top - Create My
 * Resume and Analyze My Resume - then a small uppercase label and a
 * three-column grid of the other eight compact cards.
 *
 * The split between the large pair and the compact grid is by
 * position in `DASHBOARD_CARDS`, not by a flag on any feature, so
 * the prominent pair is fixed and the two are always equal to each
 * other. There is no "next section", no gate and no step order -
 * every card is reachable from the top of the page.
 *
 * The icons are inline SVG rather than an icon font or a package. A
 * handful of glyphs are not worth a dependency, and inline SVG
 * inherits currentColor, so a card in any state draws its own icon.
 */

import { useMemo } from "react";
import { Link } from "react-router-dom";

import {
  DASHBOARD_CARDS,
  FEATURE_BY_KEY,
  destinationFor,
} from "../services/features";
import "./Landing.css";

const PATHS = {
  create: <path d="M12 5v14M5 12h14" />,
  analyse: (
    <>
      <path d="M5 3.5h9l5 5V20a1 1 0 01-1 1H5a1 1 0 01-1-1V4.5a1 1 0 011-1z" />
      <path d="M14 3.5V9h5" />
      <circle cx="11.5" cy="14" r="3" />
      <path d="M13.8 16.3L16 18.5" />
    </>
  ),
  jobs: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2.5" />
      <path d="M9 7V5.5A1.5 1.5 0 0110.5 4h3A1.5 1.5 0 0115 5.5V7" />
      <path d="M3 12h18" />
    </>
  ),
  applications: (
    <>
      <rect x="4" y="3.5" width="16" height="17" rx="2.5" />
      <path d="M8.5 9.5h7M8.5 13h7M8.5 16.5h4" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8.5" r="4" />
      <path d="M4.5 20a7.5 7.5 0 0115 0" />
    </>
  ),
  saved: (
    <path d="M6.5 4h11a1 1 0 011 1v15.2a.6.6 0 01-.93.5L12 16.6l-5.57 4.1a.6.6 0 01-.93-.5V5a1 1 0 011-1z" />
  ),
  letter: (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
      <path d="M4 7l8 5.5L20 7" />
    </>
  ),
};

function Icon({ name }) {
  return (
    <svg
      className="land-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name] || PATHS.create}
    </svg>
  );
}

export default function Landing() {
  /*
    The ten tools, in drawing order, resolved once against
    FEATURE_BY_KEY. A key with no matching feature is dropped rather
    than drawn as an empty tile, so a typo in the list cannot produce
    a card with no label and no destination.

    The first two are the large cards and the other eight are the
    compact grid below them. That split is by POSITION in
    DASHBOARD_CARDS, not by a flag on the feature, so the prominent
    pair cannot drift and neither of the two can be ranked above the
    other.
  */
  const cards = useMemo(
    () =>
      DASHBOARD_CARDS
        .map((key) => FEATURE_BY_KEY[key])
        .filter(Boolean),
    []
  );

  const primary = cards.slice(0, 2);
  const secondary = cards.slice(2);

  return (
    <div className="land">
      <header className="land-intro">
        <h1 className="land-title">How can I help you today?</h1>

        <p className="land-lede">
          Pick a tool and get straight to it. Nothing here has to be
          done before anything else.
        </p>
      </header>

      {/*
        Two large cards, side by side.

        Each is one real <Link>, so the whole surface is clickable and
        focusable in a single stop. The pill is a span inside that
        link rather than a nested button - two links, or a button
        inside a link, is announced as two separate stops and is
        invalid markup.
      */}
      <div className="land-hero-row">
        {primary.map((feature) => (
          <Link
            key={feature.key}
            to={destinationFor(feature)}
            className="land-hero-card"
          >
            <span className="land-hero-icon" aria-hidden="true">
              <Icon name={feature.icon} />
            </span>

            <span className="land-hero-text">
              <span className="land-hero-title">{feature.label}</span>
              <span className="land-hero-blurb">{feature.blurb}</span>
            </span>

            <span className="land-pill">{feature.action}</span>
          </Link>
        ))}
      </div>

      {secondary.length > 0 && (
        <>
          <p className="land-section-label">All features</p>

          <div className="land-grid">
            {secondary.map((feature) => (
              <Link
                key={feature.key}
                to={destinationFor(feature)}
                className="land-card"
              >
                <span className="land-card-icon" aria-hidden="true">
                  <Icon name={feature.icon} />
                </span>

                <span className="land-card-text">
                  <span className="land-card-title">
                    {feature.label}
                  </span>
                  <span className="land-card-blurb">{feature.blurb}</span>
                </span>

                <span className="land-card-action">
                  {feature.action}
                  <span aria-hidden="true">&rarr;</span>
                </span>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
