import { FreshnessIndicator } from './FreshnessIndicator';
import { TypedError } from './TypedError';
import { rendersAsNumeral, type FigureValue, type Freshness } from './provenance';

/**
 * The most important component in the product. Nothing else renders a number.
 *
 * `value` and `freshness` are both required, so a figure with no provenance or
 * no timestamps is a compile error rather than a review comment. That is the
 * same technique as the repository scope guard: make the wrong thing
 * impossible, not discouraged. There is deliberately no exported way to render
 * a bare number, because the moment one exists a screen will use it under time
 * pressure and the guarantee is gone.
 *
 * Provenance is encoded three times over. The fill is solid or hatched, the
 * numeral carries a tilde prefix when it is not measured, and a text label says
 * which it is. Any one of the three survives colour being unavailable.
 */
export interface FigureProps {
  readonly value: FigureValue;
  readonly freshness: Freshness;
  readonly unit?: 'usd' | 'count';
  readonly label?: string;
  readonly now?: Date;
  readonly onAction?: () => void;
  readonly actionLabel?: string;
}

function formatAmount(amount: number, unit: 'usd' | 'count'): string {
  // Fixed decimal places including trailing zeros, so a column aligns and a
  // value that happens to be round does not read as less precise.
  if (unit === 'count') {
    return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(amount);
  }
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'USD',
    // narrowSymbol, so the glyph is the dollar sign rather than US$ in a locale
    // that disambiguates. The figure is read by people scanning a column, and a
    // two character prefix in some rows and not others breaks the alignment
    // that tabular numerals exist to give.
    currencyDisplay: 'narrowSymbol',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function Figure({
  value,
  freshness,
  unit = 'usd',
  label,
  now,
  onAction,
  actionLabel,
}: FigureProps) {
  if (value.kind === 'failed') {
    if (rendersAsNumeral(value.cause)) {
      // The one legitimate zero. It reads as a zero because it is one.
      return (
        <span data-testid="figure" data-provenance="measured" data-cause="NoData">
          <span className="meter-numeral meter-fill-measured">{formatAmount(0, unit)}</span>
          <span> measured</span>
          <FreshnessIndicator freshness={freshness} {...(now ? { now } : {})} />
        </span>
      );
    }
    return (
      <span data-testid="figure" data-failed="true" data-cause={value.cause}>
        <TypedError
          cause={value.cause}
          remediation={value.remediation}
          {...(actionLabel ? { actionLabel } : {})}
          {...(onAction ? { onAction } : {})}
        />
        <FreshnessIndicator freshness={freshness} {...(now ? { now } : {})} />
      </span>
    );
  }

  const prefix = value.kind === 'measured' ? '' : '~ ';
  const text =
    value.kind === 'forecast'
      ? `${formatAmount(value.low, unit)} to ${formatAmount(value.high, unit)}`
      : formatAmount(value.amount, unit);

  const accuracy =
    value.kind === 'modelled'
      ? // Worse looking and more honest. A modelled figure with no published
        // accuracy should say so rather than imply one.
        (value.accuracy ?? 'accuracy not yet published')
      : undefined;

  return (
    <span data-testid="figure" data-provenance={value.kind}>
      {label ? <span>{label} </span> : null}
      <span className={`meter-numeral meter-fill-${value.kind}`}>
        {prefix}
        {text}
      </span>
      <span> {value.kind}</span>
      {accuracy ? <span>, {accuracy}</span> : null}
      <FreshnessIndicator freshness={freshness} {...(now ? { now } : {})} />
    </span>
  );
}
