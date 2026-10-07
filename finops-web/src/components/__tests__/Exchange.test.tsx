import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import {
  answeredExchange,
  refusedWithScreen,
  throttledExchange,
} from '../../api/fixtures/assistant';
import type { ApiExchange } from '../../api/types';
import { Exchange } from '../Exchange';

/**
 * The branches of one exchange that exist for what the API should never send.
 *
 * Each case here is a value that would do harm if drawn the obvious way: a screen path that
 * leaves the application, a gap named after a prototype property, a shape the outcome promised
 * and did not carry, a cost that is not a number. The screen tests cover what the API does send.
 * These fail if a safety branch is taken out.
 */

function renderExchange(exchange: ApiExchange) {
  return render(
    <MemoryRouter>
      <Exchange exchange={exchange} />
    </MemoryRouter>,
  );
}

function refusalWith(change: { readonly screen?: string | null; readonly gap?: string }) {
  const base = refusedWithScreen();
  if (base.refusal === null) {
    throw new Error('the refusal fixture carries no refusal, so these cases would be vacuous');
  }
  return { ...base, refusal: { ...base.refusal, ...change } };
}

/** The drift node an exchange draws for a shape it cannot draw honestly. */
function drift(container: HTMLElement): HTMLElement {
  const found = container.querySelector('[data-cause="SchemaDrift"]');
  if (!(found instanceof HTMLElement)) {
    throw new Error('no unrecognised state was drawn');
  }
  return found;
}

describe('a refusal screen path', () => {
  it('links a screen the navigation lists, to the navigation own path', () => {
    renderExchange(refusalWith({ screen: '/analyze/kubernetes-cost' }));
    const link = screen.getByRole('link', { name: 'Analyze, Kubernetes cost' });
    expect(link).toHaveAttribute('href', '/analyze/kubernetes-cost');
  });

  it('follows a screen that moved in P8, so an answer stored before the move keeps its link', () => {
    renderExchange(refusalWith({ screen: '/cost/containers' }));
    const link = screen.getByRole('link', { name: 'Analyze, Kubernetes cost' });
    expect(link).toHaveAttribute('href', '/analyze/kubernetes-cost');
  });

  it('never links a path the navigation does not list, however it is written', () => {
    // Each of these leaves the application. A slash then a backslash, a tab or a newline, and
    // then another slash, all resolve to another host under the URL parser browsers use.
    for (const path of ['//x', '/\\x', '/\t/x', '/\n/x', 'javascript:alert(1)', '/cost/']) {
      const { container, unmount } = renderExchange(refusalWith({ screen: path }));
      const refusal = within(container).getByTestId('refusal');
      expect(refusal.querySelector('a')).toBeNull();
      expect(
        within(refusal).getByTestId('refusal-screen').querySelector('code')?.textContent,
      ).toBe(path);
      unmount();
    }
  });

  it('draws an empty path as no screen at all', () => {
    for (const path of ['', '   ']) {
      const { container, unmount } = renderExchange(refusalWith({ screen: path }));
      const refusal = within(container).getByTestId('refusal');
      expect(within(refusal).queryByTestId('refusal-screen')).toBeNull();
      expect(refusal.querySelector('a')).toBeNull();
      unmount();
    }
  });
});

describe('a gap with no words for it', () => {
  it('is named by its own text, including one that is a prototype property', () => {
    for (const gap of ['__proto__', 'constructor', 'hasOwnProperty', 'weather']) {
      const { container, unmount } = renderExchange(refusalWith({ gap }));
      expect(within(container).getByTestId('refusal-gap')).toHaveTextContent(
        `the gap reported is ${gap}`,
      );
      unmount();
    }
  });
});

describe('a shape the exchange does not carry', () => {
  it('draws an answered exchange with no answer as unrecognised, not as an empty answer', () => {
    const { container } = renderExchange({ ...answeredExchange(), answer: null });
    expect(screen.queryByTestId('answer')).toBeNull();
    expect(drift(container)).toHaveTextContent('UNRECOGNISED');
    expect(drift(container)).toHaveTextContent('says ANSWERED');
  });

  it('draws an outcome that is none of the three as unrecognised, not as nothing', () => {
    const outcome = 'PONDERED' as unknown as ApiExchange['outcome'];
    const { container } = renderExchange({ ...answeredExchange(), outcome });
    expect(screen.queryByTestId('answer')).toBeNull();
    expect(drift(container)).toHaveTextContent('says PONDERED');
  });
});

describe('a failure cause this screen does not know', () => {
  it('is shown by its name, with the remediation the API wrote', () => {
    renderExchange({
      ...throttledExchange(),
      failure: { cause: 'Exploded', detail: null, remediation: 'Ask again tomorrow.' },
    });
    const failure = screen.getByTestId('exchange-failure');
    expect(failure).toHaveAttribute('data-cause', 'Exploded');
    expect(failure).toHaveTextContent('Exploded. Ask again tomorrow.');
  });
});

describe('an estimated cost that is not a number', () => {
  it('is drawn as unrecognised, never as zero', () => {
    for (const est_cost of ['n/a', '', 'NaN']) {
      const { unmount } = renderExchange({ ...answeredExchange(), est_cost });
      const cost = screen.getByTestId('exchange-cost');
      expect(cost).toHaveTextContent('UNRECOGNISED');
      expect(within(cost).queryByTestId('figure')).toBeNull();
      expect(cost.textContent).not.toContain('$');
      expect(cost.textContent).not.toMatch(/0/);
      unmount();
    }
  });
});
