import { useState, type SubmitEvent } from 'react';
import { useLocation } from 'react-router';

import { reasonOf } from '../api/client';
import { useSaveView } from '../api/queries';
import { VIEW_NAME_MAX, queryOf } from '../api/savedViews';
import { Link } from './links';
import { LIBRARY_PATH, isSavable, screenTitleFor } from './sections';

/**
 * Save view, beside Export on every built screen. FEAT-068, TASK-P8-010.
 *
 * Keeps the screen and the query it is showing under a name, for the reader alone or shared
 * with everyone in the organization, and the report library lists it. What is kept is
 * configuration and never data: opening the view later reads its screen afresh in the opener's
 * own scope, so a view shared by somebody who reads the whole estate shows a colleague only what
 * that colleague may see, and the panel says so before anything is shared.
 *
 * A disclosure, as Export is, for the expanded state and keyboard handling `summary` brings.
 */
export function SaveView() {
  const { pathname, search } = useLocation();
  // Keyed by the address, so a name typed under one filter is never saved against the next.
  return isSavable(pathname) ? (
    <Offered key={`${pathname}${search}`} pathname={pathname} search={search} />
  ) : null;
}

function Offered({ pathname, search }: { readonly pathname: string; readonly search: string }) {
  const save = useSaveView();
  const [name, setName] = useState(() => screenTitleFor(pathname));
  const [shared, setShared] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(null);
    save.mutate(
      {
        name: name.trim(),
        screen_path: pathname,
        query: queryOf(search),
        visibility: shared ? 'SHARED' : 'PRIVATE',
      },
      {
        onSuccess: (envelope) => {
          setSaved(envelope.data.name);
        },
      },
    );
  }

  return (
    <details data-testid="save-view">
      <summary>Save view</summary>
      <form data-testid="save-view-form" onSubmit={submit}>
        <label>
          Name
          <input
            data-testid="save-view-name"
            value={name}
            maxLength={VIEW_NAME_MAX}
            required
            onChange={(event) => {
              setName(event.target.value);
            }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            data-testid="save-view-shared"
            checked={shared}
            onChange={(event) => {
              setShared(event.target.checked);
            }}
          />
          Share with everyone in the organization
        </label>
        <p data-testid="save-view-note">
          Keeps this screen and its filters, never its figures. Whoever opens it sees what their
          own access allows.
        </p>
        <button
          type="submit"
          data-testid="save-view-submit"
          disabled={save.isPending || name.trim() === ''}
        >
          {save.isPending ? 'Saving' : 'Save'}
        </button>
        {saved === null ? null : (
          <p role="status" data-testid="save-view-saved">
            Saved as {saved}, in the <Link to={LIBRARY_PATH}>Report Library</Link>.
          </p>
        )}
        {save.isError ? (
          <p role="alert" data-testid="save-view-failure" className="meter-failure">
            {reasonOf(save.error)}
          </p>
        ) : null}
      </form>
    </details>
  );
}
