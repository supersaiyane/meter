import type { Account, ApiEnvelope, ApiExplore, ApiForecast, ApiMeta } from '../../api/types';
import { fileNameOf, type ApiClient, type DownloadedFile } from '../../api/client';
import type { FlatNode } from '../../components/orgNodes';

export function metaOf(partial: Partial<ApiMeta> = {}): ApiMeta {
  return {
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:30:00Z',
    scope_coverage: { visible: 2, total: 2, is_partial: false, unit: 'accounts' },
    degraded: false,
    failures: [],
    ...partial,
  };
}

export function accountOf(id: string, health: string): Account {
  return {
    provider: 'aws',
    account_id: id,
    name: `name-${id}`,
    status: 'ACTIVE',
    role_health: health,
    role_health_checked_at: '2026-08-27T09:00:00Z',
    role_health_error: health === 'HEALTHY' ? null : 'the trust policy names another principal',
    as_of: '2026-08-27T09:00:00Z',
    collected_at: '2026-08-27T09:30:00Z',
  };
}

export const TREE: FlatNode[] = [
  {
    node_id: 'r-root',
    node_type: 'ROOT',
    parent_node_id: null,
    name: 'root',
    path: '/r-root',
    depth: 0,
    reachable: true,
  },
  {
    node_id: '111122223333',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'production',
    path: '/r-root/111122223333',
    depth: 1,
    reachable: true,
  },
  {
    node_id: '444455556666',
    node_type: 'ACCOUNT',
    parent_node_id: 'r-root',
    name: 'finance',
    path: '/r-root/444455556666',
    depth: 1,
    reachable: false,
  },
];

/**
 * A client that answers a fixed envelope per path, or fails.
 *
 * `posted` records what was written, so a test can assert that a control which
 * should not have called anything did not, which is the half of a refusal that
 * an assertion on the rendering alone would miss.
 */
export const posted: string[] = [];

/**
 * What each write carried, in the order of `posted`, and undefined for one that carried no
 * body. A question to the assistant travels in the body, and a test asserting it never reached
 * the URL needs to see both halves.
 */
export const postedBodies: unknown[] = [];

export function clientReturning(
  answers: Readonly<Record<string, ApiEnvelope<unknown>>>,
  failure?: Error,
  /**
   * Answers for `getFile`, which serves an export rather than an envelope. Its own
   * map rather than a union in `answers`, because a stub that guessed whether a
   * value was a file or a payload would guess wrong exactly when a test cared.
   */
  files: Readonly<Record<string, string>> = {},
): ApiClient {
  return {
    getFile: (path: string): Promise<DownloadedFile> => {
      if (failure) return Promise.reject(failure);
      const answer = files[path];
      if (answer === undefined) {
        return Promise.reject(new Error(`no file stub for ${path}`));
      }
      return Promise.resolve({ name: fileNameOf(null, path), body: new Blob([answer]) });
    },
    post: <T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> => {
      posted.push(path);
      postedBodies.push(body);
      if (failure) return Promise.reject(failure);
      const answer = answers[path];
      if (answer === undefined) {
        return Promise.reject(new Error(`no stub for ${path}`));
      }
      return Promise.resolve(answer as ApiEnvelope<T>);
    },
    get: <T>(path: string): Promise<ApiEnvelope<T>> => {
      if (failure) return Promise.reject(failure);
      const answer = answers[path];
      if (answer === undefined) {
        return Promise.reject(new Error(`no stub for ${path}`));
      }
      return Promise.resolve(answer as ApiEnvelope<T>);
    },
  };
}

/**
 * A Cost Explorer answer whose parts agree: the rows, the points and the totals all add up to
 * $4,512.71 this period and $4,203.10 before, the way the route's own answers do. The chart
 * names two groups, unallocated among them, and folds the other two into everything else.
 */
