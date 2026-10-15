import { useMemo } from 'react';
import { lifecycleName, wasteClassName } from '../components/displayNames';

import { useRecommendations, useRefusals } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { RankedBars, type RankedPoint } from '../components/RankedBars';
import { Figure } from '../components/Figure';
import { OwnerSuggestions } from '../components/OwnerSuggestions';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useFilters } from '../shell/filters';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { RECOMMENDATION_FILTERS } from '../shell/sections';
import { ALLOCATION_TAG } from './overviewKpis';
import { RecommendationAlternatives } from './RecommendationAlternatives';
import { RecommendationFix } from './RecommendationFix';
import { severityLevel } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiRecommendation, ApiRefusal } from '../api/types';

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
  return [...totals].map(([label, value]) => ({ label: wasteClassName(label), value }));
}

/** What was looked at and left alone, TASK-P8-013 on `DataTable`. No money, so no total. */
const REFUSAL_COLUMNS: readonly Column<ApiRefusal>[] = [
  {
    key: 'resource',
    header: 'Resource',
    rowHeader: true,
    render: (one) => one.resource_id,
    sortValue: (one) => one.resource_id,
  },
  {
    key: 'rule',
    header: 'Rule',
    render: (one) => wasteClassName(one.waste_class),
    sortValue: (one) => wasteClassName(one.waste_class),
  },
  {
    // Whole, never shortened. A judgement a reader cannot argue with is one they have to
    // take on trust.
    key: 'reason',
    header: 'Why it was left alone',
    prose: true,
    render: (one) => one.reason,
  },
  {
    key: 'account',
    header: 'Account',
    render: (one) => one.account_id,
    sortValue: (one) => one.account_id,
  },
  {
    key: 'observed',
    header: 'Observed',
    numeric: true,
    render: (one) =>
      `${String(one.observation_days)} ${one.observation_days === 1 ? 'day' : 'days'}`,
    sortValue: (one) => one.observation_days,
  },
];

export function WasteScreen() {
  const query = useRecommendations();
  // FEAT-062. Beside the list and never in it: a refusal has no money, ADR-0016 ranks
  // this list by money, and a zero would sit at the bottom reading as the least valuable
  // action rather than as the absence of one.
  const declined = useRefusals();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const all = useMemo(() => found?.recommendations ?? [], [found]);
  const { values } = useFilters(RECOMMENDATION_FILTERS);
  // One finding when a FinOps Score link names it, ISS-235. The ownership sentence is about
  // the whole queue, so it keeps reading the whole queue.
  const rows = useMemo(
    () =>
      values.finding === ''
        ? all
        : all.filter((row) => row.recommendation_id === values.finding),
    [all, values.finding],
  );

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
      header: 'Estimated monthly savings',
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
      render: (row) => `${wasteClassName(row.waste_class)} ${row.resource_id}`,
    },
    {
      // TASK-P9-010. The type a rightsizing names, and a way to what it was compared with.
      key: 'target',
      header: 'Target',
      render: (row) =>
        row.target_instance_type == null ? (
          'none named'
        ) : (
          <span data-testid={`target-${row.recommendation_id}`}>
            {row.current_instance_type ?? 'its type'} to {row.target_instance_type}
            {values.finding === '' ? (
              <>
                {' '}
                <Link to={`/optimize?finding=${row.recommendation_id}`}>Alternatives</Link>
              </>
            ) : null}
          </span>
        ),
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
        <span data-testid={`lifecycle-${row.recommendation_id}`}>
          {lifecycleName(row.lifecycle)}
        </span>
      ),
    },
    {
      key: 'owner',
      header: 'Owner',
      render: (row) => (
        <>
          {row.owner === null ? (
            // Said, not left blank. An unowned finding is never fixed, and a blank
            // cell is the least noticeable way to render the fact most likely to
            // kill the work.
            <span data-testid={`unowned-${row.recommendation_id}`}>
              nobody yet
              {/* Whom to ask, from the resource's own tag, never an owner: ISS-021. Where
                  the sources below name somebody, they say it with where it came from. */}
              {row.suggested_owner === null || row.owner_suggestions.length > 0 ? null : (
                <span data-testid={`suggested-owner-${row.recommendation_id}`}>
                  ; its {ALLOCATION_TAG} tag says {row.suggested_owner}
                </span>
              )}
            </span>
          ) : (
            row.owner
          )}
          {/* TASK-P11-005. Every source's suggestion, under the owner, owned or not. */}
          <OwnerSuggestions
            id={row.recommendation_id}
            suggestions={row.owner_suggestions}
            createdBefore={row.created_before}
          />
        </>
      ),
    },
  ];

  const unowned = found?.unowned ?? 0;
  // One finding named by a link, with a target: the recommendation's own view, and the place
  // its Alternatives table belongs. TASK-P9-010.
  const one = values.finding !== '' && rows.length === 1 ? rows[0] : undefined;

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
            {unowned} of {all.length} recommendations have no owner. An unowned finding is one
            nobody is going to fix
          </span>
        )}
      </p>

      {values.finding === '' ? null : (
        <p data-testid="filtered-to-finding">
          Showing one finding, <code>{values.finding}</code>, from the FinOps Score.{' '}
          <Link to="/optimize">Show every recommendation</Link>
        </p>
      )}

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

      {one?.target_instance_type == null ? null : (
        <RecommendationAlternatives recommendationId={one.recommendation_id} />
      )}

      {/* P15, FEAT-092. Asking for the fix, its pull request and its steps, under the one
          finding a reader chose, so the decision is made with the finding in front of them. */}
      {one === undefined ? null : <RecommendationFix recommendation={one} />}

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
          <div data-testid="refusals-table">
            <DataTable
              rows={examined}
              columns={REFUSAL_COLUMNS}
              rowKey={(one) => `${one.resource_id}:${one.waste_class}`}
              caption="Least observed first. A refusal has no money, so it cannot be ranked by money: the useful order is how much the judgement rests on"
              captionTestId="refusals-caption"
              initialSort={{ key: 'observed', direction: 'ascending' }}
            />
          </div>
        </section>
      )}
    </section>
  );
}
