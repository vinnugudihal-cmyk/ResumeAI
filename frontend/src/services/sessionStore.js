import { createContext, useContext } from "react";

/**
 * The session context and the hook that reads it.
 *
 * In its own module, with no component in it, so the provider file
 * can export only a component. That keeps React Fast Refresh
 * working in development: editing the provider must not invalidate
 * the state of a module that also exports a hook.
 */

export const SessionContext = createContext(null);

export function useSession() {
  const value = useContext(SessionContext);

  if (!value) {
    throw new Error("useSession must be used inside <SessionProvider>");
  }

  return value;
}