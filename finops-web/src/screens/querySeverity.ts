import type { Severity } from '../components/SeverityBadge';
import type { ApiQueryFinding } from '../api/types';

/**
 * The API sends a word, not a number. The mapping is here rather than in the
 * API because the ramp is a rendering decision: the same four levels would be
 * five steps on a different scale, and the badge is what has to be ordered.
 *
 * In its own module because two screens rank the same findings, and a second
 * copy of this table is a second answer to how severe a finding is.
 */
const SEVERITY_LEVEL: Readonly<Record<string, Severity>> = {
  CRITICAL: 5,
  HIGH: 4,
  MEDIUM: 3,
  LOW: 2,
};

export function severityLevel(word: string): Severity {
  // An unrecognised severity reads as informational rather than critical. A
  // vocabulary change should under state a finding, never invent an alarm.
  return SEVERITY_LEVEL[word.toUpperCase()] ?? 1;
}

export function severityOf(finding: ApiQueryFinding): Severity {
  return severityLevel(finding.severity);
}
