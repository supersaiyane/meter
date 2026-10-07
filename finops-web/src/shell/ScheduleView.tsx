import { useEffect, useRef, useState, type SubmitEvent } from 'react';
import { useLocation } from 'react-router';

import { reasonOf } from '../api/client';
import type { ExportView } from '../api/exportViews';
import { useCreateSchedule, useMe } from '../api/queries';
import { scheduleRequested, type ScheduleRequest } from '../api/savedViews';
import type { ReportCadence, ReportFormat } from '../api/types';
import { CADENCES, FORMATS, recipientsOf } from '../screens/scheduleModel';
import { Link } from './links';

/**
 * Schedule, beside Export, on a screen the report library's Schedule opened. FEAT-069.
 *
 * A schedule names a saved view and one route its screen reads, which only the screen knows: the
 * routes it offers for export are the routes it is showing. So scheduling happens here, on the
 * view's own screen, and the panel offers exactly the screen's Export list, opened as the screen
 * arrives. Each run renders the chosen route for each recipient within their own access, so the
 * panel names people and never accounts.
 */

export interface ScheduleViewProps {
  /** The views the screen offers for export, from the shell's registry. */
  readonly views: readonly ExportView[];
}

export function ScheduleView({ views }: ScheduleViewProps) {
  const location = useLocation();
  const asked = scheduleRequested(location.state);
  return asked === null ? null : <Offered key={asked.viewId} asked={asked} views={views} />;
}

function Offered({ asked, views }: { readonly asked: ScheduleRequest } & ScheduleViewProps) {
  const panel = useRef<HTMLDetailsElement>(null);
  const me = useMe();
  const create = useCreateSchedule();
  const [route, setRoute] = useState<string | null>(null);
  const [format, setFormat] = useState<ReportFormat>('xlsx');
  const [cadence, setCadence] = useState<ReportCadence>('WEEKLY');
  const [typed, setTyped] = useState<string | null>(null);
  const [made, setMade] = useState(false);

  // Open as the screen arrives, once: the reader came here to schedule.
  useEffect(() => {
    if (panel.current !== null) {
      panel.current.open = true;
    }
  }, []);

  // The first route until the reader picks one: the registry fills in as the screen loads.
  const chosen = route ?? views[0]?.path ?? null;
  const people = typed ?? me.data?.data.principal_id ?? '';
  const recipients = recipientsOf(people);

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (chosen === null) {
      return;
    }
    setMade(false);
    create.mutate(
      { view_id: asked.viewId, export_path: chosen, format, cadence, recipients },
      {
        onSuccess: () => {
          setMade(true);
        },
      },
    );
  }

  return (
    <details ref={panel} data-testid="schedule-view">
      <summary>Schedule</summary>
      <form data-testid="schedule-view-form" onSubmit={submit}>
        <p data-testid="schedule-view-title">Schedule {asked.name}</p>
        {views.length === 0 ? (
          <p data-testid="schedule-view-nothing">
            This screen offers nothing for export yet, so there is nothing to schedule.
          </p>
        ) : (
          <fieldset>
            <legend>What to send</legend>
            {views.map((view) => (
              <label key={view.path}>
                <input
                  type="radio"
                  name="schedule-route"
                  data-testid="schedule-view-route"
                  value={view.path}
                  checked={chosen === view.path}
                  onChange={() => {
                    setRoute(view.path);
                  }}
                />
                {view.title}
              </label>
            ))}
          </fieldset>
        )}
        <fieldset>
          <legend>Format</legend>
          {FORMATS.map((one) => (
            <label key={one.value}>
              <input
                type="radio"
                name="schedule-format"
                data-testid={`schedule-view-format-${one.value}`}
                checked={format === one.value}
                onChange={() => {
                  setFormat(one.value);
                }}
              />
              {one.label}
            </label>
          ))}
        </fieldset>
        <label>
          How often
          <select
            data-testid="schedule-view-cadence"
            value={cadence}
            onChange={(event) => {
              setCadence(event.target.value as ReportCadence);
            }}
          >
            {CADENCES.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          For whom
          <input
            data-testid="schedule-view-recipients"
            value={people}
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
        </label>
        <p data-testid="schedule-view-note">
          Each person gets their own file, made within their own access, so nobody receives a
          row they could not open.
        </p>
        <button
          type="submit"
          data-testid="schedule-view-submit"
          disabled={create.isPending || chosen === null || recipients.length === 0}
        >
          {create.isPending ? 'Scheduling' : 'Schedule'}
        </button>
        {made ? (
          <p role="status" data-testid="schedule-view-made">
            Scheduled. It is listed under <Link to="/report/scheduled">Scheduled</Link>.
          </p>
        ) : null}
        {create.isError ? (
          <p role="alert" data-testid="schedule-view-failure" className="meter-failure">
            {reasonOf(create.error)}
          </p>
        ) : null}
      </form>
    </details>
  );
}
