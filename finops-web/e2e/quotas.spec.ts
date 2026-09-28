import { expect, test, type Page } from '@playwright/test';

/**
 * The quota surface, end to end. TASK-P5-008.
 *
 * The arc a person walks: open the quotas screen, find that most of them cannot be measured at
 * all, follow the fullest one to its page, read the increase Meter would ask for, and see that
 * Meter will not ask for it. Then find the request somebody already made outside Meter and what
 * became of it.
 *
 * Three things are asserted here that no unit test can reach, because they are about the built
 * bundle rather than the test renderer:
 *
 * 1. The second list survives the build. A quota with no usage figure arrives as a row in a
 *    separate table, with a reason, and never as a zero.
 * 2. The sentence saying Meter will not submit the request is on the page a person reaches by
 *    clicking, not on one they would have to go looking for.
 * 3. The API name Meter does not call appears nowhere in the rendered document.
 *
 * The routes are stubbed, for the reason `cost.spec.ts` gives: a failed route does not fall
 * back to a fixture, it raises and the screen renders the typed cause, so a journey against a
 * dead API would be testing the failure state. The backend has its own suite.
 */

const META = {
  as_of: '2026-09-28T06:00:00Z',
  collected_at: '2026-09-28T06:05:00Z',
  scope_coverage: { visible: 3, total: 7, is_partial: true, unit: 'quotas' },
  degraded: true,
  failures: [],
};

const MINE = '111122223333';
const THEIRS = '444455556666';
const REGION = 'eu-west-1';

const TIGHTEST = {
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
};

const UNMEASURED = {
  account_id: MINE,
  region_id: REGION,
  service_code: 'kafka',
  quota_code: 'L-MSK-BROKERS',
  quota_name: 'Brokers per account',
  limit: null,
  reason: 'Service Quotas declares no usage metric for this quota',
  is_adjustable: true,
};

const REQUEST = {
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
};

async function withSession(page: Page): Promise<void> {
  // The session is the token. There is no login screen in P0 and none is faked.
  await page.addInitScript(() => {
    window.localStorage.setItem('meter.token', 'a-session-token');
  });

  await page.route('**/api/v1/governance/quotas', async (route) => {
    await route.fulfill({
      json: {
        data: {
          measurable: [
            TIGHTEST,
            {
              ...TIGHTEST,
              service_code: 'iam',
              quota_code: 'L-FE177D64',
              quota_name: 'Roles per account',
              region_id: null,
              limit: '1000',
              used: '212',
              source: 'SERVICE_API',
              headroom: '0.788',
              is_adjustable: false,
            },
            {
              ...TIGHTEST,
              account_id: THEIRS,
              service_code: 'elasticloadbalancing',
              quota_code: 'L-53DA6B97',
              quota_name: 'Application Load Balancers per Region',
              limit: '50',
              used: '43',
              source: 'TRUSTED_ADVISOR',
              headroom: '0.14',
            },
          ],
          unmeasurable: [
            UNMEASURED,
            {
              ...UNMEASURED,
              service_code: 'rds',
              quota_code: 'L-7B6409FD',
              quota_name: 'DB instances',
              limit: '40',
              reason:
                'Only Trusted Advisor reports usage for this quota, and it could not be read: ' +
                'NotOptedIn: the account has no Business support',
            },
            {
              ...UNMEASURED,
              service_code: 'ec2',
              quota_code: 'L-0EA8095F',
              quota_name: 'AMI sharing quota',
              limit: '500',
            },
            {
              ...UNMEASURED,
              account_id: THEIRS,
              service_code: 'lambda',
              quota_code: 'L-B99A9384',
              quota_name: 'Concurrent executions',
              limit: '1000',
              reason: 'The usage metric AWS publishes for this quota returned no data',
            },
          ],
          measured_count: 3,
          found_count: 7,
        },
        meta: META,
      },
    });
  });

  await page.route('**/api/v1/governance/quotas/requests', async (route) => {
    await route.fulfill({
      json: { data: { requests: [REQUEST], open_count: 0 }, meta: META },
    });
  });

  await page.route('**/api/v1/governance/quotas/ec2/L-1216C47A', async (route) => {
    await route.fulfill({
      json: {
        data: {
          service_code: 'ec2',
          quota_code: 'L-1216C47A',
          quota_name: 'Running On-Demand Standard instances',
          is_adjustable: true,
          measurable: [TIGHTEST],
          unmeasurable: [],
          requests: [],
          history: {},
          drafts: [
            {
              account_id: MINE,
              region_id: REGION,
              current_limit: '320',
              observed_usage: '307',
              suggested_value: '520',
              working:
                'The observed peak is 307 against a limit of 320. Leaving 40 percent headroom ' +
                'above that peak needs 520, rounded up to the nearest 10. Meter does not ' +
                'submit this.',
              console_url:
                'https://eu-west-1.console.aws.amazon.com/servicequotas/home/services/ec2/' +
                'quotas/L-1216C47A',
              cli_command:
                'aws service-quotas request-service-quota-increase --service-code ec2 ' +
                '--quota-code L-1216C47A --desired-value 520 --region eu-west-1',
            },
          ],
          draft_refusals: [],
        },
        meta: META,
      },
    });
  });

  await page.route('**/api/v1/governance/quotas/kafka/L-MSK-BROKERS', async (route) => {
    await route.fulfill({
      json: {
        data: {
          service_code: 'kafka',
          quota_code: 'L-MSK-BROKERS',
          quota_name: 'Brokers per account',
          is_adjustable: true,
          measurable: [],
          unmeasurable: [UNMEASURED],
          requests: [REQUEST],
          history: {
            'request-0002': [
              { status: 'PENDING', changed_at: '2026-08-19T09:00:00Z' },
              { status: 'DENIED', changed_at: '2026-08-26T09:00:00Z' },
            ],
          },
          // No draft: nothing measures this quota, so there is no peak to size a request from.
          drafts: [],
          draft_refusals: [
            {
              account_id: MINE,
              region_id: REGION,
              reason:
                'Nothing measures usage for this quota, so there is no observed peak to size ' +
                'a request from. A suggested value here would be arithmetic over a number ' +
                'nobody has.',
            },
          ],
        },
        meta: META,
      },
    });
  });
}

