import { expect, test, type Page } from '@playwright/test';

import { demoEstate } from './estate';

/**
 * Fixes through pull requests, P15, TASK-P15-008: a payer connects the GitHub App, maps a state to
 * a repository and lets Meter merge gp2 to gp3, a narrowed reader is told why the settings are not
 * theirs, and a person asks for an accepted recommendation's fix and sees it asked for.
 */

const META = {
  as_of: '2026-10-15T10:00:00Z',
  collected_at: '2026-10-15T10:00:00Z',
  scope_coverage: { visible: 1, total: 1, is_partial: false, unit: 'payer' },
  degraded: false,
  failures: [],
};

const ME = {
  principal_id: 'p-owner',
  display_name: 'Owner',
  tenant_id: 't-1',
  tiers: ['finops'],
  accounts_in_scope: 5,
};

const VOLUME = '5c6d7e8f-9a0b-4c1d-8e2f-3a4b5c6d7e8f';

interface Put {
  readonly path: string;
  readonly body: unknown;
}

async function settings(page: Page, isGlobal: boolean): Promise<Put[]> {
  const puts: Put[] = [];
  let connection: Record<string, unknown> = {
    connected: false,
    host: null,
    app_id: null,
    key_secret_name: null,
    connected_by: null,
    connected_at: null,
  };
  let mappings: Record<string, unknown>[] = [];
  let classes: string[] = [];
  let reason: string | null = null;
  await demoEstate(page);
  await page.route('**/api/v1/me', async (route) => {
    await route.fulfill({ json: { data: { ...ME, is_global: isGlobal }, meta: META } });
  });
  await page.route('**/api/v1/remediation/connection', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON() as Record<string, string>;
      puts.push({ path: 'connection', body });
      connection = {
        ...body,
        connected: true,
        connected_by: 'p-owner',
        connected_at: META.as_of,
      };
    }
    await route.fulfill({ json: { data: connection, meta: META } });
  });
  await page.route('**/api/v1/remediation/repositories', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON() as { mappings: Record<string, unknown>[] };
      puts.push({ path: 'repositories', body });
      mappings = body.mappings.map((one) => ({
        ...one,
        set_by: 'p-owner',
        set_at: META.as_of,
      }));
    }
    const mapped = new Set(mappings.map((one) => one.state_reference));
    const unmapped = ['s3://state/storage.tfstate'].filter((one) => !mapped.has(one));
    await route.fulfill({ json: { data: { mappings, unmapped }, meta: META } });
  });
  await page.route('**/api/v1/remediation/merge-policy', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON() as { classes: string[]; reason: string };
      puts.push({ path: 'merge-policy', body });
      classes = body.classes;
      reason = body.reason;
    }
    await route.fulfill({
      json: {
        data: {
          classes,
          reversible: ['EBS_GP2_TO_GP3'],
          reason,
          set_by: reason === null ? null : 'p-owner',
          set_at: reason === null ? null : META.as_of,
          merging_on: true,
        },
        meta: META,
      },
    });
  });
  return puts;
}

test('a payer connects the app, maps a state and lets Meter merge gp2 to gp3', async ({
  page,
}) => {
  const puts = await settings(page, true);
  await page.goto('/platform/fixes');

  await expect(page.getByTestId('fix-not-connected')).toBeVisible();
  const connection = page.getByTestId('fix-connection');
  await connection.getByLabel('App ID').fill('1001');
  await connection
    .getByLabel('The secret holding its private key')
    .fill('meter/dev/codehost/github-app');
  await connection.getByRole('button', { name: 'Connect' }).click();
  await expect(page.getByTestId('fix-connected')).toContainText('GitHub App 1001');

  await expect(page.getByTestId('fix-unmapped')).toContainText('s3://state/storage.tfstate');
  const repositories = page.getByTestId('fix-repositories');
  await repositories.getByLabel('Terraform state').fill('s3://state/storage.tfstate');
  await repositories.getByLabel('Repository, owner/name').fill('acme/infra');
  await repositories.getByLabel('Folder, empty for the root').fill('storage');
  await repositories.getByRole('button', { name: 'Map it' }).click();
  await expect(page.getByTestId('fix-mapping')).toContainText('acme/infra');
  await expect(page.getByTestId('fix-unmapped')).toHaveCount(0);

  const policy = page.getByTestId('fix-merge-policy');
  await expect(page.getByTestId('fix-policy-now')).toContainText('Meter merges nothing');
  await policy.getByLabel('gp2 volumes moved to gp3').check();
  await policy.getByLabel('Why, for the record').fill('reversible, and the checks guard it');
  await policy.getByRole('button', { name: 'Save the policy' }).click();
  await expect(page.getByTestId('fix-policy-now')).toContainText(
    'Meter merges gp2 volumes moved to gp3',
  );

  expect(puts.map((one) => one.path)).toEqual(['connection', 'repositories', 'merge-policy']);
});

