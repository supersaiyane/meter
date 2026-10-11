import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ledgerCreditsFixture, ledgerFixture } from '../../api/fixtures/ledger';
import { violationsIn } from '../../components/__tests__/axe';
import { LedgerScreen } from '../LedgerScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

function renderLedger() {
  return render(
    <Harness
      client={clientReturning({
        '/api/v1/savings/ledger': ledgerFixture(),
        '/api/v1/savings/ledger/credits': ledgerCreditsFixture(),
      })}
    >
      <LedgerScreen />
    </Harness>,
  );
}

describe('LedgerScreen, FEAT-078', () => {
  it('ranks teams by the saving their verified changes held', async () => {
    renderLedger();
    await screen.findByTestId('team-platform');
    const teams = screen
      .getAllByRole('button', { pressed: false })
      .map((one) => one.textContent);
    expect(teams).toEqual(['platform', 'payments', 'No team named']);
  });

  it('names no person until a team is chosen, and then only on its own credits', async () => {
    renderLedger();
    await screen.findByTestId('team-platform');
    expect(screen.queryByText('alice')).toBeNull();
    expect(screen.queryByTestId('ledger-credits')).toBeNull();
    fireEvent.click(screen.getByTestId('team-platform'));
    const credits = await screen.findByTestId('ledger-credits');
    expect(within(credits).getByText('alice')).toBeInTheDocument();
    expect(within(credits).queryByText('carol')).toBeNull();
  });

  it('says each month in words, and a regression stops the credit', async () => {
    renderLedger();
    fireEvent.click(await screen.findByTestId('team-platform'));
    expect(
      await screen.findByTestId('months-6a1f2b3c-4d5e-4f60-8a1b-2c3d4e5f6a70'),
    ).toHaveTextContent('October 2026: held, November 2026: held');
    expect(screen.getByTestId('months-7b2a3c4d-5e6f-4a71-9b2c-3d4e5f6a7b81')).toHaveTextContent(
      'November 2026: regressed. Stopped: a month cost as much as before',
    );
  });

  it('says a month the bill holds nothing for was not observed, never a zero', async () => {
    renderLedger();
    fireEvent.click(await screen.findByTestId('team-payments'));
    expect(
      await screen.findByTestId('months-8c3b4d5e-6f70-4b82-8c3d-4e5f6a7b8c92'),
    ).toHaveTextContent('October 2026: not observed');
  });

  it('shows the credits no source named a team for under their own heading', async () => {
    renderLedger();
    fireEvent.click(await screen.findByTestId('team-none'));
    const credits = await screen.findByTestId('ledger-credits');
    expect(within(credits).getByRole('heading', { name: 'No team named' })).toBeInTheDocument();
    expect(
      within(credits).getByTestId('months-9d4c5e6f-7081-4c93-9d4e-5f6a7b8c9da3'),
    ).toHaveTextContent('no month closed yet');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderLedger();
    fireEvent.click(await screen.findByTestId('team-platform'));
    await screen.findByTestId('ledger-credits');
    expect(await violationsIn(container)).toEqual([]);
  });
});
