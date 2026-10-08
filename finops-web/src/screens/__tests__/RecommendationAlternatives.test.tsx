import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { WasteScreen } from '../WasteScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import {
  alternativesFixture,
  recommendationsFixture,
  refusalsFixture,
} from '../../api/fixtures/waste';
import type { ApiEnvelope, ApiRecommendations } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * The Alternatives table, TASK-P9-010, rendered where a reader meets it: under one finding on
 * the recommendations screen, reached from the list's Target column.
 */

const ID = '2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f';
const ALTERNATIVES = `/api/v1/waste/recommendations/${ID}/alternatives`;

function targeted(): ApiEnvelope<ApiRecommendations> {
  const base = recommendationsFixture();
  return {
    ...base,
    data: {
      ...base.data,
      recommendations: base.data.recommendations.map((row) =>
        row.recommendation_id === ID
          ? {
              ...row,
              current_instance_type: 'm5.xlarge',
              target_instance_type: 'm6i.large',
              current_hourly_price: '0.1947',
              target_hourly_price: '0.1014',
              price_version: '20260820000000',
              added_monthly_cost: null,
            }
          : row,
      ),
    },
  };
}

function renderAt(path: string) {
  return render(
    <Harness
      initialPath={path}
      client={clientReturning({
        '/api/v1/waste/recommendations': targeted(),
        '/api/v1/waste/refusals': refusalsFixture(),
        [ALTERNATIVES]: alternativesFixture(ID),
      })}
    >
      <WasteScreen />
    </Harness>,
  );
}

async function table(): Promise<HTMLElement> {
  const found = await screen.findByTestId('alternatives');
  await within(found).findByTestId('alternative-m6i.large');
  return found;
}

describe('the Alternatives table', () => {
  it('names the target in the list and links to what it was compared with', async () => {
    renderAt('/optimize');
    const target = await screen.findByTestId(`target-${ID}`);
    expect(target).toHaveTextContent('m5.xlarge to m6i.large');
    expect(within(target).getByRole('link', { name: 'Alternatives' })).toHaveAttribute(
      'href',
      `/optimize?finding=${ID}`,
    );
    // The whole queue shows no one finding's comparison.
    expect(screen.queryByTestId('alternatives')).toBeNull();
  });

  it('leads with the chosen type under one finding, and says what it was compared with', async () => {
    renderAt(`/optimize?finding=${ID}`);
    const found = await table();
    const first = within(found).getAllByRole('row')[1];
    expect(first).toHaveTextContent('m6i.large');
    expect(first).toContainElement(within(found).getByTestId('alternative-chosen'));
    expect(screen.getByTestId('alternatives-basis')).toHaveTextContent(
      'Compared with m5.xlarge at $0.1947 an hour, at list prices from price list version 20260820000000',
    );
  });

  it('keeps an option it cannot price, with the reason in the price', async () => {
    renderAt(`/optimize?finding=${ID}`);
    const found = await table();
    expect(within(found).getByTestId('unpriced-m6g.large')).toHaveTextContent(
      'not priced: the catalog holds no Linux price for m6g.large in eu-west-1',
    );
    expect(within(found).getByTestId('saving-m6g.large')).toHaveTextContent('not priced');
  });

  it('says no risk score was given rather than showing nought', async () => {
    renderAt(`/optimize?finding=${ID}`);
    const found = await table();
    expect(within(found).getByTestId('no-risk-score-m5.large')).toHaveTextContent('none given');
    expect(found).toHaveTextContent('1.00 of 4');
  });

  it('labels every price it shows a month as modelled', async () => {
    renderAt(`/optimize?finding=${ID}`);
    const found = await table();
    const figures = within(found).getAllByTestId('figure');
    expect(figures.length).toBeGreaterThan(0);
    expect(figures.every((figure) => figure.textContent.includes('modelled'))).toBe(true);
  });

  it('sorts by the money a reader compares types by', async () => {
    const user = userEvent.setup();
    renderAt(`/optimize?finding=${ID}`);
    const found = within(await table());
    for (const header of ['Per month, list', 'Monthly saving, list']) {
      const column = found.getByRole('columnheader', { name: new RegExp(`^${header}`) });
      await user.click(within(column).getByRole('button'));
      expect(column.getAttribute('aria-sort')).not.toBe('none');
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = renderAt(`/optimize?finding=${ID}`);
    await table();
    expect(await violationsIn(container)).toEqual([]);
  });
});
