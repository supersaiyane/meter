import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useLocation } from 'react-router';
import { describe, expect, it } from 'vitest';

import type { ApiClient } from '../../api/client';
import type { ApiEnvelope } from '../../api/types';
import { Harness } from '../../screens/__tests__/Harness';
import { metaOf } from '../../screens/__tests__/fixtures';
import { SearchBox } from '../SearchBox';

/**
 * The search box, FEAT-075: one box finds accounts, services and resources. An account narrows
 * every screen through the address, a service opens Cost Explorer and a resource its page.
 */

const PLATFORM = { account_id: '444455556666', name: 'Platform' };
const DATA = { account_id: '111122223333', name: 'Data and ML' };
const CHECKOUT = {
  node_id: 'n-1',
  provider_id: 'arn:aws:ecs:eu-west-1:444455556666:service/checkout-api',
  account_id: '444455556666',
  node_kind: 'COMPUTE',
  resource_type: 'AWS::ECS::Service',
  region_id: 'eu-west-1',
  availability_zone: null,
  name: 'checkout-api',
  as_of: '2026-09-19T04:00:00Z',
  collected_at: '2026-09-20T06:22:00Z',
};

/** An estate of two accounts, two services and one resource, recording what was asked. */
function estate({ accountsFail = false } = {}) {
  const asked: string[] = [];
  const answer = <T,>(data: unknown) =>
    Promise.resolve({ data, meta: metaOf() } as unknown as ApiEnvelope<T>);
  const client: ApiClient = {
    get: <T,>(path: string): Promise<ApiEnvelope<T>> => {
      asked.push(path);
      const [route = ''] = path.split('?');
      if (route === '/api/v1/accounts') {
        return accountsFail ? Promise.reject(new Error('503')) : answer<T>([PLATFORM, DATA]);
      }
      if (route === '/api/v1/cost/by-service') {
        return answer<T>([{ name: 'AmazonEC2' }, { name: 'AmazonRDS' }]);
      }
      if (route === '/api/v1/inventory/resources') {
        return answer<T>({ resources: [CHECKOUT], total: 1, limit: 8, offset: 0, filters: {} });
      }
      return Promise.reject(new Error(`no stub: ${path}`));
    },
    getFile: () => Promise.reject(new Error('no file stub')),
    post: () => Promise.reject(new Error('no write stub')),
  };
  return { client, asked };
}

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

function open(path: string, stub = estate()) {
  render(
    <Harness client={stub.client} initialPath={path}>
      <SearchBox />
      <Where />
    </Harness>,
  );
  return { asked: stub.asked, user: userEvent.setup() };
}

const where = () => screen.getByTestId('where').textContent;
const box = () =>
  screen.getByRole('combobox', { name: 'Search accounts, services and resources' });

describe('SearchBox', () => {
  it('shows All accounts when nothing is chosen, and the chosen account when one is', async () => {
    open('/?account=444455556666');
    await waitFor(() => {
      expect(box()).toHaveValue('Platform (444455556666)');
    });
  });

  it('narrows the screen to a chosen account, and All accounts combines them again', async () => {
    const { user } = open('/analyze/anomalies');
    expect(box()).toHaveValue('All accounts');

    await user.clear(box());
    await user.type(box(), 'plat');
    await user.click(await screen.findByRole('option', { name: 'Platform (444455556666)' }));
    expect(where()).toBe('/analyze/anomalies?account=444455556666');

    await user.clear(box());
    await user.click(await screen.findByRole('option', { name: 'All accounts' }));
    expect(where()).toBe('/analyze/anomalies');
  });

  it('opens Cost Explorer filtered to a chosen service, keeping the account', async () => {
    const { user } = open('/?account=444455556666');
    await user.clear(box());
    await user.type(box(), 'ec2');

    await user.click(await screen.findByRole('option', { name: 'AmazonEC2' }));

    expect(where()).toBe('/analyze/explorer?service=AmazonEC2&account=444455556666');
  });

  it('searches resources on the server once typing pauses, and opens the one chosen', async () => {
    const { user, asked } = open('/');
    await user.clear(box());
    await user.type(box(), 'checkout');

    await user.click(await screen.findByRole('option', { name: 'checkout-api' }));

    expect(asked.filter((path) => path.startsWith('/api/v1/inventory/resources'))).toEqual([
      '/api/v1/inventory/resources?q=checkout&limit=8',
    ]);
    expect(where()).toBe('/inventory/resources/n-1');
  });

  it('says when the accounts could not be read rather than offering a list missing them', async () => {
    const { user } = open('/', estate({ accountsFail: true }));
    await user.click(box());

    expect(await screen.findByTestId('search-failure')).toHaveTextContent(
      'Could not read the accounts.',
    );
  });
});
