import type { ApiEnvelope, ApiMeta, ApiQueryFinding } from '../types';

/**
 * Fixture data for the P2 query surfaces, per
 * `docs/13-UI-ARCHITECTURE.md` section 11.
 *
 * This is production code, not test code. It ships in the bundle and renders in
 * a browser, under the FIXTURE DATA band, until the routes exist. Putting it
 * under `__tests__` would have made a screen import from a test directory.
 *
 * The rows are deliberately not all happy. One modelled and expensive, one
 * measured and trivial, one unattributed. A fixture with only the happy path
 * pins the wrong screen.
 */

export const FIXTURE_META: ApiMeta = {
  as_of: '2026-09-11T04:00:00Z',
  collected_at: '2026-09-11T09:54:00Z',
  scope_coverage: { visible: 2, total: 2, is_partial: false },
  degraded: false,
  failures: [],
};

export const QUERY_FINDINGS: readonly ApiQueryFinding[] = [
  {
    finding_id: '11111111-1111-1111-1111-111111111111',
    dashboard_uid: 'abc123',
    dashboard_title: 'Platform overview',
    panel_title: 'Error rate by service',
    refresh_seconds: 10,
    window_seconds: 2592000,
    runs_per_day: 8640,
    bytes_scanned_per_run: 4294967296,
    monthly_cost: '12400.00',
    provenance: 'modelled',
    // Critical. Severity is a dollar amount expressed on a five point scale,
    // per ADR-0016, so the most expensive finding is the most severe.
    severity: 5,
    owner: 'platform-team',
    why: 'Refreshes every 10 seconds against a 30 day window, so it rescans 4 GiB 8,640 times a day.',
  },
  {
    finding_id: '22222222-2222-2222-2222-222222222222',
    dashboard_uid: 'def456',
    dashboard_title: 'Billing',
    panel_title: 'Invoice totals',
    refresh_seconds: 3600,
    window_seconds: 86400,
    runs_per_day: 24,
    bytes_scanned_per_run: 1048576,
    monthly_cost: '3.20',
    provenance: 'measured',
    severity: 1,
    owner: 'unattributed',
    why: 'Hourly refresh over a one day window. Listed for completeness.',
  },
];

export function queryFindingsFixture(): ApiEnvelope<ApiQueryFinding[]> {
  return { data: [...QUERY_FINDINGS], meta: FIXTURE_META };
}
