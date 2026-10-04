import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiError, type ApiClient } from '../../api/client';
import {
  NOT_ENABLED,
  REMEDIATION,
  answeredExchange,
  askFixture,
  exchangesFixture,
  notEnabledExchange,
  redactionsFixture,
  refusedSecret,
  refusedWithScreen,
  throttledExchange,
} from '../../api/fixtures/assistant';
import type { ApiEnvelope, ApiExchange } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { AppShell } from '../../shell/AppShell';
import { AssistantScreen } from '../AssistantScreen';
import { stampUtc } from '../enforcementTime';
import { Harness } from './Harness';
import { clientReturning, posted, postedBodies } from './fixtures';

/**
 * FEAT-038 and FEAT-042, TASK-P7-011. The screen where the citations matter more than the
 * prose.
 *
 * The failure guarded first is a figure a reader cannot trace: a number in an answer with no
 * way to see which call it was read from, which is the arrangement where a hallucinated figure
 * and a real one look identical. So the answer test walks every value from the sentence to its
 * citation and from the citation to the call, by the links a reader would follow.
 *
 * The second is three outcomes collapsing into fewer. A refusal drawn as an error, a deployment
 * with no model drawn as broken, or a failure drawn as an empty answer.
 */

const EXCHANGES = '/api/v1/assistant/exchanges';
const REDACTIONS = '/api/v1/assistant/redactions';
const ASK = '/api/v1/assistant/ask';

function clientFor(ask: ApiEnvelope<ApiExchange> = askFixture()): ApiClient {
  return clientReturning({
    [EXCHANGES]: exchangesFixture(),
    [REDACTIONS]: redactionsFixture(),
    [ASK]: ask,
  });
}

function renderScreen(client: ApiClient = clientFor()) {
  return render(
    <Harness client={client} initialPath="/assistant">
      <AssistantScreen />
    </Harness>,
  );
}

/** The history entry for one fixture exchange, found by what it is rather than by position. */
async function entryFor(exchange: ApiExchange): Promise<HTMLElement> {
  const history = await screen.findByTestId('assistant-history');
  const found = within(history)
    .getAllByTestId('exchange')
    .find((one) => one.id === `exchange-${exchange.exchange_id}`);
  if (found === undefined) {
    throw new Error(`the history has no entry for ${exchange.exchange_id}`);
  }
  return found;
}

/** The element a fragment link points at, so a test follows a link the way a reader does. */
function landing(link: Element | null): HTMLElement {
  const href = link?.getAttribute('href') ?? '';
  expect(href.startsWith('#')).toBe(true);
  const target = document.getElementById(href.slice(1));
  if (target === null) {
    throw new Error(`${href} points at nothing on the page`);
  }
  return target;
}

