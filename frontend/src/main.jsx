import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App.jsx";

import "./index.css";

/*
 * Design tokens only.
 *
 * theme.css used to be imported here and carry 900 lines of shared
 * component rules with it, which - being imported last - overrode the
 * original styling on every page that had declared its own. It now
 * defines the --app-* vocabulary and nothing else, so pages keep the
 * look their own stylesheet gives them. See the header in theme.css.
 */
import "./theme.css";

/*
 * The shared card hover.
 *
 * Imported last, so where a page declared its own competing hover
 * this one wins and every clickable card in the app responds the
 * same way: a blue line down the left edge, a small lift, a blue
 * tinted border and shadow.
 *
 * It carries no layout, no borders and no typography - only the
 * hover response, and only for an explicit list of card classes.
 * See the header in cardHover.css for what was deliberately left
 * out and why.
 */
import "./cardHover.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);