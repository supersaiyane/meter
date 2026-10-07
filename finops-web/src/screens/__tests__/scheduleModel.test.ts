import { describe, expect, it } from 'vitest';

import type { ReportCadence, ReportFormat } from '../../api/types';
import {
  CADENCES,
  FORMATS,
  cadenceWords,
  formatWords,
  recipientsOf,
  routeTitle,
  statusWords,
} from '../scheduleModel';

/** What the schedule screens say about a schedule and a run, FEAT-069. */

describe('the words for a schedule', () => {
  it('names every cadence and every format the API takes, and nothing else', () => {
    expect(CADENCES.map((one) => one.value)).toEqual([
      'DAILY',
      'WEEKLY',
      'MONTHLY',
      'MONTH_CLOSE',
    ]);
    expect(FORMATS.map((one) => one.value)).toEqual(['xlsx', 'csv']);
    expect(cadenceWords('MONTH_CLOSE')).toBe('When the month closes');
    expect(formatWords('xlsx')).toBe('Excel workbook');
  });

  it('falls back to the code for a value it does not know, rather than to nothing', () => {
    expect(cadenceWords('HOURLY' as ReportCadence)).toBe('HOURLY');
    expect(formatWords('pdf' as ReportFormat)).toBe('pdf');
  });

  it('names a route by the title its export carries, query or not', () => {
    expect(routeTitle('/api/v1/accounts?status=ACTIVE')).toBe('Accounts');
    expect(routeTitle('/api/v1/cost/explore')).toBe('Cost Explorer');
    expect(routeTitle('/api/v1/unknown')).toBe('/api/v1/unknown');
  });
});

describe('the words for a run', () => {
  it('says what became of each kind of run', () => {
    expect(statusWords({ status: 'STREAMED', failure_cause: null })).toBe(
      'Exported, downloaded at the time',
    );
    expect(statusWords({ status: 'RENDERED', failure_cause: null })).toBe(
      'Made and kept, not sent',
    );
    expect(statusWords({ status: 'SENT', failure_cause: null })).toBe('Sent');
    expect(statusWords({ status: 'FAILED', failure_cause: 'AccessDenied' })).toBe(
      'Failed: AccessDenied',
    );
    expect(statusWords({ status: 'FAILED', failure_cause: null })).toBe(
      'Failed: cause not recorded',
    );
  });
});

describe('the people a typed list names', () => {
  it('reads commas, spaces and lines, and names each person once, in order', () => {
    expect(recipientsOf(' a@x.example, b@x.example;\nc@x.example a@x.example ')).toEqual([
      'a@x.example',
      'b@x.example',
      'c@x.example',
    ]);
    expect(recipientsOf('  ')).toEqual([]);
  });
});
