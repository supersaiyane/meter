import { useMemo, useState } from 'react';

import { useCostExplore, useGeography, useResources } from '../api/queries';
import type { ApiGeographyLink } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { FixtureBand } from '../components/FixtureBand';
import type { Freshness } from '../components/provenance';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { WorldMap, type MapGeography } from '../components/WorldMap';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { exploreQuery, lastDays } from './exploreSeries';
import { GeographyTile } from './GeographyTile';
import { costsByGeography, kindName, linksBetween, linksTouching } from './geographyModel';
import { nodeColumns } from './nodeColumns';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Where the estate is, what it costs there, and what is in each place. FEAT-061, TASK-P8-017.
 *
 * **The map is a schematic and the screen keeps saying so.** A geography comes from a region
 * name prefix, which is continental: it knows Europe and cannot know Dublin. The alternative was a
 * table of coordinates per region, which has to name every region and makes the next region a
 * provider opens invisible until somebody notices, and that is the failure `check_hardcoded.py`
 * exists to prevent. The prefix costs precision and buys never being silently wrong. ISS-213.
 *
 * **Cost comes from Cost Explorer, placed by the server.** This month by region is the Explorer's
 * own view, and its answer says which geography each region is in by the same rule that groups the
 * resources, so the bubbles, the tiles and the Explorer cannot disagree and this application holds
 * no copy of the rule.
 *
 * **Every leftover is a sentence, never one number.** Resources with no region are global, a fact
 * about IAM and Route 53. A region whose prefix is unknown is unplaceable, and that is the one
 * somebody can act on. A region a collection could not read is refused, and every count above it
 * is a floor. Cost with no region and cost in an unplaceable region get their own lines too.
 *
 * **Clicking a continent lists its resources from the server.** One request per continent with
 * the geography as a filter, resolved on the server through the same rule that grouped the map.
 */

const PAGE = 25;
/** The days each tile's trend covers. */
const TREND_DAYS = 30;
/** This month by region: Cost Explorer's own view, whose rows size the bubbles. */
const MONTH_BY_REGION = exploreQuery({ group_by: 'region' });

