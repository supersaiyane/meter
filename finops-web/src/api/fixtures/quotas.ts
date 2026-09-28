import type {
  ApiEnvelope,
  ApiMeta,
  ApiQuotaDetail,
  ApiQuotaRequests,
  ApiQuotas,
} from '../types';

/**
 * The P5 surfaces, offline. FEAT-033 and FEAT-034.
 *
 * The routes are live, so `resolveSurface` never reaches these: `/api/v1/governance/quotas`
 * is deliberately absent from `FIXTURE_SURFACES`, and `tests/api/test_fixture_surfaces.py`
 * would fail the build if it were not. They exist as the typed example the screen's own tests
 * render, which is what keeps those tests from inventing a shape the route cannot produce.
 *
 * **The shape here is deliberately unflattering.** Three measured quotas and four unmeasured,
 * roughly the proportion a real estate has, and one of the unmeasured publishes no limit
 * either. A fixture where everything was measured would leave the longer of the two lists
 * rendered by nothing anybody runs, and the longer list is the sub project.
 */

const AS_OF = '2026-09-28T06:00:00Z';
const COLLECTED_AT = '2026-09-28T06:05:00Z';
const MINE = '111122223333';
const THEIRS = '444455556666';
const REGION = 'eu-west-1';

function metaWith(visible: number, total: number, unit: string): ApiMeta {
  return {
    as_of: AS_OF,
    collected_at: COLLECTED_AT,
    scope_coverage: { visible, total, is_partial: visible < total, unit },
    degraded: visible < total,
    failures: [],
  };
}

export function quotasFixture(): ApiEnvelope<ApiQuotas> {
  return {
    data: {
      measurable: [
        {
          // 307 of 320, so the bar is nearly full and this sorts first. The case the screen
          // exists to surface.
          account_id: MINE,
          region_id: REGION,
          service_code: 'ec2',
          quota_code: 'L-1216C47A',
          quota_name: 'Running On-Demand Standard instances',
          limit: '320',
          used: '307',
          source: 'AWS_USAGE_METRIC',
          headroom: '0.040625',
          is_adjustable: true,
        },
        {
          account_id: MINE,
          region_id: REGION,
          service_code: 'elasticloadbalancing',
          quota_code: 'L-53DA6B97',
          quota_name: 'Application Load Balancers per Region',
          limit: '50',
          used: '43',
          // The weakest of the three sources, and the screen names it so a reader can weigh
          // two identical figures differently.
          source: 'TRUSTED_ADVISOR',
          headroom: '0.14',
          is_adjustable: true,
        },
        {
          // Global, so no region, and a hard limit, so no draft can be offered against it.
          account_id: MINE,
          region_id: null,
          service_code: 'iam',
          quota_code: 'L-FE177D64',
          quota_name: 'Roles per account',
          limit: '1000',
          used: '212',
          source: 'SERVICE_API',
          headroom: '0.788',
          is_adjustable: false,
        },
      ],
      unmeasurable: [
        {
          account_id: MINE,
          region_id: REGION,
          service_code: 'ec2',
          quota_code: 'L-0EA8095F',
          quota_name: 'AMI sharing quota',
          limit: '500',
          reason: 'Service Quotas declares no usage metric for this quota',
          is_adjustable: false,
        },
        {
          account_id: MINE,
          region_id: REGION,
          service_code: 'rds',
          quota_code: 'L-7B6409FD',
          quota_name: 'DB instances',
          limit: '40',
          // A gap with a fix, unlike the one above it, which is why the two reasons must not
          // be collapsed into one sentence.
          reason:
            'Only Trusted Advisor reports usage for this quota, and it could not be read: ' +
            'NotOptedIn: the account has no Business support',
          is_adjustable: true,
        },
        {
          // Neither figure published. The row a screen is most likely to render as nought of
          // nought, so it is in the fixture the screen tests render.
          account_id: MINE,
          region_id: REGION,
          service_code: 'kafka',
          quota_code: 'L-MSK-BROKERS',
          quota_name: 'Brokers per account',
          limit: null,
          reason: 'Service Quotas declares no usage metric for this quota',
          is_adjustable: true,
        },
        {
          account_id: THEIRS,
          region_id: REGION,
          service_code: 'lambda',
          quota_code: 'L-B99A9384',
          quota_name: 'Concurrent executions',
          limit: '1000',
          reason: 'The usage metric AWS publishes for this quota returned no data',
          is_adjustable: true,
        },
      ],
      measured_count: 3,
      found_count: 7,
    },
    // Coverage in quotas, not accounts, which is what makes `degraded` true here. An accounts
    // denominator would report this estate as fully covered.
    meta: metaWith(3, 7, 'quotas'),
  };
}