test('a quota nobody can measure is a row with a reason, never a zero', async ({ page }) => {
  await withSession(page);
  await page.goto('/governance/quotas');

  // The ratio first, because it is what tells a reader the shorter list is not the whole story.
  await expect(page.getByTestId('quotas-ratio')).toContainText('3 of 7');

  const unmeasured = page.getByTestId('quota-unmeasured');
  await expect(unmeasured).toHaveCount(4);

  // Every one says why, and the reasons are not one sentence repeated four times.
  const reasons = await page.getByTestId('quota-reason').allTextContents();
  expect(reasons).toHaveLength(4);
  expect(new Set(reasons).size).toBeGreaterThan(1);

  // And the thing this sub project exists to prevent: no unmeasured row carries a percentage.
  await expect(unmeasured.first().getByTestId('percent-cell')).toHaveCount(0);
});

test('the fullest quota is first and is drawn on the inverted ramp', async ({ page }) => {
  await withSession(page);
  await page.goto('/governance/quotas');

  const first = page.getByTestId('quota-measured').first();
  await expect(first).toContainText('L-1216C47A');
  await expect(first.getByTestId('percent-figure')).toContainText('95.9');
  await expect(first.getByTestId('percent-track')).toHaveAttribute('data-inverted', 'true');
});

test('a quota leads to the increase Meter would ask for and would not submit', async ({
  page,
}) => {
  await withSession(page);
  await page.goto('/governance/quotas');

  await page.getByTestId('quota-measured').first().getByTestId('quota-link').click();
  await expect(page).toHaveURL(/\/governance\/quotas\/ec2\/L-1216C47A$/);

  // The figures, so the suggestion can be checked rather than taken on faith.
  await expect(page.getByTestId('draft-figures')).toContainText('520');
  await expect(page.getByTestId('draft-working')).toContainText('40 percent');

  // The sentence, on the page a person reached by clicking.
  await expect(page.getByTestId('draft-not-submitted')).toContainText('will not submit');

  // Both copyable, and the command is the CLI spelling.
  await expect(page.getByTestId('draft-command')).toContainText(
    'aws service-quotas request-service-quota-increase',
  );
  await expect(page.getByTestId('draft-console')).toHaveAttribute(
    'href',
    /console\.aws\.amazon\.com\/servicequotas/,
  );

  // The API Meter does not call appears nowhere in the rendered document.
  await expect(page.locator('body')).not.toContainText('RequestServiceQuotaIncrease');
});

test('a request made outside Meter is tracked, refusal and all', async ({ page }) => {
  await withSession(page);
  await page.goto('/governance/quotas');

  // The request is for a quota in the unmeasured list, which is the independence TASK-P5-008 is
  // about: the quotas somebody requests blind are exactly the ones with no figure to look at.
  const row = page.getByTestId('quota-request-row');
  await expect(row).toHaveCount(1);
  await expect(row.getByTestId('request-status')).toContainText('denied');

  await row.getByTestId('request-quota-link').click();
  await expect(page).toHaveURL(/\/governance\/quotas\/kafka\/L-MSK-BROKERS$/);

  // When it was denied, not only that it was.
  await expect(page.getByTestId('request-history')).toContainText('2026-08-26');
  await expect(page.getByTestId('request-not-ours')).toContainText('outside Meter');

  // And no draft, because nothing measured the quota. The reason is shown rather than an empty
  // draft, which would read as a feature that failed.
  await expect(page.getByTestId('quota-draft')).toHaveCount(0);
  await expect(page.getByTestId('draft-refused-reason')).toContainText('no observed peak');
});
