import { useState } from 'react';

import { useGeography, useResources } from '../api/queries';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import { WorldMap } from '../components/WorldMap';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Where the estate is, and what is in each place. FEAT-061.
 *
 * **The map is a schematic and the screen keeps saying so.** A geography comes from a region
 * name prefix, which is continental: it knows Europe and cannot know Dublin. The alternative
 * was a table of coordinates per region, which has to name every region and makes the next
 * region a provider opens invisible until somebody notices, and that is the failure
 * `check_hardcoded.py` exists to prevent. The prefix costs precision and buys never being
 * silently wrong. ISS-213.
 *
 * **Three leftovers, three sentences, never one number.** Resources with no region are global,
 * which is a fact about IAM and Route 53 rather than a gap. A region whose prefix is unknown is
 * unplaceable, and that is the one somebody can act on. A region a collection could not read is
 * refused, and every count above it is a floor rather than a total. Collapsing any two of those
 * would be the easy thing and would tell a reader to go and fix the wrong thing.
 *
 * **Clicking a continent lists its resources from the server.** One request per continent with
 * the geography as a filter, resolved on the server through the same rule that grouped the map,
 * because two implementations of the prefix rule would eventually disagree and a continent
 * saying three above a list showing two is the fault a reader finds before we do.
 */

const PAGE = 25;

export function GeographyScreen() {
  const [chosen, setChosen] = useState<string | null>(null);
  const query = useGeography();
  const envelope = query.data?.data;
  useReportMeta('inventory-geography', envelope?.meta);

  const found = envelope?.data;
  const geographies = found?.geographies ?? [];
  const state = surfaceStateFor(query, envelope?.meta, geographies.length, 'none', 'topology');

  // Only once something is chosen. A screen that loads the first continent's resources before
  // anybody asked is a screen that decides for the reader which continent matters.
  const resources = useResources({
    geography: chosen ?? undefined,
    limit: PAGE,
    offset: 0,
  });
  const page = chosen === null ? undefined : resources.data?.data.data;
  const rows = page?.resources ?? [];
  const selected = geographies.find((one) => one.key === chosen);

  return (
    <section aria-label="Geography">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <WorldMap
            geographies={geographies}
            selected={chosen}
            onSelect={(key) => {
              setChosen((was) => (was === key ? null : key));
            }}
          />

          {/* The three leftovers, each with its own words. Always shown, including when they are
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
          </dl>

          {selected === undefined ? (
            <p data-testid="geography-prompt">
              Choose a continent to list what is in it. Nothing is loaded until you do, because
              a screen that picks one for you has decided which continent matters
            </p>
          ) : (
            <section aria-label="Resources here" data-testid="geography-resources">
              <h3 data-testid="geography-chosen">
                {selected.name}, {selected.resources}{' '}
                {selected.resources === 1 ? 'resource' : 'resources'} in{' '}
                {selected.regions.map((region) => region.region_id).join(' and ')}
              </h3>
              <table data-testid="geography-table">
                <caption data-testid="geography-table-count">
                  {/* The denominator, like the resource list's. A page with none reads as the
                      whole continent, and a reader who acts on that acts on a subset. */}
                  {page === undefined
                    ? 'Loading'
                    : page.total === rows.length
                      ? `All ${String(page.total)} of them`
                      : `The first ${String(rows.length)} of ${String(page.total)}`}
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Resource</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Type</th>
                    <th scope="col">Account</th>
                    <th scope="col">Region</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((node) => (
                    <tr key={node.node_id}>
                      <th scope="row">
                        {/* Every row reaches the page that says what it costs and what is wrong
                            with it, the same link the resource list uses. */}
                        <Link to={`/inventory/resources/${node.node_id}`}>
                          {node.name ?? node.provider_id}
                        </Link>
                      </th>
                      <td>{node.node_kind}</td>
                      <td>{node.resource_type}</td>
                      <td>{node.account_id}</td>
                      <td>{node.region_id ?? 'global'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
