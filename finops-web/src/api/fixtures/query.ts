import type {
  ApiEnvelope,
  ApiMeta,
  ApiQueryFinding,
  ApiQueryGroup,
  ApiQueryFindingDetail,
  ApiEnforcementAction,
  ApiSurfaceInstance,
} from '../types';

/**
 * The words for the cause codes, mirroring `finops_query/severity.py`. A second
 * copy, and the guard against drift is that an unknown code renders as the code
 * itself rather than as a blank, so a vocabulary change is visible rather than
 * silent.
 */
const CAUSE_LABEL: Readonly<Record<string, string>> = {
  ALERT_ALWAYS_ON: 'Alert rules running 24x7',
  VERY_FAST_REFRESH: 'Sub minute auto refresh',
  FAST_REFRESH: 'Fast auto refresh',
  VERY_WIDE_WINDOW: 'Very wide time window',
  WIDE_WINDOW: 'Wide time window',
  METRIC_FANOUT: 'Metric queries scanning many metrics',
  NO_REFRESH: 'Manual loads only',
  ENGINE_SCAN: 'Billed per volume scanned',
};

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
  // Two of the three workspaces answered. The third is the unreachable row
  // on the surfaces screen, and a fixture that reported full coverage over a
  // partial estate would be the exact failure these screens exist to prevent.
  scope_coverage: { visible: 2, total: 3, is_partial: true, unit: 'workspaces' },
  degraded: true,
  failures: [],
};

