import { useState } from "react";
import ResumePreview from "./ResumePreview";
import { templateThumbnailUrl } from "../services/api";

/**
 * One template's thumbnail, rendered by the real PDF pipeline.
 *
 * What this replaced
 * ------------------
 * The gallery used to draw a miniature with <ResumePreview>, the same
 * React component the editor preview uses. That is a third
 * implementation of a design whose real renderer is PyMuPDF, and
 * `test_preview_parity.py` records the problem plainly: each is
 * correct on its own terms while showing the user something other
 * than what they get.
 *
 * So the image is the export. If a template looks wrong here, it is
 * wrong in the download too - which is the only honest version of a
 * preview.
 *
 * Failure is handled in three steps rather than one:
 *   - while loading, a neutral sheet, so the grid does not jump
 *   - on failure, the old React miniature, because a degraded
 *     approximation still beats an empty box
 *   - the browser's own decoding, so hundreds of A4 rasters do not
 *     stall the main thread at once
 */

export default function TemplateThumbnail({
  template,
  scale,
  className = "",
}) {
  /*
   * No effect resets this to "loading" when the template changes.
   * The gallery keys each tile by template.key, so a different
   * template is a different component instance and starts fresh
   * anyway - resetting it here would be a second render for nothing.
   */
  const [state, setState] = useState("loading");

  const src = templateThumbnailUrl(template.key, scale);

  return (
    <span className={`tg-shot ${className}`.trim()}>
      {state === "loading" && (
        <span
          className="tg-shot-loading"
          aria-hidden="true"
          data-testid="thumb-loading"
        />
      )}

      {state !== "fallback" && (
        <img
          className={`tg-shot-img ${
            state === "ready" ? "is-ready" : ""
          }`.trim()}
          src={src}
          alt={`${template.name} template preview`}
          loading="lazy"
          decoding="async"
          onLoad={() => setState("ready")}
          onError={() => setState("fallback")}
        />
      )}

      {/*
        The fallback. Kept deliberately: if thumbnail generation fails
        for one template, that tile degrades to the old approximation
        instead of showing a broken image, and the rest of the gallery
        is unaffected.
      */}
      {state === "fallback" && (
        <span className="tg-thumb tg-shot-fallback">
          <ResumePreview
            content={template.sample}
            template={template}
            settings={{
              accent: template.default_accent,
              font: template.default_font,
            }}
            emptyLabel=""
          />
        </span>
      )}
    </span>
  );
}