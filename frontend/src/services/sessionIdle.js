/**
 * Inactivity timeout, read once at load.
 *
 * Kept out of the provider module so that module can export only a
 * component, which is what the fast-refresh lint rule wants, and so
 * reading localStorage happens in a plain module rather than
 * somewhere that looks like render.
 */

export const DEFAULT_IDLE_MINUTES = 15;

/**
 * Events that count as the user still being here.
 *
 * `mousemove` is deliberately absent: it fires constantly while a
 * pointer merely rests over the window, and a timer reset by a
 * jittering sensor is not an inactivity timer at all.
 */
export const IDLE_EVENTS = [
  "mousedown",
  "keydown",
  "touchstart",
  "scroll",
  "focus",
];

export function readIdleMinutes() {
  let raw;

  try {
    raw = window.localStorage.getItem("resumeai_idle_minutes");
  } catch {
    // Private browsing modes can refuse storage. The default is
    // fine, and nothing here is worth failing to load over.
    return DEFAULT_IDLE_MINUTES;
  }

  const parsed = Number.parseInt(raw ?? "", 10);

  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_IDLE_MINUTES;
  }

  // A ceiling, because a number typed into localStorage by hand is
  // not something to hand straight to setInterval.
  return Math.min(parsed, 24 * 60);
}

export function storeIdleMinutes(minutes) {
  const parsed = Number(minutes);

  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_IDLE_MINUTES;
  }

  const clamped = Math.min(Math.round(parsed), 24 * 60);

  try {
    window.localStorage.setItem("resumeai_idle_minutes", String(clamped));
  } catch {
    /* storage refused; the default still applies for this session */
  }

  return clamped;
}