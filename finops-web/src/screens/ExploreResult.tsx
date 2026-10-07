import type { ApiExplore, ApiExploreGrouping } from '../api/types';
import { KpiTile, StackedBar } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import type { Freshness, Provenance } from '../components/provenance';
import type { Column, ColumnTotal } from '../components/tableConfig';
import { Link } from '../shell/links';
import {
  METRIC_NAMES,
  apiQuery,
  bucketTotals,
  chartOf,
  dollars,
  filterTo,
  groupingName,
  notesFor,
  periodLine,
  signedDollars,
  tableRows,
  valueName,
  windowLabel,
  type ExploreValues,
  type TableRow,
} from './exploreModel';

/**
 * What Cost Explorer answers, FEAT-065, in the layout the owner approved on 2026-10-05: the
 * period and what to know about it, three tiles, the chart by the first grouping, then one
 * table of both groupings. Every value in the table links to the same view filtered to it.
 */
interface ExploreResultProps {
  readonly explore: ApiExplore;
  readonly values: ExploreValues;
  readonly freshness: Freshness;
}

function figure(amount: number, freshness: Freshness) {
  return <Figure value={{ kind: 'measured', amount }} freshness={freshness} />;
}

function totalOf(
  pick: (row: TableRow) => number | null,
  freshness: Freshness,
): ColumnTotal<TableRow> {
  return {
    value: pick,
    unit: () => 'USD',
    provenance: (): Provenance => 'measured',
    render: (sum) => figure(sum, freshness),
  };
}

function valueCell(grouping: ApiExploreGrouping, value: string, values: ExploreValues) {
  const search = apiQuery({ ...values, ...filterTo(grouping, value) });
  return (
    <Link to={{ search: `?${search}` }} title={`Filter to ${valueName(value)}`}>
      {valueName(value)}
    </Link>
  );
}

function columnsFor(
  explore: ApiExplore,
  values: ExploreValues,
  freshness: Freshness,
): readonly Column<TableRow>[] {
  const { group_by: first, then_by: second } = explore;
  const firstColumn: Column<TableRow> = {
    key: 'first',
    header: groupingName(first),
    // The row standing for what the limit left out is not a value, so it filters to nothing.
    render: (row) => (row.rest ? row.first : valueCell(first, row.first, values)),
    sortValue: (row) => row.first,
  };
  const secondColumn: readonly Column<TableRow>[] =
    second === null
      ? []
      : [
          {
            key: 'second',
            header: groupingName(second),
            render: (row) =>
              row.rest || row.second === null ? '' : valueCell(second, row.second, values),
            sortValue: (row) => row.second,
          },
        ];
  return [
    firstColumn,
    ...secondColumn,
    {
      key: 'this',
      header: 'This period',
      numeric: true,
      render: (row) => figure(row.thisPeriod, freshness),
      sortValue: (row) => row.thisPeriod,
      total: totalOf((row) => row.thisPeriod, freshness),
    },
    {
      key: 'previous',
      header: 'Previous period',
      numeric: true,
      // Not collected is a different answer from a group that cost nothing then, so it is
      // said, and the column refuses a total rather than adding it as zero.
      render: (row) =>
        row.previousPeriod === null ? 'Not collected' : figure(row.previousPeriod, freshness),
      sortValue: (row) => row.previousPeriod,
      total: totalOf((row) => row.previousPeriod, freshness),
    },
    {
      key: 'change',
      header: 'Change',
      numeric: true,
      render: (row) => (row.change === null ? 'Not available' : figure(row.change, freshness)),
      sortValue: (row) => row.change,
      total: totalOf((row) => row.change, freshness),
    },
  ];
}

export function ExploreResult({ explore, values, freshness }: ExploreResultProps) {
  const metric = METRIC_NAMES[explore.metric] ?? explore.metric;
  const thisTotal =
    explore.total_this_period === null ? null : Number(explore.total_this_period);
  const previousTotal =
    explore.total_previous_period === null ? null : Number(explore.total_previous_period);
  const change =
    thisTotal !== null && previousTotal !== null ? thisTotal - previousTotal : null;
  const against = windowLabel(explore.previous);
  const chart = chartOf(explore);
  const by = groupingName(explore.group_by);
  const then = explore.then_by === null ? '' : ` and ${groupingName(explore.then_by)}`;
  const unit = explore.granularity === 'monthly' ? 'month' : 'day';

  return (
    <div data-testid="explore-result">
      <p data-testid="cost-period">{periodLine(explore)}</p>
      {notesFor(explore).map((note) => (
        <p key={note} data-testid="explore-note">
          {note}
        </p>
      ))}
      <div data-testid="explore-kpis">
        <KpiTile
          label={`${metric}, this period`}
          value={thisTotal}
          previous={previousTotal}
          points={bucketTotals(explore)}
          provenance="measured"
          format={dollars}
          period={against}
        />
        <KpiTile
          label="Previous period"
          value={previousTotal}
          previous={null}
          points={[]}
          provenance="measured"
          format={dollars}
          period={against}
        />
        <KpiTile
          label="Change"
          value={change}
          previous={null}
          points={[]}
          provenance="measured"
          format={signedDollars}
          period={against}
        />
      </div>
      <div data-testid="explore-chart">
        <StackedBar
          categories={chart.categories}
          series={chart.series}
          label={`${metric} by ${unit}, by ${by}`}
          format={dollars}
          categoryName={unit === 'month' ? 'Month' : 'Day'}
          orientation="columns"
        />
      </div>
      <div data-testid="explore-table">
        <DataTable
          rows={tableRows(explore)}
          columns={columnsFor(explore, values, freshness)}
          rowKey={(row) => row.key}
          caption={`${metric} by ${by}${then}`}
          initialSort={{ key: 'this', direction: 'descending' }}
        />
      </div>
    </div>
  );
}
