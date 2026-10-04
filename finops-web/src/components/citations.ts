import type { ApiCitation } from '../api/types';

/**
 * Putting cited values back into prose, P7 spec section 5.2.
 *
 * The model never writes a figure. It writes `{{name}}`, and each name is cited to the tool
 * call, the field and the value behind it. The screen substitutes the value, so every figure
 * a reader sees is one the deterministic layer read, and the failure that remains is a wrong
 * sentence beside right numbers, which a reader can catch.
 *
 * Pure, and kept out of the component file, so the rules are tested without a renderer and
 * the component file exports components alone.
 */

/** `{{name}}`, the pattern `finops_core/domain/insight.py` holds every answer to. */
const PLACEHOLDER = /\{\{([a-z][a-z0-9_]{0,31})\}\}/;

export type ProsePart =
  | { readonly kind: 'text'; readonly text: string }
  | { readonly kind: 'cited'; readonly citation: ApiCitation; readonly number: number }
  /**
   * A placeholder no citation claims. The API refuses to store one, so this is drift, and it
   * is shown as drift rather than as the raw braces or as nothing.
   */
  | { readonly kind: 'uncited'; readonly name: string };

export interface NumberedCitation {
  readonly citation: ApiCitation;
  readonly number: number;
}

export interface CitedProse {
  readonly parts: readonly ProsePart[];
  /** Every citation, numbered in the order the prose first uses it. */
  readonly numbered: readonly NumberedCitation[];
}

/**
 * The prose split on its placeholders, each one paired with its citation.
 *
 * Split rather than replaced, so the value becomes a node the screen renders rather than text
 * spliced into a string, and nothing in the prose is ever parsed as markup.
 *
 * Numbered by first use, so the markers read in order down the page. A name used twice keeps
 * its first number. A citation the prose never uses is listed after the rest rather than
 * dropped: the API refuses one, and a value the reader was sent is still shown if it arrives.
 */
export function citeProse(prose: string, citations: readonly ApiCitation[]): CitedProse {
  const byName = new Map(
    citations.map((citation) => [citation.placeholder, citation] as const),
  );
  const order: string[] = [];
  const numberOf = (name: string): number => {
    const seen = order.indexOf(name);
    if (seen !== -1) return seen + 1;
    order.push(name);
    return order.length;
  };

  // A capturing group makes split keep the names: text at even indexes, names at odd ones.
  const parts = prose.split(PLACEHOLDER).flatMap((piece, index): ProsePart[] => {
    if (index % 2 === 0) return piece === '' ? [] : [{ kind: 'text', text: piece }];
    const citation = byName.get(piece);
    return citation === undefined
      ? [{ kind: 'uncited', name: piece }]
      : [{ kind: 'cited', citation, number: numberOf(piece) }];
  });
  for (const citation of citations) numberOf(citation.placeholder);

  const numbered = order.flatMap((name, index): NumberedCitation[] => {
    const citation = byName.get(name);
    return citation === undefined ? [] : [{ citation, number: index + 1 }];
  });
  return { parts, numbered };
}

/**
 * Words that name money in a field. Everything else a tool returns is a count.
 *
 * A citation carries no unit, so the unit is read from the name of the field the value came
 * from. Every tool the assistant has today returns money under a name that says so:
 * `effective_cost`, `billed_cost`, `amortized_cost`, `monthly_cost`, the cost summary's
 * `change`, and a cluster's `total`, `allocated` and `unallocated`. A digest names its fields
 * in words, "effective_cost summed over the week", which the same rule reads. A unit on the
 * citation would make this a lookup instead of a rule, and its absence is reported as a gap in
 * the contract rather than hidden here.
 */
const MONEY = new Set([
  'cost',
  'costs',
  'spend',
  'spent',
  'saving',
  'savings',
  'price',
  'charge',
  'charges',
  'budget',
  'amount',
  'change',
  'total',
  'allocated',
  'unallocated',
]);

export function figureUnit(citation: ApiCitation): 'usd' | 'count' {
  // The envelope's own meta holds only counts: coverage and failure occurrences.
  if (citation.field.startsWith('meta.')) return 'count';
  // A selector such as `[name=m5.large]` holds dots and names of its own, and is not the field.
  const path = citation.field.replace(/\[[^\]]*\]/g, '');
  const field = path.split('.').at(-1) ?? path;
  const words = field.toLowerCase().split(/[^a-z]+/);
  return words.some((word) => MONEY.has(word)) ? 'usd' : 'count';
}

/** A decimal as the API writes one, such as `3781.9335`, `-12.5` or `0E-10`. */
const DECIMAL = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i;

/**
 * The number a decimal string holds, or null when it holds none.
 *
 * Not `Number` alone, which reads an empty string as zero. A value that arrived as nothing
 * would be drawn as a zero, which is the one thing a missing value must never become.
 */
export function amountOf(value: string): number | null {
  if (!DECIMAL.test(value)) return null;
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}

/** The most decimal places a number is drawn to in this browser's formatter. */
const MOST_PLACES = 20;

/**
 * How many decimal places a decimal string carries, so a count is drawn to its own precision.
 *
 * `0.4000` carries four and `2.5` one, so neither is rounded to a whole number, and a fraction
 * is never drawn as zero. The exponent counts: `0E-10` carries ten and `1.5E+2` none. Trailing
 * zeros are dropped when drawn, so `0.4000` reads `0.4`.
 */
export function decimalPlaces(value: string): number {
  const match = /^[+-]?\d*(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(value);
  if (match === null) return 0;
  const places = (match[1] ?? '').length - Number(match[2] ?? '0');
  return Math.min(MOST_PLACES, Math.max(0, places));
}

/** Where a marker points. Unique on the page, because `scope` is an exchange or digest id. */
export function citationAnchor(scope: string, number: number): string {
  return `cite-${scope}-${String(number)}`;
}

/** Where a citation's call points. By position, because a call id is the model's text. */
export function callAnchor(scope: string, index: number): string {
  return `call-${scope}-${String(index + 1)}`;
}
