import type {
  ApiEnvelope,
  ApiMeta,
  ApiQueryFinding,
  ApiQueryFindingDetail,
  ApiSurfaceInstance,
} from '../types';

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
    monthly_cost: '5184.00',
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
    bytes_scanned_per_run: 536870912,
    monthly_cost: '1.80',
    provenance: 'measured',
    severity: 1,
    owner: 'unattributed',
    why: 'Hourly refresh over a one day window. Listed for completeness.',
  },
];

export function queryFindingsFixture(): ApiEnvelope<ApiQueryFinding[]> {
  return { data: [...QUERY_FINDINGS], meta: FIXTURE_META };
}

/**
 * Detail rows, keyed by finding.
 *
 * `accuracy_percent` is null on both, because FEAT-018 has not published a
 * calibration. Inventing one to make the screen look finished is the one thing
 * this fixture must not do: the honest rendering of an unpublished accuracy is
 * to say it is unpublished.
 *
 * The measured fields are null for the same reason. FEAT-013 is the overlay
 * that fills them.
 */
export const QUERY_FINDING_DETAILS: Readonly<Record<string, ApiQueryFindingDetail>> = {
  '11111111-1111-1111-1111-111111111111': {
    finding_id: '11111111-1111-1111-1111-111111111111',
    dashboard_title: 'Platform overview',
    panel_title: 'Error rate by service',
    query_text:
      'fields @timestamp, @message\n| filter @message like /ERROR/\n| stats count() by bin(5m)',
    target: '/aws/ecs/meter-api',
    engine: 'CloudWatch Logs Insights',
    refresh_seconds: 10,
    window_seconds: 2592000,
    runs_per_day: 8640,
    bytes_scanned_per_run: 4294967296,
    rate_usd_per_gib: '0.005',
    monthly_cost: '5184.00',
    provenance: 'modelled',
    accuracy_percent: null,
    measured_runs_per_day: null,
    measured_bytes_scanned_per_run: null,
  },
  '22222222-2222-2222-2222-222222222222': {
    finding_id: '22222222-2222-2222-2222-222222222222',
    dashboard_title: 'Billing',
    panel_title: 'Invoice totals',
    query_text: 'fields @timestamp, invoice_total\n| sort @timestamp desc\n| limit 20',
    target: '/aws/lambda/billing-export',
    engine: 'CloudWatch Logs Insights',
    refresh_seconds: 3600,
    window_seconds: 86400,
    runs_per_day: 24,
    bytes_scanned_per_run: 536870912,
    rate_usd_per_gib: '0.005',
    monthly_cost: '1.80',
    provenance: 'measured',
    accuracy_percent: null,
    measured_runs_per_day: 24,
    measured_bytes_scanned_per_run: 536870912,
  },
};

/** Null for an id nothing knows about, which the screen renders as a cause. */
export function queryFindingDetailFixture(
  id: string,
): ApiEnvelope<ApiQueryFindingDetail | null> {
  return { data: QUERY_FINDING_DETAILS[id] ?? null, meta: FIXTURE_META };
}

/**
 * The surfaces queries live in.
 *
 * All three are `managed_grafana`, because that is the only kind with an
 * adapter: `SurfaceKind` also names `self_hosted_grafana` and `grafana_cloud`,
 * and both were descoped as TASK-P2-007 and TASK-P2-008. A fixture claiming
 * them would show an estate that cannot currently exist, which is the same
 * mistake as inventing a calibration.
 *
 * One instance is unreachable and carries its cause, because that is the row
 * this screen exists for. Its query count is null rather than zero.
 */
export const SURFACE_INSTANCES: readonly ApiSurfaceInstance[] = [
  {
    surface_id: 'ws-0a1b2c3d',
    name: 'meter-prod-eu-west-1',
    kind: 'managed_grafana',
    location: 'g-0a1b2c3d.grafana-workspace.eu-west-1.amazonaws.com',
    reachable: false,
    unreachable_cause: 'AccessDenied',
    query_count: null,
  },
  {
    surface_id: 'ws-4e5f6a7b',
    name: 'meter-prod-eu-west-2',
    kind: 'managed_grafana',
    location: 'g-4e5f6a7b.grafana-workspace.eu-west-2.amazonaws.com',
    reachable: true,
    unreachable_cause: null,
    query_count: 2,
  },
  {
    surface_id: 'ws-8c9d0e1f',
    name: 'meter-staging-eu-west-2',
    kind: 'managed_grafana',
    location: 'g-8c9d0e1f.grafana-workspace.eu-west-2.amazonaws.com',
    reachable: true,
    unreachable_cause: null,
    // A genuine zero: reachable, read, and holding nothing. It renders as 0 and
    // must not be confusable with the null above it.
    query_count: 0,
  },
];

export function surfaceInstancesFixture(): ApiEnvelope<ApiSurfaceInstance[]> {
  return { data: [...SURFACE_INSTANCES], meta: FIXTURE_META };
}
