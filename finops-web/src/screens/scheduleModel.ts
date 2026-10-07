import { EXPORT_TITLES } from '../api/exportViews';
import type { ApiReportRun, ReportCadence, ReportFormat } from '../api/types';

/**
 * What the schedule screens say about a schedule and a run. FEAT-069, TASK-P8-011.
 *
 * Kept apart from the components so each sentence is tested on its own and each component's
 * module exports only the component. A cadence is named and its next run is shown as the server
 * computed it, rather than restating here which hour or which day each cadence runs, because a
 * second copy of the server's rule is a rule that one day disagrees with it.
 */

export const CADENCES: readonly { readonly value: ReportCadence; readonly label: string }[] = [
  { value: 'DAILY', label: 'Daily' },
  { value: 'WEEKLY', label: 'Weekly' },
  { value: 'MONTHLY', label: 'Monthly' },
  { value: 'MONTH_CLOSE', label: 'When the month closes' },
];

export const FORMATS: readonly { readonly value: ReportFormat; readonly label: string }[] = [
  { value: 'xlsx', label: 'Excel workbook' },
  { value: 'csv', label: 'CSV' },
];

export function cadenceWords(cadence: ReportCadence): string {
  return CADENCES.find((one) => one.value === cadence)?.label ?? cadence;
}

export function formatWords(format: ReportFormat): string {
  return FORMATS.find((one) => one.value === format)?.label ?? format;
}

/** The view a route exports, by the title the server gives its file, or the route itself. */
export function routeTitle(path: string): string {
  const at = path.indexOf('?');
  const route = at === -1 ? path : path.slice(0, at);
  return EXPORT_TITLES[route] ?? route;
}

/** What became of a run, said from the reader's side. */
export function statusWords(run: Pick<ApiReportRun, 'status' | 'failure_cause'>): string {
  switch (run.status) {
    case 'STREAMED':
      return 'Exported, downloaded at the time';
    case 'RENDERED':
      return 'Made and kept, not sent';
    case 'SENT':
      return 'Sent';
    case 'FAILED':
      return `Failed: ${run.failure_cause ?? 'cause not recorded'}`;
  }
}

/** The people a typed list names: separated by commas, spaces or lines, each once, in order. */
export function recipientsOf(text: string): string[] {
  const people: string[] = [];
  for (const person of text.split(/[\s,;]+/)) {
    if (person !== '' && !people.includes(person)) {
      people.push(person);
    }
  }
  return people;
}
