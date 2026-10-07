import { describe, expect, it } from 'vitest';

import { resourceListFixture } from '../../api/fixtures/topology';
import type { ApiTopologyNode } from '../../api/types';
import { sortRows } from '../../components/tableConfig';
import { nodeColumns } from '../nodeColumns';

describe('the columns of a list of resources', () => {
  it('sort when the page holds the whole list', () => {
    const columns = nodeColumns(true, 'Region', (node) => node.region_id ?? 'global');
    expect(columns.every((column) => column.sortValue !== undefined)).toBe(true);
    expect(columns.map((column) => column.header)).toEqual([
      'Resource',
      'Kind',
      'Type',
      'Account',
      'Region',
    ]);
  });

  it('offer no sort on a page of a longer list, which would order the page and not the list', () => {
    const columns = nodeColumns(false, 'Location', (node) => node.account_id);
    expect(columns.some((column) => column.sortValue !== undefined)).toBe(false);
  });

  it('order by what each column shows, a nameless resource by its identifier', () => {
    const base = resourceListFixture().data.resources[0];
    if (base === undefined) throw new Error('The fixture lists no resources');
    const named: ApiTopologyNode = {
      ...base,
      node_id: 'named',
      name: 'zeta',
      provider_id: 'i-0001',
      node_kind: 'VPC',
      resource_type: 'AWS::EC2::VPC',
      account_id: '222222222222',
      region_id: 'us-east-1',
    };
    const nameless: ApiTopologyNode = {
      ...base,
      node_id: 'nameless',
      name: null,
      provider_id: 'i-0002',
      node_kind: 'INSTANCE',
      resource_type: 'AWS::EC2::Instance',
      account_id: '111111111111',
      region_id: 'eu-west-1',
    };
    const columns = nodeColumns(true, 'Region', (node) => node.region_id ?? 'global');
    // Arriving in the other order, so a column that did not sort would leave it first.
    const first = (key: string): string | undefined =>
      sortRows([named, nameless], columns, { key, direction: 'ascending' })[0]?.node_id;
    for (const key of ['resource', 'kind', 'type', 'account', 'place']) {
      expect(first(key)).toBe('nameless');
    }
  });
});
