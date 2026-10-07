import { useMemo, useState, type ReactNode } from 'react';

import { useApi } from '../api/apiContext';
import { reasonOf } from '../api/client';
import {
  runFilePath,
  useChangeSchedule,
  useDeleteSchedule,
  useReportRuns,
  useSchedules,
} from '../api/queries';
import type { ApiReportRun, ApiSchedule } from '../api/types';
import { DataTable } from '../components/DataTable';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { saveFile } from '../shell/saveFile';
import { changedAt } from './libraryModel';
import { cadenceWords, formatWords, listState, routeTitle, statusWords } from './scheduleModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Scheduled reports. FEAT-069, TASK-P8-011.
 *
 * The reader's schedules, and the reports made for them: files they exported, and files
 * schedules rendered for them, each made within their own access. A schedule is made from a
 * saved view's own screen, where the routes it reads are known, so this screen pauses, resumes
 * and deletes; it does not make one. A kept file is fetched through a route that checks the
 * reader's access again, and how long files are kept, and where they are sent, are said in the
 * server's own words, because both wait on decisions, OPEN-15 and OPEN-11.
 */

function scheduleColumns(
  actions: (schedule: ApiSchedule) => ReactNode,
): readonly Column<ApiSchedule>[] {
  return [
    {
      key: 'view',
      header: 'View',
      rowHeader: true,
      render: (schedule) => schedule.view_name ?? 'A view you can no longer open',
      sortValue: (schedule) => schedule.view_name ?? '',
    },
    {
      key: 'what',
      header: 'What it sends',
      render: (schedule) => routeTitle(schedule.export_path),
      sortValue: (schedule) => routeTitle(schedule.export_path),
    },
    {
      key: 'format',
      header: 'Format',
      render: (schedule) => formatWords(schedule.format),
      sortValue: (schedule) => schedule.format,
    },
    {
      key: 'cadence',
      header: 'How often',
      render: (schedule) => cadenceWords(schedule.cadence),
      sortValue: (schedule) => schedule.cadence,
    },
    {
      key: 'recipients',
      header: 'For whom',
      render: (schedule) => schedule.recipients.join(', '),
      sortValue: (schedule) => schedule.recipients.join(', '),
    },
    {
      key: 'next',
      header: 'Next run',
      render: (schedule) =>
        schedule.enabled ? (
          <time dateTime={schedule.next_run_at}>{changedAt(schedule.next_run_at)}</time>
        ) : (
          'Paused'
        ),
      sortValue: (schedule) => (schedule.enabled ? schedule.next_run_at : null),
    },
    { key: 'actions', header: 'Actions', render: actions },
  ];
}

function runColumns(
  download: (run: ApiReportRun) => ReactNode,
): readonly Column<ApiReportRun>[] {
  return [
    {
      key: 'what',
      header: 'What',
      rowHeader: true,
      render: (run) => routeTitle(run.view_path),
      sortValue: (run) => routeTitle(run.view_path),
    },
    {
      key: 'made',
      header: 'Made',
      render: (run) => <time dateTime={run.made_at}>{changedAt(run.made_at)}</time>,
      sortValue: (run) => run.made_at,
    },
    {
      key: 'format',
      header: 'Format',
      render: (run) => formatWords(run.format),
      sortValue: (run) => run.format,
    },
    {
      key: 'status',
      header: 'What became of it',
      prose: true,
      render: (run) => (
        <span data-testid="run-status">
          {statusWords(run)}
          {run.failure_detail === null ? null : <span>. {run.failure_detail}</span>}
        </span>
      ),
      sortValue: (run) => statusWords(run),
    },
    {
      key: 'rows',
      header: 'Rows',
      numeric: true,
      render: (run) => run.rows,
      sortValue: (run) => run.rows,
    },
    { key: 'file', header: 'File', render: download },
  ];
}