export function exploreOf(partial: Partial<ApiExplore> = {}): ApiExplore {
  return {
    metric: 'effective_cost',
    metrics_available: ['effective_cost', 'billed_cost', 'list_cost'],
    period: 'mtd',
    granularity: 'daily',
    current: { start: '2026-10-01', end: '2026-10-05' },
    previous: { start: '2026-09-01', end: '2026-09-05' },
    is_open: true,
    collected_from: '2026-08-01',
    previous_collected: true,
    group_by: { dimension: 'service', tag_key: null },
    then_by: null,
    tag_keys: ['team', 'finops:module'],
    total_this_period: '4512.71',
    total_previous_period: '4203.10',
    series: ['AmazonEC2', 'unallocated'],
    points: [
      { bucket: '2026-10-01', series: 'AmazonEC2', cost: '1000.00' },
      { bucket: '2026-10-01', series: 'unallocated', cost: '500.00' },
      { bucket: '2026-10-01', series: null, cost: '600.00' },
      { bucket: '2026-10-02', series: 'AmazonEC2', cost: '1388.40' },
      { bucket: '2026-10-02', series: 'unallocated', cost: '524.31' },
      { bucket: '2026-10-02', series: null, cost: '500.00' },
    ],
    rows: [
      { first: 'AmazonEC2', second: null, this_period: '2388.40', previous_period: '2201.00' },
      { first: 'unallocated', second: null, this_period: '1024.31', previous_period: '912.10' },
      { first: 'AmazonRDS', second: null, this_period: '600.00', previous_period: '590.00' },
      { first: 'AmazonS3', second: null, this_period: '500.00', previous_period: '500.00' },
    ],
    row_limit: 500,
    rows_omitted: 0,
    omitted_this_period: '0',
    omitted_previous_period: '0',
    ...partial,
  };
}

/**
 * A forecast answer whose parts agree: October billed to the 4th at $2,000.00, the band opening
 * from it and ending on the month end range, November shown, December withheld for its misses
 * and January for want of tests, and a backtest of three months whose ranges hold two of them.
 */
export function forecastOf(partial: Partial<ApiForecast> = {}): ApiForecast {
  const days = Array.from({ length: 31 }, (_, index) => {
    const day = `2026-10-${String(index + 1).padStart(2, '0')}`;
    if (index < 4) {
      return { day, billed: String(500 * (index + 1)), low: null, high: null };
    }
    const share = (index - 3) / 27;
    return {
      day,
      billed: null,
      low: (2000 + 13000 * share).toFixed(2),
      high: (2000 + 14000 * share).toFixed(2),
    };
  });
  return {
    provenance: 'forecast',
    method: 'weekday profile',
    method_detail:
      'Each day ahead is the average of the same weekday over the eight weeks before the forecast was made.',
    interval_percent: 80,
    max_median_miss: '0.15',
    min_held_out: 3,
    billed_through: '2026-10-04',
    billed_to_date: '2000.00',
    month_end: {
      month: '2026-10-01',
      figure: { low: '15000.00', high: '16000.00' },
      withheld: null,
      median_miss: '0.0595',
      held_out: 3,
    },
    days,
    ahead: [
      {
        month: '2026-11-01',
        figure: { low: '15700.00', high: '16100.00' },
        withheld: null,
        median_miss: '0.1110',
        held_out: 4,
      },
      {
        month: '2026-12-01',
        figure: null,
        withheld:
          'Tested on 3 months, it missed by 15.3 percent at the median, above the 15 percent it has to stay within.',
        median_miss: '0.1533',
        held_out: 3,
      },
      {
        month: '2027-01-01',
        figure: null,
        withheld:
          'The forecast is tested on 3 complete months before it is shown, and Meter holds 2 it can be tested on.',
        median_miss: '0.1961',
        held_out: 2,
      },
    ],
    backtest: [
      {
        month: '2026-09-01',
        actual: '15200.00',
        miss: '0.0400',
        low: '14900.00',
        high: '15900.00',
        within: true,
      },
      {
        month: '2026-08-01',
        actual: '17100.00',
        miss: '0.0790',
        low: '15000.00',
        high: '16000.00',
        within: false,
      },
      {
        month: '2026-07-01',
        actual: '15400.00',
        miss: '0.0595',
        low: '14800.00',
        high: '15800.00',
        within: true,
      },
    ],
    ...partial,
  };
}
