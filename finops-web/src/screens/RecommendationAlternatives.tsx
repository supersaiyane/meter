import { useAlternatives } from '../api/queries';
import type { ApiAlternative } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * What a rightsizing was compared with, TASK-P9-010, P9 spec section 8.
 *
 * Shown under one finding, the chosen type first and then the rest by their source's rank:
 * Compute Optimizer's options, or the types Meter's own rule found to fit the demand it
 * measured. Three things it must not do.
 *
 * **Drop an option it cannot price.** A type the catalog neither prices nor describes keeps its
 * row, with the reason in the price's place, because the option was offered whether or not the
 * catalog has caught up.
 *
 * **Read a missing risk score as nought.** Meter's rule gives none, and a blank would be read
 * as Compute Optimizer's "no risk"; it says none was given.
 *
 * **Let a list price pass as a measured one.** Every price is AWS's list price from one price
 * list version and every saving is modelled, labelled as `Figure` labels modelled money.
 */

const CENTS = { minimumFractionDigits: 2, maximumFractionDigits: 2 } as const;

function gib(memoryMib: number): string {
  return `${(memoryMib / 1024).toLocaleString('en-GB', { maximumFractionDigits: 1 })} GiB`;
}

function hourly(price: string): string {
  return `$${Number(price).toLocaleString('en-GB', { maximumFractionDigits: 4 })}`;
}

function columns(freshness: {
  readonly asOf: Date;
  readonly collectedAt: Date;
}): readonly Column<ApiAlternative>[] {
  const modelled = (amount: string | null, testId: string) =>
    amount === null ? (
      <span data-testid={testId}>not priced</span>
    ) : (
      <Figure value={{ kind: 'modelled', amount: Number(amount) }} freshness={freshness} />
    );
  return [
    {
      key: 'type',
      header: 'Type',
      rowHeader: true,
      render: (one) => (
        <span data-testid={`alternative-${one.instance_type}`}>
          {one.instance_type}
          {one.chosen ? <strong data-testid="alternative-chosen"> (chosen)</strong> : null}
        </span>
      ),
    },
    {
      key: 'vcpus',
      header: 'vCPUs',
      numeric: true,
      render: (one) => (one.vcpus === null ? 'not described' : String(one.vcpus)),
    },
    {
      key: 'memory',
      header: 'Memory',
      numeric: true,
      render: (one) => (one.memory_mib === null ? 'not described' : gib(one.memory_mib)),
    },
    {
      key: 'network',
      header: 'Network baseline',
      numeric: true,
      render: (one) =>
        one.network_baseline_gbps === null
          ? 'not published'
          : `${Number(one.network_baseline_gbps).toLocaleString('en-GB')} Gbps`,
    },
    {
      key: 'hourly',
      header: 'Per hour, list',
      numeric: true,
      prose: true,
      render: (one) =>
        one.hourly_price === null ? (
          <span data-testid={`unpriced-${one.instance_type}`}>
            not priced: {one.unpriced_reason ?? 'the catalog holds no price'}
          </span>
        ) : (
          hourly(one.hourly_price)
        ),
    },
    {
      key: 'monthly',
      header: 'Per month, list',
      numeric: true,
      render: (one) => modelled(one.monthly_price, `monthly-${one.instance_type}`),
      sortValue: (one) => (one.monthly_price === null ? null : Number(one.monthly_price)),
    },
    {
      key: 'saving',
      header: 'Monthly saving, list',
      numeric: true,
      render: (one) => modelled(one.monthly_saving, `saving-${one.instance_type}`),
      sortValue: (one) => (one.monthly_saving === null ? null : Number(one.monthly_saving)),
    },
    {
      key: 'risk',
      header: 'Performance risk',
      render: (one) =>
        one.performance_risk === null ? (
          <span data-testid={`no-risk-score-${one.instance_type}`}>none given</span>
        ) : (
          `${Number(one.performance_risk).toLocaleString('en-GB', CENTS)} of 4`
        ),
    },
    {
      key: 'differences',
      header: 'Differences',
      prose: true,
      render: (one) =>
        one.platform_differences.length === 0
          ? 'none named'
          : one.platform_differences.join('; '),
    },
  ];
}

export function RecommendationAlternatives({
  recommendationId,
}: {
  readonly recommendationId: string;
}) {
  const query = useAlternatives(recommendationId);
  const envelope = query.data?.data;
  const found = envelope?.data;
  const rows = found?.alternatives ?? [];
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'recommendations');
  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const current =
    found?.current_instance_type == null
      ? null
      : `${found.current_instance_type}${
          found.current_hourly_price == null
            ? ''
            : ` at ${hourly(found.current_hourly_price)} an hour`
        }`;

  return (
    <section aria-label="Alternatives" data-testid="alternatives">
      <h2>Alternatives</h2>
      <p data-testid="alternatives-basis">
        {current === null ? 'Compared with the current type' : `Compared with ${current}`}
        {found?.price_version == null
          ? ''
          : `, at list prices from price list version ${found.price_version}`}
        . Every price is a list price and every saving is modelled; the recommendation's own
        saving is scaled to what the bill shows
      </p>
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columns(freshness)}
          rowKey={(one) => `${String(one.rank)}:${one.instance_type}`}
          caption="The chosen type first, then the rest by their source's rank"
          captionTestId="alternatives-caption"
        />
      </StateBoundary>
    </section>
  );
}
