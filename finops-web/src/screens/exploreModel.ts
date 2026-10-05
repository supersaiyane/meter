import type { ApiExplore, ApiExploreGrouping, ApiExploreWindow } from '../api/types';
import type { BarSeries } from '../components/charts/StackedBar';
import { EXPLORER_FILTERS } from '../shell/sections';

/**
 * Cost Explorer's model, FEAT-065: what its controls are called, how its address becomes the
 * route's query, and how an answer becomes a chart and a table. Pure, so every rule here is
 * tested without rendering the screen.
 */

export type ExploreKey = (typeof EXPLORER_FILTERS)[number];
export type ExploreValues = Readonly<Record<ExploreKey, string>>;
export type ExploreChange = Partial<Record<ExploreKey, string>>;

/** The FOCUS columns a reader groups and filters by, in the order they are offered. */
export const COLUMNS = [
  'service',
  'service_category',
  'account',
  'region',
  'availability_zone',
  'charge_category',
  'commitment_discount_type',
  'commitment_discount_status',
] as const;
export type ExploreColumn = (typeof COLUMNS)[number];

/** Each column's name on screen, and its FOCUS name, which a practitioner also searches for. */
export const COLUMN_NAMES: Readonly<
  Record<ExploreColumn, { readonly name: string; readonly focus: string }>
> = {
  service: { name: 'Service', focus: 'ServiceName' },
  service_category: { name: 'Service category', focus: 'ServiceCategory' },
  account: { name: 'Sub account', focus: 'SubAccountId' },
  region: { name: 'Region', focus: 'RegionId' },
  availability_zone: { name: 'Availability zone', focus: 'AvailabilityZone' },
  charge_category: { name: 'Charge category', focus: 'ChargeCategory' },
  commitment_discount_type: { name: 'Commitment discount type', focus: 'CommitmentDiscountType' },
  commitment_discount_status: {
    name: 'Commitment discount status',
    focus: 'CommitmentDiscountStatus',
  },
};

export const PRESETS: readonly { readonly value: string; readonly name: string }[] = [
  { value: 'mtd', name: 'Month to date' },
  { value: '3m', name: '3 months' },
  { value: '6m', name: '6 months' },
  { value: '12m', name: '12 months' },
  { value: 'ytd', name: 'Year to date' },
  { value: 'custom', name: 'Custom' },
];

/** The measures by their FOCUS display names. */
export const METRIC_NAMES: Readonly<Record<string, string>> = {
  effective_cost: 'Effective Cost',
  billed_cost: 'Billed Cost',
  list_cost: 'List Cost',
  contracted_cost: 'Contracted Cost',
};

/** The route's word for a line item no value of a grouping claims. */
export const UNALLOCATED = 'unallocated';

const TAG = 'tag';
const TAG_PREFIX = 'tag:';
const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

export function isColumn(value: string): value is ExploreColumn {
  return (COLUMNS as readonly string[]).includes(value);
}

function one(key: ExploreKey, value: string): ExploreChange {
  return { [key]: value };
}

/** The route's query string from the screen's: the same names, the empty ones left out. */
export function apiQuery(values: ExploreValues): string {
  const params = new URLSearchParams();
  for (const key of EXPLORER_FILTERS) {
    if (values[key] !== '') params.set(key, values[key]);
  }
  return params.toString();
}

/** A grouping as its select names it: the column, or `tag:` and the key. */
export function groupingValue(dimension: string, tagKey: string): string {
  return dimension === TAG ? `${TAG_PREFIX}${tagKey}` : dimension;
}

/** The address a select's value sets, as one change, its tag key cleared for a column. */
export function groupingChange(axis: 'group_by' | 'then_by', value: string): ExploreChange {
  const tag = value.startsWith(TAG_PREFIX);
  const dimension = tag ? TAG : value;
  const key = tag ? value.slice(TAG_PREFIX.length) : '';
  return axis === 'group_by'
    ? { group_by: dimension, group_by_tag: key }
    : { then_by: dimension, then_by_tag: key };
}

/** What a grouping is called: the column's name, or the tag key it reads. */
export function groupingName(grouping: ApiExploreGrouping): string {
  if (grouping.dimension === TAG) return `Tag: ${grouping.tag_key ?? ''}`;
  return isColumn(grouping.dimension) ? COLUMN_NAMES[grouping.dimension].name : grouping.dimension;
}

/** A grouping value as a reader sees it. The unallocated bucket is named, never blank. */
export function valueName(value: string): string {
  return value === UNALLOCATED ? 'Unallocated' : value;
}

/** The address change that filters to one value of a grouping. */
export function filterTo(grouping: ApiExploreGrouping, value: string): ExploreChange {
  if (grouping.dimension === TAG) return { tag_key: grouping.tag_key ?? '', tag_value: value };
  return isColumn(grouping.dimension) ? one(grouping.dimension, value) : {};
}

export interface Chip {
  readonly label: string;
  /** The change that takes the filter away. */
  readonly clear: ExploreChange;
}

/** The filters in force, as chips a reader can take away. */
export function chipsOf(values: ExploreValues): readonly Chip[] {
  const columns = COLUMNS.filter((column) => values[column] !== '').map((column) => ({
    label: `${COLUMN_NAMES[column].name}: ${valueName(values[column])}`,
    clear: one(column, ''),
  }));
  if (values.tag_key === '' || values.tag_value === '') return columns;
  return [
    ...columns,
    {
      label: `Tag ${values.tag_key}: ${valueName(values.tag_value)}`,
      clear: { tag_key: '', tag_value: '' },
    },
  ];
}

function parts(iso: string): { readonly year: number; readonly month: number; readonly day: number } {
  const [year = 0, month = 1, day = 1] = iso.split('-').map(Number);
  return { year, month, day };
}

