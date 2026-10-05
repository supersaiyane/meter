import { useCostExplore } from '../api/queries';
import { StateBoundary } from '../components/StateBoundary';
import type { Freshness } from '../components/provenance';
import { useFilters } from '../shell/filters';
import { useReportMeta } from '../shell/metaRegistry';
import { EXPLORER_FILTERS } from '../shell/sections';
import { ExploreControls, ExploreFilters } from './ExploreControls';
import { ExploreResult } from './ExploreResult';
import { apiQuery, chipsOf } from './exploreModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Cost Explorer, FEAT-065 and TASK-P8-007. The spend and trend screen became this one on
 * 2026-10-05, named for the FinOps Framework's Reporting and Analytics capability and for AWS
 * Cost Explorer.
 *
 * The question a practitioner asks first: what a period cost, grouped two ways, and how that
 * compares with the period before. The whole view lives in the address, so a link lands on the
 * view it was copied from, and the screen hands that address to `GET /cost/explore` unchanged.
 * The controls sit outside the state boundary, so a view that answers with nothing can still be
 * changed into one that answers.
 */
export function CostScreen() {
  const filters = useFilters(EXPLORER_FILTERS);
  const query = useCostExplore(apiQuery(filters.values));
  const envelope = query.data;
  const explore = envelope?.data;
  useReportMeta('cost', envelope?.meta);

  const chips = chipsOf(filters.values);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    explore?.rows.length ?? 0,
    chips.length === 0 ? 'none' : chips.map((chip) => chip.label).join(', '),
    'cost_focus',
  );
  const freshness: Freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  return (
    <section aria-label="Cost Explorer">
      <ExploreControls values={filters.values} explore={explore} update={filters.update} />
      <ExploreFilters values={filters.values} update={filters.update} />
      <StateBoundary state={state}>
        {explore === undefined ? null : (
          <ExploreResult explore={explore} values={filters.values} freshness={freshness} />
        )}
      </StateBoundary>
    </section>
  );
}
