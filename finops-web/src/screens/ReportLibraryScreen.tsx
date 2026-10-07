import { useMemo, useState, type ReactNode, type SubmitEvent } from 'react';
import { useNavigate } from 'react-router';

import { keepAccount, useChosenAccount } from '../api/account';
import { reasonOf } from '../api/client';
import { OPEN_EXPORT } from '../api/exportViews';
import { useChangeView, useDeleteView, useSaveView, useSavedViews } from '../api/queries';
import { VIEW_NAME_MAX, hrefOf } from '../api/savedViews';
import type { ApiSavedView, SavedViewVisibility } from '../api/types';
import { DataTable } from '../components/DataTable';
import { StateBoundary } from '../components/StateBoundary';
import type { SurfaceState } from '../components/surfaceState';
import type { Column } from '../components/tableConfig';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { screenTitleFor } from '../shell/sections';
import { audienceOf, changedAt, copyName, filtersOf } from './libraryModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The report library. FEAT-068, TASK-P8-010.
 *
 * Every view the reader saved and every view somebody in the organization shared, the latest
 * changed first. A view is a screen and its query under a name and holds no figure, so opening
 * one reads its screen afresh in the reader's own scope: a view shared by a reader of the whole
 * estate shows a narrowed colleague their own accounts and nothing more.
 *
 * A view opens by its name. Any view duplicates into a private copy of the reader's own. Rename,
 * share, make private and delete belong to whoever saved it, which the API enforces and this
 * screen reflects by offering them on the reader's own rows alone. Export opens the view with its
 * Export menu already open, because a row here has no rows of its own to export.
 */

type Asking =
  | { readonly kind: 'rename'; readonly view: ApiSavedView }
  | { readonly kind: 'delete'; readonly view: ApiSavedView };

/**
 * The states this list can be in. Collector failures describe figures and a view holds none, and
 * a list cut at its limit says so in its caption, so neither changes what the table means.
 */
function libraryState(state: SurfaceState): SurfaceState {
  return state.kind === 'degraded' || state.kind === 'partial' ? { kind: 'ready' } : state;
}

function columnsFor(
  actions: (view: ApiSavedView) => ReactNode,
): readonly Column<ApiSavedView>[] {
  return [
    {
      key: 'name',
      header: 'Name',
      rowHeader: true,
      render: (view) => (
        <Link to={hrefOf(view)} data-testid="library-open">
          {view.name}
        </Link>
      ),
      sortValue: (view) => view.name.toLowerCase(),
    },
    {
      key: 'screen',
      header: 'Screen',
      render: (view) => screenTitleFor(view.screen_path),
      sortValue: (view) => screenTitleFor(view.screen_path),
    },
    {
      key: 'filters',
      header: 'Filters',
      render: filtersOf,
      sortValue: filtersOf,
    },
    {
      key: 'audience',
      header: 'Who can open it',
      render: audienceOf,
      sortValue: audienceOf,
    },
    {
      key: 'changed',
      header: 'Last changed',
      render: (view) => <time dateTime={view.updated_at}>{changedAt(view.updated_at)}</time>,
      sortValue: (view) => view.updated_at,
    },
    { key: 'actions', header: 'Actions', render: actions },
  ];
}

