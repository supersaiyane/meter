import { useQueryGroups } from '../api/queries';
import type { ApiQueryGroup } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Freshness } from '../components/provenance';
import type { Column } from '../components/tableConfig';
import { severityLevel } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Findings summed by cause, above the list they are drawn from. ADR-0016.
 *
 * Four hundred findings at 15 USD each are LOW individually and 6,000 USD
 * together. A list ranked by individual severity puts that systemic problem
 * below a single noisy panel, which is the failure a dollar threshold would
 * otherwise introduce. So the groups sit above the list, and the group carries
 * the severity of its total rather than of its worst row.
 *
 * It does not repeat the list. Four or five rows, each naming a change somebody
 * could make once, against a table that names every panel it would affect.
 */
function columnsFor(freshness: Freshness): readonly Column<ApiQueryGroup>[] {
  return [
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
    },
    { key: 'cause', header: 'Cause', prose: true, render: (row) => row.label },
    {
      key: 'findings',
      header: 'Findings',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: row.findings }}
          freshness={freshness}
          unit="count"
        />
      ),
    },
    {
      key: 'monthly',
      header: 'Monthly cost',
      numeric: true,
      render: (row) => (
        // Modelled, because the findings behind it are. A sum of estimates is
        // an estimate, and rendering it as measured would launder the doubt.
        <Figure
          value={{ kind: 'modelled', amount: Number(row.monthly_cost) }}
          freshness={freshness}
        />
      ),
    },
  ];
}

export function QueryGroups() {
  const query = useQueryGroups();
  const envelope = query.data?.data;
  const rows = envelope?.data ?? [];
  const reported = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'query_audit');
  // The list below this panel reports the partial state, and the trust strip
  // above reports the coverage. Saying it a third time here stacks two
  // identical banners on one screen, which teaches a reader to skip both.
  const state = reported.kind === 'partial' ? ({ kind: 'ready' } as const) : reported;
  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  return (
    <section aria-label="What is driving the cost">
      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columnsFor(freshness)}
          rowKey={(row) => row.cause}
          caption="What is driving the cost, worst first. One row is one change."
        />
      </StateBoundary>
    </section>
  );
}
