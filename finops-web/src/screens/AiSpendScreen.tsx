import type { ReactNode } from 'react';

import { useAiCallers, useAiGpu, useAiSpend } from '../api/queries';
import type {
  ApiAiCaller,
  ApiAiGpu,
  ApiAiGrouping,
  ApiAiSpendRow,
  ApiBasis,
  ApiMeta,
} from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure, type FigureUnit } from '../components/Figure';
import { FixtureBand } from '../components/FixtureBand';
import { PercentCell } from '../components/PercentCell';
import { StateBoundary } from '../components/StateBoundary';
import type { SurfaceState } from '../components/surfaceState';
import type { Column } from '../components/tableConfig';
import { useFilters } from '../shell/filters';
import { useReportMeta } from '../shell/metaRegistry';
import { AI_FILTERS } from '../shell/sections';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * AI spend: what the models cost, who called them, and the GPU fleet. FEAT-081 to 085, P13.
 *
 * **Every figure says how it was arrived at.** Cost is the bill's, measured. Tokens are measured
 * where the bill's own line counted them and modelled where a provider's usage report did. A cost
 * per request divides one source's cost by another's requests, so it is modelled always, and so is
 * a caller's cost, which is the bill's unit cost spread over the caller's tokens.
 *
 * **An absence is a sentence.** A line that counted no tokens, a caller the bill priced nothing for
 * and a GPU whose agent never published are each said in words. Drawn as nought, each would claim
 * a measurement that was never made.
 *
 * **Three reads, three freshnesses.** The bill, the usage reports and the GPU agent arrive on their
 * own schedules, so each panel carries its own state and its own timestamps rather than one
 * envelope speaking for all three.
 */

const GROUPINGS: readonly { readonly value: ApiAiGrouping; readonly label: string }[] = [
  { value: 'provider', label: 'Provider' },
  { value: 'model', label: 'Model' },
  { value: 'token_type', label: 'Token type' },
  { value: 'feature', label: 'Feature' },
  { value: 'caller', label: 'Caller' },
];

/** What a usage source is called on the screen. A source not named here shows as it arrived. */
const SOURCE_NAMES: Readonly<Record<string, string>> = {
  logs: 'Invocation logs',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
};

interface Freshness {
  readonly asOf: Date;
  readonly collectedAt: Date;
}

function groupingOf(value: string): ApiAiGrouping {
  return GROUPINGS.find((one) => one.value === value)?.value ?? 'provider';
}

function freshnessOf(meta: ApiMeta | undefined): Freshness {
  return { asOf: new Date(meta?.as_of ?? 0), collectedAt: new Date(meta?.collected_at ?? 0) };
}

