import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiError, type ApiClient } from '../../api/client';
import type { ApiEnvelope, ApiSavedView } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { audienceOf, changedAt, copyName, filtersOf } from '../libraryModel';
import { ReportLibraryScreen } from '../ReportLibraryScreen';
import { Harness } from './Harness';
import { changed, clientReturning, metaOf, posted, postedBodies } from './fixtures';
import { sortEveryColumn } from './sortEveryColumn';

/** The report library, FEAT-068 and TASK-P8-010: open, rename, duplicate, share, delete, export. */

const LIST = '/api/v1/reports/views';

function view(overrides: Partial<ApiSavedView> = {}): ApiSavedView {
  return {
    view_id: 'v-mine',
    name: 'Active accounts',
    screen_path: '/inventory/accounts',
    query: { status: 'ACTIVE' },
    visibility: 'PRIVATE',
    owned: true,
    created_at: '2026-10-07T06:00:00Z',
    updated_at: '2026-10-07T06:30:00Z',
    ...overrides,
  };
}

const MINE = view();
const THEIRS = view({
  view_id: 'v-theirs',
  name: 'Explorer by service',
  screen_path: '/analyze/explorer',
  query: { group: 'service', filter: ['a', 'b'] },
  visibility: 'SHARED',
  owned: false,
  updated_at: '2026-10-07T05:00:00Z',
});

function listed(rows: readonly ApiSavedView[], partial?: { readonly total: number }) {
  return {
    data: rows,
    meta: metaOf({
      scope_coverage: {
        visible: rows.length,
        total: partial?.total ?? rows.length,
        is_partial: partial !== undefined,
        unit: 'saved views',
      },
    }),
  };
}

/** Where the screen sent the reader, and with what state. */
function Landed() {
  const location = useLocation();
  return (
    <p data-testid="landed" data-state={JSON.stringify(location.state)}>
      {`${location.pathname}${location.search}`}
    </p>
  );
}

interface Options {
  readonly rows?: readonly ApiSavedView[];
  readonly failure?: Error;
  readonly refusal?: Error;
  readonly partial?: { readonly total: number };
  readonly at?: string;
}

/** A client whose list, change and copy answer as the API does, each on its own path. */
function libraryClient({
  rows = [MINE, THEIRS],
  failure,
  refusal,
  partial,
}: Options): ApiClient {
  const base = clientReturning(
    {
      [LIST]: listed(rows, partial),
      [`${LIST}/v-mine`]: { data: { ...MINE, name: 'Renamed' }, meta: metaOf() },
    },
    failure,
  );
  return {
    ...base,
    patch: <T,>(path: string, body: unknown): Promise<ApiEnvelope<T>> =>
      refusal === undefined ? base.patch<T>(path, body) : Promise.reject(refusal),
    post: <T,>(path: string, body?: unknown): Promise<ApiEnvelope<T>> => {
      posted.push(path);
      postedBodies.push(body);
      const made = {
        ...MINE,
        ...(body as Partial<ApiSavedView>),
        view_id: 'v-copy',
        owned: true,
      };
      return Promise.resolve({ data: made, meta: metaOf() } as ApiEnvelope<T>);
    },
  };
}

function renderLibrary(options: Options = {}) {
  return render(
    <Harness client={libraryClient(options)} initialPath={options.at ?? '/report/library'}>
      <Routes>
        <Route path="/report/library" element={<ReportLibraryScreen />} />
        <Route path="*" element={<Landed />} />
      </Routes>
    </Harness>,
  );
}

function rowOf(name: string): HTMLElement {
  const row = screen.getByRole('rowheader', { name }).closest('tr');
  if (row === null) {
    throw new Error(`no row for ${name}`);
  }
  return row;
}

beforeEach(() => {
  posted.length = 0;
  postedBodies.length = 0;
  changed.length = 0;
});