describe('AssistantScreen, an answer', () => {
  it('traces every value from the sentence to its citation and from there to its call', async () => {
    renderScreen();
    const fixture = answeredExchange();
    const entry = await entryFor(fixture);
    const answer = within(entry).getByTestId('answer');
    const citations = fixture.answer?.citations ?? [];
    expect(citations.length).toBeGreaterThan(0);

    for (const citation of citations) {
      const value = answer.querySelector(
        `[data-testid="cited-value"][data-placeholder="${citation.placeholder}"]`,
      );
      if (!(value instanceof HTMLElement)) {
        throw new Error(`${citation.placeholder} is not in the sentence`);
      }
      // A figure is a Figure, carrying the provenance it was cited with. A label is its text.
      if (citation.kind === 'figure') {
        expect(within(value).getByTestId('figure')).toHaveAttribute(
          'data-provenance',
          citation.provenance,
        );
      } else {
        expect(within(value).getByTestId('cited-label')).toHaveTextContent(citation.value);
      }

      // From the marker to the entry that names the tool, the call, the field and as_of.
      const cited = landing(within(value).getByTestId('citation-marker'));
      expect(cited).toHaveAttribute('data-testid', 'citation');
      expect(within(cited).getByTestId('citation-tool')).toHaveTextContent(citation.tool);
      expect(within(cited).getByTestId('citation-call')).toHaveTextContent(citation.call_id);
      expect(within(cited).getByTestId('citation-field')).toHaveTextContent(citation.field);
      expect(within(cited).getByTestId('citation-as-of')).toHaveTextContent(
        stampUtc(citation.as_of),
      );

      // And from the entry to the call the exchange actually made.
      const call = landing(within(cited).getByTestId('citation-call').closest('a'));
      expect(call).toHaveAttribute('data-testid', 'tool-call');
      expect(within(call).getByTestId('tool-call-id')).toHaveTextContent(citation.call_id);
      expect(within(call).getByTestId('tool-call-tool')).toHaveTextContent(citation.tool);
    }
  });

  it('puts the cited values into the prose and leaves no placeholder behind', async () => {
    renderScreen();
    const entry = await entryFor(answeredExchange());
    const prose = within(entry).getByTestId('cited-prose');
    expect(prose.textContent).not.toMatch(/\{\{|\}\}/);
    // The figures as the Figure formats them, and the label as it was cited.
    expect(prose).toHaveTextContent('$3,781.93');
    expect(prose).toHaveTextContent('$6,197.65');
    expect(prose).toHaveTextContent('AmazonEC2');
    expect(prose).toHaveTextContent('$2,043.11');
    // The modelled figure keeps its treatment mid sentence: the tilde and the word.
    expect(prose).toHaveTextContent('~ $412.50 modelled');
  });

  it('lists every call the model made, in order, including the one that never returned', async () => {
    renderScreen();
    const fixture = answeredExchange();
    const entry = await entryFor(fixture);
    const calls = within(entry).getAllByTestId('tool-call');
    expect(calls.map((call) => within(call).getByTestId('tool-call-id').textContent)).toEqual(
      fixture.tool_calls.map((call) => call.call_id),
    );
    const silent = calls.filter((call) => call.dataset['returned'] === 'false');
    expect(silent).toHaveLength(1);
    expect(silent[0]).toHaveTextContent('did not return');
  });
});

describe('AssistantScreen, a refusal', () => {
  it('names what is missing and links the screen that would show it', async () => {
    renderScreen();
    const entry = await entryFor(refusedWithScreen());
    const refusal = within(entry).getByTestId('refusal');
    expect(refusal).toHaveAttribute('data-gap', 'figure');
    expect(within(refusal).getByTestId('refusal-gap')).toHaveTextContent(
      'Not answered: the figure is not there to cite.',
    );
    expect(within(refusal).getByTestId('refusal-reason')).toHaveTextContent(
      'split cost allocation data is not enabled',
    );
    // By the words the navigation uses, and to the route the API named.
    const link = within(refusal).getByRole('link', { name: 'Cost, Containers' });
    expect(link).toHaveAttribute('href', '/cost/containers');
    // A refusal is not an error and not an answer.
    expect(within(entry).queryByTestId('answer')).toBeNull();
    expect(within(entry).queryByTestId('exchange-failure')).toBeNull();
    expect(refusal.querySelector('.meter-failure')).toBeNull();
  });

  it('offers no link when no screen would show it', async () => {
    renderScreen();
    const entry = await entryFor(refusedSecret());
    const refusal = within(entry).getByTestId('refusal');
    expect(within(refusal).getByTestId('refusal-gap')).toHaveTextContent(
      'the question held a secret, so it was sent nowhere',
    );
    expect(within(refusal).queryByTestId('refusal-screen')).toBeNull();
    expect(within(refusal).queryAllByRole('link')).toEqual([]);
  });
});

