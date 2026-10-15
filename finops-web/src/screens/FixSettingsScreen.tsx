import { useId, useState } from 'react';

import { reasonOf } from '../api/client';
import { useMe } from '../api/queries';
import {
  useCodeHostConnection,
  useConnect,
  useMapRepositories,
  useMergePolicy,
  useRepositoryMappings,
  useSetMergePolicy,
  type MappingIn,
} from '../api/remediation';
import type { ApiMergePolicy, ApiRepositoryMapping } from '../api/types';
import { DataTable } from '../components/DataTable';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';

/**
 * Where fixes go and which Meter may merge, FEAT-091 and FEAT-094, TASK-P15-008.
 *
 * Three settings the organization owns: the GitHub App fixes go through, the repository each
 * Terraform state's fixes go to, and the reversible fixes Meter may merge. Each is shown and
 * changed by a person whose scope is the whole organization; anyone else is told why rather than
 * shown an empty form. The key is never here, only the name of the secret that holds it.
 */

const NEEDS_THE_ORGANIZATION =
  'Where fixes go and which Meter may merge belong to the organization, so they need a scope ' +
  'that covers the whole organization.';

function Connection() {
  const appId = useId();
  const secretId = useId();
  const found = useCodeHostConnection(true);
  const connect = useConnect();
  const [app, setApp] = useState('');
  const [secret, setSecret] = useState('');
  const now = found.data?.data;
  return (
    <section aria-label="The code host" data-testid="fix-connection">
      <h2>The code host</h2>
      {found.isError ? <p role="alert">{reasonOf(found.error)}</p> : null}
      {now === undefined ? null : now.connected ? (
        <p data-testid="fix-connected">
          GitHub App {now.app_id}, its key in the secret <code>{now.key_secret_name}</code>,
          connected by {now.connected_by}.
        </p>
      ) : (
        <p data-testid="fix-not-connected">
          No code host is connected, so no fix can be opened. Register and install the GitHub
          App, then connect it here.
        </p>
      )}
      <form
        aria-label="Connect the GitHub App"
        onSubmit={(event) => {
          event.preventDefault();
          connect.mutate({
            host: 'github',
            app_id: app.trim(),
            key_secret_name: secret.trim(),
          });
        }}
      >
        <label htmlFor={appId}>App ID</label>
        <input
          id={appId}
          value={app}
          onChange={(event) => {
            setApp(event.target.value);
          }}
        />
        <label htmlFor={secretId}>The secret holding its private key</label>
        <input
          id={secretId}
          value={secret}
          placeholder="meter/<env>/codehost/github-app"
          onChange={(event) => {
            setSecret(event.target.value);
          }}
        />
        <button type="submit" disabled={connect.isPending || app.trim() === ''}>
          Connect
        </button>
        {connect.isError ? (
          <p role="alert" data-testid="fix-connect-refused">
            {reasonOf(connect.error)}
          </p>
        ) : null}
      </form>
    </section>
  );
}

function asIn(mapping: ApiRepositoryMapping): MappingIn {
  return {
    state_reference: mapping.state_reference,
    repository: mapping.repository,
    base_branch: mapping.base_branch,
    folder: mapping.folder,
  };
}

function mappingColumns(
  busy: boolean,
  remove: (state: string) => void,
): readonly Column<ApiRepositoryMapping>[] {
  return [
    { key: 'state', header: 'State', render: (row) => row.state_reference },
    { key: 'repository', header: 'Repository', render: (row) => row.repository },
    { key: 'branch', header: 'Branch', render: (row) => row.base_branch },
    {
      key: 'folder',
      header: 'Folder',
      render: (row) => (row.folder === '' ? 'the root' : row.folder),
    },
    { key: 'set_by', header: 'Set by', render: (row) => row.set_by },
    {
      key: 'change',
      header: 'Change',
      render: (row) => (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            remove(row.state_reference);
          }}
        >
          Remove
        </button>
      ),
    },
  ];
}

const EMPTY: MappingIn = {
  state_reference: '',
  repository: '',
  base_branch: 'main',
  folder: '',
};

