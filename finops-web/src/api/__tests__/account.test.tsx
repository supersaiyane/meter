import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { Harness } from '../../screens/__tests__/Harness';
import { metaOf } from '../../screens/__tests__/fixtures';
import { Link } from '../../shell/links';
import {
  CHOSEN_ACCOUNT_PARAM,
  keepAccount,
  useChosenAccount,
  withChosenAccount,
} from '../account';
import type { ApiClient } from '../client';
import { useAccountChoices, useAccounts } from '../queries';
import type { ApiEnvelope } from '../types';

/**
 * The account chosen in the address, FEAT-075: read from the address, sent to the API under a
 * name of its own, kept by every destination, and part of every cache key, so one account's
 * figures are never served under another's.
 */

const CHOSEN = '444455556666';
const OTHER = '111122223333';

function at(path: string) {
  return function Router({ children }: { readonly children: ReactNode }) {
    return <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>;
  };
}

/** A client answering every read with an empty list, recording what was asked. */
function recording() {
  const asked: string[] = [];
  const client: ApiClient = {
    get: <T,>(path: string): Promise<ApiEnvelope<T>> => {
      asked.push(path);
      return Promise.resolve({ data: [], meta: metaOf() } as unknown as ApiEnvelope<T>);
    },
    patch: () => Promise.reject(new Error('no patch stub')),
    delete: () => Promise.reject(new Error('no delete stub')),
    getFile: () => Promise.reject(new Error('no file stub')),
    post: () => Promise.reject(new Error('no write stub')),
  };
  return { client, asked };
}

describe('the account chosen in the address', () => {
  it('is read from the address, and an empty value is no choice', () => {
    const read = (path: string) =>
      renderHook(() => useChosenAccount(), { wrapper: at(path) }).result.current;

    expect(read(`/?account=${CHOSEN}`)).toBe(CHOSEN);
    expect(read('/?account=')).toBeNull();
    expect(read('/')).toBeNull();
  });

  it('is sent to the API under its own name, beside any account filter a route reads', () => {
    expect(withChosenAccount('/api/v1/accounts', CHOSEN)).toBe(
      `/api/v1/accounts?${CHOSEN_ACCOUNT_PARAM}=${CHOSEN}`,
    );
    expect(withChosenAccount(`/api/v1/cost/explore?account=${OTHER}`, CHOSEN)).toBe(
      `/api/v1/cost/explore?account=${OTHER}&chosen_account=${CHOSEN}`,
    );
    expect(withChosenAccount('/api/v1/accounts', null)).toBe('/api/v1/accounts');
    expect(withChosenAccount('/x', 'a b&c')).toBe('/x?chosen_account=a%20b%26c');
  });

  it('is kept by a destination naming none, and one naming its own account keeps that one', () => {
    expect(keepAccount('/analyze/explorer', CHOSEN)).toEqual({
      pathname: '/analyze/explorer',
      search: `?account=${CHOSEN}`,
    });
    expect(keepAccount('/analyze/explorer?service=AmazonEC2#top', CHOSEN)).toEqual({
      pathname: '/analyze/explorer',
      search: `?service=AmazonEC2&account=${CHOSEN}`,
      hash: '#top',
    });
    expect(keepAccount(`/inventory/resources?account=${OTHER}`, CHOSEN)).toBe(
      `/inventory/resources?account=${OTHER}`,
    );
    expect(keepAccount({ pathname: 'details' }, CHOSEN)).toEqual({
      pathname: 'details',
      search: `?account=${CHOSEN}`,
    });
    expect(keepAccount('/analyze/explorer', null)).toBe('/analyze/explorer');
  });
});

describe('every read', () => {
  function Accounts() {
    const { data } = useAccounts();
    return (
      <>
        <p>{data === undefined ? 'reading' : 'read'}</p>
        <Link to={`/?account=${OTHER}`}>another account</Link>
      </>
    );
  }

  it('carries the chosen account to the server', async () => {
    const { client, asked } = recording();
    render(
      <Harness client={client} initialPath={`/?account=${CHOSEN}`}>
        <Accounts />
      </Harness>,
    );

    await screen.findByText('read');
    expect(asked).toEqual([`/api/v1/accounts?chosen_account=${CHOSEN}`]);
  });

  it('asks again when the account changes rather than showing the last one from the cache', async () => {
    const { client, asked } = recording();
    render(
      <Harness client={client} initialPath={`/?account=${CHOSEN}`}>
        <Accounts />
      </Harness>,
    );
    await screen.findByText('read');

    fireEvent.click(screen.getByText('another account'));

    await waitFor(() => {
      expect(asked).toEqual([
        `/api/v1/accounts?chosen_account=${CHOSEN}`,
        `/api/v1/accounts?chosen_account=${OTHER}`,
      ]);
    });
  });

  it('except the list the search box offers, which a choice must never narrow', async () => {
    const { client, asked } = recording();
    function Choices() {
      const { data } = useAccountChoices();
      return <p>{data === undefined ? 'reading' : 'read'}</p>;
    }
    render(
      <Harness client={client} initialPath={`/?account=${CHOSEN}`}>
        <Choices />
      </Harness>,
    );

    await screen.findByText('read');
    expect(asked).toEqual(['/api/v1/accounts']);
  });
});
