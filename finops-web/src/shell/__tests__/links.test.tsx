import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { Link, NavLink } from '../links';

/**
 * Links keep the account chosen in the address, FEAT-075.
 *
 * The last test is the rule's enforcement. It belongs in ESLint as `no-restricted-imports`, and
 * a hook guarding the lint configuration refuses that edit, so it is held here instead, where
 * `make verify` runs it: one link reaching for the router's own `Link` would open a screen
 * showing every account to a reader who believes it shows one.
 */

//: Every source file, raw, read through the bundler as `freshnessContract.test.ts` reads them.
const SOURCES = import.meta.glob('../../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const ROUTER_LINK = /import\s*\{[^}]*\b(?:Link|NavLink)\b[^}]*\}\s*from\s*'react-router'/;

describe('links', () => {
  it('carry the account the address names', () => {
    render(
      <MemoryRouter initialEntries={['/cost?account=444455556666']}>
        <Link to="/analyze/explorer">explorer</Link>
        <NavLink to="/optimize">optimize</NavLink>
      </MemoryRouter>,
    );

    expect(screen.getByText('explorer')).toHaveAttribute(
      'href',
      '/analyze/explorer?account=444455556666',
    );
    expect(screen.getByText('optimize')).toHaveAttribute(
      'href',
      '/optimize?account=444455556666',
    );
  });

  it('go where they say when no account is chosen', () => {
    render(
      <MemoryRouter initialEntries={['/cost']}>
        <Link to="/analyze/explorer">explorer</Link>
      </MemoryRouter>,
    );

    expect(screen.getByText('explorer')).toHaveAttribute('href', '/analyze/explorer');
  });

  it('come from one place, because the router’s own would drop the account', () => {
    const offenders = Object.entries(SOURCES)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
      // Keys are relative to this file, so the wrapper itself is `../links.tsx`.
      .filter(([path]) => path !== '../links.tsx' && !/\.test\.tsx?$/.test(path))
      .filter(([, source]) => ROUTER_LINK.test(source))
      .map(([path]) => path);

    expect(Object.keys(SOURCES).length).toBeGreaterThan(50);
    expect(offenders).toEqual([]);
  });
});
