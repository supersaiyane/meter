import { useParams } from 'react-router';

import { useQueryFinding } from '../api/queries';
import { Sparkline } from '../components/Sparkline';
import { Figure } from '../components/Figure';
import { RemediationControls } from './RemediationControls';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { Freshness } from '../components/provenance';
import { amountFigure } from './findingFigure';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * One finding, with its full working, per P2 spec section 9.2.
 *
 * Generous density, because the reader is making a judgement rather than
 * scanning. Publishing the arithmetic is what makes a modelled number arguable
 * rather than magic: an engineer who disagrees can point at the line they
 * disagree with, and that is the difference between a finding that gets fixed
 * and a finding that gets dismissed.
 *
 * The accuracy caveat is not written here. `Figure` renders it from the value's
 * provenance, so a screen cannot show a modelled number without it, and cannot
 * accidentally attach one to a measured number either.
 */

const MIB = 1024 ** 2;
const GIB = 1024 ** 3;

function integer(value: number): string {
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 }).format(value);
}

/** The money as it is written elsewhere on the page, so the two agree.
 *
 * Grouped and to two places, which is what `Figure` does. Without the grouping
 * the same number reads as $2520.00 here and $2,520.00 six lines above it, and
 * a reader who notices that stops trusting both.
 */
function money(amount: string): string {
  return `$${Number(amount).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function firstOf(history: readonly { readonly cost_month_usd: string }[]): string {
  return money(history[0]?.cost_month_usd ?? '0');
}

function lastOf(history: readonly { readonly cost_month_usd: string }[]): string {
  return money(history[history.length - 1]?.cost_month_usd ?? '0');
}

export function QueryFindingDetailScreen() {
  const { id = '' } = useParams();
  const query = useQueryFinding(id);
  const envelope = query.data?.data;
  const detail = envelope?.data ?? null;
  useReportMeta('query-finding', envelope?.meta);

  const settled = !query.isPending && !query.isError && envelope !== undefined;
  if (settled && detail === null) {
    // A finding that does not exist is not an empty filter and not a failure.
    // Three conditions, three renderings.
    // `settled` established that the query resolved, so the source is known.
    return (
      <section aria-label="Finding">
        <FixtureBand source={query.data.source} />
        <p data-testid="finding-not-found">No finding with id {id}.</p>
      </section>
    );
  }

  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const state = surfaceStateFor(query, envelope?.meta, detail ? 1 : 0, 'none', 'query_audit');
  // Absent, not empty, when the API predates ISS-172. An old API and a new
  // interface coexist during a rolling deploy by design, constraint 12, and a
  // screen that throws on a field the other half has not learned to send yet
  // turns a version skew into an outage. Named costSeries because History is a
  // DOM global and shadowing it reads as a mistake.
  const costSeries = detail?.history ?? [];

  return (
    <section aria-label="Finding">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        {detail ? (
          <article>
            <h2>
              {detail.dashboard_title}, {detail.panel_title}
            </h2>

            <h3>Monthly cost</h3>
            <Figure value={amountFigure(detail)} freshness={freshness} unit="usd" />

            <h3>Over time</h3>
            {/* ISS-172. The audit has written one row per query per day since
                it was built and nothing read them. A cost with no history
                behind it can say a query is expensive and not that somebody
                made it so. */}
            {costSeries.length > 1 ? (
              <p data-testid="finding-trend">
                <Sparkline
                  points={costSeries.map((point) => Number(point.cost_month_usd))}
                  // Modelled if any day in the series was. A shape drawn
                  // through a mixture is only as good as its weakest point,
                  // and drawing it solid would claim otherwise.
                  provenance={
                    costSeries.every((point) => point.provenance === 'measured')
                      ? 'measured'
                      : 'modelled'
                  }
                  label={`Monthly cost across ${String(costSeries.length)} days`}
                />{' '}
                <span data-testid="finding-trend-words">
                  {firstOf(costSeries)} on {costSeries[0]?.run_date}, {lastOf(costSeries)} now
                </span>
              </p>
            ) : (
              // One observation is not a flat trend, and drawing it as one
              // would assert a stability nobody has watched.
              <p data-testid="finding-trend" data-state="never-collected">
                Seen once, on {costSeries[0]?.run_date ?? 'no recorded day'}. There is no trend
                until it has been audited twice.
              </p>
            )}

            <h3>The query</h3>
            {/* Shown whole. A summary of a query is not evidence. */}
            <pre data-testid="finding-query">{detail.query_text}</pre>

            <h3>Target</h3>
            <p>
              {detail.targets.join(', ') || 'not stated'}, on {detail.engine}
            </p>

            <h3>The working</h3>
            <ul data-testid="finding-working">
              <li>{integer(Number(detail.runs_per_day))} runs per day</li>
              <li>{integer((detail.scan_bytes_per_run ?? 0) / MIB)} MiB scanned per run</li>
              <li>{integer(detail.window_seconds / 86400)} day window</li>
              <li>${detail.rate_usd_per_gib} per GiB scanned</li>
              <li>
                {integer(
                  (Number(detail.runs_per_day) * (detail.scan_bytes_per_run ?? 0) * 30) / GIB,
                )}{' '}
                GiB scanned per month
              </li>
            </ul>

            <RemediationControls detail={detail} />

            <h3>Measured evidence</h3>
            {detail.measured_runs === null ? (
              // FEAT-013 is the overlay that fills this. Saying so beats an
              // empty section that reads as "nothing was found".
              <p data-state="never-collected">
                not yet collected, arrives with the measured overlay
              </p>
            ) : (
              <ul>
                <li>
                  <Figure
                    value={{ kind: 'measured', amount: detail.measured_runs }}
                    freshness={freshness}
                    unit="count"
                    label="Runs observed"
                  />
                </li>
              </ul>
            )}
          </article>
        ) : null}
      </StateBoundary>
    </section>
  );
}
