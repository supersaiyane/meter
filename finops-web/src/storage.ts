/**
 * Browser storage, which is allowed to refuse.
 *
 * A private window, a browser set to block site data, and some embedded views
 * do not return null from `localStorage`. They throw on the property access
 * itself, before any key is named. Every call site therefore has to be wrapped,
 * and the one that was not, the session token read in `main.tsx`, meant the
 * whole application failed to start rather than starting without a token and
 * showing the typed refusal it already knows how to show.
 *
 * Reading and writing both fail quietly, because everything kept here is a
 * convenience: which state the navigation was left in, and a token whose
 * absence the API already answers for. Nothing that must survive belongs here.
 */

function store(): Storage | null {
  try {
    // The access, not the call. This is the line that throws.
    const candidate: unknown = window.localStorage;
    // Some environments substitute an object with no methods on it, which fails
    // later and further away than it should.
    return typeof (candidate as Storage | null)?.getItem === 'function'
      ? (candidate as Storage)
      : null;
  } catch {
    return null;
  }
}

/** The stored value, or null when there is none and when there cannot be one. */
export function readStored(key: string): string | null {
  try {
    return store()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** Best effort. A preference that cannot be saved costs one click next time. */
export function writeStored(key: string, value: string): void {
  try {
    store()?.setItem(key, value);
  } catch {
    // Quota exceeded and blocked site data both land here.
  }
}
