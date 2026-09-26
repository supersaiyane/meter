import { useState } from 'react';
import { Link } from 'react-router';

import { useGraphCoverage, useResources } from '../api/queries';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { ApiResourceFilters, ApiSliceCoverage, ApiTopologyNode } from '../api/types';
import { useReportMeta } from '../shell/metaRegistry';
import { saidOf } from './sliceCoverage';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Every resource this scope can see, filtered and paged. FEAT-056, closing ISS-204.
 *
 * The navigation has promised this screen since P4 began and the P4 specification never
 * scheduled one, so a delivered sub project was named as the thing that would bring a screen
 * nobody planned. It is built rather than the marker edited until the inconsistency goes away.
 *
 * **It is not a worse map, it is a different question.** The map answers what is connected to
 * what around one root, bounded to four hops. It cannot answer how many gp2 volumes are in one
 * region, which is what somebody actually arrives with, and orientation is the gap the
 * competitive review names twice.
 *
 * **Two things it has to say honestly, and both are above the table.** That this is a page of
 * a larger number, because a list without its denominator reads as complete. And that part of
 * the estate was never read, because a slice that refused us contributes no rows while looking
 * exactly like a region that is genuinely empty. A count at the top of a list is a claim about
 * the estate.
 */

/** A page that reads well and is small enough that the paging controls get exercised. */
const PAGE = 50;

/** Null region means global, null zone means regional. Never unknown, and never blank. */
function placeOf(node: ApiTopologyNode): string {
  if (node.availability_zone !== null) return node.availability_zone;
  return node.region_id ?? 'global';
}

function Choice({
  id,
  label,
  options,
  value,
  onChange,
}: {
  readonly id: string;
  readonly label: string;
  readonly options: readonly string[];
  readonly value: string;
  readonly onChange: (next: string) => void;
}) {
  return (
    <p>
      <label htmlFor={id}>{label}</label>{' '}
      <select
        id={id}
        data-testid={id}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {/* Every value in this list occurs in the estate, because the server read them from
            the data. A select offering fourteen kinds where four exist teaches a reader that
            ten of the filters are broken. */}
        <option value="">Any</option>
        {options.map((one) => (
          <option key={one} value={one}>
            {one}
          </option>
        ))}
      </select>
    </p>
  );
}

