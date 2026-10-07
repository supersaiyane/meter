import { useReconciliation } from '../api/queries';
import type { ApiInvoiceComparison } from '../api/types';
import { DataTable } from '../components/DataTable';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import {
  answeredInstead,
  money,
  periodWords,
  signed,
  stateWords,
  tolerancePercent,
} from './reconciliationModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Invoice reconciliation. FEAT-076, TASK-P10-005.
 *
 * Each invoice the payer was issued for a billing period, beside the billed cost Meter holds on
 * the rows carrying its id. The point is a figure Meter did not produce, so the invoice's amounts
 * are always shown and Meter's are shown only where they were compared: a Marketplace invoice no
 * row carries says so in words, never as a zero beside a difference of the whole amount.
 *
 * **Every state in words.** The state column says what the comparison means, and the difference
 * sits beside it with its sign, Meter's figure less the invoice's, so a reader can see which side
 * is higher without working it out.
 *
 * **Payer wide.** A reader who cannot see the whole payer is told why in the route's own words,
 * and is shown no total, because a sum over some accounts beside an invoice over all of them
 * would be a mismatch Meter invented.
 */

const COLUMNS: readonly Column<ApiInvoiceComparison>[] = [
  {
    key: 'invoice',
    header: 'Invoice',
    render: (row) =>
      row.original_invoice_id === null
        ? row.invoice_id
        : `${row.invoice_id}, a credit memo correcting ${row.original_invoice_id}`,
  },
  { key: 'issuer', header: 'Issued by', render: (row) => row.invoice_issuer_name },
  {
    key: 'invoice_before_tax',
    header: 'Invoice, before tax',
    numeric: true,
    render: (row) => money(row.invoice_before_tax, row.billing_currency),
    sortValue: (row) => Number(row.invoice_before_tax),
  },
  {
    key: 'meter_before_tax',
    header: 'Meter, before tax',
    numeric: true,
    render: (row) => money(row.meter_before_tax, row.billing_currency),
  },
  {
    key: 'difference_before_tax',
    header: 'Difference',
    numeric: true,
    render: (row) => (
      <span data-testid="reconciliation-difference">
        {signed(row.difference_before_tax, row.billing_currency)}
      </span>
    ),
    sortValue: (row) =>
      row.difference_before_tax === null ? null : Math.abs(Number(row.difference_before_tax)),
  },
  {
    key: 'tax',
    header: 'Tax, invoice and difference',
    numeric: true,
    render: (row) =>
      `${money(row.invoice_tax, row.billing_currency)}, ${signed(row.difference_tax, row.billing_currency)}`,
  },
  {
    key: 'state',
    header: 'State',
    render: (row) => (
      <span data-testid="reconciliation-state" data-state={row.state}>
        {stateWords(row.state)}
      </span>
    ),
    sortValue: (row) => row.state,
  },
];

export function ReconciliationScreen() {
  const query = useReconciliation();
  const envelope = query.data?.data;
  useReportMeta('report-reconciliation', envelope?.meta);
  const instead = answeredInstead(query.error);
  if (instead !== null) {
    return (
      <section aria-label="Invoice reconciliation">
        <p data-testid="reconciliation-instead">{instead}</p>
      </section>
    );
  }

  const found = envelope?.data;
  const invoices = found?.invoices ?? [];
  // A period with no invoice is not empty: it is open or unreadable, and says which below.
  const shown = found?.state ? 1 : invoices.length;
  const state = surfaceStateFor(query, envelope?.meta, shown, 'none', 'invoices');

  return (
    <section aria-label="Invoice reconciliation">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        {found === undefined ? null : (
          <>
            <p data-testid="reconciliation-period">
              Billing period starting {found.period}, {found.period_status.toLowerCase()}.
            </p>
            <p data-testid="reconciliation-provenance" data-provenance="measured">
              Measured on both sides: each invoice is read from the provider, and Meter&apos;s
              figure is the billed cost on the rows carrying its id, before tax and tax apart. A
              difference is Meter&apos;s figure less the invoice&apos;s. Matched means within{' '}
              {tolerancePercent(found.tolerance)} of the invoice or one cent, a modelled
              tolerance.
            </p>
            {found.state === null ? (
              <DataTable
                rows={invoices}
                columns={COLUMNS}
                rowKey={(row) => row.invoice_id}
                caption={`Invoices for the billing period starting ${found.period}`}
                rowAttributes={(row) => ({
                  'data-testid': 'reconciliation-row',
                  'data-state': row.state,
                })}
              />
            ) : (
              <p data-testid="reconciliation-period-state" data-state={found.state}>
                {periodWords(found)}
              </p>
            )}
          </>
        )}
      </StateBoundary>
    </section>
  );
}