export const QUERY_FINDINGS: readonly ApiQueryFinding[] = [
  {
    finding_id: '11111111-1111-1111-1111-111111111111',
    dashboard_uid: 'abc123',
    dashboard_title: 'Platform overview',
    panel_title: 'Error rate by service',
    folder_uid: 'folder-platform',
    engine: 'LOGS_INSIGHTS',
    origin: 'PANEL',
    refresh_seconds: 10,
    window_seconds: 2592000,
    runs_per_day: '8640.00',
    scan_bytes_per_run: 4294967296,
    monthly_cost: '5184.00',
    provenance: 'modelled',
    measured_runs: null,
    // Critical. Severity is a dollar amount expressed on a five point scale,
    // per ADR-0016, so the most expensive finding is the most severe.
    severity: 'CRITICAL',
    cause: 'VERY_FAST_REFRESH',
    owner: 'platform-team@example.com',
    owner_source: 'FOLDER_MAP',
    why: 'Refreshes every 10 seconds against a 30 day window, so it rescans 4 GiB 8,640 times a day.',
    as_of: '2026-09-11T04:00:00Z',
    collected_at: '2026-09-11T09:54:00Z',
  },
  {
    finding_id: '22222222-2222-2222-2222-222222222222',
    dashboard_uid: 'def456',
    dashboard_title: 'Billing',
    panel_title: 'Invoice totals',
    folder_uid: 'folder-billing',
    engine: 'LOGS_INSIGHTS',
    origin: 'PANEL',
    refresh_seconds: 3600,
    window_seconds: 86400,
    runs_per_day: '24.00',
    scan_bytes_per_run: 536870912,
    monthly_cost: '1.80',
    provenance: 'measured',
    measured_runs: 24,
    severity: 'LOW',
    cause: 'NO_REFRESH',
    owner: null,
    owner_source: null,
    why: 'Hourly refresh over a one day window. Listed for completeness.',
    as_of: '2026-09-11T04:00:00Z',
    collected_at: '2026-09-11T09:54:00Z',
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
/**
 * The list row this detail expands, by id. Throws rather than asserting the
 * index is there: a detail built on a row that has been renumbered would
 * otherwise carry undefined into every field the two share.
 */
function listRow(findingId: string): ApiQueryFinding {
  const found = QUERY_FINDINGS.find((row) => row.finding_id === findingId);
  if (!found) {
    throw new Error(`no fixture finding with id ${findingId}`);
  }
  return found;
}

/**
 * Groups, summed from the findings above rather than written out again. A hand
 * written total is a second answer to the same question, and the whole point of
 * a group is that its figure is the sum of its rows.
 */
export const QUERY_GROUPS: ApiQueryGroup[] = ((): ApiQueryGroup[] => {
  const byCause = new Map<string, { findings: number; total: number }>();
  for (const finding of QUERY_FINDINGS) {
    const entry = byCause.get(finding.cause) ?? { findings: 0, total: 0 };
    byCause.set(finding.cause, {
      findings: entry.findings + 1,
      total: entry.total + Number(finding.monthly_cost),
    });
  }
  return [...byCause.entries()]
    .map(([cause, entry]) => ({
      cause,
      label: CAUSE_LABEL[cause] ?? cause,
      findings: entry.findings,
      monthly_cost: entry.total.toFixed(2),
      severity: entry.total >= 1000 ? 'CRITICAL' : entry.total >= 100 ? 'HIGH' : 'MEDIUM',
      as_of: '2026-09-11T04:00:00Z',
      collected_at: '2026-09-11T09:54:00Z',
    }))
    .sort((left, right) => Number(right.monthly_cost) - Number(left.monthly_cost));
})();

export function queryGroupsFixture(): ApiEnvelope<ApiQueryGroup[]> {
  return { data: QUERY_GROUPS, meta: FIXTURE_META };
}

export const QUERY_FINDING_DETAILS: Readonly<Record<string, ApiQueryFindingDetail>> = {
  '11111111-1111-1111-1111-111111111111': {
    ...listRow('11111111-1111-1111-1111-111111111111'),
    query_text:
      'fields @timestamp, @message\n| filter @message like /ERROR/\n| stats count() by bin(5m)',
    targets: ['/aws/ecs/meter-api'],
    region: 'eu-west-2',
    last_editor: null,
    rate_usd_per_gib: '0.005',
    accuracy_percent: null,
    applied_change_id: null,
  },
  '22222222-2222-2222-2222-222222222222': {
    ...listRow('22222222-2222-2222-2222-222222222222'),
    query_text: 'fields @timestamp, invoice_total\n| sort @timestamp desc\n| limit 20',
    targets: ['/aws/lambda/billing-export'],
    region: 'eu-west-2',
    last_editor: null,
    rate_usd_per_gib: '0.005',
    accuracy_percent: null,
    applied_change_id: null,
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
 * All three are `AMG`, because that is the only kind with an adapter:
 * `SurfaceKind` also names `SELF_HOSTED` and `CLOUD`,
 * and both were descoped as TASK-P2-007 and TASK-P2-008. A fixture claiming
 * them would show an estate that cannot currently exist, which is the same
 * mistake as inventing a calibration.
 *
 * One instance is unreachable and carries its cause, because that is the row
 * this screen exists for. Its query count is null rather than zero.
 */
export const SURFACE_INSTANCES: readonly ApiSurfaceInstance[] = [
  {
    instance_id: '0a1b2c3d-0000-4000-8000-000000000001',
    name: 'meter-prod-eu-west-1',
    kind: 'AMG',
    endpoint: 'https://g-0a1b2c3d.grafana-workspace.eu-west-1.amazonaws.com',
    account_id: '111122223333',
    region_id: 'eu-west-1',
    reachable: false,
    unreachable_reason: 'AccessDenied',
    refresh_floor_seconds: null,
    query_count: null,
    as_of: '2026-09-11T04:00:00Z',
    collected_at: '2026-09-11T09:54:00Z',
  },
  {
    instance_id: '4e5f6a7b-0000-4000-8000-000000000002',
    name: 'meter-prod-eu-west-2',
    kind: 'AMG',
    endpoint: 'https://g-4e5f6a7b.grafana-workspace.eu-west-2.amazonaws.com',
    account_id: '111122223333',
    region_id: 'eu-west-2',
    reachable: true,
    unreachable_reason: null,
    refresh_floor_seconds: null,
    query_count: 2,
    as_of: '2026-09-11T04:00:00Z',
    collected_at: '2026-09-11T09:54:00Z',
  },
  {
    instance_id: '8c9d0e1f-0000-4000-8000-000000000003',
    name: 'meter-staging-eu-west-2',
    kind: 'AMG',
    endpoint: 'https://g-8c9d0e1f.grafana-workspace.eu-west-2.amazonaws.com',
    account_id: '444455556666',
    region_id: 'eu-west-2',
    reachable: true,
    unreachable_reason: null,
    refresh_floor_seconds: 30,
    // A genuine zero: reachable, read, and holding nothing. It renders as 0 and
    // must not be confusable with the null above it.
    query_count: 0,
    as_of: '2026-09-11T04:00:00Z',
    collected_at: '2026-09-11T09:54:00Z',
  },
];

export function surfaceInstancesFixture(): ApiEnvelope<ApiSurfaceInstance[]> {
  return { data: [...SURFACE_INSTANCES], meta: FIXTURE_META };
}

/**
 * What the controls did.
 *
 * Two rows on purpose. A THROTTLE that expires, so the countdown and the
 * absolute time both have something to show, and an ALERT that never expires
 * and cannot be revoked, so the absent revoke control has a row to be absent
 * from. `reason_finding_id` points at a real finding, because an action nobody
 * can trace to its cause is an action nobody will dare revoke.
 */
export const ENFORCEMENT_ACTIONS: readonly ApiEnforcementAction[] = [
  {
    action_id: '33333333-3333-3333-3333-333333333333',
    action: 'THROTTLE',
    principal: 'arn:aws:iam::role/grafana-datasource',
    applied_at: '2026-09-06T09:45:00Z',
    expires_at: '2026-09-06T10:45:00Z',
    reason_finding_id: '11111111-1111-1111-1111-111111111111',
    revocable: true,
  },
  {
    action_id: '44444444-4444-4444-4444-444444444444',
    action: 'ALERT',
    principal: 'arn:aws:iam::role/reporting',
    applied_at: '2026-09-05T11:00:00Z',
    expires_at: null,
    reason_finding_id: '22222222-2222-2222-2222-222222222222',
    revocable: false,
  },
];

export function enforcementActionsFixture(): ApiEnvelope<ApiEnforcementAction[]> {
  return { data: [...ENFORCEMENT_ACTIONS], meta: FIXTURE_META };
}
