/**
 * Signing out.
 *
 * There used to be two different handlers on the dashboard. The
 * one in Settings cleared everything, but the "Sign Out" item in
 * the profile menu only removed one localStorage key and then
 * navigated. It never told the server, so the session cookie was
 * still valid, the route guard found a live session on the next
 * render and sent the user straight back to the dashboard.
 *
 * This module is the single implementation every page uses, so
 * that cannot drift apart again.
 */

import { logoutUser } from "./api";
import {
  clearAllForUser,
  purgeLegacyEntries,
} from "./sessionCache";

export const USER_KEY = "resumeai_user";

/**
 * Read the signed-in user id from localStorage.
 *
 * Tolerant of a missing, unparseable or legacy-shaped value: the
 * cache is cleared by prefix rather than by id, so an id we cannot
 * read is not a reason to leave someone else's data behind.
 */
function currentUserId() {
  try {
    const raw = localStorage.getItem(USER_KEY);

    if (!raw) return null;

    const parsed = JSON.parse(raw);

    return parsed?.id ?? null;
  } catch {
    return null;
  }
}

/**
 * Drop every trace of this account from the browser.
 *
 * The session cache is namespaced per user, so clearing the
 * current user's entries stops the next person on a shared
 * machine from seeing their resume data. Legacy unscoped keys are
 * removed too.
 */
export function clearAuthState() {
  const userId = currentUserId();

  try {
    clearAllForUser(userId);
    purgeLegacyEntries();
    localStorage.removeItem(USER_KEY);
  } catch {
    // Private browsing modes can refuse storage. The server-side
    // session is cleared regardless, which is what actually
    // protects the account.
  }
}

/**
 * Sign out for real.
 *
 * Order matters: the local state is cleared first so the UI stops
 * trusting this session even if the network call fails. The server
 * call is attempted either way, and a failure there is swallowed
 * because the user still ends up on the Login page.
 */
export async function signOut() {
  clearAuthState();

  try {
    await logoutUser();
  } catch {
    // A failed request must not trap the user on a protected page.
    // The cookie may still be live, but the guard will notice on
    // the next navigation and send them back here.
  }
}