function RenamePanel({
  view,
  busy,
  onRename,
  onCancel,
}: {
  readonly view: ApiSavedView;
  readonly busy: boolean;
  readonly onRename: (name: string) => void;
  readonly onCancel: () => void;
}) {
  const [name, setName] = useState(view.name);
  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    onRename(name.trim());
  }
  return (
    <form data-testid="library-rename" onSubmit={submit}>
      <label>
        Rename {view.name}
        <input
          data-testid="library-rename-name"
          value={name}
          maxLength={VIEW_NAME_MAX}
          required
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </label>
      <button
        type="submit"
        data-testid="library-rename-save"
        disabled={busy || name.trim() === ''}
      >
        Save name
      </button>
      <button type="button" data-testid="library-rename-cancel" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

function DeletePanel({
  view,
  busy,
  onDelete,
  onCancel,
}: {
  readonly view: ApiSavedView;
  readonly busy: boolean;
  readonly onDelete: () => void;
  readonly onCancel: () => void;
}) {
  return (
    <div role="group" aria-label={`Delete ${view.name}`} data-testid="library-delete">
      <p>
        Delete {view.name}? A deleted view cannot be brought back
        {view.visibility === 'SHARED'
          ? ', and it leaves the library of everyone it was shared with'
          : ''}
        .
      </p>
      <button
        type="button"
        data-testid="library-delete-confirm"
        disabled={busy}
        onClick={onDelete}
      >
        Delete
      </button>
      <button type="button" data-testid="library-delete-cancel" onClick={onCancel}>
        Keep it
      </button>
    </div>
  );
}

export function ReportLibraryScreen() {
  const query = useSavedViews();
  const envelope = query.data;
  const views = useMemo(() => envelope?.data ?? [], [envelope]);
  useReportMeta('report-library', envelope?.meta);
  const state = libraryState(
    surfaceStateFor(query, envelope?.meta, views.length, 'none', 'saved views'),
  );

  const navigate = useNavigate();
  const account = useChosenAccount();
  const change = useChangeView();
  const remove = useDeleteView();
  const copy = useSaveView();
  const busy = change.isPending || remove.isPending || copy.isPending;
  const [asking, setAsking] = useState<Asking | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  function begin(): void {
    setNotice(null);
    setFailure(null);
  }

  function failed(error: unknown): void {
    // Said, in the API's words. A refusal is a sentence written for the reader.
    setFailure(reasonOf(error));
  }

  function duplicate(view: ApiSavedView): void {
    begin();
    copy.mutate(
      {
        name: copyName(view.name),
        screen_path: view.screen_path,
        query: view.query,
        visibility: 'PRIVATE',
      },
      {
        onSuccess: (made) => {
          setNotice(`Duplicated as ${made.data.name}, private to you.`);
        },
        onError: failed,
      },
    );
  }

  function share(view: ApiSavedView): void {
    begin();
    const visibility: SavedViewVisibility = view.visibility === 'SHARED' ? 'PRIVATE' : 'SHARED';
    change.mutate(
      { viewId: view.view_id, change: { visibility } },
      {
        onSuccess: (changed) => {
          setNotice(
            visibility === 'SHARED'
              ? `${changed.data.name} is shared with everyone in the organization. Each of them sees it in their own scope.`
              : `${changed.data.name} is private to you again.`,
          );
        },
        onError: failed,
      },
    );
  }

  function rename(view: ApiSavedView, name: string): void {
    begin();
    change.mutate(
      { viewId: view.view_id, change: { name } },
      {
        onSuccess: (changed) => {
          setAsking(null);
          setNotice(`Renamed to ${changed.data.name}.`);
        },
        onError: failed,
      },
    );
  }

  function destroy(view: ApiSavedView): void {
    begin();
    remove.mutate(view.view_id, {
      onSuccess: (gone) => {
        setAsking(null);
        setNotice(`Deleted ${gone.data.name}.`);
      },
      onError: failed,
    });
  }

  function exportView(view: ApiSavedView): void {
    // Through the account rule every link follows, FEAT-075, so Export opens what Open opens.
    void navigate(keepAccount(hrefOf(view), account), { state: OPEN_EXPORT });
  }

  const actions = (view: ApiSavedView) => (
    <div role="group" aria-label={`${view.name}, actions`} data-testid="library-actions">
      <button
        type="button"
        data-testid="library-export"
        onClick={() => {
          exportView(view);
        }}
      >
        Export
      </button>
      <button
        type="button"
        data-testid="library-duplicate"
        disabled={busy}
        onClick={() => {
          duplicate(view);
        }}
      >
        Duplicate
      </button>
      {view.owned ? (
        <>
          <button
            type="button"
            data-testid="library-rename-start"
            disabled={busy}
            onClick={() => {
              begin();
              setAsking({ kind: 'rename', view });
            }}
          >
            Rename
          </button>
          <button
            type="button"
            data-testid="library-share"
            disabled={busy}
            onClick={() => {
              share(view);
            }}
          >
            {view.visibility === 'SHARED' ? 'Make private' : 'Share'}
          </button>
          <button
            type="button"
            data-testid="library-delete-start"
            disabled={busy}
            onClick={() => {
              begin();
              setAsking({ kind: 'delete', view });
            }}
          >
            Delete
          </button>
        </>
      ) : null}
    </div>
  );
  // Rebuilt with the rows, so a button's handler always acts on the row as it now stands.
  const columns = columnsFor(actions);
  const coverage = envelope?.meta.scope_coverage;
  const caption =
    coverage?.is_partial === true
      ? `The latest ${String(coverage.visible)} of ${String(coverage.total)} saved views`
      : `${String(views.length)} saved views, the latest changed first`;

  return (
    <section aria-label="Report Library">
      <p data-testid="library-intro">
        A saved view keeps a screen and its filters, never its figures. Opening one reads the
        screen afresh, so whoever opens a shared view sees what their own access allows.
      </p>

      {asking?.kind === 'rename' ? (
        <RenamePanel
          key={asking.view.view_id}
          view={asking.view}
          busy={busy}
          onRename={(name) => {
            rename(asking.view, name);
          }}
          onCancel={() => {
            setAsking(null);
          }}
        />
      ) : null}
      {asking?.kind === 'delete' ? (
        <DeletePanel
          key={asking.view.view_id}
          view={asking.view}
          busy={busy}
          onDelete={() => {
            destroy(asking.view);
          }}
          onCancel={() => {
            setAsking(null);
          }}
        />
      ) : null}
      {notice === null ? null : (
        <p role="status" data-testid="library-notice">
          {notice}
        </p>
      )}
      {failure === null ? null : (
        <p role="alert" data-testid="library-failure" className="meter-failure">
          {failure}
        </p>
      )}

      {state.kind === 'empty' ? (
        <p data-testid="library-empty">
          No saved views yet. Save view, beside Export on any screen, keeps that screen and its
          filters here, for you alone or for everyone in the organization.
        </p>
      ) : (
        <StateBoundary state={state}>
          <DataTable
            rows={views}
            columns={columns}
            rowKey={(view) => view.view_id}
            initialSort={{ key: 'changed', direction: 'descending' }}
            caption={caption}
            captionTestId="library-caption"
            rowAttributes={(view) => ({
              'data-testid': 'library-row',
              'data-owned': String(view.owned),
              'data-visibility': view.visibility,
            })}
          />
        </StateBoundary>
      )}
    </section>
  );
}