function Repositories() {
  const stateId = useId();
  const repositoryId = useId();
  const branchId = useId();
  const folderId = useId();
  const found = useRepositoryMappings(true);
  const map = useMapRepositories();
  const [draft, setDraft] = useState<MappingIn>(EMPTY);
  const mappings = found.data?.data.mappings ?? [];
  const unmapped = found.data?.data.unmapped ?? [];
  const save = (next: readonly MappingIn[]) => {
    map.mutate(
      { mappings: next },
      {
        onSuccess: () => {
          setDraft(EMPTY);
        },
      },
    );
  };
  return (
    <section aria-label="Where fixes go" data-testid="fix-repositories">
      <h2>Where fixes go</h2>
      {found.isError ? <p role="alert">{reasonOf(found.error)}</p> : null}
      {mappings.length === 0 ? (
        <p data-testid="fix-no-mappings">No Terraform state is mapped to a repository yet.</p>
      ) : (
        <DataTable
          rows={mappings}
          columns={mappingColumns(map.isPending, (state) => {
            save(mappings.filter((other) => other.state_reference !== state).map(asIn));
          })}
          rowKey={(row) => row.state_reference}
          rowAttributes={() => ({ 'data-testid': 'fix-mapping' })}
          caption="Each Terraform state, and the folder whose Terraform wrote it"
        />
      )}
      {unmapped.length === 0 ? null : (
        <p data-testid="fix-unmapped">
          Fixes for resources in these states have nowhere to go until each is mapped:{' '}
          {unmapped.join(', ')}.
        </p>
      )}
      <form
        aria-label="Map a state to a repository"
        onSubmit={(event) => {
          event.preventDefault();
          save([...mappings.map(asIn), { ...draft, folder: draft.folder.trim() }]);
        }}
      >
        <label htmlFor={stateId}>Terraform state</label>
        <input
          id={stateId}
          list={`${stateId}-unmapped`}
          value={draft.state_reference}
          onChange={(event) => {
            setDraft({ ...draft, state_reference: event.target.value });
          }}
        />
        <datalist id={`${stateId}-unmapped`}>
          {unmapped.map((one) => (
            <option key={one} value={one} />
          ))}
        </datalist>
        <label htmlFor={repositoryId}>Repository, owner/name</label>
        <input
          id={repositoryId}
          value={draft.repository}
          onChange={(event) => {
            setDraft({ ...draft, repository: event.target.value });
          }}
        />
        <label htmlFor={branchId}>Base branch</label>
        <input
          id={branchId}
          value={draft.base_branch}
          onChange={(event) => {
            setDraft({ ...draft, base_branch: event.target.value });
          }}
        />
        <label htmlFor={folderId}>Folder, empty for the root</label>
        <input
          id={folderId}
          value={draft.folder}
          onChange={(event) => {
            setDraft({ ...draft, folder: event.target.value });
          }}
        />
        <button
          type="submit"
          disabled={map.isPending || draft.state_reference === '' || draft.repository === ''}
        >
          Map it
        </button>
        {map.isError ? (
          <p role="alert" data-testid="fix-map-refused">
            {reasonOf(map.error)}
          </p>
        ) : null}
      </form>
    </section>
  );
}

const NAMES: Readonly<Record<string, string>> = { EBS_GP2_TO_GP3: 'gp2 volumes moved to gp3' };

function PolicyForm({ policy }: { readonly policy: ApiMergePolicy }) {
  const reasonId = useId();
  const set = useSetMergePolicy();
  const [chosen, setChosen] = useState<readonly string[]>(policy.classes);
  const [reason, setReason] = useState('');
  return (
    <form
      aria-label="Which fixes Meter may merge"
      onSubmit={(event) => {
        event.preventDefault();
        set.mutate({ classes: chosen, reason: reason.trim() });
      }}
    >
      <fieldset>
        <legend>Meter may merge, once the repository&apos;s checks and reviews pass</legend>
        {policy.reversible.map((one) => (
          <label key={one}>
            <input
              type="checkbox"
              checked={chosen.includes(one)}
              onChange={(event) => {
                setChosen(
                  event.target.checked
                    ? [...chosen, one]
                    : chosen.filter((other) => other !== one),
                );
              }}
            />{' '}
            {NAMES[one] ?? one}
          </label>
        ))}
      </fieldset>
      <label htmlFor={reasonId}>Why, for the record</label>
      <textarea
        id={reasonId}
        value={reason}
        maxLength={500}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
      <button type="submit" disabled={set.isPending || reason.trim().length < 3}>
        Save the policy
      </button>
      {set.isError ? (
        <p role="alert" data-testid="fix-policy-refused">
          {reasonOf(set.error)}
        </p>
      ) : null}
    </form>
  );
}

function MergePolicy() {
  const found = useMergePolicy(true);
  const policy = found.data?.data;
  return (
    <section aria-label="What Meter may merge" data-testid="fix-merge-policy">
      <h2>What Meter may merge</h2>
      <p>
        Only a fix that loses nothing if it is wrong may ever be merged by Meter, and only one
        Meter opened. A removal is always merged by a person. ADR-0038.
      </p>
      {found.isError ? <p role="alert">{reasonOf(found.error)}</p> : null}
      {policy === undefined ? null : (
        <>
          <p data-testid="fix-policy-now">
            {policy.classes.length === 0
              ? 'Meter merges nothing: the policy names no class.'
              : `Meter merges ${policy.classes.map((one) => NAMES[one] ?? one).join(', ')}, set ` +
                `by ${policy.set_by ?? 'nobody'}: ${policy.reason ?? ''}`}
          </p>
          {policy.merging_on ? null : (
            <p data-testid="fix-merging-off">
              Merging is turned off for every tenant, the pull_request_merge flag, whatever the
              policy names. Pull requests are still opened and followed.
            </p>
          )}
          <PolicyForm key={policy.classes.join(',')} policy={policy} />
        </>
      )}
    </section>
  );
}

export function FixSettingsScreen() {
  const me = useMe();
  const organization = me.data?.data.is_global === true;
  const connection = useCodeHostConnection(organization);
  useReportMeta('fix-settings', connection.data?.meta);
  return (
    <section aria-labelledby="fix-settings-title" data-testid="fix-settings">
      <h1 id="fix-settings-title">Fixes</h1>
      {me.data === undefined ? null : organization ? (
        <>
          <Connection />
          <Repositories />
          <MergePolicy />
        </>
      ) : (
        <p data-testid="fix-settings-refused">{NEEDS_THE_ORGANIZATION}</p>
      )}
    </section>
  );
}
