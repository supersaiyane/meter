import { VIEW_NAME_MAX } from '../api/savedViews';
import type { ApiSavedView } from '../api/types';

/**
 * What the report library says about each view. FEAT-068, TASK-P8-010.
 *
 * Kept apart from the screen so each sentence can be tested on its own, and so the screen's
 * module exports only the screen.
 */

const SUFFIX = ' (copy)';

/** A copy's name: the original's, said to be a copy, and never longer than the API keeps. */
export function copyName(name: string): string {
  return `${name.slice(0, VIEW_NAME_MAX - SUFFIX.length)}${SUFFIX}`;
}

/** When a view last changed, as an absolute time in the zone the API keeps it in. */
export function changedAt(stamp: string): string {
  const instant = new Date(stamp);
  return Number.isNaN(instant.getTime())
    ? stamp
    : `${instant.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** Who may open a view, said from the reader's side of it. */
export function audienceOf(view: Pick<ApiSavedView, 'visibility' | 'owned'>): string {
  if (view.visibility === 'PRIVATE') {
    return 'Only you';
  }
  return view.owned ? 'Everyone, shared by you' : 'Everyone, shared with you';
}

/** The parameters a view keeps, by name, or None for a screen kept as it opens. */
export function filtersOf(view: Pick<ApiSavedView, 'query'>): string {
  const keys = Object.keys(view.query);
  return keys.length === 0 ? 'None' : keys.join(', ');
}
