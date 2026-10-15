import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { FixSettingsScreen } from '../FixSettingsScreen';
import { Harness } from './Harness';
import { changed, clientReturning, metaOf } from './fixtures';
import { CONNECTION, MERGE_POLICY, REPOSITORIES } from '../../api/remediation';
import type {
  ApiCodeHostConnection,
  ApiEnvelope,
  ApiMergePolicy,
  ApiRepositoryMappings,
  Me,
} from '../../api/types';

/**
 * Where fixes go and which Meter may merge, TASK-P15-008, FEAT-091 and FEAT-094: shown and changed
 * by a person whose scope is the whole organization, and refused with the reason to anyone else.
 */

function envelope<T>(data: T): ApiEnvelope<T> {
  return { data, meta: metaOf() };
}

function me(isGlobal: boolean): ApiEnvelope<Me> {
  return envelope({
    principal_id: 'p-owner',
    display_name: 'Owner',
    tenant_id: 't-1',
    tiers: ['finops'],
    is_global: isGlobal,
    accounts_in_scope: 5,
  });
}

const CONNECTED: ApiCodeHostConnection = {
  connected: true,
  host: 'github',
  app_id: '1001',
  key_secret_name: 'meter/dev/codehost/github-app',
  connected_by: 'p-owner',
  connected_at: '2026-10-15T10:00:00Z',
};

const MAPPED: ApiRepositoryMappings = {
  mappings: [
    {
      state_reference: 's3://state/storage.tfstate',
      repository: 'acme/infra',
      base_branch: 'main',
      folder: 'storage',
      set_by: 'p-owner',
      set_at: '2026-10-15T10:00:00Z',
    },
  ],
  unmapped: ['s3://state/network.tfstate'],
};

function policyOf(partial: Partial<ApiMergePolicy> = {}): ApiMergePolicy {
  return {
    classes: [],
    reversible: ['EBS_GP2_TO_GP3'],
    reason: null,
    set_by: null,
    set_at: null,
    merging_on: true,
    ...partial,
  };
}

function renderWith(
  isGlobal: boolean,
  connection: ApiCodeHostConnection = CONNECTED,
  policy: ApiMergePolicy = policyOf(),
) {
  return render(
    <Harness
      initialPath="/platform/fixes"
      client={clientReturning({
        '/api/v1/me': me(isGlobal),
        [CONNECTION]: envelope(connection),
        [REPOSITORIES]: envelope(MAPPED),
        [MERGE_POLICY]: envelope(policy),
      })}
    >
      <FixSettingsScreen />
    </Harness>,
  );
}

beforeEach(() => {
  changed.length = 0;
});

describe('the fix settings', () => {
  it('tells a narrowed reader why, and shows no form', async () => {
    renderWith(false);
    expect(await screen.findByTestId('fix-settings-refused')).toHaveTextContent(
      'need a scope that covers the whole organization',
    );
    expect(screen.queryByTestId('fix-connection')).toBeNull();
  });

  it('shows the connection, the mapping, the states with nowhere to go and the policy', async () => {
    renderWith(true);
    expect(await screen.findByTestId('fix-connected')).toHaveTextContent(
      'GitHub App 1001, its key in the secret meter/dev/codehost/github-app',
    );
    expect(await screen.findByTestId('fix-mapping')).toHaveTextContent('acme/infra');
    expect(screen.getByTestId('fix-unmapped')).toHaveTextContent('s3://state/network.tfstate');
    expect(await screen.findByTestId('fix-policy-now')).toHaveTextContent(
      'Meter merges nothing: the policy names no class.',
    );
    expect(screen.queryByTestId('fix-merging-off')).toBeNull();
  });

  it('connects the GitHub App by its id and its secret', async () => {
    renderWith(true, { ...CONNECTED, connected: false, app_id: null, key_secret_name: null });
    const section = await screen.findByTestId('fix-connection');
    await screen.findByTestId('fix-not-connected');
    await userEvent.type(within(section).getByLabelText('App ID'), '1001');
    await userEvent.type(
      within(section).getByLabelText('The secret holding its private key'),
      'meter/dev/codehost/github-app',
    );
    await userEvent.click(within(section).getByRole('button', { name: 'Connect' }));
    expect(changed).toContainEqual({
      method: 'PUT',
      path: CONNECTION,
      body: {
        host: 'github',
        app_id: '1001',
        key_secret_name: 'meter/dev/codehost/github-app',
      },
    });
  });

  it('maps a state to a repository, keeping the mappings already there', async () => {
    renderWith(true);
    const section = await screen.findByTestId('fix-repositories');
    await screen.findByTestId('fix-mapping');
    await userEvent.type(
      within(section).getByLabelText('Terraform state'),
      's3://state/network.tfstate',
    );
    await userEvent.type(
      within(section).getByLabelText('Repository, owner/name'),
      'acme/infra',
    );
    await userEvent.type(
      within(section).getByLabelText('Folder, empty for the root'),
      'network',
    );
    await userEvent.click(within(section).getByRole('button', { name: 'Map it' }));
    const put = changed.find((one) => one.path === REPOSITORIES);
    expect(put?.body).toEqual({
      mappings: [
        {
          state_reference: 's3://state/storage.tfstate',
          repository: 'acme/infra',
          base_branch: 'main',
          folder: 'storage',
        },
        {
          state_reference: 's3://state/network.tfstate',
          repository: 'acme/infra',
          base_branch: 'main',
          folder: 'network',
        },
      ],
    });
  });

  it('names gp2 to gp3 in the policy, with the reason', async () => {
    renderWith(true);
    const section = await screen.findByTestId('fix-merge-policy');
    await screen.findByTestId('fix-policy-now');
    await userEvent.click(within(section).getByLabelText('gp2 volumes moved to gp3'));
    await userEvent.type(within(section).getByLabelText('Why, for the record'), 'reversible');
    await userEvent.click(within(section).getByRole('button', { name: 'Save the policy' }));
    expect(changed).toContainEqual({
      method: 'PUT',
      path: MERGE_POLICY,
      body: { classes: ['EBS_GP2_TO_GP3'], reason: 'reversible' },
    });
  });

  it('says merging is off when the flag is', async () => {
    renderWith(true, CONNECTED, policyOf({ merging_on: false }));
    expect(await screen.findByTestId('fix-merging-off')).toHaveTextContent(
      'Merging is turned off for every tenant',
    );
  });
});
