import type {
  ApiEnvelope,
  ApiRealizedSavings,
  ApiRecommendations,
  ApiRefusals,
  ApiScores,
} from '../types';
import { meta } from './cost';

/**
 * The P3 surfaces, offline.
 *
 * Each fixture deliberately contains the case its screen exists to render
 * honestly, rather than a tidy row of successes:
 *
 * - a recommendation with no owner, because ISS-021 says an unowned finding is
 *   never fixed and the screen has to say so rather than leave a blank cell
 * - a recommendation whose money is large and whose confidence is low, because
 *   the two are separate facts and the screen must not let a reader read one as
 *   a discount on the other
 * - an INCONCLUSIVE saving with an unobserved usage quantity, because that is
 *   the row a tool normally hides and the one that proves the metric is honest
 * - a score component that could not be computed, because it renders as absent
 *   rather than as nought
 * - an account with no score at all, because nobody assessed it and that is not
 *   the same as assessing it badly
 */

export function recommendationsFixture(): ApiEnvelope<ApiRecommendations> {
  return {
    data: {
      recommendations: [
        {
          recommendation_id: '2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f',
          account_id: 'fake-product-a',
          source: 'METER',
          waste_class: 'RIGHTSIZE_INSTANCE',
          resource_id: 'i-0a1b2c3d4e5f6a7b8',
          region_id: 'eu-west-1',
          estimated_monthly_saving: '412.6400',
          severity: 'HIGH',
          // Large money, low confidence. The pair a blended score would hide.
          confidence: 'LOW',
          observation_days: 15,
          lifecycle: 'OPEN',
          owner: null,
          suggested_owner: 'platform',
          ticket_reference: null,
          rationale:
            'p99 CPU of 11.4 percent against 4 vCPU over 15 days, so 1 vCPU with the ' +
            '30 percent headroom rule. Sized on 15 days, which is one day over the floor',
          reversible: true,
          disturbs_running_work: true,
          is_no_regret: false,
          risk_why:
            'A resize needs a stop and a start, so the workload is interrupted. The instance ' +
            'type can be set back afterwards.',
        },
        {
          recommendation_id: '3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d',
          account_id: 'fake-platform-b',
          source: 'COMPUTE_OPTIMIZER',
          waste_class: 'GRAVITON_CANDIDATE',
          resource_id: 'i-1b2c3d4e5f6a7b8c9',
          region_id: 'eu-west-1',
          estimated_monthly_saving: '188.2000',
          severity: 'MEDIUM',
          confidence: 'HIGH',
          observation_days: 45,
          lifecycle: 'ACCEPTED',
          owner: 'platform@example.local',
          suggested_owner: null,
          ticket_reference: 'FAKE-1042',
          rationale:
            'm5.xlarge on x86 with no architecture specific workload detected over 45 days. ' +
            'The equivalent m6g.xlarge is 20 percent cheaper per hour',
          reversible: true,
          disturbs_running_work: true,
          is_no_regret: false,
          risk_why:
            'A different processor architecture, so every binary on the instance has to run on ' +
            'arm64. Reversible, and the most likely finding on this list to fail in a way the ' +
            'bill cannot see.',
        },
        {
          recommendation_id: '4b5c6d7e-8f90-4b1c-8d2e-3f4a5b6c7d8e',
          account_id: 'fake-platform-b',
          source: 'METER',
          waste_class: 'EBS_UNATTACHED',
          resource_id: 'vol-2c3d4e5f6a7b8c9d0',
          region_id: 'eu-west-2',
          estimated_monthly_saving: '64.0000',
          severity: 'LOW',
          confidence: 'HIGH',
          observation_days: 92,
          lifecycle: 'DONE',
          owner: 'storage@example.local',
          suggested_owner: null,
          ticket_reference: 'FAKE-1019',
          rationale:
            '800 GiB gp3 volume attached to nothing for 92 days. The saving is the whole cost',
          reversible: false,
          disturbs_running_work: false,
          is_no_regret: false,
          risk_why:
            'Deleting a volume is final. It is attached to nothing, so nothing stops, and ' +
            'nothing gets the data back either. It reads as safe because of the first half.',
        },
        {
          // The no regret case, and the reason this fixture gained an entry. An alarm that
          // has never left insufficient data has never fired, so deleting it removes no
          // coverage that ever existed, and it can be recreated from its own definition.
          // Small money deliberately: the group's claim is that these are easy, not big.
          recommendation_id: '7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d',
          account_id: 'fake-platform-a',
          source: 'METER',
          waste_class: 'ALARM_INSUFFICIENT_DATA',
          resource_id: 'fake-orphaned-queue-depth',
          region_id: 'eu-west-1',
          estimated_monthly_saving: '0.1000',
          severity: 'LOW',
          confidence: 'HIGH',
          observation_days: 243,
          lifecycle: 'OPEN',
          owner: null,
          suggested_owner: null,
          ticket_reference: null,
          rationale:
            'In the insufficient data state since 2026-01-26, 243 days, so it has never evaluated. ' +
            'The queue it watches no longer exists',
          reversible: true,
          disturbs_running_work: false,
          is_no_regret: true,
          risk_why:
            'An alarm can be recreated from its own definition, and one that has never left ' +
            'insufficient data has never fired. Deleting it removes no coverage that existed.',
        },
      ],
      unowned: 2,
    },
    meta: meta(6),
  };
}

