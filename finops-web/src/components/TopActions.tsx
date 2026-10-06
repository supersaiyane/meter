import { Link } from '../shell/links';
import { DataTable } from './DataTable';
import { wasteClassName } from './displayNames';

import type { ApiRecommendation } from '../api/types';
import { Figure } from './Figure';
import { SeverityBadge } from './SeverityBadge';
import type { Freshness } from './provenance';
import { severityLevel } from '../screens/querySeverity';
import { PER_GROUP, riskLabel } from './actionRisk';
import type { Column } from './tableConfig';

/**
 * What to do this morning, ranked, with what each one costs if it is wrong.
 *
 * FEAT-052, adopted from the 2026-09-26 IBM Turbonomic review, whose Top Actions widget
 * ranks the five most valuable actions per category and flags the ones that can be applied
 * immediately. We cannot flag that, because Meter applies nothing, constraint 6. What
 * transfers is the ranking and the risk.
 *
 * **Two groups, and the second one is short on purpose.** Biggest saving is ranked by money,
 * per ADR-0016, which is the same order `/waste` uses so a reader moving between the two
 * sees the same list. No regret is reversible and disturbing nothing, and only three of the
 * waste classes qualify, so this group is often nearly empty. That is the honest
 * shape rather than a defect: a page of easy wins would be inventing most of them.
 *
 * **Every row says whether it is permanent.** This is the part a naive low risk flag gets
 * wrong. Five of the eight classes that disturb nothing cannot be undone, including the two
 * a reader is most likely to apply without thinking: releasing an unassociated address and
 * setting a retention period on a log group. So the label leads with permanent rather than
 * with the absence of disruption.
 *
 * It owns no query. Every row comes from the same hook `/waste` reads, which is the home
 * screen's rule: a panel with its own query will one day disagree with the screen it
 * summarises, and a reader who catches that stops trusting both.
 */

export interface TopActionsProps {
  /** The recommendations the waste hook returned, in whatever order it returned them. */
  readonly recommendations: readonly ApiRecommendation[];
  /**
   * The timestamps behind these figures, from the same envelope the rows came in.
   *
   * Required rather than optional because `Figure` requires it, and that requirement is the
   * point: a number with no provenance and no timestamps should be a compile error rather
   * than a review comment.
   */
  readonly freshness: Freshness;
}

function openOnly(rows: readonly ApiRecommendation[]): readonly ApiRecommendation[] {
  // A finding somebody has already accepted or rejected is not something to do this morning.
  return rows.filter((row) => row.lifecycle === 'OPEN');
}

function bySaving(rows: readonly ApiRecommendation[]): readonly ApiRecommendation[] {
  // Sorted here rather than trusted, because this panel is handed whatever order the hook
  // returned and a panel that assumed one would be silently wrong the day a filter changed.
  return [...rows].sort(
    (left, right) =>
      Number(right.estimated_monthly_saving) - Number(left.estimated_monthly_saving),
  );
}

/**
 * A group's findings, TASK-P8-013 on `DataTable`, ranked by money and sortable by anything.
 * No total: a group can hold two findings on one resource that are alternatives, and adding
 * their savings would count one saving twice.
 */
function columnsFor(freshness: Freshness): readonly Column<ApiRecommendation>[] {
  return [
    {
      key: 'finding',
      header: 'Finding',
      rowHeader: true,
      render: (row) => (
        <>
          <Link to="/optimize">{wasteClassName(row.waste_class)}</Link>
          {/* The resource, because a class on its own names no work. */}
          <span> {row.resource_id}</span>
        </>
      ),
      sortValue: (row) => wasteClassName(row.waste_class),
    },
    {
      key: 'account',
      header: 'Account',
      render: (row) => row.account_id,
      sortValue: (row) => row.account_id,
    },
    {
      key: 'saving',
      header: 'Estimated monthly savings',
      numeric: true,
      // Modelled, never measured. Figure carries the label.
      render: (row) => (
        <Figure
          value={{ kind: 'modelled', amount: Number(row.estimated_monthly_saving) }}
          freshness={freshness}
          unit="usd"
        />
      ),
      sortValue: (row) => Number(row.estimated_monthly_saving),
    },
    {
      key: 'severity',
      header: 'Severity',
      // Through the one shared mapping, so this panel and the recommendations screen cannot
      // mean different things by high.
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
      sortValue: (row) => severityLevel(row.severity),
    },
    {
      key: 'risk',
      header: 'If it is wrong',
      prose: true,
      // The label is the scan, the sentence is the decision. Both, because a reader who only
      // sees the label will act on the wrong one of them.
      render: (row) => (
        <>
          <strong>{riskLabel(row)}</strong>
          <span> {row.risk_why}</span>
        </>
      ),
    },
  ];
}

function Group({
  id,
  heading,
  explains,
  rows,
  total,
  freshness,
}: {
  readonly id: string;
  readonly heading: string;
  readonly explains: string;
  readonly rows: readonly ApiRecommendation[];
  readonly total: number;
  readonly freshness: Freshness;
}) {
  return (
    <div data-testid={id}>
      <h4>{heading}</h4>
      <p>{explains}</p>
      {rows.length === 0 ? (
        // Said, not blank. An empty group is a claim about the estate and has to read as one.
        <p data-testid={`${id}-empty`}>
          Nothing open in this group, which is an answer rather than a gap.
        </p>
      ) : (
        <DataTable
          rows={rows}
          columns={columnsFor(freshness)}
          rowKey={(row) => row.recommendation_id}
          caption={
            rows.length === total
              ? `All ${String(total)}`
              : `The ${String(rows.length)} of ${String(total)} worth doing first`
          }
          initialSort={{ key: 'saving', direction: 'descending' }}
        />
      )}
    </div>
  );
}

export function TopActions({ recommendations, freshness }: TopActionsProps) {
  const open = openOnly(recommendations);
  const ranked = bySaving(open);
  const noRegret = ranked.filter((row) => row.is_no_regret);

  return (
    <section data-testid="top-actions" aria-label="Top actions">
      <h3>
        <Link to="/optimize">Top actions</Link>
      </h3>
      <Group
        id="top-actions-saving"
        heading="Biggest saving"
        explains="Ranked by money, the same order the recommendations screen uses."
        rows={ranked.slice(0, PER_GROUP)}
        total={open.length}
        freshness={freshness}
      />
      <Group
        id="top-actions-no-regret"
        heading="No regret"
        explains={
          'Reversible, and nothing stops to apply them. Most kinds of finding do not ' +
          'qualify, so this group is short by design rather than by accident.'
        }
        rows={noRegret.slice(0, PER_GROUP)}
        total={noRegret.length}
        freshness={freshness}
      />
      {/* The absence that matters. There is no performance category here because Meter has
          no performance dimension at all, which the competitive review records as the
          largest gap that is not obvious from a feature list. Naming it beats leaving a
          reader to assume the two groups are the whole picture. */}
      <p data-testid="top-actions-absent">
        No performance group. Meter judges what is oversized and never what is starved, so
        nothing here can tell you a workload needs more.
      </p>
    </section>
  );
}
