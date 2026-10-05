import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import type { ApiForecast } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { ForecastScreen } from '../ForecastScreen';
import { Harness } from './Harness';
import { clientReturning, forecastOf, metaOf } from './fixtures';

/** Forecasts, FEAT-066 and TASK-P8-008: a range or a reason, never a point. */

function renderForecast(answer: ApiForecast = forecastOf(), failure?: Error) {
  return render(
    <Harness
      client={clientReturning(
        { '/api/v1/cost/forecast': { data: answer, meta: metaOf() } },
        failure,
      )}
      initialPath="/plan/forecasts"
    >
      <ForecastScreen />
    </Harness>,
  );
}

function withheldMonthEnd(): ApiForecast {
  const shown = forecastOf();
  return forecastOf({
    month_end: {
      ...shown.month_end,
      figure: null,
      withheld:
        'The forecast is tested on 3 complete months before it is shown, and Meter holds 1 it can be tested on.',
      median_miss: '0.0400',
      held_out: 1,
    },
    days: shown.days.map((day) => ({ ...day, low: null, high: null })),
    backtest: [
      {
        month: '2026-09-01',
        actual: '15200.00',
        miss: '0.0400',
        low: null,
        high: null,
        within: null,
      },
    ],
  });
}

describe('ForecastScreen', () => {
  it('shows the month end as a range labelled forecast, beside its accuracy and method', async () => {
    renderForecast();
    const range = await screen.findByTestId('forecast-range');
    const figure = within(range).getByTestId('figure');
    expect(figure).toHaveAttribute('data-provenance', 'forecast');
    expect(figure).toHaveTextContent(/15,000\.00 to .*16,000\.00/);
    const accuracy = screen.getByTestId('forecast-accuracy');
    expect(accuracy).toHaveTextContent(
      'Median miss 6.0% over the last 3 months, measured by backtest.',
    );
    expect(accuracy).toHaveTextContent('Method: weekday profile.');
    expect(accuracy).toHaveTextContent(
      'at least 3 complete months with a median miss of at most 15.0%',
    );
  });

  it('says why there is no month end figure instead of showing one', async () => {
    renderForecast(withheldMonthEnd());
    expect(await screen.findAllByTestId('forecast-withheld')).not.toHaveLength(0);
    expect(screen.queryByTestId('forecast-range')).not.toBeInTheDocument();
    const headline = screen.getByTestId('forecast-month-end');
    expect(headline).toHaveTextContent('tested on 3 complete months before it is shown');
    expect(headline.querySelector('[data-provenance="forecast"]')).toBeNull();
    expect(screen.getByTestId('forecast-backtest')).toHaveTextContent('Withheld');
  });

  it('lists the next three months, each a range or the sentence saying why', async () => {
    renderForecast();
    const ahead = within(await screen.findByTestId('forecast-ahead'));
    expect(ahead.getAllByTestId('forecast-withheld')).toHaveLength(2);
    expect(
      ahead.getAllByTestId('figure').filter((one) => one.dataset['provenance'] === 'forecast'),
    ).toHaveLength(1);
    expect(ahead.getByText('November 2026')).toBeInTheDocument();
  });

  it('shows the backtest month by month, and whether the range held each', async () => {
    renderForecast();
    const backtest = within(await screen.findByTestId('forecast-backtest'));
    expect(backtest.getAllByText('Yes')).toHaveLength(2);
    expect(backtest.getAllByText('No')).toHaveLength(1);
  });

  it('draws the billed days and the band on one chart', async () => {
    renderForecast();
    const chart = within(await screen.findByTestId('forecast-chart'));
    expect(chart.getByTestId('forecast-band')).toBeInTheDocument();
    expect(chart.getAllByTestId('area-layer')).toHaveLength(1);
  });

  it('says what failed rather than showing a forecast of nothing', async () => {
    renderForecast(forecastOf(), new ApiError(404, 'No billing period has been collected.'));
    expect(await screen.findByText(/No billing period has been collected/)).toBeInTheDocument();
    expect(screen.queryByTestId('forecast')).not.toBeInTheDocument();
  });

  it('passes an accessibility check', async () => {
    const { container } = renderForecast();
    await screen.findByTestId('forecast-range');
    expect(await violationsIn(container)).toEqual([]);
  });
});
