import type { ApiTopologyNode } from '../api/types';
import type { Column } from '../components/tableConfig';
import { Link } from '../shell/links';

/**
 * The columns of a list of resources, TASK-P8-013, shared by the resource list and Geography.
 *
 * **They sort only when the page holds the whole list.** A page of a longer list arrives in
 * the server's order, and sorting it would order fifty rows and read as ordering every one, so
 * until the whole list is on the page the columns do not offer to, and the caption's count says
 * which part this is.
 */
export function nodeColumns(
  whole: boolean,
  placeHeader: string,
  place: (node: ApiTopologyNode) => string,
): readonly Column<ApiTopologyNode>[] {
  const sorted = (pick: (node: ApiTopologyNode) => string) =>
    whole ? { sortValue: pick } : {};
  return [
    {
      key: 'resource',
      header: 'Resource',
      rowHeader: true,
      // Every row leads to the page that answers what it costs and what is wrong with it,
      // which is the whole reason FEAT-053 exists.
      render: (node) => (
        <Link to={`/inventory/resources/${node.node_id}`}>{node.name ?? node.provider_id}</Link>
      ),
      ...sorted((node) => node.name ?? node.provider_id),
    },
    {
      key: 'kind',
      header: 'Kind',
      render: (node) => node.node_kind,
      ...sorted((node) => node.node_kind),
    },
    {
      // The provider's own word, beside the lossy kind. Ten of the estate's types are OTHER,
      // so without this a list is unlabelled boxes.
      key: 'type',
      header: 'Type',
      render: (node) => node.resource_type,
      ...sorted((node) => node.resource_type),
    },
    {
      key: 'account',
      header: 'Account',
      render: (node) => node.account_id,
      ...sorted((node) => node.account_id),
    },
    { key: 'place', header: placeHeader, render: place, ...sorted(place) },
  ];
}
