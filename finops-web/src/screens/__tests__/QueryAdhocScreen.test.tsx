import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QueryAdhocScreen } from '../QueryAdhocScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { adhocQueriesFixture } from '../../api/fixtures/query';
import { violationsIn } from '../../components/__tests__/axe';

function renderAdhoc() {
  return render(
    <Harness client={clientReturning({ '/api/v1/query/adhoc': adhocQueriesFixture() })}>
      <QueryAdhocScreen />
    </Harness>,
  );
}

function rowContaining(text: string): HTMLElement {
  const row = screen.getByText(text, { exact: false }).closest('tr');
  if (row === null) {
    throw new Error(`no row containing ${text}`);
  }
  return row;
}

describe('QueryAdhocScreen', () => {
  it('names the person who ran it', async () => {
    // The point of the screen. A cost with no name attached is a number nobody
    // can act on, and the action here is a conversation rather than a control.
    renderAdhoc();
    expect(await screen.findByText('bob@example.com')).toBeInTheDocument();
  });

  it('reports a query nobody can be traced to, rather than dropping it', async () => {
    // An expensive query with no owner is the case this feature exists for, so
    // a null principal is named and ranked beside the rest.
    renderAdhoc();
    await screen.findByText('bob@example.com');
    const row = rowContaining('stats count() by bin(5m)');
    expect(within(row).getByText('unattributed')).toBeInTheDocument();
  });

  it('renders every cost as measured and never as modelled', async () => {
    // An ad hoc query exists only in the evidence. There is no definition to
    // model it from, so a modelled figure here would be an invention rather
    // than an estimate.
    renderAdhoc();
    await screen.findByText('bob@example.com');
    const figures = document.querySelectorAll('[data-testid="figure"]');
    expect(figures.length).toBeGreaterThan(0);
    for (const figure of figures) {
      expect(figure.getAttribute('data-provenance')).toBe('measured');
    }
  });

  it('shows the query whole, because a shortened one is unrecognisable', async () => {
    // The reader has to recognise their own query to act on it. Truncating it
    // would make the row unactionable while still looking informative.
    renderAdhoc();
    expect(
      await screen.findByText(
        'fields @timestamp, @message | filter @message like /timeout/ | sort @timestamp desc',
      ),
    ).toBeInTheDocument();
  });

  it('puts the most expensive first', async () => {
    renderAdhoc();
    await screen.findByText('bob@example.com');
    const rows = [...document.querySelectorAll('tbody tr')];
    expect(rows[0]?.textContent).toContain('54.00');
    expect(rows[1]?.textContent).toContain('4.50');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderAdhoc();
    await screen.findByText('bob@example.com');
    expect(await violationsIn(container)).toEqual([]);
  });
});