export function quotaRequestsFixture(): ApiEnvelope<ApiQuotaRequests> {
  return {
    data: {
      requests: [
        {
          request_id: 'request-0001',
          account_id: MINE,
          region_id: REGION,
          service_code: 'ec2',
          quota_code: 'L-1216C47A',
          quota_name: 'Running On-Demand Standard instances',
          desired_value: '640',
          status: 'PENDING',
          is_open: true,
          requested_at: '2026-09-18T09:00:00Z',
          last_updated_at: '2026-09-20T09:00:00Z',
          submitted_by_meter: false,
        },
        {
          // Refused, and for a quota nothing can measure. Both halves matter: a fixture where
          // every request was approved would leave the state a reader most needs rendered by
          // nothing, and tracking a quota with no figure is the independence TASK-P5-008 is
          // about.
          request_id: 'request-0002',
          account_id: MINE,
          region_id: REGION,
          service_code: 'kafka',
          quota_code: 'L-MSK-BROKERS',
          quota_name: 'Brokers per account',
          desired_value: '30',
          status: 'DENIED',
          is_open: false,
          requested_at: '2026-08-19T09:00:00Z',
          last_updated_at: '2026-08-26T09:00:00Z',
          submitted_by_meter: false,
        },
      ],
      open_count: 1,
    },
    meta: metaWith(1, 1, 'accounts'),
  };
}

export function quotaDetailFixture(): ApiEnvelope<ApiQuotaDetail> {
  const quotas = quotasFixture().data;
  const requests = quotaRequestsFixture().data;
  const [tightest] = quotas.measurable;
  if (tightest === undefined) {
    throw new Error('the quotas fixture has no measured rows, so a detail cannot be built');
  }
  return {
    data: {
      service_code: tightest.service_code,
      quota_code: tightest.quota_code,
      quota_name: tightest.quota_name,
      is_adjustable: tightest.is_adjustable,
      // The same quota in two accounts, because a quota code is per slice: nearly full in one
      // and comfortable in the other is the case a single row would answer wrongly.
      measurable: [
        tightest,
        { ...tightest, account_id: THEIRS, limit: '64', used: '20', headroom: '0.6875' },
      ],
      unmeasurable: [],
      requests: requests.requests.filter((one) => one.quota_code === tightest.quota_code),
      history: {
        'request-0001': [
          { status: 'PENDING', changed_at: '2026-09-18T09:00:00Z' },
          { status: 'CASE_OPENED', changed_at: '2026-09-20T09:00:00Z' },
        ],
      },
      // One draft and one refusal, so the screen has to render both paths. The refusal is the
      // comfortable slice: asking for more of something an account is not short of wastes a
      // reviewer's time, and a screen that drafted it anyway would look more capable and be
      // less useful.
      drafts: [
        {
          account_id: MINE,
          region_id: REGION,
          current_limit: '320',
          observed_usage: '307',
          suggested_value: '520',
          working:
            'The observed peak is 307 against a limit of 320. Leaving 40 percent headroom ' +
            'above that peak needs 520, rounded up to the nearest 10. Meter does not submit ' +
            'this.',
          console_url:
            'https://eu-west-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/' +
            'L-1216C47A',
          cli_command:
            'aws service-quotas request-service-quota-increase --service-code ec2 ' +
            '--quota-code L-1216C47A --desired-value 520 --region eu-west-1',
        },
      ],
      draft_refusals: [
        {
          account_id: THEIRS,
          region_id: REGION,
          reason:
            'The observed peak already leaves more headroom than a request would ask for, so ' +
            'an increase would be asking for something this account is not short of.',
        },
      ],
    },
    meta: metaWith(2, 2, 'accounts'),
  };
}