describe('AssistantScreen, a failure', () => {
  it('names its typed cause, the way every other failure is drawn', async () => {
    renderScreen();
    const fixture = throttledExchange();
    const entry = await entryFor(fixture);
    const failure = within(entry).getByTestId('exchange-failure');
    expect(failure).toHaveAttribute('data-cause', 'Throttled');
    const typed = within(failure).getByRole('status');
    expect(typed).toHaveClass('meter-failure');
    expect(typed).toHaveTextContent('THROTTLED');
    expect(typed).toHaveTextContent(fixture.failure?.remediation ?? 'missing');
    expect(within(failure).getByTestId('failure-detail')).toHaveTextContent(
      fixture.failure?.detail ?? 'missing',
    );
    expect(within(entry).queryByTestId('answer')).toBeNull();
    expect(within(entry).queryByTestId('refusal')).toBeNull();
  });

  it('reads a deployment with no model as not enabled, not as broken', async () => {
    renderScreen();
    const entry = await entryFor(notEnabledExchange());
    const failure = within(entry).getByTestId('exchange-failure');
    expect(failure).toHaveAttribute('data-state', 'not-enabled');
    expect(within(failure).getByTestId('not-enabled')).toHaveTextContent('Not enabled.');
    // What is missing, and how to switch it on, both in the API's words.
    expect(within(failure).getByTestId('failure-detail')).toHaveTextContent(NOT_ENABLED);
    expect(within(failure).getByTestId('failure-remediation')).toHaveTextContent(
      REMEDIATION.NotOptedIn,
    );
    // Not in the failure colour, and not announced as a failure.
    expect(entry.querySelector('.meter-failure')).toBeNull();
    expect(within(entry).getByTestId('exchange-model')).toHaveTextContent('reached no model');
  });

  it('shows the remediation the API wrote for every cause, and none about a collector', async () => {
    // One failed exchange per typed cause, each carrying the API's remediation for it.
    const failures = Object.entries(REMEDIATION).map(([cause, remediation], index) => ({
      ...throttledExchange(),
      exchange_id: `7a1c0f3e-0100-4000-8000-00000000010${String(index)}`,
      question: `A question that failed with ${cause}`,
      failure: { cause, detail: `What happened, for ${cause}.`, remediation },
    }));
    expect(failures).toHaveLength(7);
    renderScreen(
      clientReturning({
        [EXCHANGES]: { ...exchangesFixture(), data: failures },
        [REDACTIONS]: redactionsFixture(),
      }),
    );
    for (const exchange of failures) {
      const entry = await entryFor(exchange);
      const failure = within(entry).getByTestId('exchange-failure');
      expect(failure).toHaveAttribute('data-cause', exchange.failure.cause);
      expect(failure).toHaveTextContent(exchange.failure.remediation);
      expect(failure).toHaveTextContent(exchange.failure.detail);
    }
    expect(screen.getByTestId('assistant-history')).not.toHaveTextContent(/collector/i);
  });
});

describe('AssistantScreen, what each exchange cost', () => {
  it('shows tokens as measured and the estimated cost as modelled on every exchange', async () => {
    renderScreen();
    const history = await screen.findByTestId('assistant-history');
    const entries = within(history).getAllByTestId('exchange');
    expect(entries).toHaveLength(exchangesFixture().data.length);
    for (const entry of entries) {
      for (const tokens of ['exchange-input-tokens', 'exchange-output-tokens']) {
        expect(within(within(entry).getByTestId(tokens)).getByTestId('figure')).toHaveAttribute(
          'data-provenance',
          'measured',
        );
      }
      const cost = within(within(entry).getByTestId('exchange-cost')).getByTestId('figure');
      expect(cost).toHaveAttribute('data-provenance', 'modelled');
      expect(cost).toHaveTextContent('~');
    }
  });

  it('gives the figures and the model the answer was bought from', async () => {
    renderScreen();
    const fixture = answeredExchange();
    const entry = await entryFor(fixture);
    expect(within(entry).getByTestId('exchange-input-tokens')).toHaveTextContent('4,210');
    expect(within(entry).getByTestId('exchange-output-tokens')).toHaveTextContent('286');
    expect(within(entry).getByTestId('exchange-cost')).toHaveTextContent('~ $0.02 modelled');
    expect(within(entry).getByTestId('exchange-model')).toHaveTextContent(
      fixture.model_id ?? '',
    );
  });

  it('says a cost under a cent is under a cent, rather than letting it read as nothing', async () => {
    const cheap = { ...answeredExchange(), est_cost: '0.0031500000' };
    renderScreen(
      clientReturning({
        [EXCHANGES]: { ...exchangesFixture(), data: [cheap] },
        [REDACTIONS]: redactionsFixture(),
      }),
    );
    const entry = await entryFor(cheap);
    expect(within(entry).getByTestId('exchange-cost-small')).toHaveTextContent('under a cent');
  });
});

