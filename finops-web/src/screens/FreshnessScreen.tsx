import { useFreshness } from '../api/queries';
import { collectorName } from '../components/displayNames';
import type { Freshness } from '../api/types';
import { CadenceBar } from '../components/CadenceBar';
import { DataTable } from '../components/DataTable';
import { StateBoundary } from '../components/StateBoundary';
import { formatAge } from '../components/provenance';
import { latenessOf } from '../components/lateness';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * How stale each collector is, per scope, against its own cadence.
 *
 * A daily collector six hours old is fine and an hourly one six hours old is
 * not, so the cadence is shown beside the age. A single staleness threshold
 * across collectors would call one of those wrong every time.
 *
 * Three states, not two. A collector that has never once succeeded is not a
 * stale one, and until ISS-163 it was not on this page at all: the page listed
 * watermarks, and a watermark only exists after a success, so the row a reader
 * comes here to find was the row it left out.
 */
const COLUMNS: readonly Column<Freshness>[] = [
  { key: 'collector', header: 'Collector', render: (row) => collectorName(row.collector) },
  { key: 'scope', header: 'Scope', render: (row) => row.scope_key },
  {
    key: 'age',
    header: 'Age',
    numeric: true,
    render: (row) =>
      row.age_seconds === null ? (
        // Not a zero and not a dash. There has been no collection to age.
        <span className="meter-stale">never</span>
      ) : (
        formatAge(row.age_seconds)
      ),
  },
  {
    key: 'cadence',
    header: 'Cadence',
    numeric: true,
    render: (row) =>
      row.cadence_seconds === null
        ? // An unknown cadence is not a healthy one, and saying so beats a blank.
          'not scheduled'
        : `${String(Math.round(row.cadence_seconds / 60))} min`,
  },
  {
    key: 'lateness',
    header: 'Against its cadence',
    numeric: true,
    // The two columns to the left, read together, which is arithmetic the screen should have
    // done. A daily collector six hours old is fine and an hourly one six hours old is not, and
    // that comparison is the whole reason this page exists rather than a single threshold.
    render: (row) => (
      <CadenceBar ageSeconds={row.age_seconds} cadenceSeconds={row.cadence_seconds} />
    ),
  },
  {
    key: 'stale',
    header: 'State',
    render: (row) => {
      if (row.state === 'current') {
        return <span>current</span>;
      }
      if (row.state === 'stale') {
        return <span className="meter-stale">stale</span>;
      }
      // Named with its cause, because the reader's next question is why, and
      // this page is where they came to ask it.
      return (
        <span className="meter-failure">
          never collected{row.cause === null ? '' : `, ${row.cause}`}
        </span>
      );
    },
  },
];

export function FreshnessScreen() {
  const query = useFreshness();
  useReportMeta('freshness', query.data?.meta);
  const rows = query.data?.data ?? [];
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'freshness');

  // Counted once here rather than read off the table by eye. Undefined lateness is deliberately
  // not in the numerator or the denominator: a collector nothing schedules cannot be late, and
  // one that never succeeded is not late either, it has no age at all. Rolling either into a
  // count of late collectors would inflate the number that decides whether somebody investigates.
  const measurable = rows.filter(
    (row) => latenessOf(row.age_seconds, row.cadence_seconds) !== null,
  );
  const late = measurable.filter(
    (row) => (latenessOf(row.age_seconds, row.cadence_seconds) ?? 0) > 1,
  );
  const unmeasurable = rows.length - measurable.length;

  return (
    <section aria-label="Data Freshness">
      {/* Outside the boundary, like the anomalies screen's history sentence. It is a fact about
          the estate rather than about this request, and it is the question a reader opens this
          screen with. */}
      <p data-testid="freshness-summary">
        {measurable.length === 0
          ? 'No collector here can be judged against a cadence yet'
          : `${String(late.length)} of ${String(measurable.length)} collectors are past their own ` +
            'cadence'}
        {unmeasurable === 0
          ? ''
          : `. ${String(unmeasurable)} more cannot be judged at all, and ${
              unmeasurable === 1 ? 'is' : 'are'
            } counted as neither late nor current`}
      </p>

      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={COLUMNS}
          rowKey={(row) => `${row.collector}|${row.scope_key}`}
          caption="Collector freshness"
        />
      </StateBoundary>
    </section>
  );
}
