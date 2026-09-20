import { describe, expect, it } from 'vitest';

import { countdown, minutesUntil, stampUtc } from '../enforcementTime';

describe('stampUtc', () => {
  it('carries the date, so an old control does not read as a recent one', () => {
    expect(stampUtc('2026-09-06T09:45:00Z')).toBe('2026-09-06 09:45 UTC');
  });

  it('renders in UTC regardless of where the reader is', () => {
    // The test machine is not on UTC. A local time formatter would pass a test
    // written in London and fail the same test in Mumbai.
    expect(stampUtc('2026-09-06T23:30:00Z')).toBe('2026-09-06 23:30 UTC');
  });
});

describe('countdown', () => {
  const now = new Date('2026-09-06T10:00:00Z');

  it('reads in minutes under an hour', () => {
    expect(countdown('2026-09-06T10:45:00Z', now)).toBe('in 45 min');
  });

  it('reads in hours and minutes beyond one', () => {
    expect(countdown('2026-09-07T00:30:00Z', now)).toBe('in 14 h 30 min');
  });

  it('says expired rather than counting backwards', () => {
    expect(countdown('2026-09-06T09:00:00Z', now)).toBe('expired');
  });

  it('counts whole minutes remaining', () => {
    expect(minutesUntil('2026-09-06T10:45:00Z', now)).toBe(45);
  });
});
