/**
 * The vocabulary every figure in this product is described in.
 *
 * `FigureValue` is a discriminated union rather than a number with optional
 * fields beside it, and that is the whole design. A forecast has `low` and
 * `high` and no single amount, so a point forecast is not something a caller
 * can express and then be reviewed for. ADR-0015 condition 2 is a rendering
 * rule, and this is it expressed in the type system.
 *
 * A failure carries its cause and what to do about it, and carries no amount at
 * all. There is deliberately no shape here that pairs a failure with a number.
 */

/** The seven causes from `finops_core.errors`. Closed, and mirrored deliberately. */
export type Cause =
  | 'AccessDenied'
  | 'Throttled'
  | 'NotOptedIn'
  | 'NoData'
  | 'Unreachable'
  | 'SchemaDrift'
  /**
   * A value this deployment set that does not exist at the provider. ADR-0026, ISS-215.
   *
   * It exists because SchemaDrift was absorbing it and saying the wrong thing: an aggregator
   * name with a typo in it told an operator their schema had drifted and sent them to look for
   * an API change, when the fix was one line of their own settings.
   */
  | 'Misconfigured';

/**
 * Where a figure came from. Three words, and every figure carries one.
 *
 * `forecast` is here before anything produces one, TASK-P6-012. ADR-0015 lists four
 * conditions a forecast must meet before it is shown, and its fourth is this third word:
 * a forecast rendered as `modelled` would be read as an estimate of the present rather
 * than a claim about the future. Adding the word inside the task that first forecasts
 * would have tangled a cross cutting change to every screen with a new feature, so it
 * lands alone. Nothing constructs a `forecast` yet, and `forecastUnproduced.test.ts`
 * fails if a screen starts to before somebody decides it meets the other three.
 */
export type Provenance = 'measured' | 'modelled' | 'forecast';

export type FigureValue =
  | { readonly kind: 'measured'; readonly amount: number }
  | { readonly kind: 'modelled'; readonly amount: number; readonly accuracy?: string }
  /** Never a point. A forecast that renders as one number is a forecast lying. */
  | { readonly kind: 'forecast'; readonly low: number; readonly high: number }
  | { readonly kind: 'failed'; readonly cause: Cause; readonly remediation: string };

/**
 * Two timestamps, never one. `asOf` is when the value was true at the source
 * and `collectedAt` is when Meter fetched it. Conflating them makes a stale
 * number look fresh, which is constraint 10 in CLAUDE.md.
 */
export interface Freshness {
  readonly asOf: Date;
  readonly collectedAt: Date;
  /**
   * The collector's own interval. Staleness is judged against it rather than a
   * fixed threshold, because a daily collector six hours old is fine and an
   * hourly one six hours old is not.
   */
  readonly cadenceSeconds?: number;
}

/** How each cause is written on screen. `NoData` has no label because it is a number. */
export const CAUSE_LABEL: Readonly<Record<Exclude<Cause, 'NoData'>, string>> = {
  AccessDenied: 'ACCESS DENIED',
  Throttled: 'THROTTLED',
  NotOptedIn: 'NOT ENABLED',
  Unreachable: 'UNREACHABLE',
  SchemaDrift: 'UNRECOGNISED',
  /* Not "INVALID" and not "ERROR". The word has to say whose problem it is, which is the
     whole reason this cause was separated from UNRECOGNISED. */
  Misconfigured: 'MISCONFIGURED',
};

/**
 * The one cause that may be drawn as a number.
 *
 * Everything else renders its cause instead of a numeral. If a refusal could
 * render as zero, a column of costs would contain zeros meaning "free" and
 * zeros meaning "we could not look", and nothing on the page would tell them
 * apart. That distinction is the entire product.
 */
export function rendersAsNumeral(cause: Cause): cause is 'NoData' {
  // A type guard rather than a boolean, so the narrowing is enforced by the
  // compiler instead of remembered by the caller.
  return cause === 'NoData';
}

export function isStale(freshness: Freshness, now: Date, multiple = 2): boolean {
  if (freshness.cadenceSeconds === undefined) {
    // An unknown cadence is not a healthy one. Reporting fresh here would be a
    // guess dressed as a fact.
    return true;
  }
  const ageSeconds = (now.getTime() - freshness.asOf.getTime()) / 1000;
  return ageSeconds > freshness.cadenceSeconds * multiple;
}

/**
 * An age a person reads correctly. "6 min ago" is understood at a glance and
 * "11:04:22Z" requires arithmetic from the reader while they are trying to
 * think about something else.
 */
export function formatAge(seconds: number): string {
  if (seconds < 60) {
    return 'under a minute ago';
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${String(minutes)} min ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    return `${String(hours)} h ago`;
  }
  return `${String(Math.floor(hours / 24))} days ago`;
}
