import { ApiError, reasonOf } from '../api/client';
import type { ApiReconciliation } from '../api/types';

/**
 * Invoice reconciliation in words. FEAT-076, TASK-P10-005.
 *
 * Pure, so the screen and the Overview tile say the same thing about the same payload. The
 * comparison is the server's; nothing here recomputes a state or a difference.
 */

/** What each state means to a reader, rather than its name on the wire. */
const STATE_WORDS: Readonly<Record<string, string>> = {
  Matched: 'Matches the invoice',
  Mismatched: 'Differs from the invoice',
  'No rows': 'No cost row carries this invoice',
  'Currency differs': 'Billed in another currency, not converted',
};

export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

/** An amount in its currency to the cent, or the words for a figure that was not compared. */
export function money(amount: string | null, currency: string): string {
  if (amount === null) return 'Not compared';
  return Number(amount).toLocaleString('en-GB', {
    style: 'currency',
    currency,
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** A difference with its sign said, because which side is higher is the whole point of it. */
export function signed(amount: string | null, currency: string): string {
  if (amount === null) return 'Not compared';
  return Number(amount) > 0 ? `+${money(amount, currency)}` : money(amount, currency);
}

/** The modelled tolerance as a reader says it: 0.0001 is a hundredth of a percent. */
export function tolerancePercent(tolerance: string): string {
  return `${String(Number((Number(tolerance) * 100).toFixed(4)))} percent`;
}

/** Why a period has nothing to compare, for a payload whose state says so. */
export function periodWords(data: ApiReconciliation): string {
  if (data.state === 'Not readable') {
    return (
      `The invoices for this period could not be read: ${data.cause ?? 'cause not reported'}. ` +
      'Nothing is compared, and nothing is shown as zero.'
    );
  }
  return (
    'No invoice has been issued for this period yet, so there is nothing to compare. A period ' +
    'closes when its invoice arrives.'
  );
}

/**
 * The route's own sentence when it answered without a comparison: a 403 for a reader who cannot
 * see the whole payer, and a 404 for a period nobody has read. Both are answers rather than
 * failures, and rendering either as a failed read would name a cause that did not happen.
 */
export function answeredInstead(error: unknown): string | null {
  if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
    // The body is `{"detail": "..."}`, and the sentence inside it is what a reader is owed.
    return reasonOf(error);
  }
  return null;
}
