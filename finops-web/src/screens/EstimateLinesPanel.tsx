import { useId, useMemo } from 'react';

import { useEstimate } from '../api/queries';
import type { ApiEstimateLine } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { freshnessOf } from './commitmentFormat';
import {
  WITHIN_PERCENT,
  actionsName,
  pullRequestName,
  unpricedSentence,
  verdictSentence,
} from './estimatesModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * One plan's changes, FEAT-095 and FEAT-097, TASK-P16-008. The changes Meter could not price come
 * first and each says why, as the comment lists them; a priced one names its parts and, once a
 * merged plan created it, what the bill said.
 */

type Freshness = ReturnType<typeof freshnessOf>;

function money(value: string | null, freshness: Freshness) {
  return value === null ? (
    'None'
  ) : (
    <Figure value={{ kind: 'modelled', amount: Number(value) }} freshness={freshness} />
  );
}

function why(line: ApiEstimateLine): string {
  const said = [
    ...(line.reason === null ? [] : [line.reason]),
    ...line.notes,
    ...(line.unknown.length === 0 ? [] : [`Unknown until apply: ${line.unknown.join(', ')}`]),
    ...(line.withheld.length === 0
      ? []
      : [`Withheld as sensitive: ${line.withheld.join(', ')}`]),
  ];
  return said.join('. ');
}

function parts(line: ApiEstimateLine): string {
  return line.components
    .map(
      (part) =>
        `${part.side}: ${part.what}, ${part.quantity} ${part.unit} at ${part.unit_price}`,
    )
    .join('; ');
}

function lineColumns(freshness: Freshness): readonly Column<ApiEstimateLine>[] {
  return [
    {
      key: 'address',
      header: 'Resource',
      rowHeader: true,
      render: (line) => <code>{line.address}</code>,
      sortValue: (line) => line.address,
    },
    { key: 'actions', header: 'Change', render: (line) => actionsName(line.actions) },
    {
      key: 'before',
      header: 'Monthly before',
      numeric: true,
      render: (line) => money(line.monthly_before, freshness),
    },
    {
      key: 'after',
      header: 'Monthly after',
      numeric: true,
      render: (line) => money(line.monthly_after, freshness),
    },
    {
      key: 'why',
      header: 'Why not priced, and notes',
      prose: true,
      cellTestId: 'line-why',
      render: why,
    },
    { key: 'parts', header: 'Priced parts', prose: true, render: parts },
    {
      key: 'bill',
      header: 'Against the bill',
      prose: true,
      cellTestId: 'line-bill',
      render: (line) =>
        line.comparison === null ? '' : verdictSentence(line.comparison, WITHIN_PERCENT),
    },
  ];
}

export function EstimateLinesPanel({ planId }: { readonly planId: string }) {
  const heading = useId();
  const query = useEstimate(planId);
  const envelope = query.data;
  const found = envelope?.data;
  const lines = useMemo(() => found?.lines ?? [], [found]);
  useReportMeta('estimate', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, lines.length, 'none', 'plan_estimates');
  const freshness = freshnessOf(envelope?.meta);
  const unpriced = lines.filter((line) => line.reason !== null).length;
  return (
    <section className="meter-panel" aria-labelledby={heading} data-testid="estimate-lines">
      <h2 id={heading}>
        {found === undefined ? 'The plan' : pullRequestName(found.plan)}, commit{' '}
        <code>{found?.plan.head_sha.slice(0, 12) ?? ''}</code>
      </h2>
      <p data-testid="estimate-lines-headline">{unpricedSentence(unpriced, lines.length)}</p>
      <StateBoundary state={state}>
        <DataTable
          rows={lines}
          columns={lineColumns(freshness)}
          rowKey={(line) => line.address}
          caption={`${String(lines.length)} changes, the unpriced first`}
        />
      </StateBoundary>
      {found === undefined ? null : (
        <p data-testid="estimate-assumptions">{found.assumptions}</p>
      )}
    </section>
  );
}
