import { expect, test, type Page } from '@playwright/test';

/**
 * Forecasts, end to end. FEAT-066, TASK-P8-008.
 *
 * The route is stubbed, as every journey stubs its routes, with an answer shaped the way the
 * route answers: a month end shown as a range or refused with its reason, the months ahead
 * refused, and a backtest. What the journey proves is the promise ADR-0015 makes a reader: a
 * forecast arrives as a range with its accuracy beside it, or as a sentence, never as a number.
 */

const META = {
  as_of: '2026-10-04T06:00:00Z',
  collected_at: '2026-10-04T06:05:00Z',
  scope_coverage: { visible: 5, total: 5, is_partial: false, unit: 'accounts' },
  degraded: false,
  failures: [],
};

const NOT_TESTED =
  'The forecast is tested on 3 complete months before it is shown, and Meter holds 1 it can be tested on.';

function answer(withheld: boolean): unknown {
  const days = Array.from({ length: 31 }, (_, index) => {
    const day = `2026-10-${String(index + 1).padStart(2, '0')}`;
    if (index < 4) return { day, billed: String(500 * (index + 1)), low: null, high: null };
    const share = (index - 3) / 27;
    return {
      day,
      billed: null,
      low: withheld ? null : (2000 + 13000 * share).toFixed(2),
      high: withheld ? null : (2000 + 14000 * share).toFixed(2),
    };
  });
  return {
    provenance: 'forecast',
    method: 'weekday profile',
    method_detail:
      'Each day ahead is the average of the same weekday over the eight weeks before the forecast was made.',
    interval_percent: 80,
    max_median_miss: '0.15',
    min_held_out: 3,
    billed_through: '2026-10-04',
    billed_to_date: '2000.00',
    month_end: {
      month: '2026-10-01',
      figure: withheld ? null : { low: '15000.00', high: '16000.00' },
      withheld: withheld ? NOT_TESTED : null,
      median_miss: withheld ? '0.0400' : '0.0595',
      held_out: withheld ? 1 : 3,
    },
    days,
    ahead: ['2026-11-01', '2026-12-01', '2027-01-01'].map((month) => ({
      month,
      figure: null,
      withheld: NOT_TESTED,
      median_miss: null,
      held_out: 1,
    })),
    backtest: [
      {
        month: '2026-09-01',
        actual: '15200.00',
        miss: '0.0400',
        low: withheld ? null : '14900.00',
        high: withheld ? null : '15900.00',
        within: withheld ? null : true,
      },
    ],
  };
}

async function withForecast(page: Page, withheld: boolean): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });
  await page.route('**/api/v1/cost/forecast*', async (route) => {
    await route.fulfill({ json: { data: answer(withheld), meta: META } });
  });
}

test('a forecast is a range with its accuracy beside it, never one number', async ({
  page,
}) => {
  await withForecast(page, false);
  await page.goto('/plan/forecasts');

  const range = page.getByTestId('forecast-range');
  await expect(range).toContainText(/15,000\.00 to .*16,000\.00/);
  await expect(range.getByTestId('figure')).toHaveAttribute('data-provenance', 'forecast');
  await expect(page.getByTestId('forecast-accuracy')).toContainText('measured by backtest');
  await expect(page.getByTestId('forecast-chart').getByTestId('forecast-band')).toBeVisible();

  // The months the route would not forecast say so, in the place a figure would have gone.
  await expect(
    page.getByTestId('forecast-ahead').getByTestId('forecast-withheld').first(),
  ).toContainText('tested on 3 complete months');
});

test('a forecast nobody could check says why instead of showing a figure', async ({ page }) => {
  await withForecast(page, true);
  await page.goto('/plan/forecasts');

  await expect(page.getByTestId('forecast-month-end')).toContainText(
    'tested on 3 complete months before it is shown',
  );
  await expect(page.getByTestId('forecast-range')).toHaveCount(0);
  await expect(page.getByTestId('forecast-backtest')).toContainText('Withheld');
});
