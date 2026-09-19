/**
 * Rendering when a control stops.
 *
 * Both forms, always. An incident bridge needs "how long do I have" and "when
 * exactly", and a countdown alone cannot be written into an incident log.
 *
 * UTC, and it says UTC. An absolute time with no zone is not absolute, and this
 * value is read by people in different offices during the same incident.
 *
 * The date is always shown, never just the time. A control applied three days
 * ago rendered as `09:45 UTC` reads as one applied this morning, and the
 * project's own writing rule is absolute dates only for the same reason.
 */

export function stampUtc(iso: string): string {
  const at = new Date(iso);
  const date = at.toISOString().slice(0, 10);
  const hours = String(at.getUTCHours()).padStart(2, '0');
  const minutes = String(at.getUTCMinutes()).padStart(2, '0');
  return `${date} ${hours}:${minutes} UTC`;
}

/** Whole minutes remaining. Negative once the expiry has passed. */
export function minutesUntil(iso: string, now: Date): number {
  return Math.floor((new Date(iso).getTime() - now.getTime()) / 60_000);
}

export function countdown(iso: string, now: Date): string {
  const minutes = minutesUntil(iso, now);
  if (minutes < 0) {
    // Expired is a state, not a negative duration.
    return 'expired';
  }
  if (minutes < 60) {
    return `in ${String(minutes)} min`;
  }
  const hours = Math.floor(minutes / 60);
  return `in ${String(hours)} h ${String(minutes % 60)} min`;
}
