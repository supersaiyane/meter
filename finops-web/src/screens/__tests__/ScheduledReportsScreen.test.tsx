import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient, type DownloadedFile } from '../../api/client';
import type { ApiReportRun, ApiSchedule, ApiSchedules } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { ScheduledReportsScreen } from '../ScheduledReportsScreen';
import { Harness } from './Harness';
import { changed, clientReturning, metaOf } from './fixtures';
import { sortEveryColumn } from './sortEveryColumn';

/** Scheduled reports: pause, resume and delete, and the reports made for the reader. FEAT-069. */

const SCHEDULES = '/api/v1/reports/schedules';
const RUNS = '/api/v1/reports/runs';

function schedule(overrides: Partial<ApiSchedule> = {}): ApiSchedule {
  return {
    schedule_id: 's-1',
    view_id: 'v-1',
    view_name: 'Active accounts',
    screen_path: '/inventory/accounts',
    export_path: '/api/v1/accounts?status=ACTIVE',
    format: 'xlsx',
    cadence: 'WEEKLY',
    recipients: ['dev@example.local', 'ops@example.local'],
    enabled: true,
    next_run_at: '2026-10-12T06:00:00Z',
    created_at: '2026-10-07T09:00:00Z',
    updated_at: '2026-10-07T09:00:00Z',
    ...overrides,
  };
}

function run(overrides: Partial<ApiReportRun> = {}): ApiReportRun {
  return {
    run_id: 'r-1',
    schedule_id: 's-1',
    view_path: '/api/v1/accounts',
    view_query: 'status=ACTIVE',
    format: 'xlsx',
    status: 'RENDERED',
    rows: 2,
    bytes: 1200,
    truncated: false,
    failure_cause: null,
    failure_detail: null,
    has_file: true,
    made_at: '2026-10-05T06:00:00Z',
    finished_at: '2026-10-05T06:00:02Z',
    as_of: '2026-10-05T04:00:00Z',
    collected_at: '2026-10-05T05:00:00Z',
    ...overrides,
  };
}

const PAUSED = schedule({
  schedule_id: 's-2',
  view_name: null,
  enabled: false,
  cadence: 'DAILY',
});
const RUN_ROWS = [
  run(),
  run({
    run_id: 'r-2',
    status: 'FAILED',
    failure_cause: 'AccessDenied',
    failure_detail: 'this person reaches no account',
    has_file: false,
    rows: 0,
    made_at: '2026-10-06T06:00:00Z',
  }),
  run({ run_id: 'r-3', schedule_id: null, status: 'STREAMED', has_file: false }),
];

interface Options {
  readonly schedules?: readonly ApiSchedule[];
  readonly runs?: readonly ApiReportRun[];
  readonly rendering?: boolean;
  readonly failure?: Error;
  readonly fileFailure?: Error;
}

function renderScreen(options: Options = {}) {
  const { schedules = [schedule(), PAUSED], runs = RUN_ROWS, rendering = true } = options;
  const listed: ApiSchedules = {
    rendering,
    retention: 'Files are kept until a retention period is decided, OPEN-15.',
    delivery: 'Nothing is sent yet: where reports go is OPEN-11.',
    schedules,
  };
  const asked: string[] = [];
  const base = clientReturning(
    {
      [SCHEDULES]: {
        data: listed,
        meta: metaOf({
          scope_coverage: {
            visible: schedules.length,
            total: schedules.length,
            is_partial: false,
            unit: 'schedules',
          },
        }),
      },
      [RUNS]: { data: runs, meta: metaOf() },
      [`${SCHEDULES}/s-1`]: { data: schedule({ enabled: false }), meta: metaOf() },
      [`${SCHEDULES}/s-2`]: { data: { ...PAUSED, enabled: true }, meta: metaOf() },
    },
    options.failure,
  );
  const client: ApiClient = {
    ...base,
    getFile: (path: string): Promise<DownloadedFile> => {
      asked.push(path);
      if (options.fileFailure !== undefined) return Promise.reject(options.fileFailure);
      return Promise.resolve({
        name: 'meter-accounts-2026-10-05.xlsx',
        body: new Blob(['cells']),
      });
    },
  };
  return {
    asked,
    ...render(
      <Harness client={client} initialPath="/report/scheduled">
        <ScheduledReportsScreen />
      </Harness>,
    ),
  };
}

function rowOf(name: string): HTMLElement {
  const row = screen.getByRole('rowheader', { name }).closest('tr');
  if (row === null) throw new Error(`no row for ${name}`);
  return row;
}

