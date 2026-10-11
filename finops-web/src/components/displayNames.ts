/**
 * The words a person reads for the codes the API sends, P8 spec section 5.3, as
 * the owner approved them on 2026-10-05 in
 * `docs/specs/2026-10-05-p8-label-table.md`.
 *
 * No raw identifier reaches a screen. A code this file does not know is still
 * shown, in words, because hiding it would hide the drift, and the test over
 * the rendered text of every screen holds the rest.
 */

import type { ApiOwnerSuggestion } from '../api/types';

type Names = Readonly<Record<string, string>>;

export const WASTE_CLASS_NAMES: Names = {
  RIGHTSIZE_INSTANCE: 'Rightsizing',
  IDLE_INSTANCE: 'Idle instance',
  GRAVITON_CANDIDATE: 'Graviton migration',
  EBS_OVERPROVISIONED: 'Overprovisioned volume',
  EBS_GP2_TO_GP3: 'gp2 to gp3 volume',
  EBS_UNATTACHED: 'Unattached volume',
  SNAPSHOT_AGED: 'Aged snapshot',
  NAT_GATEWAY_IDLE: 'Idle NAT gateway',
  LOAD_BALANCER_IDLE: 'Idle load balancer',
  ELASTIC_IP_UNASSOCIATED: 'Unassociated Elastic IP',
  DYNAMODB_OVERPROVISIONED: 'Overprovisioned DynamoDB capacity',
  LOG_GROUP_NO_RETENTION: 'Log group with no retention',
  LOG_GROUP_UNQUERIED: 'Unqueried log group',
  LOG_DUPLICATE_DELIVERY: 'Duplicate log delivery',
  METRIC_UNQUERIED: 'Unqueried metric',
  ALARM_INSUFFICIENT_DATA: 'Alarm with insufficient data',
  CONTAINER_RIGHTSIZE: 'Kubernetes rightsizing',
  PARKABLE_WINDOW: 'Off hours scheduling',
  COMMITMENT_UNCOVERED: 'Not covered by a commitment',
  UPSIZE_INSTANCE: 'Needs a larger type',
};

export const LIFECYCLE_NAMES: Names = {
  OPEN: 'Open',
  ACCEPTED: 'Accepted',
  IN_PROGRESS: 'In progress',
  DONE: 'Done',
  VERIFIED: 'Verified',
  REGRESSED: 'Regressed',
  DISMISSED: 'Dismissed',
};

export const RECOMMENDATION_SOURCE_NAMES: Names = {
  COMPUTE_OPTIMIZER: 'AWS Compute Optimizer',
  COST_OPTIMIZATION_HUB: 'AWS Cost Optimization Hub',
  TRUSTED_ADVISOR: 'AWS Trusted Advisor',
  METER: 'Meter',
};

export const VERDICT_NAMES: Names = {
  VERIFIED: 'Verified',
  REGRESSED: 'Regressed',
  INCONCLUSIVE: 'Inconclusive',
};

export const RUN_STATUS_NAMES: Names = {
  pending: 'Pending',
  running: 'Running',
  succeeded: 'Succeeded',
  partial: 'Partial',
  failed: 'Failed',
};

/** Both spellings the API sends: coverage rows use one, the gap actions the other. */
export const COMMITMENT_TYPE_NAMES: Names = {
  SavingsPlan: 'Savings Plan',
  ReservedInstance: 'Reserved Instance',
  SAVINGS_PLAN: 'Savings Plan',
  RESERVED_INSTANCE: 'Reserved Instance',
};

/** Keyed by the name each collector declares, which is not always its module's name. */
export const COLLECTOR_NAMES: Names = {
  account_health: 'Account health',
  budgets: 'Budgets',
  commitment: 'Commitments',
  commitment_actions: 'Commitment actions',
  container_usage: 'Kubernetes usage',
  cost_anomaly: 'Cost anomalies',
  cost_focus: 'Cost and usage (FOCUS)',
  finops_score: 'FinOps Score',
  iac_state: 'Infrastructure as code state',
  inventory: 'Resource inventory',
  org_tree: 'Organization',
  partition_maintenance: 'Partition maintenance',
  platform_cost: 'Meter Cost',
  query_audit: 'Query audit',
  query_evidence: 'Query evidence',
  quotas: 'Service quotas',
  realized_savings: 'Realized Savings',
  recommendations: 'Recommendations',
  retention_audit: 'Retention, audit records',
  retention_cost: 'Retention, cost records',
  retention_operational: 'Retention, operational records',
  retention_principal: 'Retention, personal records',
  retention_scope_cache: 'Retention, scope cache',
  team_digests: 'Team digests',
  waste_cloudwatch: 'CloudWatch waste',
  waste_compute: 'Compute waste',
  waste_parking: 'Off hours scheduling',
};

/**
 * The provider's own word for a cost column, shown in its tooltip, because
 * practitioners search for both. Keyed by the column's heading, so a table
 * cannot drop a tooltip by forgetting to ask for one.
 */
export const COST_COLUMN_TERMS: Names = {
  'Effective Cost': 'AWS: amortized cost',
  'Billed Cost': 'AWS: unblended cost',
  'Unused commitment': 'AWS: unused Savings Plan or Reserved Instance commitment',
  'On-Demand cost': 'AWS: On-Demand cost',
  Impact: 'AWS Cost Anomaly Detection: total impact',
  'Actual cost': 'AWS Cost Anomaly Detection: actual spend',
  'Expected cost': 'AWS Cost Anomaly Detection: expected spend',
  'Estimated monthly savings': 'AWS: estimated monthly savings',
};

/** A code nobody named yet, in words: `NEW_THING`, `new_thing` and `NewThing` read "New thing". */
export function inWords(code: string): string {
  const words = code
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function named(names: Names, code: string): string {
  return names[code] ?? inWords(code);
}

export function wasteClassName(code: string): string {
  return named(WASTE_CLASS_NAMES, code);
}

export function lifecycleName(code: string): string {
  return named(LIFECYCLE_NAMES, code);
}

export function recommendationSourceName(code: string): string {
  return named(RECOMMENDATION_SOURCE_NAMES, code);
}

export function verdictName(code: string): string {
  return named(VERDICT_NAMES, code);
}

export function runStatusName(code: string): string {
  return named(RUN_STATUS_NAMES, code);
}

export function commitmentTypeName(code: string): string {
  return named(COMMITMENT_TYPE_NAMES, code);
}

export function collectorName(code: string): string {
  return named(COLLECTOR_NAMES, code);
}

/** One owner suggestion in words: whom, and why its source names them. TASK-P11-005. */
export function suggestionText(one: ApiOwnerSuggestion): string {
  switch (one.source) {
    case 'CATALOGUE':
      return `${one.owner}, the catalogue's ${one.detail} application`;
    case 'TAG':
      return `${one.owner}, its ${one.detail} tag`;
    case 'CREATOR':
      return one.kind === 'AUTOMATION'
        ? `${one.owner}, the pipeline that created it`
        : `${one.owner}, who created it`;
  }
}