function monthName(month: number): string {
  return MONTHS[month - 1] ?? '';
}

/** A date as a reader says it: 1 August 2026. */
export function dayLabel(iso: string): string {
  const { year, month, day } = parts(iso);
  return `${String(day)} ${monthName(month)} ${String(year)}`;
}

/** A window as a reader says it, naming a month or a year once where both ends share it. */
export function windowLabel(window: ApiExploreWindow): string {
  const start = parts(window.start);
  const end = parts(window.end);
  if (window.start === window.end) return dayLabel(window.end);
  if (start.year !== end.year) return `${dayLabel(window.start)} to ${dayLabel(window.end)}`;
  if (start.month !== end.month) {
    return `${String(start.day)} ${monthName(start.month)} to ${dayLabel(window.end)}`;
  }
  return `${String(start.day)} to ${dayLabel(window.end)}`;
}

/** A chart category: a day as 1 Oct, a month as Oct 2026. */
export function bucketLabel(iso: string, granularity: string): string {
  const { year, month, day } = parts(iso);
  const short = monthName(month).slice(0, 3);
  return granularity === 'monthly' ? `${short} ${String(year)}` : `${String(day)} ${short}`;
}

/** The sentence above the figures: the window, the preset, and what it is compared with. */
export function periodLine(explore: ApiExplore): string {
  const preset = PRESETS.find((candidate) => candidate.value === explore.period)?.name ?? '';
  const compared = explore.previous_collected
    ? `, compared with ${windowLabel(explore.previous)}`
    : '';
  return `${windowLabel(explore.current)}, ${preset.toLowerCase()}${compared}`;
}

/** What a reader has to know before trusting the totals, one sentence each. */
export function notesFor(explore: ApiExplore): readonly string[] {
  const notes: string[] = [];
  if (explore.is_open) {
    notes.push('The period ends today and is still open, so it is not yet a whole period.');
  }
  const from = explore.collected_from;
  if (from !== null && from > explore.current.start) {
    notes.push(
      `Meter holds line items from ${dayLabel(from)}, so this period's total starts there and not on ${dayLabel(explore.current.start)}.`,
    );
  }
  if (!explore.previous_collected) {
    notes.push(
      from === null
        ? 'Meter holds no line items before this period, so it is not compared.'
        : `The period before, ${windowLabel(explore.previous)}, starts before ${dayLabel(from)}, the first day Meter holds, so it is not compared.`,
    );
  }
  return notes;
}

/** Money to the cent, as Figure draws it, for the tiles and the chart's table. */
export function dollars(value: number): string {
  const sign = value < 0 ? '-' : '';
  const amount = Math.abs(value).toLocaleString('en-GB', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${sign}$${amount}`;
}

/** A change, with its sign said even when it is a rise. */
export function signedDollars(value: number): string {
  return `${value > 0 ? '+' : ''}${dollars(value)}`;
}

/** The chart: one category per day or month, a series per named group and one for the rest. */
export function chartOf(explore: ApiExplore): {
  readonly categories: readonly string[];
  readonly series: readonly BarSeries[];
} {
  const buckets = [...new Set(explore.points.map((point) => point.bucket))].sort();
  const rest = explore.points.some((point) => point.series === null);
  const names: readonly (string | null)[] = [...explore.series, ...(rest ? [null] : [])];
  const costs = new Map(
    explore.points.map((point) => [JSON.stringify([point.bucket, point.series]), point.cost]),
  );
  const series = names.map((name) => ({
    key: name === null ? 'rest' : `group:${name}`,
    label: name === null ? 'Everything else' : valueName(name),
    provenance: 'measured' as const,
    // A day with no line item for a group cost that group nothing. Measured, not missing.
    values: buckets.map((bucket) => Number(costs.get(JSON.stringify([bucket, name])) ?? 0)),
  }));
  return { categories: buckets.map((bucket) => bucketLabel(bucket, explore.granularity)), series };
}

/** Each day's or month's total, oldest first, for the tile's trend line. */
export function bucketTotals(explore: ApiExplore): readonly number[] {
  const buckets = [...new Set(explore.points.map((point) => point.bucket))].sort();
  return buckets.map((bucket) =>
    explore.points
      .filter((point) => point.bucket === bucket)
      .reduce((sum, point) => sum + Number(point.cost), 0),
  );
}

export interface TableRow {
  readonly key: string;
  readonly first: string;
  readonly second: string | null;
  readonly thisPeriod: number;
  readonly previousPeriod: number | null;
  readonly change: number | null;
  /** The row standing for every row the limit left out. Not a value, so not a filter. */
  readonly rest: boolean;
}

/** The table's rows, and one more for what the row limit left out, so the totals reconcile. */
export function tableRows(explore: ApiExplore): readonly TableRow[] {
  const rows = explore.rows.map((row) => {
    const thisPeriod = Number(row.this_period);
    const previousPeriod = row.previous_period === null ? null : Number(row.previous_period);
    return {
      key: JSON.stringify([row.first, row.second]),
      first: row.first,
      second: row.second,
      thisPeriod,
      previousPeriod,
      change: previousPeriod === null ? null : thisPeriod - previousPeriod,
      rest: false,
    };
  });
  if (explore.rows_omitted === 0) return rows;
  const thisPeriod = Number(explore.omitted_this_period);
  const previousPeriod =
    explore.omitted_previous_period === null ? null : Number(explore.omitted_previous_period);
  return [
    ...rows,
    {
      key: 'rest',
      first: `${String(explore.rows_omitted)} more rows`,
      second: null,
      thisPeriod,
      previousPeriod,
      change: previousPeriod === null ? null : thisPeriod - previousPeriod,
      rest: true,
    },
  ];
}
