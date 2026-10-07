import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import type { ApiSavedView } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { Harness } from '../../screens/__tests__/Harness';
import {
  clientReturning,
  metaOf,
  posted,
  postedBodies,
} from '../../screens/__tests__/fixtures';
import { SaveView } from '../SaveView';
import { LIBRARY_PATH, TABS, allScreens, isSavable, screenFor } from '../sections';

/** Save view, beside Export, FEAT-068 and TASK-P8-010. */

const SAVED: ApiSavedView = {
  view_id: 'v-new',
  name: 'EC2 by service',
  screen_path: '/analyze/explorer',
  query: { group: 'service' },
  visibility: 'PRIVATE',
  owned: true,
  created_at: '2026-10-07T06:00:00Z',
  updated_at: '2026-10-07T06:00:00Z',
};

function renderAt(path: string, failure?: Error) {
  const client = clientReturning(
    { '/api/v1/reports/views': { data: SAVED, meta: metaOf() } },
    failure,
  );
  return render(
    <Harness client={client} initialPath={path}>
      <SaveView />
    </Harness>,
  );
}

beforeEach(() => {
  posted.length = 0;
  postedBodies.length = 0;
});

describe('where a view can be saved from', () => {
  it('is every built screen, and no screen that is not built yet', () => {
    const screens = allScreens().filter((one) => one.path !== LIBRARY_PATH);
    expect(screens.some((one) => one.arrives !== null)).toBe(true);
    for (const one of screens) {
      expect(isSavable(one.path)).toBe(one.arrives === null);
    }
  });

  it('is every tab of a built screen', () => {
    const tabs = Object.entries(TABS).flatMap(([owner, held]) =>
      held.map((tab) => ({ path: tab.path, built: screenFor(owner)?.arrives === null })),
    );
    expect(tabs.length).toBeGreaterThan(3);
    for (const tab of tabs) {
      expect(isSavable(tab.path)).toBe(tab.built);
    }
  });

  it("is never the library itself, one resource's page, or an address the navigation lacks", () => {
    expect(isSavable(LIBRARY_PATH)).toBe(false);
    expect(isSavable('/inventory/resources/node-1')).toBe(false);
    expect(isSavable('/nowhere')).toBe(false);
  });
});

describe('Save view', () => {
  it('saves the screen and its query, private unless shared, under the name given', async () => {
    renderAt('/analyze/explorer?group=service&filter=b&filter=a');
    fireEvent.change(screen.getByTestId('save-view-name'), {
      target: { value: '  EC2 by service  ' },
    });
    fireEvent.click(screen.getByTestId('save-view-submit'));

    expect(await screen.findByTestId('save-view-saved')).toHaveTextContent(
      'Saved as EC2 by service, in the Report Library.',
    );
    expect(screen.getByRole('link', { name: 'Report Library' })).toHaveAttribute(
      'href',
      LIBRARY_PATH,
    );
    expect(posted).toEqual(['/api/v1/reports/views']);
    expect(postedBodies).toEqual([
      {
        name: 'EC2 by service',
        screen_path: '/analyze/explorer',
        query: { group: 'service', filter: ['b', 'a'] },
        visibility: 'PRIVATE',
      },
    ]);
  });

  it('shares when asked to, and says a refusal in the words the API gave', async () => {
    const refusal = new ApiError(
      422,
      '{"detail":[{"msg":"Value error, a saved view needs a name that is not blank"}]}',
    );
    renderAt('/analyze/explorer', refusal);
    fireEvent.click(screen.getByTestId('save-view-shared'));
    fireEvent.click(screen.getByTestId('save-view-submit'));

    expect(await screen.findByTestId('save-view-failure')).toHaveTextContent(
      'a saved view needs a name that is not blank',
    );
    expect(postedBodies).toEqual([expect.objectContaining({ visibility: 'SHARED' })]);
    expect(screen.queryByTestId('save-view-saved')).toBeNull();
  });

  it('is named after its screen, and will not save a name that is blank', () => {
    renderAt('/plan/budgets');
    const name = screen.getByTestId('save-view-name');
    expect(name).toHaveValue(screenFor('/plan/budgets')?.label);
    fireEvent.change(name, { target: { value: '   ' } });
    expect(screen.getByTestId('save-view-submit')).toBeDisabled();
  });

  it('says before anything is shared that a view keeps no figures', () => {
    renderAt('/plan/budgets');
    expect(screen.getByTestId('save-view-note')).toHaveTextContent(
      'Keeps this screen and its filters, never its figures.',
    );
  });

  it('is not offered where no view can be saved', () => {
    const unbuilt = allScreens().find((one) => one.arrives !== null);
    expect(unbuilt).toBeDefined();
    for (const path of [LIBRARY_PATH, '/inventory/resources/node-1', unbuilt?.path ?? '']) {
      const { unmount } = renderAt(path);
      expect(screen.queryByTestId('save-view')).toBeNull();
      unmount();
    }
  });

  it('has no accessibility violations', async () => {
    const { container } = renderAt('/plan/budgets');
    expect(await violationsIn(container)).toEqual([]);
  });
});
