import { describe, expect, it } from 'vitest';

import type { Account, ApiCostSlice, ApiTopologyNode } from '../../api/types';
import {
  ALL_ACCOUNTS,
  SHOWN_PER_SECTION,
  accountLabel,
  accountSection,
  optionFor,
  resourceSection,
  sectionsFor,
  serviceSection,
} from '../searchModel';

/** What the search box offers, FEAT-075, decided without a browser. */

function account(account_id: string, name: string): Account {
  return { account_id, name } as Account;
}

function slice(name: string): ApiCostSlice {
  return { name, effective_cost: '1.00', billed_cost: '1.00' } as ApiCostSlice;
}

function node(partial: Partial<ApiTopologyNode>): ApiTopologyNode {
  return {
    node_id: 'n-1',
    provider_id: 'arn:aws:ec2:eu-west-1:444455556666:instance/i-0abc',
    account_id: '444455556666',
    node_kind: 'COMPUTE',
    resource_type: 'AWS::EC2::Instance',
    region_id: 'eu-west-1',
    availability_zone: null,
    name: null,
    as_of: '2026-09-19T04:00:00Z',
    collected_at: '2026-09-20T06:22:00Z',
    ...partial,
  };
}

const ESTATE = [
  account('444455556666', 'Platform'),
  account('111122223333', 'Data and ML'),
  account('777788889999', '777788889999'),
];

describe('the accounts the box offers', () => {
  it('puts All accounts first whatever was typed', () => {
    expect(accountSection(ESTATE, '').children[0]).toBe(ALL_ACCOUNTS);
    expect(accountSection(ESTATE, 'platform').children[0]).toBe(ALL_ACCOUNTS);
  });

  it('matches a number or a name, ignoring case, and lists them by name', () => {
    expect(accountSection(ESTATE, 'PLAT').children.map((option) => option.label)).toEqual([
      'All accounts',
      'Platform (444455556666)',
    ]);
    expect(accountSection(ESTATE, '1111').children.map((option) => option.id)).toEqual([
      'all',
      'account:111122223333',
    ]);
    expect(accountSection(ESTATE, '').children.map((option) => option.label)).toEqual([
      'All accounts',
      '777788889999',
      'Data and ML (111122223333)',
      'Platform (444455556666)',
    ]);
  });

  it('shows a bounded number at 1,399 and says how many more typing would find', () => {
    const many = Array.from({ length: 1399 }, (_, index) =>
      account(String(100000000000 + index), `Account ${String(index).padStart(4, '0')}`),
    );

    const section = accountSection(many, '');

    expect(section.children).toHaveLength(SHOWN_PER_SECTION + 1);
    expect(section.name).toBe('Accounts, 50 of 1,399 shown, type to narrow');
  });

  it('labels an account by its number alone when it has no other name', () => {
    expect(accountLabel({ account_id: '777788889999', name: '' })).toBe('777788889999');
    expect(accountLabel({ account_id: '444455556666', name: 'Platform' })).toBe(
      'Platform (444455556666)',
    );
  });
});

describe('the services the box offers', () => {
  const SERVICES = [slice('AmazonEC2'), slice('AmazonRDS'), slice('unallocated')];

  it('offers none until something is typed', () => {
    expect(serviceSection(SERVICES, '  ')).toBeNull();
  });

  it('matches by name and never offers spend with no service as a service', () => {
    expect(serviceSection(SERVICES, 'ec2')?.children.map((option) => option.action)).toEqual([
      { kind: 'service', service: 'AmazonEC2' },
    ]);
    expect(serviceSection(SERVICES, 'unalloc')).toBeNull();
  });
});

describe('the resources the box offers', () => {
  it('names a resource by its name, or by the end of its ARN when it has none', () => {
    const section = resourceSection([node({ name: 'checkout-api' }), node({ node_id: 'n-2' })]);

    expect(section?.children.map((option) => option.label)).toEqual(['checkout-api', 'i-0abc']);
    expect(section?.children[0]?.detail).toBe('AWS::EC2::Instance, 444455556666, eu-west-1');
    expect(section?.children[1]?.action).toEqual({ kind: 'resource', nodeId: 'n-2' });
  });

  it('says global for a resource that belongs to no region', () => {
    expect(resourceSection([node({ region_id: null })])?.children[0]?.detail).toContain(
      'global',
    );
  });

  it('offers no section when the server found nothing', () => {
    expect(resourceSection([])).toBeNull();
  });
});

describe('choosing', () => {
  it('finds an option by its key across every section, and keeps only sections with options', () => {
    const sections = sectionsFor([
      accountSection(ESTATE, 'ec2'),
      serviceSection([slice('AmazonEC2')], 'ec2'),
      null,
    ]);

    expect(sections.map((section) => section.id)).toEqual(['accounts', 'services']);
    expect(optionFor(sections, 'service:AmazonEC2')?.label).toBe('AmazonEC2');
    expect(optionFor(sections, 'all')).toBe(ALL_ACCOUNTS);
    expect(optionFor(sections, null)).toBeUndefined();
  });
});