describe('AssistantScreen, asking', () => {
  beforeEach(() => {
    posted.length = 0;
    postedBodies.length = 0;
  });

  it('offers a labelled question limited to what the API accepts, and no empty question', async () => {
    renderScreen();
    const box = screen.getByLabelText('Your question');
    expect(box).toHaveAttribute('maxLength', '2000');
    expect(screen.getByTestId('ask-submit')).toBeDisabled();
    await userEvent.type(box, '   ');
    expect(screen.getByTestId('ask-submit')).toBeDisabled();
    expect(screen.getByTestId('ask-limit')).toHaveTextContent('3 of 2000 characters.');
  });

  it('sends the question in the body and shows the answer that came back', async () => {
    renderScreen();
    const question = 'What did we spend last month, and which service cost the most?';
    await userEvent.type(screen.getByLabelText('Your question'), question);
    await userEvent.click(screen.getByTestId('ask-submit'));

    const latest = await screen.findByTestId('assistant-latest');
    expect(within(latest).getByTestId('exchange')).toHaveAttribute('data-outcome', 'ANSWERED');
    expect(within(latest).getByTestId('cited-prose')).toHaveTextContent('$3,781.93');
    // In the body and never in the URL, where every access log on the way would keep it.
    expect(posted).toEqual([ASK]);
    expect(postedBodies).toEqual([{ question }]);
    // Shown once, as the latest, and not again at the top of the history.
    await waitFor(() => {
      const history = screen.getByTestId('assistant-history');
      expect(within(history).queryByText(question)).toBeNull();
    });
    expect(screen.getByLabelText('Your question')).toHaveValue('');
  });

  it('disables asking again while the first question is out', async () => {
    let settle: (answer: ApiEnvelope<ApiExchange>) => void = () => undefined;
    const base = clientFor();
    const slow: ApiClient = {
      ...base,
      post: <T,>() =>
        new Promise<ApiEnvelope<T>>((resolve) => {
          settle = (answer) => {
            resolve(answer as ApiEnvelope<T>);
          };
        }),
    };
    renderScreen(slow);
    await userEvent.type(screen.getByLabelText('Your question'), 'Which team spent the most?');
    await userEvent.click(screen.getByTestId('ask-submit'));
    expect(screen.getByTestId('ask-submit')).toBeDisabled();
    expect(screen.getByTestId('ask-status')).toHaveTextContent('Asking.');
    settle(askFixture(notEnabledExchange()));
    const latest = await screen.findByTestId('assistant-latest');
    expect(within(latest).getByTestId('not-enabled')).toBeInTheDocument();
  });

  it('says a failed request failed, and draws no answer for it', async () => {
    const base = clientFor();
    const broken: ApiClient = {
      ...base,
      post: () => Promise.reject(new ApiError(503, 'Service Unavailable')),
    };
    renderScreen(broken);
    await userEvent.type(screen.getByLabelText('Your question'), 'Which team spent the most?');
    await userEvent.click(screen.getByTestId('ask-submit'));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('The request failed, so no answer came back.');
    expect(error).toHaveTextContent('503');
    expect(screen.queryByTestId('assistant-latest')).toBeNull();
    // Kept, so asking again does not mean typing it again.
    expect(screen.getByLabelText('Your question')).toHaveValue('Which team spent the most?');
  });

  it('says how the question ended in the live region, not only that it was asked', async () => {
    // A screen reader heard "Asking" and then nothing, because the region emptied as the
    // result was drawn. It now says how the question ended.
    for (const [exchange, said] of [
      [answeredExchange(), 'Answered, shown below.'],
      [refusedWithScreen(), 'Not answered, shown below.'],
      [throttledExchange(), 'Failed, shown below.'],
      [notEnabledExchange(), 'Not enabled, shown below.'],
    ] as const) {
      const { unmount } = renderScreen(clientFor(askFixture(exchange)));
      await userEvent.type(screen.getByLabelText('Your question'), exchange.question);
      await userEvent.click(screen.getByTestId('ask-submit'));
      await screen.findByTestId('assistant-latest');
      expect(screen.getByTestId('ask-status')).toHaveTextContent(said);
      unmount();
    }
  });

  it('keeps the question when it was refused or failed, and clears it only once answered', async () => {
    for (const exchange of [refusedWithScreen(), throttledExchange(), notEnabledExchange()]) {
      const { unmount } = renderScreen(clientFor(askFixture(exchange)));
      await userEvent.type(
        screen.getByLabelText('Your question'),
        'Which team spent the most?',
      );
      await userEvent.click(screen.getByTestId('ask-submit'));
      await screen.findByTestId('assistant-latest');
      // A minute later, or narrower, without typing it again.
      expect(screen.getByLabelText('Your question')).toHaveValue('Which team spent the most?');
      unmount();
    }
  });

  it('shows the answer without waiting for the lists to be read again', async () => {
    // The lists answer once, and every read after that never comes back. The answer is drawn
    // anyway, because it does not depend on them.
    const base = clientFor();
    const asked = new Set<string>();
    const stalled: ApiClient = {
      ...base,
      get: <T,>(path: string) => {
        if (asked.has(path)) return new Promise<ApiEnvelope<T>>(() => undefined);
        asked.add(path);
        return base.get<T>(path);
      },
    };
    renderScreen(stalled);
    await screen.findByTestId('redaction-rule');
    await userEvent.type(screen.getByLabelText('Your question'), 'What did we spend?');
    await userEvent.click(screen.getByTestId('ask-submit'));
    const latest = await screen.findByTestId('assistant-latest');
    expect(within(latest).getByTestId('cited-prose')).toHaveTextContent('$3,781.93');
    expect(screen.getByTestId('ask-submit')).not.toHaveTextContent('Asking');
  });
});

