import { useQuotaRequests, useQuotas } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { FixtureBand } from '../components/FixtureBand';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import type { ApiQuota, ApiQuotaRequest, ApiUnmeasurableQuota } from '../api/types';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What this estate is allowed to run, and how much of that nobody can measure. FEAT-033.
 *
 * **Two lists, because one would have to sort the nulls.** A quota nothing measured has no
 * headroom, and that is not zero headroom. Put it in one list with the rest and it lands
 * somewhere: at the top it reads as urgent, at the bottom as safe, and neither is known. So
 * the measured ones are ranked by how full they are and the unmeasured ones are listed
 * alphabetically, which is the only order that makes no claim. P5 spec section 9.
 *
 * **The second list is expected to be longer, and the ratio is stated rather than implied.**
 * There is no single API for used against limit across AWS. Service Quotas gives limits, the
 * `AWS/Usage` namespace covers a subset, Trusted Advisor needs a support tier, and the rest
 * needs service specific calls that do not all exist. A product that hid that would be
 * showing a reader three healthy quotas and letting them assume the other forty were fine.
 *
 * **The bar is inverted, and this screen is the first caller that needs it.** `PercentCell`
 * carried an `inverted` flag with nothing passing it, because coverage and utilization are
 * both better high. A quota is the opposite: a high figure is the finding, so the ramp runs
 * the other way, and the flag existed precisely so the first screen needing it would not
 * reach for a colour override on a shared class.
 *
 * **Every figure here is measured.** Nothing is modelled, so no provenance judgement is being
 * made: a limit and a usage both come from a provider, and the only arithmetic this screen
 * does is one subtraction.
 */

/**
 * How full the quota is, from the headroom the server sent.
 *
 * Derived from headroom rather than from `used / limit`, although both are on the row. The
 * server ranks the list by headroom, so taking the bar from the same number guarantees the
 * picture and the order agree. Computing it independently would let a rounding difference put
 * a longer bar above a shorter one, which is the kind of wrongness nobody reports because it
 * looks like a rendering quirk.
 */
function fullness(quota: ApiQuota): number | null {
  if (quota.headroom === null) {
    return null;
  }
  return 1 - Number(quota.headroom);
}

/** What measured it, in words a reader can weigh one against another. */
const SOURCE_LABEL: Readonly<Record<string, string>> = {
  AWS_USAGE_METRIC: 'CloudWatch usage metric',
  TRUSTED_ADVISOR: 'Trusted Advisor',
  SERVICE_API: 'counted directly',
};

function where(quota: ApiQuota | ApiUnmeasurableQuota): string {
  // A global quota says so rather than showing a blank or a placeholder region. An account
  // level limit shown once per region would be added up by whoever read it.
  return quota.region_id ?? 'all regions';
}

/**
 * Where the detail page for this quota lives.
 *
 * Every row links, including the unmeasured ones. Otherwise the longer of the two lists is a
 * list of dead ends, and it is the list where a reader most wants to know whether anybody has
 * asked for an increase: a quota with no figure is exactly the one somebody requests blind.
 */
function pathFor(quota: ApiQuota | ApiUnmeasurableQuota): string {
  return `/govern/quotas/${quota.service_code}/${quota.quota_code}`;
}

function keyFor(quota: ApiQuota | ApiUnmeasurableQuota): string {
  return `${quota.account_id}:${quota.region_id ?? 'global'}:${quota.quota_code}`;
}

/** A figure the API sends as a decimal string, as a number to sort by, or absent. */
function amount(value: string | null): number | null {
  return value === null ? null : Number(value);
}

/**
 * The quota's name and code, linked to its page. Every row links, including the unmeasured
 * ones: otherwise the longer list is a list of dead ends, and it is the list where a reader
 * most wants to know whether anybody has asked for an increase.
 */
function quotaColumn<Row extends ApiQuota | ApiUnmeasurableQuota>(): Column<Row> {
  return {
    key: 'quota',
    header: 'Quota',
    render: (quota) => (
      <>
        <Link data-testid="quota-link" to={pathFor(quota)}>
          <strong>{quota.quota_name}</strong>
        </Link>
        <span data-testid="quota-code"> {quota.quota_code}</span>
      </>
    ),
    sortValue: (quota) => quota.quota_name,
  };
}

function placeColumns<Row extends ApiQuota | ApiUnmeasurableQuota>(): readonly Column<Row>[] {
  return [
    {
      key: 'account',
      header: 'Account',
      render: (quota) => quota.account_id,
      sortValue: (quota) => quota.account_id,
    },
    { key: 'region', header: 'Region', render: where, sortValue: where },
  ];
}

// No totals on any of the three: each row is a different quota in its own unit, and a sum of
// vCPUs, buckets and requests is a number that counts nothing.
const MEASURED_COLUMNS: readonly Column<ApiQuota>[] = [
  quotaColumn<ApiQuota>(),
  ...placeColumns<ApiQuota>(),
  {
    key: 'used',
    header: 'Used',
    numeric: true,
    render: (quota) => (
      <>
        {quota.used}
        <span> of {quota.limit ?? 'no published limit'}</span>
      </>
    ),
    sortValue: (quota) => Number(quota.used),
  },
  {
    key: 'full',
    header: 'Full',
    render: (quota) => (
      <PercentCell
        fraction={fullness(quota)}
        absent="The limit is not published, so how full this is cannot be stated."
        provenance="measured"
        inverted
      />
    ),
    sortValue: fullness,
  },
  {
    key: 'source',
    header: 'Measured by',
    cellTestId: 'quota-source',
    render: (quota) => SOURCE_LABEL[quota.source] ?? quota.source,
    sortValue: (quota) => SOURCE_LABEL[quota.source] ?? quota.source,
  },
];