export function realizedSavingsFixture(): ApiEnvelope<ApiRealizedSavings> {
  return {
    data: {
      savings: [
        {
          recommendation_id: '4b5c6d7e-8f90-4b1c-8d2e-3f4a5b6c7d8e',
          cost_before: '192.0000',
          cost_after: '0.0000',
          usage_before: '24000.0000',
          usage_after: '0.0000',
          verdict: 'VERIFIED',
          why:
            '2026-05-24 to 2026-06-23 cost 192.00, 2026-07-23 to 2026-08-22 cost 0.00, ' +
            'a fall of 192.00 at 100.0 percent, and usage moved from 24000.0000 to 0.0000, ' +
            'a change of 100.0 percent. Cost fell at least as fast as usage, so the resource ' +
            'is cheaper per unit of work',
          window_before_start: '2026-05-24',
          window_after_end: '2026-08-22',
        },
        {
          recommendation_id: '3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d',
          cost_before: '540.0000',
          cost_after: '324.0000',
          // Unobserved, not zero. The row that proves the metric is honest.
          usage_before: null,
          usage_after: null,
          verdict: 'INCONCLUSIVE',
          why:
            '2026-05-24 to 2026-06-23 cost 540.00, 2026-07-23 to 2026-08-22 cost 324.00, ' +
            'a fall of 40.0 percent. The billing rows carry no usage quantity for this ' +
            'resource, so there is no control: this cannot be told apart from a workload ' +
            'that shrank on its own. Unobserved, not zero',
          window_before_start: '2026-05-24',
          window_after_end: '2026-08-22',
        },
        {
          recommendation_id: '5c6d7e8f-9012-4c2d-8e3f-4a5b6c7d8e9f',
          cost_before: '310.0000',
          cost_after: '318.0000',
          usage_before: '7440.0000',
          usage_after: '7440.0000',
          verdict: 'REGRESSED',
          why:
            '2026-05-24 to 2026-06-23 cost 310.00, 2026-07-23 to 2026-08-22 cost 318.00. ' +
            'Cost did not fall, so whatever was done either did not take effect or did ' +
            'not persist',
          window_before_start: '2026-05-24',
          window_after_end: '2026-08-22',
        },
      ],
      by_verdict: {
        VERIFIED: { count: 1, realized_monthly: '192.0000' },
        INCONCLUSIVE: { count: 1, realized_monthly: '216.0000' },
        REGRESSED: { count: 1, realized_monthly: '-8.0000' },
      },
    },
    meta: meta(7),
  };
}

