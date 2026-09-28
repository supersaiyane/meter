import { useQuotas } from '../api/queries';
import { FixtureBand } from '../components/FixtureBand';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
import type { ApiQuota, ApiUnmeasurableQuota } from '../api/types';
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

function keyFor(quota: ApiQuota | ApiUnmeasurableQuota): string {
  return `${quota.account_id}:${quota.region_id ?? 'global'}:${quota.quota_code}`;
}

function Measured({ quota }: { readonly quota: ApiQuota }) {
  return (
    <tr data-testid="quota-measured">
      <td>
        <strong>{quota.quota_name}</strong>
        <span data-testid="quota-code"> {quota.quota_code}</span>
      </td>
      <td>{quota.account_id}</td>
      <td>{where(quota)}</td>
      <td>
        {quota.used}
        <span> of {quota.limit ?? 'no published limit'}</span>
      </td>
      <td>
        <PercentCell
          fraction={fullness(quota)}
          absent="The limit is not published, so how full this is cannot be stated."
          provenance="measured"
          inverted
        />
      </td>
      <td data-testid="quota-source">{SOURCE_LABEL[quota.source] ?? quota.source}</td>
    </tr>
  );
}

function Unmeasured({ quota }: { readonly quota: ApiUnmeasurableQuota }) {
  return (
    <tr data-testid="quota-unmeasured">
      <td>
        <strong>{quota.quota_name}</strong>
        <span data-testid="quota-code"> {quota.quota_code}</span>
      </td>
      <td>{quota.account_id}</td>
      <td>{where(quota)}</td>
      <td>{quota.limit ?? 'no published limit'}</td>
      {/* No usage cell at all, not an empty one. An empty cell in a column of numbers reads
          as a measurement that came back zero, which is the one thing this must not say. */}
      <td data-testid="quota-reason">{quota.reason}</td>
    </tr>
  );
}

export function QuotasScreen() {
  const query = useQuotas();
  const envelope = query.data?.data;
  useReportMeta('governance-quotas', envelope?.meta);

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
          <table data-testid="quotas-measured">
            <caption>Quotas with a usage figure, the fullest first</caption>
            <thead>
              <tr>
                <th scope="col">Quota</th>
                <th scope="col">Account</th>
                <th scope="col">Region</th>
                <th scope="col">Used</th>
                <th scope="col">Full</th>
                <th scope="col">Measured by</th>
              </tr>
            </thead>
            <tbody>
              {measurable.map((one) => (
                <Measured key={keyFor(one)} quota={one} />
              ))}
            </tbody>
          </table>

          {unmeasurable.length > 0 ? (
            <>
              <h3 data-testid="quotas-unmeasured-heading">
                {unmeasurable.length === 1
                  ? 'One quota nothing measures'
                  : `${String(unmeasurable.length)} quotas nothing measures`}
              </h3>
              <table data-testid="quotas-unmeasured">
                <caption>
                  Quotas with a limit and no usage, by name. Nothing here is at zero: nothing
                  here has been measured, and the reason on each row says which source
                  declined.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Quota</th>
                    <th scope="col">Account</th>
                    <th scope="col">Region</th>
                    <th scope="col">Limit</th>
                    <th scope="col">Why there is no figure</th>
                  </tr>
                </thead>
                <tbody>
                  {unmeasurable.map((one) => (
                    <Unmeasured key={keyFor(one)} quota={one} />
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
        </>
      </StateBoundary>
    </section>
  );
}
