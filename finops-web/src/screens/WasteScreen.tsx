import { useMemo } from 'react';

import { useRecommendations, useRefusals } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { RankedBars, type RankedPoint } from '../components/RankedBars';
import { Figure } from '../components/Figure';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { severityLevel } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiRecommendation } from '../api/types';

/**
 * What the estate should cost instead. FEAT-025, FEAT-026, FEAT-028.
 *
 * Two decisions carry this screen, and both are about what sits next to what.
 *
 * **Money and confidence are not adjacent.** A reader comparing them side by
 * side reads confidence as a discount on the money, which it is not: a ten
 * thousand dollar finding resting on three weeks of data is worth exactly ten
 * thousand dollars if it is right, and the confidence says how likely that is,
 * not how much less it is worth. The commitments screen keeps its two
 * percentages apart for the same reason, and the columns here are ordered so
 * the working comes between them.
 *
 * **The estimate is labelled modelled.** It is arithmetic over observed metrics
 * rather than a figure anybody has seen on a bill, and the realized savings
 * screen is where measured money lives. `Figure` carries that distinction in
 * three ways at once, so it survives a screenshot and a colourblind reader.
 *
 * A recommendation with no owner says so in words. ISS-021's lesson is that an
 * unowned finding is never fixed, and a blank cell is the least noticeable way
 * to render the single fact most likely to kill the work.
 */

function money(amount: string): number {
  return Number(amount);
}

/**
 * Modelled monthly saving per waste class, open findings only.
 *
 * Open only, because a finding that is DONE has had its saving taken and one that is DISMISSED
 * was judged not to be waste. Charting the whole queue would draw money that is not available and
 * would grow the picture every time somebody fixed something, which is the wrong direction.
 * FEAT-029 is the only thing in the product allowed to say a saving happened.
 */
function savingByClass(rows: readonly ApiRecommendation[]): readonly RankedPoint[] {
  const totals = new Map<string, number>();
  for (const row of rows) {
    if (row.lifecycle !== 'OPEN') continue;
    const current = totals.get(row.waste_class) ?? 0;
    totals.set(row.waste_class, current + Number(row.estimated_monthly_saving));
  }
  return [...totals].map(([label, value]) => ({ label, value }));
}

export function WasteScreen() {
  const query = useRecommendations();
  // FEAT-062. Beside the list and never in it: a refusal has no money, ADR-0016 ranks
  // this list by money, and a zero would sit at the bottom reading as the least valuable
  // action rather than as the absence of one.
  const declined = useRefusals();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const rows = useMemo(() => found?.recommendations ?? [], [found]);

  const byClass = useMemo(() => savingByClass(rows), [rows]);
  const examined = declined.data?.data.data.refusals ?? [];
  useReportMeta('waste-recommendations', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'recommendation');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const columns: readonly Column<ApiRecommendation>[] = [
    {
      key: 'severity',
      header: 'Severity',
      // From the money, per ADR-0016, and through the same mapping the query
      // findings use, so two screens do not mean different things by "high".
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
    },
    {
      key: 'saving',
      header: 'Monthly saving',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'modelled', amount: money(row.estimated_monthly_saving) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'what',
      header: 'What',
      render: (row) => `${row.waste_class} ${row.resource_id}`,
    },
    {
      key: 'where',
      header: 'Where',
      render: (row) => `${row.account_id} ${row.region_id}`,
    },
    {
      key: 'rationale',
      // Between the money and the confidence on purpose, and not only as
      // padding: the working is what a reader needs in order to judge the
      // confidence for themselves rather than take the label on trust.
      header: 'Why',
      prose: true,
      render: (row) => row.rationale,
    },
    {
      key: 'confidence',
      header: 'Confidence',
      render: (row) => (
        <span data-testid={`confidence-${row.recommendation_id}`}>
          {row.confidence} on {row.observation_days} days
        </span>
      ),
    },
    {
      key: 'lifecycle',
      header: 'State',
      render: (row) => (
        <span data-testid={`lifecycle-${row.recommendation_id}`}>{row.lifecycle}</span>
      ),
    },
    {
      key: 'owner',
      header: 'Owner',
      render: (row) =>
        row.owner === null ? (
          // Said, not left blank. An unowned finding is never fixed, and a blank
          // cell is the least noticeable way to render the fact most likely to
          // kill the work.
          <span data-testid={`unowned-${row.recommendation_id}`}>nobody yet</span>
        ) : (
          row.owner
        ),
    },
  ];

  const unowned = found?.unowned ?? 0;

  return (
    <section aria-label="Recommendations">
      {/*
        Outside the boundary, like the anomalies screen's history sentence. This
        is a fact about the queue rather than about the request, and it is the
        one a reader should see before they start reading rows.
      */}
      <p data-testid="waste-ownership">
        {unowned === 0 ? (
          <span data-testid="waste-all-owned">Every open recommendation has an owner</span>
        ) : (
          <span data-testid="waste-unowned-count">
            {unowned} of {rows.length} recommendations have no owner. An unowned finding is one
            nobody is going to fix
          </span>
        )}
      </p>

      <StateBoundary state={state}>
        {/* Where the money is, before the list of what to do about it. A queue sorted by
            saving answers which single finding is largest; this answers which kind of waste
            the estate has, which is the question that changes what somebody builds next.
            Hatched, because every figure in it is modelled: no saving here has been
            measured, and FEAT-029 is the only thing allowed to say one happened. */}
        <RankedBars
          points={byClass}
          provenance="modelled"
          format={(value) => `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`}
          restLabel="smaller classes"
        />

        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.recommendation_id}
          caption={`${String(rows.length)} ${
            rows.length === 1 ? 'recommendation' : 'recommendations'
          }, biggest saving first`}
        />
      </StateBoundary>

      {/* What the rules looked at and declined. ADR-0027: Meter cannot honestly say a
          workload is starved, because it cannot verify a performance finding and verification
          is its whole claim. It can say it looked, which is what the complaint behind that gap
          was actually about. A service that never appears above is otherwise indistinguishable
          from one nobody examined. */}
      {examined.length === 0 ? null : (
        <section aria-label="Examined and not flagged" data-testid="refusals">
          <h2>Looked at and left alone</h2>
          <p data-testid="refusals-count">
            {declined.data?.data.data.examined ?? 0} resources were examined and nothing was
            recommended. Each line says which rule asked and what it measured, so a reader can
            disagree with it
          </p>
          <table data-testid="refusals-table">
            <caption data-testid="refusals-caption">
              Least observed first. A refusal has no money, so it cannot be ranked by money: the
              useful order is how much the judgement rests on
            </caption>
            <thead>
              <tr>
                <th scope="col">Resource</th>
                <th scope="col">Rule</th>
                <th scope="col">Why it was left alone</th>
                <th scope="col">Account</th>
                <th scope="col">Observed</th>
              </tr>
            </thead>
            <tbody>
              {examined.map((one) => (
                <tr key={`${one.resource_id}:${one.waste_class}`}>
                  <th scope="row">{one.resource_id}</th>
                  <td>{one.waste_class}</td>
                  {/* Whole, never shortened. A judgement a reader cannot argue with is one
                      they have to take on trust. */}
                  <td className="meter-prose">{one.reason}</td>
                  <td>{one.account_id}</td>
                  <td>
                    {one.observation_days} {one.observation_days === 1 ? 'day' : 'days'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </section>
  );
}
