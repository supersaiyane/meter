import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { WasteScreen } from '../WasteScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf, posted, postedBodies } from './fixtures';
import {
  alternativesFixture,
  recommendationsFixture,
  refusalsFixture,
} from '../../api/fixtures/waste';
import { FIXES, askPath } from '../../api/remediation';
import type { ApiEnvelope, ApiFix, ApiFixes } from '../../api/types';

/**
 * A recommendation's fix, TASK-P15-008, FEAT-092: under the one finding a reader chose on the
 * recommendations screen, ask for it, read its pull request and steps, and read why where there
 * is none.
 */

const ACCEPTED = '3a4b5c6d-7e8f-4a0b-9c1d-2e3f4a5b6c7d';
const OPEN = '2f3c1d4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f';

function fixOf(partial: Partial<ApiFix> = {}): ApiFix {
  return {
    fix_id: 'fix-1',
    recommendation_id: ACCEPTED,
    sub_account_id: 'fake-platform-a',
    status: 'REQUESTED',
    repository: null,
    branch: null,
    number: null,
    url: null,
    note: null,
    requested_by: 'owner@example.local',
    requested_at: '2026-10-15T10:00:00Z',
    merged_by: null,
    merged_at: null,
    closed_at: null,
    reason: null,
    failure_cause: null,
    steps: [
      {
        from_status: null,
        to_status: 'REQUESTED',
        principal: 'owner@example.local',
        note: null,
        at: '2026-10-15T10:00:00Z',
      },
    ],
    ...partial,
  };
}

function envelope<T>(data: T): ApiEnvelope<T> {
  return { data, meta: metaOf() };
}

function renderAt(id: string, fixes: readonly ApiFix[], ask?: ApiFix) {
  return render(
    <Harness
      initialPath={`/optimize?finding=${id}`}
      client={clientReturning({
        '/api/v1/waste/recommendations': recommendationsFixture(),
        '/api/v1/waste/refusals': refusalsFixture(),
        [`/api/v1/waste/recommendations/${id}/alternatives`]: alternativesFixture(id),
        [FIXES]: envelope<ApiFixes>({ fixes }),
        ...(ask === undefined ? {} : { [askPath(id)]: envelope(ask) }),
      })}
    >
      <WasteScreen />
    </Harness>,
  );
}

beforeEach(() => {
  posted.length = 0;
  postedBodies.length = 0;
});

describe('a recommendation fix', () => {
  it('asks for a pull request for an accepted recommendation, with the note', async () => {
    renderAt(ACCEPTED, [], fixOf());
    const form = await screen.findByTestId('fix-ask');
    expect(screen.getByTestId('fix-none')).toHaveTextContent('No fix has been asked for.');
    await userEvent.type(within(form).getByRole('textbox'), '  storage agrees  ');
    await userEvent.click(within(form).getByRole('button', { name: 'Ask for a pull request' }));
    expect(posted).toContain(askPath(ACCEPTED));
    expect(postedBodies.at(-1)).toEqual({ note: 'storage agrees' });
  });

  it('asks a reader to accept the recommendation first', async () => {
    renderAt(OPEN, []);
    const first = await screen.findByTestId('fix-accept-first');
    expect(first).toHaveTextContent('accepted with an owner');
    expect(first).toHaveTextContent('It is open.');
    expect(screen.queryByTestId('fix-ask')).toBeNull();
  });

  it('shows the open pull request and its steps, and offers no second ask', async () => {
    const open = fixOf({
      status: 'OPEN',
      repository: 'acme/infra',
      number: 7,
      url: 'https://github.com/acme/infra/pull/7',
      steps: [
        ...fixOf().steps,
        {
          from_status: 'REQUESTED',
          to_status: 'OPEN',
          principal: 'meter',
          note: 'Opened #7',
          at: '2026-10-15T10:10:00Z',
        },
      ],
    });
    renderAt(ACCEPTED, [open]);
    const said = await screen.findByTestId('fix-said');
    expect(said).toHaveTextContent('Pull request #7 is open in acme/infra.');
    expect(within(said).getByRole('link', { name: 'Open the pull request' })).toHaveAttribute(
      'href',
      'https://github.com/acme/infra/pull/7',
    );
    expect(within(screen.getByTestId('fix-steps')).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByTestId('fix-steps')).toHaveTextContent('open by meter: Opened #7');
    expect(screen.queryByTestId('fix-ask')).toBeNull();
  });

  it('says why there is no pull request, and lets the person ask again', async () => {
    const none = fixOf({
      status: 'NOT_AUTHORED',
      reason: 'No repository is mapped for the state s3://state/storage.tfstate.',
    });
    renderAt(ACCEPTED, [none]);
    expect(await screen.findByTestId('fix-said')).toHaveTextContent(
      'No pull request: No repository is mapped for the state s3://state/storage.tfstate.',
    );
    expect(screen.getByTestId('fix-ask')).toBeInTheDocument();
  });

  it("shows a refused ask in the API's own words", async () => {
    renderAt(ACCEPTED, []);
    const form = await screen.findByTestId('fix-ask');
    await userEvent.click(within(form).getByRole('button', { name: 'Ask for a pull request' }));
    expect(await screen.findByTestId('fix-ask-refused')).toHaveTextContent('no stub for');
  });
});