export function scoresFixture(): ApiEnvelope<ApiScores> {
  return {
    data: {
      scores: [
        {
          account_id: 'fake-product-a',
          total: 54,
          available_weight: 85,
          why:
            '54 out of 100, from 3 of 4 components carrying 85 of 100 weight. Not computed, ' +
            'and excluded rather than scored as nought: verification',
          components: [
            {
              name: 'waste',
              points: '22.400',
              weight: 40,
              why:
                '412.64 of identified monthly saving against 9380.00 of spend, 4.4 percent, ' +
                'against a ceiling of 20.0 percent',
              findings: ['2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'],
            },
            {
              name: 'coverage',
              points: '20.000',
              weight: 20,
              why: '1 of 1 accounts had enough observation to judge, 100.0 percent',
              findings: [],
            },
            {
              name: 'responsiveness',
              points: '0.000',
              weight: 25,
              why:
                '0.0 percent of the identified money is owned or in progress. 1 of 1 findings ' +
                'are open with no owner, and an unowned finding is never fixed',
              findings: ['2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f'],
            },
            {
              // Excluded, not nought. Rendering this as zero would report the
              // worst possible posture for a dimension nobody measured.
              name: 'verification',
              points: null,
              weight: 15,
              why:
                'Nothing has been verified either way. 0 verdicts are inconclusive, which ' +
                'says nothing about posture rather than something bad about it',
              findings: [],
            },
          ],
          as_of: '2026-09-21T06:00:00+00:00',
        },
        {
          account_id: 'fake-platform-b',
          total: 78,
          available_weight: 100,
          why:
            '78 out of 100, from 4 of 4 components carrying 100 of 100 weight. Every ' +
            'component was computable',
          components: [
            {
              name: 'waste',
              points: '30.800',
              weight: 40,
              why:
                '252.20 of identified monthly saving against 5480.00 of spend, 4.6 percent, ' +
                'against a ceiling of 20.0 percent',
              findings: [
                '3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d',
                '4b5c6d7e-8f90-4b1c-8d2e-3f4a5b6c7d8e',
              ],
            },
            {
              name: 'coverage',
              points: '20.000',
              weight: 20,
              why: '1 of 1 accounts had enough observation to judge, 100.0 percent',
              findings: [],
            },
            {
              name: 'responsiveness',
              points: '25.000',
              weight: 25,
              why:
                '100.0 percent of the identified money is owned or in progress. 0 of 2 ' +
                'findings are open with no owner, and an unowned finding is never fixed',
              findings: [],
            },
            {
              name: 'verification',
              points: '7.500',
              weight: 15,
              why:
                '1 of 2 completed changes were confirmed in the bill, 50.0 percent. 1 more ' +
                'were inconclusive and are excluded rather than counted against',
              findings: ['5c6d7e8f-9012-4c2d-8e3f-4a5b6c7d8e9f'],
            },
          ],
          as_of: '2026-09-21T06:00:00+00:00',
        },
      ],
      // Assessed by nobody, which is why it carries no number rather than a bad one.
      unscored: ['fake-sandbox-c'],
    },
    meta: meta(8),
  };
}

/**
 * What Meter looked at and declined to recommend. FEAT-062, ADR-0027.
 *
 * Four refusals across two rules, because the point of the surface is that a reader can see
 * which question was asked. Two of them rest on ninety days and one on four, so the ordering
 * the screen uses has something to order: a judgement made over four days is the one worth
 * questioning first, and it cannot be ranked by money because a refusal has none.
 */
export function refusalsFixture(): ApiEnvelope<ApiRefusals> {
  return {
    data: {
      refusals: [
        {
          resource_id: 'i-young',
          account_id: 'fake-platform-a',
          region_id: 'us-fake-1',
          waste_class: 'IDLE_INSTANCE',
          reason: '4 days is under the 14 day floor',
          observation_days: 4,
        },
        {
          resource_id: 'i-theirs',
          account_id: 'fake-product-b',
          region_id: 'eu-fake-1',
          waste_class: 'RIGHTSIZE_INSTANCE',
          reason: 'p99 of 91.0 percent leaves no room to shrink',
          observation_days: 60,
        },
        {
          resource_id: 'i-busy',
          account_id: 'fake-platform-a',
          region_id: 'us-fake-1',
          waste_class: 'RIGHTSIZE_INSTANCE',
          reason: 'p99 of 87.3 percent leaves no room to shrink',
          observation_days: 90,
        },
        {
          resource_id: 'i-memory-bound',
          account_id: 'fake-platform-a',
          region_id: 'us-fake-1',
          waste_class: 'RIGHTSIZE_INSTANCE',
          reason:
            '94 percent memory ceiling, so this is memory bound and a CPU rule must not shrink it',
          observation_days: 90,
        },
      ],
      examined: 4,
    },
    meta: {
      as_of: '2026-09-21T06:00:00Z',
      collected_at: '2026-09-21T06:05:00Z',
      scope_coverage: { visible: 4, total: 5, is_partial: true, unit: 'accounts' },
      degraded: false,
      failures: [],
    },
  };
}
