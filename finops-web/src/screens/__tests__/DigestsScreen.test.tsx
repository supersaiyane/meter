import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ApiClient } from '../../api/client';
import {
  UNSENT,
  digestsFixture,
  executiveDigest,
  teamDigest,
} from '../../api/fixtures/assistant';
import type { ApiDigest, ApiEnvelope } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { AppShell } from '../../shell/AppShell';
import { DigestsScreen } from '../DigestsScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

/**
 * FEAT-041, TASK-P7-012. Digests, composed whether or not anybody can send them.
 *
 * The failure guarded is a digest nobody could send rendered as if it went somewhere, or
 * rendered as nothing, when it is the state every deployment is in until OPEN-11 names a
 * sender. The second is a digest whose figures cannot be checked: it obeys the rule an answer
 * obeys, so it is drawn by the answer's own citation component and checked the same way.
 */

const PATH = '/api/v1/assistant/digests';
const NOW = new Date('2026-10-04T09:00:00Z');

function clientFor(fixture: ApiEnvelope<ApiDigest[]> = digestsFixture()): ApiClient {
  return clientReturning({ [PATH]: fixture });
}

function renderScreen(fixture?: ApiEnvelope<ApiDigest[]>) {
  return render(
    <Harness client={clientFor(fixture)} initialPath="/assistant/digests">
      <DigestsScreen />
    </Harness>,
  );
}

async function digestFor(digest: ApiDigest): Promise<HTMLElement> {
  const all = await screen.findAllByTestId('digest');
  const found = all.find((one) => one.dataset['audience'] === digest.audience);
  if (found === undefined) {
    throw new Error(`no ${digest.audience} digest on the page`);
  }
  return found;
}

describe('DigestsScreen', () => {
  it('says who each digest is for, the week it covers and when it was composed', async () => {
    renderScreen();
    const executive = await digestFor(executiveDigest());
    expect(within(executive).getByTestId('digest-audience')).toHaveTextContent(
      'The organization',
    );
    expect(within(executive).getByTestId('digest-week')).toHaveTextContent(
      'Executive digest for the week 2026-09-21 to 2026-09-27, composed 2026-09-28 06:00 UTC.',
    );
    const team = await digestFor(teamDigest());
    expect(within(team).getByTestId('digest-audience')).toHaveTextContent('Team payments');
    expect(within(team).getByTestId('digest-week')).toHaveTextContent(
      'Team digest for the week',
    );
  });

  it('says composed and not sent, with the reason that was stored', async () => {
    renderScreen();
    const team = await digestFor(teamDigest());
    expect(team).toHaveAttribute('data-sent', 'false');
    const unsent = within(team).getByTestId('digest-unsent');
    expect(unsent).toHaveTextContent('Composed and not sent.');
    expect(unsent).toHaveTextContent(UNSENT);
    expect(within(team).queryByTestId('digest-sent')).toBeNull();
  });

  it('says when a sent digest was sent, and nothing about a reason it does not have', async () => {
    renderScreen();
    const executive = await digestFor(executiveDigest());
    expect(executive).toHaveAttribute('data-sent', 'true');
    expect(within(executive).getByTestId('digest-sent')).toHaveTextContent(
      'Sent 2026-09-28 06:05 UTC.',
    );
    expect(within(executive).queryByTestId('digest-unsent')).toBeNull();
  });

  it('draws the prose with the answer citations, every value traced to its entry', async () => {
    renderScreen();
    for (const fixture of [executiveDigest(), teamDigest()]) {
      const digest = await digestFor(fixture);
      const prose = within(digest).getByTestId('cited-prose');
      expect(prose.textContent).not.toMatch(/\{\{|\}\}/);
      const entries = within(digest).getAllByTestId('citation');
      expect(entries).toHaveLength(fixture.citations.length);
      for (const marker of within(prose).getAllByTestId('citation-marker')) {
        const target = document.getElementById((marker.getAttribute('href') ?? '').slice(1));
        expect(entries).toContain(target);
      }
      // Every figure in a digest is spend read from the bill, so measured, and money.
      for (const figure of within(prose).getAllByTestId('figure')) {
        expect(figure).toHaveAttribute('data-provenance', 'measured');
        expect(figure).toHaveTextContent('$');
      }
    }
    const executive = await digestFor(executiveDigest());
    // Each value followed by its bracketed marker, so copied out of the page a date and the
    // number of its citation do not run together.
    expect(within(executive).getByTestId('cited-prose')).toHaveTextContent(
      'In the week to 2026-09-27[1], the organization spent $27,410.55 measured[2]',
    );
  });

  it('tells a narrowed reader digests need organization wide scope, not that none exist', async () => {
    const fixture = digestsFixture();
    renderScreen({
      data: [],
      meta: {
        ...fixture.meta,
        as_of: null,
        collected_at: null,
        scope_coverage: { visible: 0, total: 1, is_partial: true, unit: 'payer' },
        degraded: true,
      },
    });
    await waitFor(() => {
      expect(screen.getByTestId('state')).toHaveAttribute('data-state', 'partial');
    });
    expect(screen.getByTestId('state')).toHaveTextContent('organization wide scope');
    expect(screen.queryByText(/Not yet collected/)).toBeNull();
  });

  it('says a digest has never been composed when none has', async () => {
    const fixture = digestsFixture();
    renderScreen({ data: [], meta: { ...fixture.meta, as_of: null, collected_at: null } });
    await waitFor(() => {
      expect(screen.getByTestId('state')).toHaveAttribute('data-state', 'never-collected');
    });
    expect(screen.getByTestId('state')).toHaveTextContent('Not yet collected by team_digests.');
  });

  it('reports its coverage and freshness to the trust strip, as every screen does', async () => {
    render(
      <Harness client={clientFor()} initialPath="/assistant/digests">
        <AppShell now={NOW}>
          <DigestsScreen />
        </AppShell>
      </Harness>,
    );
    await screen.findAllByTestId('digest');
    expect(screen.getByTestId('coverage')).toHaveTextContent('Showing all 1 payer');
    const freshness = screen.getByTestId('global-freshness');
    expect(freshness).toHaveAttribute('data-state', 'collected');
    expect(freshness).toHaveTextContent('as of 2026-09-28 04:00');
  });
});

describe('accessibility', () => {
  it('has no violations inside the shell, and meets every heading level in order', async () => {
    // Inside the shell, because the page heading is the shell's, and a screen whose own first
    // heading sits two levels under it passes alone and fails on the page.
    const { container } = render(
      <Harness client={clientFor()} initialPath="/assistant/digests">
        <AppShell now={NOW}>
          <DigestsScreen />
        </AppShell>
      </Harness>,
    );
    await screen.findAllByTestId('digest');
    const levels = [...container.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
      Number(heading.tagName.slice(1)),
    );
    expect(levels.slice(0, 3)).toEqual([1, 2, 3]);
    expect(levels.slice(1).every((level, index) => level - (levels[index] ?? level) <= 1)).toBe(
      true,
    );
    expect(await violationsIn(container)).toEqual([]);
  });
});