function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString('en-GB')} ${count === 1 ? one : many}`;
}

function money(amount: number, freshness: Freshness) {
  return <Figure value={{ kind: 'measured', amount }} freshness={freshness} />;
}

/** Every number the map and its tooltip show, one row per geography. */
function geographyColumns(freshness: Freshness): readonly Column<MapGeography>[] {
  return [
    {
      key: 'geography',
      header: 'Geography',
      rowHeader: true,
      render: (one) => one.name,
      sortValue: (one) => one.name,
    },
    {
      key: 'cost',
      header: 'Effective Cost',
      numeric: true,
      render: (one) => (one.cost === null ? 'Not read' : money(one.cost, freshness)),
      sortValue: (one) => one.cost,
      total: {
        value: (one) => one.cost,
        unit: () => 'USD',
        provenance: () => 'measured',
        render: (sum) => money(sum, freshness),
      },
    },
    {
      key: 'resources',
      header: 'Resources',
      numeric: true,
      render: (one) => one.resources.toLocaleString('en-GB'),
      sortValue: (one) => one.resources,
      total: {
        value: (one) => one.resources,
        unit: () => 'resources',
        provenance: () => 'measured',
        render: (sum) => sum.toLocaleString('en-GB'),
      },
    },
    {
      // No total: one account in two geographies is one account, and adding would count two.
      key: 'accounts',
      header: 'Accounts',
      numeric: true,
      render: (one) => one.accounts.toLocaleString('en-GB'),
      sortValue: (one) => one.accounts,
    },
    {
      key: 'regions',
      header: 'Regions',
      prose: true,
      render: (one) => (one.regions.length > 0 ? one.regions.join(', ') : 'None with resources'),
    },
    {
      // No total either: a link between two geographies is counted in both of them.
      key: 'links',
      header: 'Links to other regions',
      numeric: true,
      render: (one) => one.links.toLocaleString('en-GB'),
      sortValue: (one) => one.links,
    },
  ];
}

/** Every link across a region boundary, including the ones the map cannot draw. */
function linkColumns(names: ReadonlyMap<string, string>): readonly Column<ApiGeographyLink>[] {
  const place = (key: string | null): string =>
    key === null ? 'a region no table places' : (names.get(key) ?? key);
  const between = (link: ApiGeographyLink): string =>
    link.one_geography !== null && link.one_geography === link.other_geography
      ? `Inside ${place(link.one_geography)}, so not drawn`
      : `${place(link.one_geography)} and ${place(link.other_geography)}`;
  return [
    {
      key: 'regions',
      header: 'Regions',
      rowHeader: true,
      render: (link) => `${link.one_region} and ${link.other_region}`,
      sortValue: (link) => `${link.one_region} ${link.other_region}`,
    },
    { key: 'geographies', header: 'Geographies', render: between, sortValue: between },
    {
      key: 'links',
      header: 'Links',
      numeric: true,
      render: (link) => link.links.toLocaleString('en-GB'),
      sortValue: (link) => link.links,
      total: {
        value: (link) => link.links,
        unit: () => 'links',
        provenance: () => 'measured',
        render: (sum) => sum.toLocaleString('en-GB'),
      },
    },
    {
      key: 'kinds',
      header: 'Joined by',
      render: (link) => link.kinds.map(kindName).join(', '),
    },
  ];
}

export function GeographyScreen() {
  const [chosen, setChosen] = useState<string | null>(null);
  const query = useGeography();
  const envelope = query.data?.data;
  useReportMeta('inventory-geography', envelope?.meta);

  const found = envelope?.data;
  const geographies = found?.geographies ?? [];
  const state = surfaceStateFor(query, envelope?.meta, geographies.length, 'none', 'topology');

  // This month by region sizes the bubbles and heads the tiles.
  const month = useCostExplore(MONTH_BY_REGION, { title: 'Effective Cost by region, month to date' });
  useReportMeta('geography-cost', month.data?.meta);
  const monthState = surfaceStateFor(month, month.data?.meta, 1, 'none', 'cost_focus_daily');
  const monthView = month.data?.data;
  const costs = useMemo(
    () => (monthView === undefined ? null : costsByGeography(monthView)),
    [monthView],
  );
  const freshness: Freshness = {
    asOf: new Date(month.data?.meta.as_of ?? 0),
    collectedAt: new Date(month.data?.meta.collected_at ?? 0),
  };

  // The last thirty days by region, which says which regions each tile's trend asks about: a
  // region that billed last month and not yet this one still belongs in the shape.
  const window = useMemo(() => lastDays(TREND_DAYS, new Date()), []);
  const recent = useCostExplore(
    exploreQuery({ group_by: 'region', period: 'custom', start: window.start, end: window.end }),
    { offered: false },
  );
  const recentView = recent.data?.data;
  const recentCosts = useMemo(
    () => (recentView === undefined ? null : costsByGeography(recentView)),
    [recentView],
  );

  const links = useMemo(() => found?.links ?? [], [found]);
  const drawn = useMemo(() => linksBetween(links), [links]);

  // Every geography with resources, then any with cost and none, which the map must not drop.
  const mapped: readonly MapGeography[] = [
    ...geographies.map((one) => ({
      key: one.key,
      name: one.name,
      resources: one.resources,
      accounts: one.accounts,
      regions: one.regions.map((region) => region.region_id),
      cost: costs === null ? null : (costs.now.get(one.key) ?? 0),
      links: linksTouching(one.key, links),
    })),
    ...[...(costs?.now.keys() ?? [])]
      .filter((key) => !geographies.some((one) => one.key === key))
      .map((key) => ({
        key,
        name: costs?.names.get(key) ?? key,
        resources: 0,
        accounts: 0,
        regions: [],
        cost: costs?.now.get(key) ?? 0,
        links: linksTouching(key, links),
      })),
  ];
  const names = new Map(mapped.map((one) => [one.key, one.name]));
  const unsized = month.isPending
    ? 'This month’s Effective Cost is still loading, so every bubble is the same size for now.'
    : costs === null
      ? 'This month’s Effective Cost could not be read, so every bubble is the same size.'
      : null;

  // Only once something is chosen. A screen that loads the first continent's resources before
  // anybody asked is a screen that decides for the reader which continent matters.
  const resources = useResources({
    geography: chosen ?? undefined,
    limit: PAGE,
    offset: 0,
  });
  const page = chosen === null ? undefined : resources.data?.data.data;
  const rows = page?.resources ?? [];
  const selected = mapped.find((one) => one.key === chosen);
  const choose = (key: string) => {
    setChosen((was) => (was === key ? null : key));
  };

  return (
    <section aria-label="Geography">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <WorldMap
            geographies={mapped}
            links={drawn}
            unsized={unsized}
            freshness={freshness}
            selected={chosen}
            onSelect={choose}
          />

          <section data-testid="geography-tiles" aria-label="Each geography">
            {mapped.map((one) => (
              <GeographyTile
                key={one.key}
                geography={one.key}
                name={one.name}
                cost={one.cost}
                previous={costs?.before === null ? null : (costs?.before.get(one.key) ?? null)}
                state={monthState}
                costRegions={recentCosts?.regions.get(one.key) ?? []}
                window={window}
                windowUnread={recent.isError}
                regions={one.regions}
                resources={one.resources}
                accounts={one.accounts}
                selected={chosen === one.key}
                onSelect={() => {
                  choose(one.key);
                }}
              />
            ))}
          </section>

          <section data-testid="geography-summary" aria-label="Every geography">
            <DataTable
              rows={mapped}
              columns={geographyColumns(freshness)}
              rowKey={(one) => one.key}
              caption="Every geography: Effective Cost this month to date, measured, and the estate"
              rowAttributes={(one) => ({ 'data-key': one.key })}
            />
          </section>

          <section data-testid="geography-links" aria-label="Links across regions">
            {links.length === 0 ? (
              <p data-testid="geography-links-none">
                No resource you can read is linked to one in another region
              </p>
            ) : (
              <DataTable
                rows={links}
                columns={linkColumns(names)}
                rowKey={(link) => `${link.one_region} ${link.other_region}`}
                caption="Links across regions, as pairs of resources, measured"
              />
            )}
          </section>

          {/* The leftovers, each with its own words. Always shown, including when they are
              nought, because "every region placed" is an answer and a missing line is not. */}
          <dl data-testid="geography-leftovers">
            <dt>Belonging to no region</dt>
            <dd data-testid="geography-global">
              {found?.global_resources ?? 0} resources have no region at all. IAM, DNS and the
              organization itself are global, which is a fact about the service and not a gap in
              the inventory
            </dd>

            <dt>In a region we cannot place</dt>
            <dd data-testid="geography-unplaceable">
              {(found?.unplaceable.length ?? 0) === 0
                ? 'Every region we can see was placed on a continent'
                : `${String(found?.unplaceable_resources ?? 0)} resources are in ` +
                  `${String(found?.unplaceable.length ?? 0)} region` +
                  `${(found?.unplaceable.length ?? 0) === 1 ? '' : 's'} whose name does not say ` +
                  `which geography it is in: ${(found?.unplaceable ?? []).join(', ')}. They are ` +
                  'counted here rather than left off the map, and the fix is one more row in the ' +
                  'geography table'}
            </dd>

            <dt>In a region we could not read</dt>
            <dd data-testid="geography-refused">
              {(found?.refused.length ?? 0) === 0
                ? 'Every region we can see was read'
                : `${String(found?.refused.length ?? 0)} region` +
                  `${(found?.refused.length ?? 0) === 1 ? '' : 's'} refused us: ` +
                  `${(found?.refused ?? []).join(', ')}. What is in them is unknown rather than ` +
                  'nothing, so every count above is a floor'}
            </dd>

            {costs === null ? null : (
              <>
                <dt>Cost with no region</dt>
                <dd data-testid="geography-cost-global">
                  {money(costs.global, freshness)} this month carries no region: global services,
                  support and fees, which no continent owns
                </dd>

                <dt>Cost in a region we cannot place</dt>
                <dd data-testid="geography-cost-unplaced">
                  {costs.unplaced.length === 0
                    ? 'Every region that billed this month was placed on a continent'
                    : `${plural(costs.unplaced.length, 'region', 'regions')} billed this month ` +
                      `with a name that does not say which geography: ${costs.unplaced
                        .map((one) => one.region)
                        .join(', ')}. Their cost is in Cost Explorer, not on the map`}
                </dd>

                {costs.omitted.groups === 0 ? null : (
                  <>
                    <dt>Regions past Cost Explorer’s row limit</dt>
                    <dd data-testid="geography-cost-omitted">
                      {plural(costs.omitted.groups, 'region', 'regions')} costing{' '}
                      {money(costs.omitted.cost, freshness)} are not itemised, so the
                      continents above add up to less than the month
                    </dd>
                  </>
                )}
              </>
            )}
          </dl>

          {selected === undefined ? (
            <p data-testid="geography-prompt">
              Choose a continent to list what is in it. Nothing is loaded until you do, because
              a screen that picks one for you has decided which continent matters
            </p>
          ) : (
            <section aria-label="Resources here" data-testid="geography-resources">
              <h3 data-testid="geography-chosen">
                {selected.name}, {plural(selected.resources, 'resource', 'resources')}
                {selected.regions.length > 0 ? ` in ${selected.regions.join(' and ')}` : ''}
              </h3>
              <div data-testid="geography-table">
                <DataTable
                  rows={rows}
                  columns={nodeColumns(
                    page !== undefined && page.total === rows.length,
                    'Region',
                    (node) => node.region_id ?? 'global',
                  )}
                  rowKey={(node) => node.node_id}
                  // The denominator, like the resource list's. A page with none reads as the
                  // whole continent, and a reader who acts on that acts on a subset.
                  caption={
                    page === undefined
                      ? 'Loading'
                      : page.total === rows.length
                        ? `All ${String(page.total)} of them`
                        : `The first ${String(rows.length)} of ${String(page.total)}`
                  }
                  captionTestId="geography-table-count"
                />
              </div>
              {page !== undefined && page.total > rows.length ? (
                // Not paginated here on purpose. The resource list already does paging and
                // filtering properly, and a second pager on a different screen is a second
                // place for the offset arithmetic to be wrong.
                <p data-testid="geography-more">
                  <Link to={`/inventory/resources?geography=${selected.key}`}>
                    Open all {page.total} in the resource list, where they can be filtered and
                    paged
                  </Link>
                </p>
              ) : null}
            </section>
          )}
        </>
      </StateBoundary>
    </section>
  );
}