export function ScheduledReportsScreen() {
  const client = useApi();
  const schedulesQuery = useSchedules();
  const runsQuery = useReportRuns();
  const change = useChangeSchedule();
  const remove = useDeleteSchedule();
  const scheduled = schedulesQuery.data;
  const made = runsQuery.data;
  const schedules = useMemo(() => scheduled?.data.schedules ?? [], [scheduled]);
  const runs = useMemo(() => made?.data ?? [], [made]);
  useReportMeta('report-schedules', scheduled?.meta);

  const [deleting, setDeleting] = useState<ApiSchedule | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [fetching, setFetching] = useState<string | null>(null);
  const busy = change.isPending || remove.isPending;

  function begin(): void {
    setNotice(null);
    setFailure(null);
  }

  function failed(error: unknown): void {
    setFailure(reasonOf(error));
  }

  function toggle(schedule: ApiSchedule): void {
    begin();
    change.mutate(
      { scheduleId: schedule.schedule_id, change: { enabled: !schedule.enabled } },
      {
        onSuccess: (changed) => {
          setNotice(
            changed.data.enabled
              ? `Resumed. It runs next on ${changedAt(changed.data.next_run_at)}.`
              : 'Paused. Nothing runs until it is resumed.',
          );
        },
        onError: failed,
      },
    );
  }

  function destroy(schedule: ApiSchedule): void {
    begin();
    remove.mutate(schedule.schedule_id, {
      onSuccess: () => {
        setDeleting(null);
        setNotice(
          'Deleted. The reports it already made stay with the people they were made for.',
        );
      },
      onError: failed,
    });
  }

  async function fetchFile(run: ApiReportRun): Promise<void> {
    begin();
    setFetching(run.run_id);
    try {
      const file = await client.getFile(runFilePath(run.run_id));
      if (!saveFile(file.name, file.body)) {
        setFailure('This browser cannot save a file a page made. Ask the API for it directly.');
      }
    } catch (error) {
      failed(error);
    } finally {
      setFetching(null);
    }
  }

  const actions = (schedule: ApiSchedule) => (
    <div
      role="group"
      aria-label={`Schedule of ${schedule.view_name ?? 'a view'}, actions`}
      data-testid="scheduled-actions"
    >
      <button
        type="button"
        data-testid="scheduled-toggle"
        disabled={busy}
        onClick={() => {
          toggle(schedule);
        }}
      >
        {schedule.enabled ? 'Pause' : 'Resume'}
      </button>
      <button
        type="button"
        data-testid="scheduled-delete-start"
        disabled={busy}
        onClick={() => {
          begin();
          setDeleting(schedule);
        }}
      >
        Delete
      </button>
    </div>
  );

  const download = (run: ApiReportRun) =>
    run.has_file ? (
      <button
        type="button"
        data-testid="run-download"
        disabled={fetching !== null}
        onClick={() => {
          void fetchFile(run);
        }}
      >
        {fetching === run.run_id ? 'Fetching' : 'Download'}
      </button>
    ) : (
      'None kept'
    );

  const scheduleState = listState(
    surfaceStateFor(
      schedulesQuery,
      scheduled?.meta,
      schedules.length,
      'none',
      'report_schedules',
    ),
  );
  const runState = listState(
    surfaceStateFor(runsQuery, made?.meta, runs.length, 'none', 'report_schedules'),
  );
  const runCoverage = made?.meta.scope_coverage;

  return (
    <section aria-label="Scheduled">
      {scheduled === undefined ? null : (
        <div data-testid="scheduled-terms">
          {scheduled.data.rendering ? null : (
            <p data-testid="scheduled-off" className="meter-failure">
              This deployment renders no scheduled reports, because no bucket is configured to
              keep them in.
            </p>
          )}
          <p data-testid="scheduled-delivery">{scheduled.data.delivery}</p>
          <p data-testid="scheduled-retention">{scheduled.data.retention}</p>
        </div>
      )}
      {deleting === null ? null : (
        <div role="group" aria-label="Delete a schedule" data-testid="scheduled-delete">
          <p>
            Delete the schedule of {deleting.view_name ?? 'this view'}? Nothing runs again, and
            the reports it already made stay with the people they were made for.
          </p>
          <button
            type="button"
            data-testid="scheduled-delete-confirm"
            disabled={busy}
            onClick={() => {
              destroy(deleting);
            }}
          >
            Delete
          </button>
          <button
            type="button"
            data-testid="scheduled-delete-cancel"
            onClick={() => {
              setDeleting(null);
            }}
          >
            Keep it
          </button>
        </div>
      )}
      {notice === null ? null : (
        <p role="status" data-testid="scheduled-notice">
          {notice}
        </p>
      )}
      {failure === null ? null : (
        <p role="alert" data-testid="scheduled-failure" className="meter-failure">
          {failure}
        </p>
      )}

      <h2>Your schedules</h2>
      {scheduleState.kind === 'empty' ? (
        <p data-testid="scheduled-empty">
          No schedules yet. Open a saved view from the Report Library with Schedule, and choose
          what it sends and how often.
        </p>
      ) : (
        <StateBoundary state={scheduleState}>
          <DataTable
            rows={schedules}
            columns={scheduleColumns(actions)}
            rowKey={(schedule) => schedule.schedule_id}
            caption={`${String(schedules.length)} schedules, the latest changed first`}
            captionTestId="scheduled-caption"
            rowAttributes={(schedule) => ({
              'data-testid': 'scheduled-row',
              'data-enabled': String(schedule.enabled),
            })}
          />
        </StateBoundary>
      )}

      <h2>Reports made for you</h2>
      {runState.kind === 'empty' ? (
        <p data-testid="runs-empty">
          Nothing yet. A report a schedule makes for you, and a file you export, are listed
          here.
        </p>
      ) : (
        <StateBoundary state={runState}>
          <DataTable
            rows={runs}
            columns={runColumns(download)}
            rowKey={(run) => run.run_id}
            initialSort={{ key: 'made', direction: 'descending' }}
            caption={
              runCoverage?.is_partial === true
                ? `The latest ${String(runCoverage.visible)} of ${String(runCoverage.total)} reports`
                : `${String(runs.length)} reports, the latest made first`
            }
            captionTestId="runs-caption"
            rowAttributes={(run) => ({ 'data-testid': 'run-row', 'data-status': run.status })}
          />
        </StateBoundary>
      )}
    </section>
  );
}