describe('the report library', () => {
  it("lists the reader's views and the shared ones, saying who can open each", async () => {
    renderLibrary();
    await screen.findByRole('rowheader', { name: MINE.name });
    expect(screen.getAllByTestId('library-row')).toHaveLength(2);
    expect(within(rowOf(MINE.name)).getByText('Only you')).toBeInTheDocument();
    expect(
      within(rowOf(THEIRS.name)).getByText('Everyone, shared with you'),
    ).toBeInTheDocument();
    expect(within(rowOf(THEIRS.name)).getByText('group, filter')).toBeInTheDocument();
    expect(screen.getByTestId('library-caption')).toHaveTextContent(
      '2 saved views, the latest changed first',
    );
    expect(screen.getByTestId('library-intro')).toHaveTextContent('never its figures');
  });

  it('opens a view at its screen and its query', async () => {
    renderLibrary();
    const link = await screen.findByRole('link', { name: THEIRS.name });
    expect(link).toHaveAttribute('href', '/analyze/explorer?group=service&filter=a&filter=b');
  });

  it("offers renaming, sharing and deleting on the reader's own views alone", async () => {
    renderLibrary();
    await screen.findByRole('rowheader', { name: MINE.name });
    const mine = within(rowOf(MINE.name));
    const theirs = within(rowOf(THEIRS.name));
    for (const id of ['library-rename-start', 'library-share', 'library-delete-start']) {
      expect(mine.getByTestId(id)).toBeInTheDocument();
      expect(theirs.queryByTestId(id)).toBeNull();
    }
    for (const id of ['library-export', 'library-duplicate']) {
      expect(theirs.getByTestId(id)).toBeInTheDocument();
    }
  });

  it('renames a view, and cancelling asks nothing of the API', async () => {
    renderLibrary();
    await screen.findByRole('rowheader', { name: MINE.name });
    fireEvent.click(within(rowOf(MINE.name)).getByTestId('library-rename-start'));
    fireEvent.click(screen.getByTestId('library-rename-cancel'));
    expect(screen.queryByTestId('library-rename')).toBeNull();
    expect(changed).toEqual([]);

    fireEvent.click(within(rowOf(MINE.name)).getByTestId('library-rename-start'));
    const name = screen.getByTestId('library-rename-name');
    expect(name).toHaveValue(MINE.name);
    fireEvent.change(name, { target: { value: '   ' } });
    expect(screen.getByTestId('library-rename-save')).toBeDisabled();
    fireEvent.change(name, { target: { value: ' Renamed ' } });
    fireEvent.click(screen.getByTestId('library-rename-save'));

    expect(await screen.findByTestId('library-notice')).toHaveTextContent(
      'Renamed to Renamed.',
    );
    expect(changed).toEqual([
      { method: 'PATCH', path: `${LIST}/v-mine`, body: { name: 'Renamed' } },
    ]);
    expect(screen.queryByTestId('library-rename')).toBeNull();
  });

  it('shares a private view, saying each person sees it in their own scope', async () => {
    renderLibrary();
    await screen.findByRole('rowheader', { name: MINE.name });
    fireEvent.click(within(rowOf(MINE.name)).getByTestId('library-share'));
    expect(await screen.findByTestId('library-notice')).toHaveTextContent(
      'Each of them sees it in their own scope.',
    );
    expect(changed).toEqual([
      { method: 'PATCH', path: `${LIST}/v-mine`, body: { visibility: 'SHARED' } },
    ]);
  });

  it('makes a shared view private again', async () => {
    renderLibrary({ rows: [{ ...MINE, visibility: 'SHARED' }] });
    await screen.findByRole('rowheader', { name: MINE.name });
    const share = within(rowOf(MINE.name)).getByTestId('library-share');
    expect(share).toHaveTextContent('Make private');
    fireEvent.click(share);
    expect(await screen.findByTestId('library-notice')).toHaveTextContent(
      'private to you again',
    );
    expect(changed).toEqual([
      { method: 'PATCH', path: `${LIST}/v-mine`, body: { visibility: 'PRIVATE' } },
    ]);
  });

  it('asks before deleting, and keeping it deletes nothing', async () => {
    renderLibrary({ rows: [{ ...MINE, visibility: 'SHARED' }] });
    await screen.findByRole('rowheader', { name: MINE.name });
    fireEvent.click(within(rowOf(MINE.name)).getByTestId('library-delete-start'));
    expect(screen.getByTestId('library-delete')).toHaveTextContent(
      'leaves the library of everyone it was shared with',
    );
    fireEvent.click(screen.getByTestId('library-delete-cancel'));
    expect(changed).toEqual([]);

    fireEvent.click(within(rowOf(MINE.name)).getByTestId('library-delete-start'));
    fireEvent.click(screen.getByTestId('library-delete-confirm'));
    expect(await screen.findByTestId('library-notice')).toHaveTextContent('Deleted Renamed.');
    expect(changed).toEqual([{ method: 'DELETE', path: `${LIST}/v-mine`, body: undefined }]);
  });

  it("duplicates anybody's view into a private copy of the reader's own", async () => {
    renderLibrary();
    await screen.findByRole('rowheader', { name: THEIRS.name });
    fireEvent.click(within(rowOf(THEIRS.name)).getByTestId('library-duplicate'));
    expect(await screen.findByTestId('library-notice')).toHaveTextContent(
      'Duplicated as Explorer by service (copy), private to you.',
    );
    expect(posted).toEqual([LIST]);
    expect(postedBodies).toEqual([
      {
        name: 'Explorer by service (copy)',
        screen_path: THEIRS.screen_path,
        query: THEIRS.query,
        visibility: 'PRIVATE',
      },
    ]);
  });

  it('exports a view by opening it with its Export menu asked for', async () => {
    renderLibrary();
    await screen.findByRole('rowheader', { name: THEIRS.name });
    fireEvent.click(within(rowOf(THEIRS.name)).getByTestId('library-export'));
    const landed = await screen.findByTestId('landed');
    expect(landed).toHaveTextContent('/analyze/explorer?group=service&filter=a&filter=b');
    expect(landed).toHaveAttribute('data-state', '{"openExport":true}');
  });

  it('keeps the account the reader chose, on Open and on Export alike', async () => {
    renderLibrary({ at: '/report/library?account=111122223333' });
    const link = await screen.findByRole('link', { name: THEIRS.name });
    expect(link.getAttribute('href')).toContain('account=111122223333');
    fireEvent.click(within(rowOf(THEIRS.name)).getByTestId('library-export'));
    expect(await screen.findByTestId('landed')).toHaveTextContent('account=111122223333');
  });

  it('says a refusal in the words the API wrote for the reader', async () => {
    const said = 'Only the person who saved this view may rename, share or delete it.';
    renderLibrary({ refusal: new ApiError(403, JSON.stringify({ detail: said })) });
    await screen.findByRole('rowheader', { name: MINE.name });
    fireEvent.click(within(rowOf(MINE.name)).getByTestId('library-share'));
    expect(await screen.findByTestId('library-failure')).toHaveTextContent(said);
    expect(screen.queryByTestId('library-notice')).toBeNull();
  });

  it('says how to fill an empty library', async () => {
    renderLibrary({ rows: [] });
    expect(await screen.findByTestId('library-empty')).toHaveTextContent(
      'Save view, beside Export on any screen',
    );
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('says a list cut at its limit is cut', async () => {
    renderLibrary({ partial: { total: 600 } });
    expect(await screen.findByTestId('library-caption')).toHaveTextContent(
      'The latest 2 of 600 saved views',
    );
  });

  it('fails as a failure, never as an empty library', async () => {
    renderLibrary({ failure: new Error('Throttled') });
    await waitFor(() => {
      expect(screen.getByTestId('state')).toHaveAttribute('data-state', 'failed');
    });
    expect(screen.queryByTestId('library-empty')).toBeNull();
  });

  it('sorts every column it can, both ways', async () => {
    const { container } = renderLibrary();
    await screen.findByRole('rowheader', { name: MINE.name });
    expect(sortEveryColumn(container)).toBe(5);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderLibrary();
    await screen.findByRole('rowheader', { name: MINE.name });
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('what the library says about a view', () => {
  it('names a copy as a copy, within the length the API keeps', () => {
    expect(copyName('Accounts')).toBe('Accounts (copy)');
    const long = copyName('x'.repeat(200));
    expect(long).toHaveLength(120);
    expect(long.endsWith(' (copy)')).toBe(true);
  });

  it('gives a change as an absolute time, and an unreadable one as it came', () => {
    expect(changedAt('2026-10-07T06:30:59.123456Z')).toBe('2026-10-07 06:30 UTC');
    expect(changedAt('2026-10-07T12:00:00+05:30')).toBe('2026-10-07 06:30 UTC');
    expect(changedAt('not a time')).toBe('not a time');
  });

  it("says who can open a view from the reader's side", () => {
    expect(audienceOf({ visibility: 'PRIVATE', owned: true })).toBe('Only you');
    expect(audienceOf({ visibility: 'SHARED', owned: true })).toBe('Everyone, shared by you');
    expect(audienceOf({ visibility: 'SHARED', owned: false })).toBe(
      'Everyone, shared with you',
    );
  });

  it('names the parameters a view keeps, or says it keeps none', () => {
    expect(filtersOf({ query: {} })).toBe('None');
    expect(filtersOf({ query: { status: 'ACTIVE', sort: ['name'] } })).toBe('status, sort');
  });
});
