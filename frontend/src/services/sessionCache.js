/**
 * Per-user local cache for resume data.
 *
 * localStorage is shared by every account that uses the same
 * browser and the same origin. Storing "the current analysis"
 * under one fixed key meant a newly signed-in user rehydrated
 * the previous user's resume, score, skills and history from
 * this cache.
 *
 * Every entry is therefore namespaced by the authenticated
 * user id, and the owner is also written inside the value and
 * checked on read. An entry that does not belong to the signed
 * in user is never returned.
 */

const NAMESPACE = "resumeai";

// Cached record names.
export const ANALYSIS = "analysis";
export const FILE_META = "file_meta";
export const PREVIOUS_ANALYSIS = "previous_analysis";

const RECORD_NAMES = [ANALYSIS, FILE_META, PREVIOUS_ANALYSIS];

// Keys written by older versions of the app. They were never
// scoped to a user, so they can hold another account's data and
// must not be read again.
const LEGACY_KEYS = [
  "resumeai_analysis",
  "resumeai_file_meta",
  "resumeai_previous_analysis",
];

function storageKey(name, userId) {
  return `${NAMESPACE}_${name}:${userId}`;
}

/**
 * Read a cached record, but only when it belongs to userId.
 * Returns null when there is nothing usable.
 */
export function readForUser(name, userId, valueKey) {
  if (userId === null || userId === undefined) {
    return null;
  }

  let raw;

  try {
    raw = window.localStorage.getItem(storageKey(name, userId));
  } catch {
    return null;
  }

  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw);

    // The owner is verified again on read, so a record can
    // never be handed to the wrong account even if a key were
    // ever reused or copied.
    if (
      parsed === null ||
      typeof parsed !== "object" ||
      parsed.ownerId !== userId
    ) {
      return null;
    }

    const value = valueKey ? parsed.value : parsed;

    return value === undefined ? null : value;
  } catch {
    return null;
  }
}

/**
 * Save a record for one user only.
 */
export function writeForUser(name, userId, value, valueKey) {
  if (userId === null || userId === undefined) {
    return;
  }

  try {
    const payload = { ownerId: userId, value };

    window.localStorage.setItem(
      storageKey(name, userId),
      JSON.stringify(valueKey ? payload : { ...value, ownerId: userId })
    );
  } catch {
    // A full or unavailable store must never break the app.
  }
}

/**
 * Remove one record for one user.
 */
export function clearForUser(name, userId) {
  if (userId === null || userId === undefined) {
    return;
  }

  try {
    window.localStorage.removeItem(storageKey(name, userId));
  } catch {
    // ignore
  }
}

/**
 * Remove every resume record belonging to one user.
 */
export function clearAllForUser(userId) {
  RECORD_NAMES.forEach((name) => clearForUser(name, userId));
}

/**
 * Delete the old unscoped keys so a previous version's data
 * cannot reappear on someone's dashboard.
 */
export function purgeLegacyEntries() {
  try {
    LEGACY_KEYS.forEach((key) =>
      window.localStorage.removeItem(key)
    );
  } catch {
    // ignore
  }
}
