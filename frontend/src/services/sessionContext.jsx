import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchCurrentUser } from "./api";
import { clearAuthState, signOut as endSession } from "./authSession";
import { IDLE_EVENTS, readIdleMinutes } from "./sessionIdle";
import { SessionContext } from "./sessionStore";

/**
 * One session, checked once, with an inactivity clock.
 *
 * `useSession` used to be a plain hook that every component called
 * for itself, so opening the root URL fired three parallel
 * `/auth/me` requests - one from RootRedirect, one from
 * RequireAuth, one from the failure watcher. Two of them sat
 * PENDING while the third answered, and the root URL spent most of a
 * second on "Checking your session..." before it could say "no".
 *
 * It also owns the inactivity timer, which did not exist at all: a
 * session cookie lived for seven days, so a shared browser left the
 * previous person signed in.
 */

export function SessionProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [idleMinutes, setIdleMinutes] = useState(readIdleMinutes);

  const idleTimer = useRef(null);

  const end = useCallback(async () => {
    clearTimeout(idleTimer.current);

    // Local state first, so the guard locks immediately, then the
    // server. Stored work is never touched: another account's data
    // lives under its own cache keys, and this user's resumes and
    // analyses are rows in the database that nothing here deletes.
    setUser(null);
    clearAuthState();

    try {
      await endSession();
    } catch {
      // A failed request must not strand the user on a protected
      // page. The cookie may still be live; the guard catches it on
      // the next check.
    }
  }, []);

  // ---- who am I ----
  const check = useCallback(() => {
    return fetchCurrentUser()
      .then((session) => {
        // One request answers both questions: who this is, and how
        // long it is willing to stay signed in.
        setUser(session?.user || null);

        const minutes = Number(session?.idleMinutes);

        if (Number.isFinite(minutes) && minutes >= 1) {
          setIdleMinutes(Math.min(minutes, 24 * 60));
        }

        return session?.user || null;
      })
      .catch(() => {
        // An unreachable backend is treated as signed out rather
        // than as an indefinite spinner.
        setUser(null);

        return null;
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  /*
   * Re-read the session from the server.
   *
   * This is what makes signing in work at all. The check above runs
   * once when the app loads, so immediately after a successful
   * login the provider still believed nobody was signed in - the
   * browser had the cookie, but React did not. Navigating to a
   * protected page then bounced straight back to /login, and it
   * looked as though the sign-in had failed when it had actually
   * worked.
   *
   * Signing in calls this first, then navigates.
   */
  const refresh = useCallback(() => check(), [check]);

  // ---- inactivity ----
  const arm = useCallback(() => {
    clearTimeout(idleTimer.current);

    idleTimer.current = setTimeout(() => {
      end();
    }, idleMinutes * 60 * 1000);
  }, [end, idleMinutes]);

  useEffect(() => {
    if (!user) {
      clearTimeout(idleTimer.current);
      return undefined;
    }

    arm();

    const onActivity = () => arm();

    IDLE_EVENTS.forEach((name) =>
      window.addEventListener(name, onActivity, { passive: true })
    );

    return () => {
      IDLE_EVENTS.forEach((name) =>
        window.removeEventListener(name, onActivity)
      );

      clearTimeout(idleTimer.current);
    };
  }, [user, arm]);

  const value = useMemo(
    () => ({ user, loading, signOut: end, idleMinutes, refresh }),
    [user, loading, end, idleMinutes, refresh]
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