beforeEach(() => {
  changed.length = 0;
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:meter'),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('your schedules', () => {
  it('lists each schedule in words, and says what the deployment does with what they make', async () => {
    renderScreen();
    await screen.findByRole('rowheader', { name: 'Active accounts' });
    const active = within(rowOf('Active accounts'));
    for (const said of [
      'Accounts',
      'Excel workbook',
      'Weekly',
      'dev@example.local, ops@example.local',
      '2026-10-12 06:00 UTC',
    ]) {
      expect(active.getByText(said)).toBeInTheDocument();
    }
    const paused = within(rowOf('A view you can no longer open'));
    expect(paused.getByText('Paused')).toBeInTheDocument();
    expect(paused.getByTestId('scheduled-toggle')).toHaveTextContent('Resume');
    expect(screen.getByTestId('scheduled-delivery')).toHaveTextContent('OPEN-11');
    expect(screen.getByTestId('scheduled-retention')).toHaveTextContent('OPEN-15');
    expect(screen.queryByTestId('scheduled-off')).toBeNull();
  });

  it('says plainly when the deployment renders nothing', async () => {
    renderScreen({ rendering: false });
    expect(await screen.findByTestId('scheduled-off')).toHaveTextContent(
      'renders no scheduled reports',
    );
  });

  it('pauses a schedule and resumes another', async () => {
    renderScreen();
    await screen.findByRole('rowheader', { name: 'Active accounts' });
    fireEvent.click(within(rowOf('Active accounts')).getByTestId('scheduled-toggle'));
    expect(await screen.findByTestId('scheduled-notice')).toHaveTextContent('Paused.');
    fireEvent.click(
      within(rowOf('A view you can no longer open')).getByTestId('scheduled-toggle'),
    );
    await waitFor(() => {
      expect(screen.getByTestId('scheduled-notice')).toHaveTextContent(
        'Resumed. It runs next on',
      );
    });
    expect(changed).toEqual([
      { method: 'PATCH', path: `${SCHEDULES}/s-1`, body: { enabled: false } },
      { method: 'PATCH', path: `${SCHEDULES}/s-2`, body: { enabled: true } },
    ]);
  });

  it('asks before deleting, and keeping it deletes nothing', async () => {
    renderScreen();
    await screen.findByRole('rowheader', { name: 'Active accounts' });
    fireEvent.click(within(rowOf('Active accounts')).getByTestId('scheduled-delete-start'));
    expect(screen.getByTestId('scheduled-delete')).toHaveTextContent('stay with the people');
    fireEvent.click(screen.getByTestId('scheduled-delete-cancel'));
    expect(changed).toEqual([]);
    fireEvent.click(within(rowOf('Active accounts')).getByTestId('scheduled-delete-start'));
    fireEvent.click(screen.getByTestId('scheduled-delete-confirm'));
    expect(await screen.findByTestId('scheduled-notice')).toHaveTextContent('Deleted.');
    expect(changed).toEqual([{ method: 'DELETE', path: `${SCHEDULES}/s-1`, body: undefined }]);
  });

  it('says how to make a schedule when there is none', async () => {
    renderScreen({ schedules: [] });
    expect(await screen.findByTestId('scheduled-empty')).toHaveTextContent('Report Library');
  });
});

describe('reports made for you', () => {
  it('says what became of each run, and offers the kept files', async () => {
    renderScreen();
    const rows = await screen.findAllByTestId('run-row');
    expect(rows.map((row) => row.getAttribute('data-status'))).toEqual([
      'FAILED',
      'RENDERED',
      'STREAMED',
    ]);
    const statuses = screen.getAllByTestId('run-status').map((cell) => cell.textContent);
    expect(statuses).toEqual([
      'Failed: AccessDenied. this person reaches no account',
      'Made and kept, not sent',
      'Exported, downloaded at the time',
    ]);
    expect(screen.getAllByTestId('run-download')).toHaveLength(1);
    expect(screen.getAllByText('None kept')).toHaveLength(2);
  });

  it('fetches a kept file through the route that checks scope again', async () => {
    const { asked } = renderScreen();
    fireEvent.click(await screen.findByTestId('run-download'));
    await waitFor(() => {
      expect(asked).toEqual(['/api/v1/reports/runs/r-1/file']);
    });
    expect(screen.queryByTestId('scheduled-failure')).toBeNull();
  });

  it('says why a file was refused, in the API words', async () => {
    const said = 'Your access has narrowed since this file was made, so it is not handed over.';
    renderScreen({ fileFailure: new ApiError(403, JSON.stringify({ detail: said })) });
    fireEvent.click(await screen.findByTestId('run-download'));
    expect(await screen.findByTestId('scheduled-failure')).toHaveTextContent(said);
  });

  it('says what will appear when nothing has been made', async () => {
    renderScreen({ runs: [] });
    expect(await screen.findByTestId('runs-empty')).toHaveTextContent('Nothing yet');
  });
});

describe('the screen', () => {
  it('fails as a failure, never as an empty list', async () => {
    renderScreen({ failure: new Error('Throttled') });
    await waitFor(() => {
      expect(
        screen.getAllByTestId('state').map((state) => state.getAttribute('data-state')),
      ).toEqual(['failed', 'failed']);
    });
    expect(screen.queryByTestId('scheduled-empty')).toBeNull();
  });

  it('sorts every column it can, both ways', async () => {
    const { container } = renderScreen();
    await screen.findByRole('rowheader', { name: 'Active accounts' });
    await screen.findAllByTestId('run-row');
    expect(sortEveryColumn(container)).toBe(11);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderScreen();
    await screen.findByRole('rowheader', { name: 'Active accounts' });
    await screen.findAllByTestId('run-row');
    expect(await violationsIn(container)).toEqual([]);
  });
});