export function ResourceListScreen() {
  const [account, setAccount] = useState('');
  const [region, setRegion] = useState('');
  const [kind, setKind] = useState('');
  const [type, setType] = useState('');
  const [offset, setOffset] = useState(0);

  const query = useResources({
    accountId: account === '' ? undefined : account,
    regionId: region === '' ? undefined : region,
    nodeKind: kind === '' ? undefined : kind,
    resourceType: type === '' ? undefined : type,
    limit: PAGE,
    offset,
  });
  const estate = useGraphCoverage();

  const envelope = query.data?.data;
  const estateEnvelope = estate.data?.data;
  useReportMeta('inventory-resources', envelope?.meta);
  useReportMeta('inventory-coverage', estateEnvelope?.meta);

  const page = envelope?.data;
  const rows = page?.resources ?? [];
  const unreadable = estateEnvelope?.data.incomplete ?? [];
  const filters: ApiResourceFilters = page?.filters ?? {
    account_id: [],
    region_id: [],
    node_kind: [],
    resource_type: [],
  };
  // What was actually filtered on, in the reader's own terms. `StateBoundary` prints this
  // beside "nothing matches this filter", and the literal string none over a narrowed list is
  // how a reader concludes the estate is empty when their own filter emptied it.
  const narrowed = [
    account === '' ? null : `account ${account}`,
    region === '' ? null : `region ${region}`,
    kind === '' ? null : `kind ${kind}`,
    type === '' ? null : `type ${type}`,
  ].filter((one) => one !== null);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    rows.length,
    narrowed.length === 0 ? 'none' : narrowed.join(', '),
    'inventory',
  );

  /** Any filter change returns to the first page. Staying on page four of a narrower result
   *  shows an empty table, which reads as "nothing matches" when the truth is that the reader
   *  is past the end. */
  function narrow(set: (next: string) => void) {
    return (next: string) => {
      set(next);
      setOffset(0);
    };
  }

  const shown = page === undefined ? 0 : page.offset + rows.length;

  return (
    <section aria-label="Resources">
      <FixtureBand source={query.data?.source} />

      {/* Above the table, never under it. A slice that refused us contributes no rows while
          looking exactly like a region that is genuinely empty, and a reader who has already
          read the list has already concluded it was everything. */}
      {unreadable.length > 0 ? (
        <div role="status" data-testid="estate-coverage" className="meter-stale">
          <p>
            {unreadable.length === 1
              ? 'One slice of the estate could not be read, so resources in it are missing ' +
                'from this list rather than absent from the estate.'
              : `${String(unreadable.length)} slices of the estate could not be read, so ` +
                'resources in them are missing from this list rather than absent from the ' +
                'estate.'}
          </p>
          <ul>
            {unreadable.map((slice: ApiSliceCoverage) => (
              <li key={`${slice.account_id}:${slice.region_id ?? 'global'}`}>
                {saidOf(slice)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div role="group" aria-label="Narrow the list">
        <Choice
          id="filter-account"
          label="Account"
          options={filters.account_id}
          value={account}
          onChange={narrow(setAccount)}
        />
        <Choice
          id="filter-region"
          label="Region"
          options={filters.region_id}
          value={region}
          onChange={narrow(setRegion)}
        />
        <Choice
          id="filter-kind"
          label="Kind"
          options={filters.node_kind}
          value={kind}
          onChange={narrow(setKind)}
        />
        <Choice
          id="filter-type"
          label="Type"
          options={filters.resource_type}
          value={type}
          onChange={narrow(setType)}
        />
      </div>

      <StateBoundary state={state}>
        {page ? (
          <>
            {/* No empty branch here. `StateBoundary` renders the empty case itself and never
                reaches these children, which is how every other screen behaves, and a second
                empty message behind an unreachable condition is worse than none: it reads as
                the thing that handles the case and it never runs. What this screen owes the
                boundary is the filter label below, so its message names what was filtered on
                rather than saying "none" over a narrowed list. */}
            <table data-testid="resources">
              <caption data-testid="resources-count">
                {/* The denominator, every time. A page that does not publish it reads as
                      the whole estate, and a reader who acts on that is acting on a subset. */}
                {page.total === rows.length
                  ? `All ${String(page.total)} resources in your scope`
                  : `${String(page.offset + 1)} to ${String(shown)} of ${String(page.total)} ` +
                    'resources in your scope'}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Resource</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Type</th>
                  <th scope="col">Account</th>
                  <th scope="col">Location</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((node) => (
                  <tr key={node.node_id}>
                    <th scope="row">
                      {/* Every row leads to the page that answers what it costs and what is
                            wrong with it, which is the whole reason FEAT-053 exists. */}
                      <Link to={`/inventory/resources/${node.node_id}`}>
                        {node.name ?? node.provider_id}
                      </Link>
                    </th>
                    <td>{node.node_kind}</td>
                    {/* The provider's own word, beside the lossy kind. Ten of the estate's
                          types are OTHER, so without this a list is unlabelled boxes. */}
                    <td>{node.resource_type}</td>
                    <td>{node.account_id}</td>
                    <td>{placeOf(node)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <p role="group" aria-label="Pages">
              <button
                type="button"
                data-testid="resources-previous"
                disabled={page.offset === 0}
                onClick={() => {
                  setOffset(Math.max(0, page.offset - page.limit));
                }}
              >
                Previous
              </button>{' '}
              <button
                type="button"
                data-testid="resources-next"
                disabled={shown >= page.total}
                onClick={() => {
                  setOffset(page.offset + page.limit);
                }}
              >
                Next
              </button>
            </p>
          </>
        ) : null}
      </StateBoundary>
    </section>
  );
}
