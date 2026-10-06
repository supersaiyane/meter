import type { Account, ApiCostSlice, ApiTopologyNode } from '../api/types';

/**
 * What the search box in the top bar offers, FEAT-075, decided here rather than in the
 * component so every rule is tested without a browser.
 *
 * The owner chose on 2026-10-06 that one box finds accounts, services and resources. An account
 * narrows every screen, a service opens Cost Explorer filtered to it and a resource opens its
 * page. All accounts is first and is the default.
 */

/** What choosing an option does. */
export type SearchAction =
  | { readonly kind: 'all' }
  | { readonly kind: 'account'; readonly accountId: string }
  | { readonly kind: 'service'; readonly service: string }
  | { readonly kind: 'resource'; readonly nodeId: string };

export interface SearchOption {
  /** Unique across every section, because the list box keys on it. */
  readonly id: string;
  readonly label: string;
  readonly detail: string;
  readonly action: SearchAction;
}

export interface SearchSection {
  readonly id: 'accounts' | 'services' | 'resources';
  readonly name: string;
  readonly children: readonly SearchOption[];
}

/** Accounts and services shown at once. More are found by typing, never by scrolling 1,399. */
export const SHOWN_PER_SECTION = 50;

/** Characters typed before resources are searched on the server, and how many come back. */
export const RESOURCE_SEARCH_FROM = 3;
export const RESOURCE_MATCHES = 8;

/** The service grouping's name for spend with no service, which is not a service to open. */
const NO_SERVICE = 'unallocated';

export const ALL_ACCOUNTS: SearchOption = {
  id: 'all',
  label: 'All accounts',
  detail: 'Every account this session can see, combined',
  action: { kind: 'all' },
};

function contains(query: string, ...fields: readonly string[]): boolean {
  const wanted = query.trim().toLowerCase();
  return fields.some((field) => field.toLowerCase().includes(wanted));
}

/** An account as the box shows it: its name and number, or the number when it has no name. */
export function accountLabel(account: Pick<Account, 'account_id' | 'name'>): string {
  return account.name === '' || account.name === account.account_id
    ? account.account_id
    : `${account.name} (${account.account_id})`;
}

function cut(name: string, matched: number): string {
  return matched > SHOWN_PER_SECTION
    ? `${name}, ${String(SHOWN_PER_SECTION)} of ${matched.toLocaleString('en-US')} shown, type to narrow`
    : name;
}

/** All accounts first, then the accounts whose number or name holds what was typed, by name. */
export function accountSection(accounts: readonly Account[], query: string): SearchSection {
  // Sorted in place, which touches only the fresh array `filter` returned.
  const matched = accounts
    .filter((account) => contains(query, account.account_id, account.name))
    .sort((one, other) => one.name.localeCompare(other.name, 'en'));
  return {
    id: 'accounts',
    name: cut('Accounts', matched.length),
    children: [
      ALL_ACCOUNTS,
      ...matched.slice(0, SHOWN_PER_SECTION).map((account) => ({
        id: `account:${account.account_id}`,
        label: accountLabel(account),
        detail: 'Show every screen for this account alone',
        action: { kind: 'account', accountId: account.account_id } as const,
      })),
    ],
  };
}

/** Services with spend whose name holds what was typed. None until something is typed. */
export function serviceSection(
  services: readonly ApiCostSlice[],
  query: string,
): SearchSection | null {
  if (query.trim() === '') {
    return null;
  }
  const matched = services.filter(
    (service) => service.name !== NO_SERVICE && contains(query, service.name),
  );
  if (matched.length === 0) {
    return null;
  }
  return {
    id: 'services',
    name: cut('Services', matched.length),
    children: matched.slice(0, SHOWN_PER_SECTION).map((service) => ({
      id: `service:${service.name}`,
      label: service.name,
      detail: 'Open in Cost Explorer',
      action: { kind: 'service', service: service.name } as const,
    })),
  };
}

/** The last part of an ARN, which is the part a person recognises. */
function arnTail(arn: string): string {
  const parts = arn.split(/[:/]/);
  return parts.at(-1) ?? arn;
}

/** Resources the server found for what was typed. */
export function resourceSection(nodes: readonly ApiTopologyNode[]): SearchSection | null {
  if (nodes.length === 0) {
    return null;
  }
  return {
    id: 'resources',
    name: 'Resources',
    children: nodes.map((node) => ({
      id: `resource:${node.node_id}`,
      label: node.name ?? arnTail(node.provider_id),
      detail: [node.resource_type, node.account_id, node.region_id ?? 'global'].join(', '),
      action: { kind: 'resource', nodeId: node.node_id } as const,
    })),
  };
}

/** Every section with something in it, in the order the box shows them. */
export function sectionsFor(parts: readonly (SearchSection | null)[]): SearchSection[] {
  return parts.filter((part): part is SearchSection => part !== null);
}

/** One option by its key, across every section. */
export function optionFor(
  sections: readonly SearchSection[],
  key: string | number | null,
): SearchOption | undefined {
  return sections.flatMap((section) => section.children).find((option) => option.id === key);
}
