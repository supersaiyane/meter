import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ApiQueryFindingDetail, ApiRemediation } from '../../api/types';
import { QUERY_FINDING_DETAILS } from '../../api/fixtures/query';
import { RemediationControls } from '../RemediationControls';
import { Harness } from './Harness';
import { clientReturning, metaOf, posted } from './fixtures';

const BASE = QUERY_FINDING_DETAILS[
  '11111111-1111-1111-1111-111111111111'
] as ApiQueryFindingDetail;
const APPLY = `/api/v1/query/remediate/${BASE.finding_id}`;
const UNDO = `${APPLY}/undo`;

function outcome(partial: Partial<ApiRemediation> = {}): ApiRemediation {
  return {
    finding_id: BASE.finding_id,
    applied: true,
    reverted: false,
    detail: '',
    change_id: 'aaaaaaaa-0000-4000-8000-000000000001',
    ...partial,
  };
}

function renderControls(detail: ApiQueryFindingDetail, answer: ApiRemediation) {
  return render(
    <Harness
      client={clientReturning({
        [APPLY]: { data: answer, meta: metaOf() },
        [UNDO]: { data: answer, meta: metaOf() },
      })}
    >
      <RemediationControls detail={detail} />
    </Harness>,
  );
}

describe('RemediationControls', () => {
  beforeEach(() => {
    posted.length = 0;
  });

  it('offers no undo when there is nothing to undo', () => {
    // Absent, not disabled. A control that looks available and does nothing is
    // worse than one that is not there.
    renderControls({ ...BASE, applied_change_id: null }, outcome());
    expect(screen.queryByTestId('undo')).toBeNull();
    expect(screen.getByTestId('remediate')).toBeInTheDocument();
  });

  it('offers no remediation when a change is still applied', () => {
    // The two are never both present. A second remediation on top of one
    // already applied would be the first one's undo under a different name.
    renderControls({ ...BASE, applied_change_id: 'a-change' }, outcome());
    expect(screen.queryByTestId('remediate')).toBeNull();
    expect(screen.getByTestId('undo')).toBeInTheDocument();
  });

  it('undoes through the route the server exposes', async () => {
    renderControls({ ...BASE, applied_change_id: 'a-change' }, outcome());
    await userEvent.click(screen.getByTestId('undo'));
    await waitFor(() => {
      expect(screen.getByTestId('remediation-outcome')).toBeInTheDocument();
    });
    expect(posted).toEqual([UNDO]);
  });

  it('shows a refusal in the words the server used', async () => {
    // The server knows why it refused. The screen paraphrasing it would be a
    // second, worse explanation of the same thing.
    const refused = outcome({
      applied: false,
      change_id: null,
      detail: 'write level is none, and a panel rewrite needs full',
    });
    renderControls({ ...BASE, applied_change_id: null }, refused);
    await userEvent.click(screen.getByTestId('remediate'));
    await waitFor(() => {
      expect(screen.getByText(/write level is none/)).toBeInTheDocument();
    });
    expect(screen.getByTestId('remediation-outcome').dataset['applied']).toBe('false');
  });

  it('does not report success for a write that reverted itself', async () => {
    // The estate is unchanged. A screen claiming otherwise would leave a reader
    // believing a panel was fixed when it was put straight back.
    const reverted = outcome({
      applied: false,
      reverted: true,
      change_id: null,
      detail: 'the element did not match what was written, so it was reverted',
    });
    renderControls({ ...BASE, applied_change_id: null }, reverted);
    await userEvent.click(screen.getByTestId('remediate'));
    await waitFor(() => {
      expect(screen.getByText(/reverted/)).toBeInTheDocument();
    });
    expect(screen.getByTestId('remediation-outcome').dataset['applied']).toBe('false');
  });
});
