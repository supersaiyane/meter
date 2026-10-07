import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { EnforcementScreen } from '../EnforcementScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { violationsIn } from '../../components/__tests__/axe';

const THROTTLE = '33333333-3333-3333-3333-333333333333';
const NOW = new Date('2026-09-06T10:00:00Z');

function renderEnforcement() {
  return render(
    <Harness client={clientReturning({})}>
      <EnforcementScreen now={NOW} />
    </Harness>,
  );
}

function rowFor(text: string): HTMLElement {
  const row = screen.getByText(text).closest('tr');
  if (row === null) {
    throw new Error(`no row for ${text}`);
  }
  return row;
}

describe('EnforcementScreen', () => {
  it('shows expiry as an absolute time and a countdown together', async () => {
    // An incident bridge needs "how long do I have" and "when exactly". A
    // countdown alone cannot be written into an incident log.
    const cell = await (renderEnforcement(), screen.findByTestId(`expires-${THROTTLE}`));
    expect(cell).toHaveTextContent('10:45');
    expect(cell).toHaveTextContent(/45 min/);
  });

  it('states the zone, because an absolute time without one is ambiguous', async () => {
    renderEnforcement();
    expect(await screen.findByTestId(`expires-${THROTTLE}`)).toHaveTextContent('UTC');
  });

  it('offers revoke on an action the API says is revocable', async () => {
    renderEnforcement();
    await screen.findByTestId(`expires-${THROTTLE}`);
    const row = rowFor('arn:aws:iam::role/grafana-datasource');
    expect(within(row).getByRole('button', { name: /revoke/i })).toBeInTheDocument();
  });

  it('omits revoke entirely, rather than disabling it, when it is not revocable', async () => {
    // A control that looks available and is not is worse than an absent one.
    // The write level is the API's decision, per architectural constraint 8.
    renderEnforcement();
    await screen.findByTestId(`expires-${THROTTLE}`);
    const row = rowFor('arn:aws:iam::role/reporting');
    expect(within(row).queryByRole('button', { name: /revoke/i })).toBeNull();
    expect(row.querySelector('button[disabled]')).toBeNull();
  });

  it('says an action does not expire rather than leaving the cell empty', async () => {
    renderEnforcement();
    await screen.findByTestId(`expires-${THROTTLE}`);
    const row = rowFor('arn:aws:iam::role/reporting');
    expect(row).toHaveTextContent(/does not expire/i);
  });

  it('links an action to the finding that caused it', async () => {
    renderEnforcement();
    await screen.findByTestId(`expires-${THROTTLE}`);
    const row = rowFor('arn:aws:iam::role/grafana-datasource');
    expect(within(row).getByRole('link', { name: /why/i })).toHaveAttribute(
      'href',
      '/govern/query-cost/findings/11111111-1111-1111-1111-111111111111',
    );
  });

  it('says revoke did nothing rather than failing silently on a fixture', async () => {
    // A button that does nothing when clicked is the failure this product
    // spends its whole design budget avoiding.
    renderEnforcement();
    await screen.findByTestId(`expires-${THROTTLE}`);
    const row = rowFor('arn:aws:iam::role/grafana-datasource');
    await userEvent.click(within(row).getByRole('button', { name: /revoke/i }));
    expect(screen.getByTestId('revoke-note')).toHaveTextContent(/not connected yet/i);
    expect(screen.getByTestId('revoke-note')).toHaveTextContent(/was not changed/i);
  });

  it('says so while it is running on a fixture', async () => {
    renderEnforcement();
    expect(await screen.findByTestId('fixture-band')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderEnforcement();
    await screen.findByRole('table');
    expect(await violationsIn(container)).toEqual([]);
  });
});
