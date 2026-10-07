import { useCostExplore } from '../api/queries';
import { KpiTile } from '../components/charts';
import type { SurfaceState } from '../components/surfaceState';
import { dailyTotals, regionsQuery } from './geographyModel';
import { wholeDollars } from './overviewKpis';

/**
 * One geography's glass tile under the map, TASK-P8-017: this month's Effective Cost against the
 * same days last month, and thirty days of its shape.
 *
 * **Its trend is its own Cost Explorer view.** The view by region names five series and folds the
 * rest, so a geography's days cannot be read off it; each tile asks for its own regions instead,
 * which is one small request per geography and an answer the Explorer itself would give.
 *
 * **The estate stays when the cost does not.** The resource count and the control that lists
 * them come from the geography route, so they are drawn as the tile's footer, which a failed
 * cost read does not replace.
 */
export interface GeographyTileProps {
  readonly geography: string;
  readonly name: string;
  readonly cost: number | null;
  readonly previous: number | null;
  /** The month view's state, which stands in for the figure while it is loading or failed. */
  readonly state: SurfaceState;
  /** The regions that carried cost over the trend's window, which the trend asks for. */
  readonly costRegions: readonly string[];
  readonly window: { readonly start: string; readonly end: string };
  /** True when the view that names those regions could not be read, so no trend can be asked. */
  readonly windowUnread: boolean;
  /** The regions with resources, from the geography route. */
  readonly regions: readonly string[];
  readonly resources: number;
  readonly accounts: number;
  readonly selected: boolean;
  readonly onSelect: () => void;
}

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString('en-GB')} ${count === 1 ? one : many}`;
}

export function GeographyTile({
  geography,
  name,
  cost,
  previous,
  state,
  costRegions,
  window,
  windowUnread,
  regions,
  resources,
  accounts,
  selected,
  onSelect,
}: GeographyTileProps) {
  const trend = useCostExplore(regionsQuery(costRegions, window), {
    enabled: costRegions.length > 0,
    offered: false,
  });
  return (
    <KpiTile
      label={name}
      value={cost}
      previous={previous}
      points={dailyTotals(trend.data?.data)}
      provenance="measured"
      format={wholeDollars}
      period="the same days last month"
      state={state}
      // Said rather than left as a missing line: an empty shape reads as a quiet month.
      {...(windowUnread || trend.isError ? { note: 'The thirty day trend could not be read' } : {})}
      footer={
        <div data-testid="geography-tile-footer">
          <p data-testid="geography-tile-estate">
            {plural(resources, 'resource', 'resources')} in{' '}
            {plural(accounts, 'account', 'accounts')}
            {regions.length > 0 ? `: ${regions.join(', ')}` : ''}
          </p>
          {resources > 0 ? (
            <button
              type="button"
              data-testid="world-map-choice"
              data-key={geography}
              aria-pressed={selected}
              onClick={onSelect}
            >
              {selected ? 'Hide its resources' : `List its ${plural(resources, 'resource', 'resources')}`}
            </button>
          ) : null}
        </div>
      }
    />
  );
}
