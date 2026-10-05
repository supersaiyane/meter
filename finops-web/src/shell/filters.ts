import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

/**
 * Filters live in the query string, `docs/13-UI-ARCHITECTURE.md` section 5 and
 * P8 spec section 5.6, so a link, a bookmark and a saved view carry the same
 * state, and back and forward walk through filters as they walk through
 * screens. ISS-235 was the gap: two links carried a filter and nothing read it.
 *
 * A screen names the keys it reads, the same constant its entry in
 * `sections.ts` declares. A key it does not name stays in the address and is
 * never applied, and the shell says so on the page.
 */
export interface Filters<K extends string> {
  /** Each key's value, or the empty string when the address does not set it. */
  readonly values: Readonly<Record<K, string>>;
  /** Sets one key, or takes it out for the empty string, as a new history entry. */
  readonly set: (key: K, value: string) => void;
}

export function useFilters<K extends string>(keys: readonly K[]): Filters<K> {
  const [params, setParams] = useSearchParams();
  const values = useMemo(
    () =>
      Object.fromEntries(keys.map((key) => [key, params.get(key) ?? ''])) as Record<K, string>,
    [keys, params],
  );
  const set = useCallback(
    (key: K, value: string) => {
      setParams((current) => {
        const next = new URLSearchParams(current);
        if (value === '') {
          next.delete(key);
        } else {
          next.set(key, value);
        }
        return next;
      });
    },
    [setParams],
  );
  return { values, set };
}
