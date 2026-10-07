import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiProvider } from '../../api/ApiProvider';
import { ApiError, type ApiClient } from '../../api/client';
import type { ExportView } from '../../api/exportViews';
import { scheduleState } from '../../api/savedViews';
import type { Me } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import {
  clientReturning,
  metaOf,
  posted,
  postedBodies,
} from '../../screens/__tests__/fixtures';
import { ScheduleView } from '../ScheduleView';

/** Schedule, on a view's own screen, opened by the library's Schedule. FEAT-069. */

const ME: Me = {
  principal_id: 'dev@example.local',
  display_name: 'Dev',
  tenant_id: 't-1',
  tiers: ['analyst'],
  is_global: false,
  accounts_in_scope: 1,
};

const VIEWS: readonly ExportView[] = [
  { title: 'Accounts', path: '/api/v1/accounts?status=ACTIVE' },
  { title: 'Organisation', path: '/api/v1/org/tree' },
];

function renderPanel(
  options: { views?: readonly ExportView[]; asked?: boolean; failure?: Error } = {},
) {
  const { views = VIEWS, asked = true, failure } = options;
  const base = clientReturning({
    '/api/v1/me': { data: ME, meta: metaOf() },
    '/api/v1/reports/schedules': { data: { schedule_id: 's-1' }, meta: metaOf() },
  });
  const client: ApiClient =
    failure === undefined ? base : { ...base, post: () => Promise.reject(failure) };
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const entry = {
    pathname: '/inventory/accounts',
    search: '?status=ACTIVE',
    state: asked ? scheduleState({ view_id: 'v-1', name: 'Active accounts' }) : null,
  };
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <QueryClientProvider client={queries}>
        <ApiProvider client={client}>
          <ScheduleView views={views} />
        </ApiProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  posted.length = 0;
  postedBodies.length = 0;
});

describe('Schedule', () => {
  it('is offered only to a reader the library sent here to schedule', () => {
    renderPanel({ asked: false });
    expect(screen.queryByTestId('schedule-view')).toBeNull();
  });

  it('opens as the screen arrives, offering the routes the screen exports', async () => {
    renderPanel();
    expect(screen.getByTestId('schedule-view')).toHaveAttribute('open');
    expect(screen.getByTestId('schedule-view-title')).toHaveTextContent(
      'Schedule Active accounts',
    );
    const routes = screen.getAllByTestId('schedule-view-route');
    expect(routes.map((route) => (route as HTMLInputElement).value)).toEqual(
      VIEWS.map((view) => view.path),
    );
    expect(routes[0]).toBeChecked();
    // The reader is the first recipient, once the API has said who they are.
    await waitFor(() => {
      expect(screen.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');
    });
  });

  it('schedules the chosen route, format and cadence for the people named', async () => {
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');
    });
    fireEvent.click(screen.getAllByTestId('schedule-view-route')[1] as HTMLElement);
    fireEvent.click(screen.getByTestId('schedule-view-format-csv'));
    fireEvent.change(screen.getByTestId('schedule-view-cadence'), {
      target: { value: 'MONTH_CLOSE' },
    });
    fireEvent.change(screen.getByTestId('schedule-view-recipients'), {
      target: { value: 'dev@example.local, ops@example.local dev@example.local' },
    });
    fireEvent.click(screen.getByTestId('schedule-view-submit'));

    expect(await screen.findByTestId('schedule-view-made')).toHaveTextContent('Scheduled.');
    expect(screen.getByRole('link', { name: 'Scheduled' })).toHaveAttribute(
      'href',
      '/report/scheduled',
    );
    expect(posted).toEqual(['/api/v1/reports/schedules']);
    expect(postedBodies).toEqual([
      {
        view_id: 'v-1',
        export_path: '/api/v1/org/tree',
        format: 'csv',
        cadence: 'MONTH_CLOSE',
        recipients: ['dev@example.local', 'ops@example.local'],
      },
    ]);
  });

  it('cannot schedule a screen that exports nothing, or for nobody', async () => {
    const { unmount } = renderPanel({ views: [] });
    expect(screen.getByTestId('schedule-view-nothing')).toBeInTheDocument();
    expect(screen.getByTestId('schedule-view-submit')).toBeDisabled();
    unmount();
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');
    });
    fireEvent.change(screen.getByTestId('schedule-view-recipients'), {
      target: { value: ' , ' },
    });
    expect(screen.getByTestId('schedule-view-submit')).toBeDisabled();
  });

  it('says a refusal in the words the API gave', async () => {
    const said = 'This is not a route a screen exports.';
    renderPanel({ failure: new ApiError(422, JSON.stringify({ detail: said })) });
    await waitFor(() => {
      expect(screen.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');
    });
    fireEvent.click(screen.getByTestId('schedule-view-submit'));
    expect(await screen.findByTestId('schedule-view-failure')).toHaveTextContent(said);
    expect(screen.queryByTestId('schedule-view-made')).toBeNull();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('schedule-view-recipients')).toHaveValue('dev@example.local');
    });
    expect(await violationsIn(container)).toEqual([]);
  });
});