test('a narrowed reader is told the settings belong to the organization', async ({ page }) => {
  await settings(page, false);
  await page.goto('/platform/fixes');
  await expect(page.getByTestId('fix-settings-refused')).toContainText(
    'need a scope that covers the whole organization',
  );
  await expect(page.getByTestId('fix-connection')).toHaveCount(0);
});

test('a person asks for the fix of an accepted recommendation and sees it asked for', async ({
  page,
}) => {
  const notes: unknown[] = [];
  let fixes: Record<string, unknown>[] = [];
  await demoEstate(page);
  await page.route('**/api/v1/waste/recommendations', async (route) => {
    await route.fulfill({
      json: {
        data: {
          recommendations: [
            {
              recommendation_id: VOLUME,
              account_id: 'fake-product-a',
              source: 'METER',
              waste_class: 'EBS_GP2_TO_GP3',
              resource_id: 'vol-0abc',
              region_id: 'eu-west-1',
              estimated_monthly_saving: '12.4000',
              severity: 'LOW',
              confidence: 'HIGH',
              observation_days: 30,
              lifecycle: 'ACCEPTED',
              owner: 'storage',
              suggested_owner: 'storage',
              owner_suggestions: [],
              created_before: null,
              ticket_reference: null,
              rationale: 'gp3 gives the same IOPS and throughput for less',
              current_instance_type: null,
              target_instance_type: null,
              current_hourly_price: null,
              target_hourly_price: null,
              price_version: null,
              added_monthly_cost: null,
            },
          ],
          unowned: 0,
        },
        meta: META,
      },
    });
  });
  await page.route('**/api/v1/remediation/pull-requests', async (route) => {
    await route.fulfill({ json: { data: { fixes }, meta: META } });
  });
  await page.route(`**/api/v1/waste/recommendations/${VOLUME}/pull-request`, async (route) => {
    notes.push(route.request().postDataJSON());
    const fix = {
      fix_id: 'fix-1',
      recommendation_id: VOLUME,
      sub_account_id: 'fake-product-a',
      status: 'REQUESTED',
      repository: null,
      branch: null,
      number: null,
      url: null,
      note: 'storage agrees',
      requested_by: 'p-owner',
      requested_at: META.as_of,
      merged_by: null,
      merged_at: null,
      closed_at: null,
      reason: null,
      failure_cause: null,
      steps: [
        {
          from_status: null,
          to_status: 'REQUESTED',
          principal: 'p-owner',
          note: 'storage agrees',
          at: META.as_of,
        },
      ],
    };
    fixes = [fix];
    await route.fulfill({ json: { data: fix, meta: META } });
  });

  await page.goto(`/optimize?finding=${VOLUME}`);
  const fix = page.getByTestId('recommendation-fix');
  await expect(fix.getByTestId('fix-none')).toBeVisible();
  await fix.getByLabel('A note for the reviewers, if any').fill('storage agrees');
  await fix.getByRole('button', { name: 'Ask for a pull request' }).click();
  await expect(fix.getByTestId('fix-said')).toContainText('Asked for by p-owner');
  await expect(fix.getByTestId('fix-ask')).toHaveCount(0);
  expect(notes).toEqual([{ note: 'storage agrees' }]);
});