const UNMEASURED_COLUMNS: readonly Column<ApiUnmeasurableQuota>[] = [
  quotaColumn<ApiUnmeasurableQuota>(),
  ...placeColumns<ApiUnmeasurableQuota>(),
  {
    key: 'limit',
    header: 'Limit',
    numeric: true,
    render: (quota) => quota.limit ?? 'no published limit',
    sortValue: (quota) => amount(quota.limit),
  },
  // No usage column at all, not an empty one. An empty cell in a column of numbers reads as a
  // measurement that came back zero, which is the one thing this must not say.
  {
    key: 'reason',
    header: 'Why there is no figure',
    prose: true,
    cellTestId: 'quota-reason',
    render: (quota) => quota.reason,
  },
];

const REQUEST_COLUMNS: readonly Column<ApiQuotaRequest>[] = [
  {
    key: 'quota',
    header: 'Quota',
    render: (request) => (
      <Link
        data-testid="request-quota-link"
        to={`/govern/quotas/${request.service_code}/${request.quota_code}`}
      >
        {request.quota_name}
      </Link>
    ),
    sortValue: (request) => request.quota_name,
  },
  {
    key: 'account',
    header: 'Account',
    render: (request) => request.account_id,
    sortValue: (request) => request.account_id,
  },
  {
    key: 'asked',
    header: 'Asked for',
    numeric: true,
    render: (request) => request.desired_value,
    sortValue: (request) => Number(request.desired_value),
  },
  {
    key: 'status',
    header: 'Status',
    cellTestId: 'request-status',
    render: (request) => request.status.replace('_', ' ').toLowerCase(),
    sortValue: (request) => request.status,
  },
  {
    key: 'requested',
    header: 'Requested',
    render: (request) => request.requested_at.slice(0, 10),
    sortValue: (request) => request.requested_at,
  },
];

export function QuotasScreen() {
  const query = useQuotas();
  const envelope = query.data?.data;
  useReportMeta('governance-quotas', envelope?.meta);

  // A second read rather than a field on the first, because a request is not a sample of
  // quotas: most are for quotas nothing can measure, so folding them into the quota payload
  // would invite a join that drops exactly the rows somebody is chasing.
  const requestQuery = useQuotaRequests();
  const requests = requestQuery.data?.data.data.requests ?? [];
  const open = requestQuery.data?.data.data.open_count ?? 0;

  const found = envelope?.data;
  const measurable = found?.measurable ?? [];
  const unmeasurable = found?.unmeasurable ?? [];
  const measured = found?.measured_count ?? 0;
  const total = found?.found_count ?? 0;
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    measurable.length + unmeasurable.length,
    'none',
    'quotas',
  );

  return (
    <section aria-label="Quotas">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <p data-testid="quotas-ratio">
            {measured} of {total} quotas have a usage figure. The rest have a limit and nothing
            measuring it, which is a limit of what AWS publishes rather than of this product:
            there is no single API for used against limit across its services.
          </p>

          <h3 data-testid="quotas-measured-heading">
            {measured === 1
              ? 'One quota with a usage figure'
              : `${String(measured)} quotas with a usage figure`}
          </h3>
          <div data-testid="quotas-measured">
            <DataTable
              rows={measurable}
              columns={MEASURED_COLUMNS}
              rowKey={keyFor}
              caption="Quotas with a usage figure, the fullest first"
              initialSort={{ key: 'full', direction: 'descending' }}
              rowAttributes={() => ({ 'data-testid': 'quota-measured' })}
            />
          </div>

          {unmeasurable.length > 0 ? (
            <>
              <h3 data-testid="quotas-unmeasured-heading">
                {unmeasurable.length === 1
                  ? 'One quota nothing measures'
                  : `${String(unmeasurable.length)} quotas nothing measures`}
              </h3>
              <div data-testid="quotas-unmeasured">
                <DataTable
                  rows={unmeasurable}
                  columns={UNMEASURED_COLUMNS}
                  rowKey={keyFor}
                  caption="Quotas with a limit and no usage, by name. Nothing here is at zero: nothing here has been measured, and the reason on each row says which source declined."
                  initialSort={{ key: 'quota', direction: 'ascending' }}
                  rowAttributes={() => ({ 'data-testid': 'quota-unmeasured' })}
                />
              </div>
            </>
          ) : null}

          {requests.length > 0 ? (
            <>
              <h3 data-testid="quota-requests-heading">
                {open === 1
                  ? 'One increase request still open'
                  : `${String(open)} increase requests still open`}
              </h3>
              <div data-testid="quota-requests">
                <DataTable
                  rows={requests}
                  columns={REQUEST_COLUMNS}
                  rowKey={(request) => request.request_id}
                  caption="Increases somebody asked AWS for, the open ones first. Settled requests stay, refusals included: somebody waiting on an increase wants to know it was denied three weeks ago more than they want a shorter list. Meter reads this history and never adds to it."
                  rowAttributes={(request) => ({
                    'data-testid': 'quota-request-row',
                    'data-status': request.status,
                  })}
                />
              </div>
            </>
          ) : null}
        </>
      </StateBoundary>
    </section>
  );
}