describe('AssistantScreen, the history and what was kept out', () => {
  it('lists each redaction by its rule and what was done, never the secret', async () => {
    renderScreen();
    const rule = await screen.findByTestId('redaction-rule');
    expect(rule).toHaveTextContent('aws-access-token');
    expect(screen.getByTestId('redaction-action')).toHaveTextContent('Blocked.');
    // The question it was found in is on the page, and the link lands on it.
    const link = screen.getByRole('link', { name: 'The question it was found in' });
    expect(landing(link)).toHaveAttribute('data-testid', 'exchange');
  });

  it('says a history that could not be read could not be read, and lists nothing', async () => {
    renderScreen(clientReturning({}, new ApiError(403, 'AccessDenied: no tier')));
    // Both of the asker's lists, each as the typed failure, and neither as an empty list.
    await waitFor(() => {
      const states = screen.getAllByTestId('state').map((state) => state.dataset['state']);
      expect(states).toEqual(['failed', 'failed']);
    });
    expect(screen.queryByTestId('exchange')).toBeNull();
  });
});

describe('AssistantScreen, the trust strip', () => {
  it('says each citation carries its own date, and makes up no date for the page', async () => {
    renderInShell();
    await screen.findByTestId('redaction-rule');
    await waitFor(() => {
      expect(screen.getByTestId('global-freshness')).toHaveAttribute(
        'data-state',
        'per-figure',
      );
    });
    expect(screen.getByTestId('global-freshness')).toHaveTextContent(
      'Each citation carries its own as of date',
    );
    // The envelopes carry no as_of, and the strip invents none, nor claims nothing was collected.
    const strip = screen.getByTestId('trust-strip');
    expect(within(strip).queryByTestId('freshness')).toBeNull();
    expect(strip.textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(strip).not.toHaveTextContent('Not yet collected');
    // What the strip points at: each cited figure states its own.
    const entry = await entryFor(answeredExchange());
    expect(within(entry).getAllByTestId('citation-as-of')).toHaveLength(
      answeredExchange().answer?.citations.length ?? 0,
    );
  });
});

/** The screen inside the shell, so the page heading the shell draws is part of what is checked. */
function renderInShell(client: ApiClient = clientFor()) {
  return render(
    <Harness client={client} initialPath="/assistant">
      <AppShell now={new Date('2026-10-04T09:00:00Z')}>
        <AssistantScreen />
      </AppShell>
    </Harness>,
  );
}

/** Every heading level in document order, and whether any step skips a level going down. */
function skipsALevel(container: HTMLElement): boolean {
  const levels = [...container.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
    Number(heading.tagName.slice(1)),
  );
  return levels.slice(1).some((level, index) => level - (levels[index] ?? level) > 1);
}

describe('accessibility', () => {
  it('has no violations with every outcome on the page, inside the shell', async () => {
    const { container } = renderInShell();
    await screen.findByTestId('assistant-history');
    await screen.findByTestId('redaction-rule');
    expect(skipsALevel(container)).toBe(false);
    expect(await violationsIn(container)).toEqual([]);
  });

  it('has no violations once an answer has come back, inside the shell', async () => {
    const { container } = renderInShell();
    await userEvent.type(screen.getByLabelText('Your question'), 'What did we spend?');
    await userEvent.click(screen.getByTestId('ask-submit'));
    await screen.findByTestId('assistant-latest');
    expect(skipsALevel(container)).toBe(false);
    expect(await violationsIn(container)).toEqual([]);
  });
});
