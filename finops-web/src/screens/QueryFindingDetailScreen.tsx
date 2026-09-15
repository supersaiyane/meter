import { useParams } from 'react-router';

import { useQueryFinding } from '../api/queries';
import { Figure } from '../components/Figure';
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

  return (
    <section aria-label="Finding">
      <FixtureBand source={query.data?.source ?? 'fixture'} />
      <StateBoundary state={state}>
        {detail ? (
          <article>
            <h2>
              {detail.dashboard_title}, {detail.panel_title}
            </h2>

            <h3>Monthly cost</h3>
            <Figure value={amountFigure(detail)} freshness={freshness} unit="usd" />

            <h3>The query</h3>
            {/* Shown whole. A summary of a query is not evidence. */}
            <pre data-testid="finding-query">{detail.query_text}</pre>

            <h3>Target</h3>
            <p>
              {detail.target}, on {detail.engine}
            </p>

            <h3>The working</h3>
            <ul data-testid="finding-working">
              <li>{integer(detail.runs_per_day)} runs per day</li>
              <li>{integer(detail.bytes_scanned_per_run / MIB)} MiB scanned per run</li>
              <li>{integer(detail.window_seconds / 86400)} day window</li>
              <li>${detail.rate_usd_per_gib} per GiB scanned</li>
              <li>
                {integer((detail.runs_per_day * detail.bytes_scanned_per_run * 30) / GIB)} GiB
                scanned per month
              </li>
            </ul>

            <h3>Measured evidence</h3>
            {detail.measured_runs_per_day === null ? (
              // FEAT-013 is the overlay that fills this. Saying so beats an
              // empty section that reads as "nothing was found".
              <p data-state="never-collected">
                not yet collected, arrives with the measured overlay
              </p>
            ) : (
              <ul>
                <li>
                  <Figure
                    value={{ kind: 'measured', amount: detail.measured_runs_per_day }}
                    freshness={freshness}
                    unit="count"
                    label="Runs per day observed"
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
