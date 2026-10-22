/**
 * Time-of-day greeting for the dashboard.
 *
 * Split out rather than inlined so the hour boundary is one testable
 * function instead of a ternary buried in a component, and so the
 * dashboard does not have to know what time it is.
 *
 * Deliberately plain. "Good morning" says hello without pretending to
 * know anything about the person reading it; anything more specific
 * ("Ready to land your next role?") is a claim the app cannot make.
 */

const HOUR = 1000 * 60 * 60;

export function greetingFor(date = new Date()) {
  const hour = date.getHours();

  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";

  return "Good evening";
}

/* Exported so a test can pin a time without touching the clock. */
export function greetingAt(hour) {
  return greetingFor(new Date(Date.now() - (Date.now() % HOUR) + hour * HOUR));
}