/** A billing period's first day as the month it names. */
function monthOf(period: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${period}T00:00:00Z`));
}

/** Nothing to show, as distinct from a failure: the honest empty, said rather than drawn. */
function isNothing(state: SurfaceState): boolean {
  return state.kind === 'never-collected' || state.kind === 'empty';
}

/** A figure with its basis, or the words for one nothing counted. Never a nought in its place. */
function known(
  amount: string | number | null,
  basis: ApiBasis | null,
  freshness: Freshness,
  absent: string,
  unit: FigureUnit,
): ReactNode {
  if (amount === null || basis === null) {
    return <span data-testid="ai-absent">{absent}</span>;
  }
  return (
    <Figure value={{ kind: basis, amount: Number(amount) }} freshness={freshness} unit={unit} />
  );
}

/** The spend table's columns. Grouped by provider, the group is the provider, so it is not repeated. */
function spendColumns(
  grouping: ApiAiGrouping,
  label: string,
  freshness: Freshness,
): readonly Column<ApiAiSpendRow>[] {
  const columns: readonly Column<ApiAiSpendRow>[] = [
    {
      key: 'name',
      header: label,
      rowHeader: true,
      render: (row) => <strong>{row.name}</strong>,
      sortValue: (row) => row.name,
    },
    { key: 'provider', header: 'Provider', render: (row) => row.provider },
    {
      key: 'cost',
      header: 'Cost',
      numeric: true,
      cellTestId: 'ai-spend-cost',
      render: (row) => known(row.cost, 'measured', freshness, '', 'usd'),
      sortValue: (row) => Number(row.cost),
      total: {
        value: (row) => Number(row.cost),
        unit: () => 'USD',
        provenance: () => 'measured',
        render: (sum) => (
          <Figure value={{ kind: 'measured', amount: sum }} freshness={freshness} />
        ),
      },
    },
    {
      key: 'tokens',
      header: 'Tokens',
      numeric: true,
      render: (row) => known(row.tokens, row.tokens_basis, freshness, 'not counted', 'count'),
      sortValue: (row) => (row.tokens === null ? null : Number(row.tokens)),
    },
    {
      key: 'requests',
      header: 'Requests',
      numeric: true,
      // Modelled always: a usage report's requests shared across the bill's lines by their cost.
      render: (row) => known(row.requests, 'modelled', freshness, 'not counted', 'count'),
      sortValue: (row) => row.requests,
    },
    {
      key: 'per-1k',
      header: 'Per 1,000 tokens',
      numeric: true,
      cellTestId: 'ai-per-1k',
      render: (row) =>
        known(
          row.cost_per_1k_tokens,
          row.cost_per_1k_tokens_basis,
          freshness,
          'no tokens counted',
          'usd-unit',
        ),
      sortValue: (row) =>
        row.cost_per_1k_tokens === null ? null : Number(row.cost_per_1k_tokens),
    },
    {
      key: 'per-request',
      header: 'Per request',
      numeric: true,
      cellTestId: 'ai-per-request',
      render: (row) =>
        known(
          row.cost_per_request,
          row.cost_per_request_basis,
          freshness,
          'no requests counted',
          'usd-unit',
        ),
      sortValue: (row) => (row.cost_per_request === null ? null : Number(row.cost_per_request)),
    },
  ];
  return grouping === 'provider' ? columns.filter((one) => one.key !== 'provider') : columns;
}

function SpendPanel({
  grouping,
  period,
  onGroup,
}: {
  readonly grouping: ApiAiGrouping;
  readonly period: string;
  readonly onGroup: (value: ApiAiGrouping) => void;
}) {
  const query = useAiSpend(grouping, period);
  const envelope = query.data?.data;
  useReportMeta('ai-spend', envelope?.meta);
  const found = envelope?.data;
  const rows = found?.rows ?? [];
  const freshness = freshnessOf(envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'cost_focus');
  const label = GROUPINGS.find((one) => one.value === grouping)?.label ?? 'Provider';
  const connected = found?.connected ?? [];

  return (
    <section aria-labelledby="ai-spend-heading" data-testid="ai-spend">
      <h2 id="ai-spend-heading">Spend by {label.toLowerCase()}</h2>
      <FixtureBand source={query.data?.source} />
      <label data-testid="ai-grouping">
        <span>Group by</span>
        <select
          value={grouping}
          onChange={(event) => {
            onGroup(groupingOf(event.target.value));
          }}
        >
          {GROUPINGS.map((one) => (
            <option key={one.value} value={one.value}>
              {one.label}
            </option>
          ))}
        </select>
      </label>
      {isNothing(state) || found?.period === null ? (
        <p data-testid="ai-spend-none">
          No bill Meter has read holds AI spend you can see. Model spend appears here once a
          bill carries it or a provider is connected.
        </p>
      ) : (
        <StateBoundary state={state}>
          <p data-testid="ai-spend-total">
            {found?.period ? monthOf(found.period) : ''}:{' '}
            <Figure
              value={{ kind: 'measured', amount: Number(found?.total_cost ?? 0) }}
              freshness={freshness}
            />{' '}
            of AI spend. Cost is the bill's own; each other figure says whether it was measured
            or modelled.
          </p>
          <p data-testid="ai-connected">
            {connected.length === 0
              ? 'No connected AI provider is visible at this scope, so this is the cloud bill alone.'
              : `Connected: ${connected
                  .map((one) => `${one.name} (${SOURCE_NAMES[one.provider] ?? one.provider})`)
                  .join(', ')}.`}
          </p>
          <DataTable
            rows={rows}
            columns={spendColumns(grouping, label, freshness)}
            rowKey={(row) => `${row.provider}/${row.name}`}
            caption={`AI spend by ${label.toLowerCase()}, the largest first`}
            initialSort={{ key: 'cost', direction: 'descending' }}
            rowAttributes={() => ({ 'data-testid': 'ai-spend-row' })}
          />
        </StateBoundary>
      )}
    </section>
  );
}

function callerColumns(freshness: Freshness): readonly Column<ApiAiCaller>[] {
  return [
    {
      key: 'caller',
      header: 'Caller',
      rowHeader: true,
      render: (row) => <strong>{row.caller}</strong>,
      sortValue: (row) => row.caller,
    },
    {
      key: 'application',
      header: 'Application',
      render: (row) => (row.application === '' ? 'not named' : row.application),
    },
    { key: 'model', header: 'Model', render: (row) => row.model },
    {
      key: 'source',
      header: 'Counted by',
      render: (row) => SOURCE_NAMES[row.source] ?? row.source,
    },
    {
      key: 'tokens',
      header: 'Tokens',
      numeric: true,
      render: (row) => known(row.tokens, 'measured', freshness, '', 'count'),
      sortValue: (row) => row.tokens,
    },
    {
      key: 'requests',
      header: 'Requests',
      numeric: true,
      render: (row) => known(row.requests, 'measured', freshness, 'not reported', 'count'),
      sortValue: (row) => row.requests,
    },
    {
      key: 'cost',
      header: 'Cost',
      numeric: true,
      cellTestId: 'ai-caller-cost',
      render: (row) =>
        known(row.modelled_cost, row.modelled_cost_basis, freshness, 'not priced', 'usd'),
      sortValue: (row) => (row.modelled_cost === null ? null : Number(row.modelled_cost)),
    },
  ];
}

function CallersPanel({ period }: { readonly period: string }) {
  const query = useAiCallers(period);
  const envelope = query.data?.data;
  useReportMeta('ai-callers', envelope?.meta);
  const callers = envelope?.data.callers ?? [];
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    callers.length,
    'none',
    'bedrock_invocations',
  );

  return (
    <section aria-labelledby="ai-callers-heading" data-testid="ai-callers">
      <h2 id="ai-callers-heading">Who called which model</h2>
      <FixtureBand source={query.data?.source} />
      {isNothing(state) ? (
        <p data-testid="ai-callers-none">
          No invocation log or provider usage report named a caller you can see. Invocation
          logging is off, or no provider is connected.
        </p>
      ) : (
        <StateBoundary state={state}>
          <p>
            Tokens and requests as the logs and reports counted them. A caller's cost is
            modelled: the bill's price for the same model and day, spread over the caller's
            tokens.
          </p>
          <DataTable
            rows={callers}
            columns={callerColumns(freshnessOf(envelope?.meta))}
            rowKey={(row) =>
              `${row.source}/${row.account_id}/${row.caller}/${row.application}/${row.model}`
            }
            caption="Callers, the most costly first; a caller the bill priced nothing for, last"
            rowAttributes={() => ({ 'data-testid': 'ai-caller-row' })}
          />
        </StateBoundary>
      )}
    </section>
  );
}

/** The agent's average as a fraction, or null where it published nothing. */
function averageOf(row: ApiAiGpu): number | null {
  return row.average_percent === null ? null : Number(row.average_percent) / 100;
}

function gpuColumns(freshness: Freshness): readonly Column<ApiAiGpu>[] {
  return [
    {
      key: 'instance',
      header: 'Instance',
      rowHeader: true,
      render: (row) => (
        <>
          <strong>{row.instance_id}</strong> {row.instance_type}
        </>
      ),
      sortValue: (row) => row.instance_id,
    },
    { key: 'account', header: 'Account', render: (row) => row.account_id },
    { key: 'region', header: 'Region', render: (row) => row.region_id ?? 'not named' },
    {
      key: 'hours',
      header: 'Hours',
      numeric: true,
      render: (row) => known(row.hours, 'measured', freshness, '', 'count'),
      sortValue: (row) => Number(row.hours),
    },
    {
      key: 'cost',
      header: 'Cost',
      numeric: true,
      render: (row) => known(row.cost, 'measured', freshness, '', 'usd'),
      sortValue: (row) => Number(row.cost),
      total: {
        value: (row) => Number(row.cost),
        unit: () => 'USD',
        provenance: () => 'measured',
        render: (sum) => (
          <Figure value={{ kind: 'measured', amount: sum }} freshness={freshness} />
        ),
      },
    },
    {
      key: 'average',
      header: 'Average utilization',
      numeric: true,
      cellTestId: 'ai-gpu-average',
      render: (row) => (
        <PercentCell fraction={averageOf(row)} absent="not published" provenance="measured" />
      ),
      sortValue: averageOf,
    },
    {
      key: 'published',
      header: 'Agent published',
      cellTestId: 'ai-gpu-published',
      render: (row) =>
        row.utilization === 'not published'
          ? 'not published'
          : `${String(row.days_published)} of ${String(row.days_billed)} days, peak ${row.peak_percent ?? ''}%`,
    },
  ];
}

function GpuPanel({ period }: { readonly period: string }) {
  const query = useAiGpu(period);
  const envelope = query.data?.data;
  useReportMeta('ai-gpu', envelope?.meta);
  const instances = envelope?.data.instances ?? [];
  const state = surfaceStateFor(query, envelope?.meta, instances.length, 'none', 'cost_focus');

  return (
    <section aria-labelledby="ai-gpu-heading" data-testid="ai-gpu">
      <h2 id="ai-gpu-heading">GPU instances</h2>
      <FixtureBand source={query.data?.source} />
      {isNothing(state) ? (
        <p data-testid="ai-gpu-none">
          No bill Meter has read names a GPU instance you can see.
        </p>
      ) : (
        <StateBoundary state={state}>
          <p>
            Hours and cost from the bill. Utilization from the CloudWatch agent on the instance;
            an instance whose agent published nothing says so rather than reading as idle.
          </p>
          <DataTable
            rows={instances}
            columns={gpuColumns(freshnessOf(envelope?.meta))}
            rowKey={(row) => `${row.account_id}/${row.instance_id}`}
            caption="GPU instances, the most costly first"
            initialSort={{ key: 'cost', direction: 'descending' }}
            rowAttributes={(row) => ({
              'data-testid': 'ai-gpu-row',
              'data-utilization': row.utilization,
            })}
          />
        </StateBoundary>
      )}
    </section>
  );
}

export function AiSpendScreen() {
  const { values, set } = useFilters(AI_FILTERS);
  const grouping = groupingOf(values.group_by);
  return (
    <section aria-label="AI spend" className="meter-ai">
      <SpendPanel
        grouping={grouping}
        period={values.period}
        onGroup={(value) => {
          set('group_by', value === 'provider' ? '' : value);
        }}
      />
      <CallersPanel period={values.period} />
      <GpuPanel period={values.period} />
    </section>
  );
}
