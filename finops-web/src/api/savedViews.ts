import type { ApiSavedView, SavedViewQuery } from './types';

/**
 * A saved view's address, both ways. FEAT-068, TASK-P8-010.
 *
 * A view keeps the screen's query string as an object, which is what the API stores and checks:
 * a parameter given once is its value, and one given more than once is every value in order, as
 * the browser's own `URLSearchParams` holds them. Both directions live in this one module, so the
 * control that saves an address and the screen that opens it again cannot disagree about either.
 */

/** The longest name the API keeps, its `ck_saved_view__named` constraint. */
export const VIEW_NAME_MAX = 120;

/** The query a view keeps, from the address's query string, with or without its `?`. */
export function queryOf(search: string): SavedViewQuery {
  const params = new URLSearchParams(search);
  const query: Record<string, string | readonly string[]> = {};
  for (const key of new Set(params.keys())) {
    const values = params.getAll(key);
    query[key] = values.length === 1 ? (values[0] ?? '') : values;
  }
  return query;
}

/** The address that opens a view: its screen, and its query in the order it was kept. */
export function hrefOf(view: Pick<ApiSavedView, 'screen_path' | 'query'>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(view.query)) {
    for (const one of typeof value === 'string' ? [value] : value) {
      params.append(key, one);
    }
  }
  const search = params.toString();
  return search === '' ? view.screen_path : `${view.screen_path}?${search}`;
}
