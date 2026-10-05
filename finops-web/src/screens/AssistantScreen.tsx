import { useState, type SubmitEvent } from 'react';

import { useAsk, useExchanges, useRedactions } from '../api/queries';
import type { ApiExchange, ApiMeta, ApiRedaction } from '../api/types';
import { DataTable } from '../components/DataTable';
import { Exchange } from '../components/Exchange';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { SurfaceState } from '../components/surfaceState';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { stampUtc } from './enforcementTime';
import { surfaceStateFor, type QueryLike } from './surfaceStateFor';

/**
 * Ask a question of the product, and see where every value in the answer came from. FEAT-038
 * and FEAT-042, TASK-P7-011.
 *
 * **The answer is not the interesting part of the screen. The citations are.** Spec section 9.
 * Every figure is a Figure, and each carries a numbered marker to the tool call behind it, so a
 * reader who does not trust the sentence checks the number here rather than taking it on trust.
 *
 * **Three outcomes, three shapes.** An answer, a refusal that names what is missing, and a typed
 * failure. A deployment with no model answers every question with the last of these, as not
 * enabled, which is its normal state rather than a fault.
 *
 * **The cost of the conversation is on the page.** Tokens and the estimated cost on every
 * exchange, because a FinOps product that hides what its own assistant costs has picked the one
 * figure it is not allowed to be coy about.
 *
 * **What was kept out of a prompt is on the page too.** A question holding a credential is
 * blocked before it is sent anywhere, and the asker sees which rule caught it. Never the secret,
 * which no route can return because no column holds it.
 */

/** `QUESTION_MAX_LENGTH` in `finops_api/schemas.py`. A longer question is refused there. */
const QUESTION_LIMIT = 2000;

/** Why one of the asker's own lists can be short: the API returns the newest and counts all. */
const NEWEST_ONLY = 'Only the newest are listed here.';

/**
 * Which of the seven states one of the asker's own lists is in.
 *
 * Not `surfaceStateFor` alone. An exchange records Meter's own work and has no `as_of`, spec
 * section 6.1, so the envelope's is always null, and the shared rule would call every history
 * never collected. Pending and failed are decided by the shared rule, so a failed request reads
 * the same here as everywhere, and the rest is decided here in the shared rule's order.
 */
function ownWorkState(
  query: QueryLike,
  meta: ApiMeta | undefined,
  rows: number,
  filter: string,
): SurfaceState {
  const shared = surfaceStateFor(query, meta, rows, filter, 'assistant');
  if (shared.kind === 'loading' || shared.kind === 'failed' || meta === undefined)
    return shared;
  if (rows === 0) return { kind: 'empty', filter };
  if (meta.scope_coverage.is_partial) {
    return {
      kind: 'partial',
      missing: meta.scope_coverage.total - meta.scope_coverage.visible,
      reason: NEWEST_ONLY,
    };
  }
  if (meta.failures.length > 0) {
    return {
      kind: 'degraded',
      failing: [...new Set(meta.failures.map((failure) => failure.collector))],
    };
  }
  return { kind: 'ready' };
}

/**
 * What the live region says when a result arrives, so a screen reader hears how the question
 * ended, and does not hear "Asking" followed by silence. Not enabled is said as that, as the
 * block below says it, because it is a setting and not a fault.
 */
function arrived(exchange: ApiExchange): string {
  const outcome: string = exchange.outcome;
  if (outcome === 'ANSWERED') return 'Answered, shown below.';
  if (outcome === 'REFUSED') return 'Not answered, shown below.';
  if (outcome === 'FAILED') {
    return exchange.failure?.cause === 'NotOptedIn'
      ? 'Not enabled, shown below.'
      : 'Failed, shown below.';
  }
  return 'An outcome this screen does not know, shown below.';
}

function AskForm({
  pending,
  failure,
  result,
  onAsk,
}: {
  readonly pending: boolean;
  readonly failure: Error | null;
  /** How the last question ended, in words for the live region, or empty before any has. */
  readonly result: string;
  /** Asks, and calls `answered` only if the question was answered. */
  readonly onAsk: (question: string, answered: () => void) => void;
}) {
  const [question, setQuestion] = useState('');
  const blank = question.trim() === '';

  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (blank || pending) return;
    onAsk(question, () => {
      // Only the question that was asked is cleared. Words typed while it was out are kept.
      setQuestion((current) => (current === question ? '' : current));
    });
  };

  return (
    <form data-testid="ask-form" aria-label="Ask a question" onSubmit={submit}>
      <label htmlFor="assistant-question">Your question</label>
      <textarea
        id="assistant-question"
        data-testid="ask-question"
        name="question"
        rows={3}
        maxLength={QUESTION_LIMIT}
        aria-describedby="assistant-question-limit assistant-question-note"
        value={question}
        onChange={(event) => {
          setQuestion(event.target.value);
        }}
      />
      <p id="assistant-question-limit" data-testid="ask-limit">
        {`${String(question.length)} of ${String(QUESTION_LIMIT)} characters.`}
      </p>
      <p id="assistant-question-note">
        Answered from the routes the screens read, as you, so it sees what you can see and no
        more. The question is kept with its answer, and one holding a credential is blocked
        before it is sent anywhere.
      </p>
      <button type="submit" data-testid="ask-submit" disabled={pending || blank}>
        {pending ? 'Asking' : 'Ask'}
      </button>
      {/* Present while empty, so the words are announced when they arrive: asking while the
          question is out, then how it ended once the result is drawn below. */}
      <p role="status" data-testid="ask-status">
        {pending
          ? 'Asking. The model reads the routes it needs, which takes a few seconds.'
          : result}
      </p>
      {failure === null ? null : (
        // The request itself failed, so there is no exchange to draw. Said in the words the
        // client was given, and never drawn as an answer or as an empty one.
        <p role="alert" data-testid="ask-error" className="meter-failure">
          The request failed, so no answer came back. {failure.message}
        </p>
      )}
    </form>
  );
}

/** The redaction events, each linked to its question when that question is on the page. */
function redactionColumns(listed: ReadonlySet<string>): readonly Column<ApiRedaction>[] {
  return [
    {
      key: 'when',
      header: 'When',
      render: (row) => <time dateTime={row.occurred_at}>{stampUtc(row.occurred_at)}</time>,
    },
    {
      key: 'rule',
      header: 'Rule',
      render: (row) => <code data-testid="redaction-rule">{row.rule_id}</code>,
    },
    {
      key: 'action',
      header: 'What happened',
      prose: true,
      render: (row) => (
        <span data-testid="redaction-action" data-action={row.action}>
          {row.action === 'BLOCKED'
            ? 'Blocked. The question was sent nowhere. Treat the credential as exposed and rotate it.'
            : 'Redacted. The secret was removed and the rest of the question was sent.'}
        </span>
      ),
    },
    {
      key: 'question',
      header: 'Question',
      render: (row) =>
        listed.has(row.exchange_id) ? (
          <a href={`#exchange-${row.exchange_id}`}>The question it was found in</a>
        ) : (
          'Older than the questions listed'
        ),
    },
  ];
}

export function AssistantScreen() {
  const exchanges = useExchanges();
  const redactions = useRedactions();
  const ask = useAsk();

  const history = exchanges.data?.data;
  const caught = redactions.data?.data;
  // Both lists are Meter's own work, so neither envelope carries an as_of, spec section 6.1,
  // and none is made up here. What carries one is each cited figure, beside it, and an event
  // states when it happened, so the strip says freshness is per figure rather than claiming
  // nothing was collected.
  useReportMeta('assistant-exchanges', history?.meta, 'per-figure');
  useReportMeta('assistant-redactions', caught?.meta, 'per-figure');

  // The latest exchange is drawn on its own, so it is left out of the history below rather than
  // drawn twice once the list has been read again.
  const latest = ask.data?.data;
  const earlier = (history?.data ?? []).filter(
    (exchange) => exchange.exchange_id !== latest?.exchange_id,
  );
  const events = caught?.data ?? [];
  const listed = new Set([
    ...earlier.map((exchange) => exchange.exchange_id),
    ...(latest === undefined ? [] : [latest.exchange_id]),
  ]);

  const historyState = ownWorkState(
    exchanges,
    history?.meta,
    earlier.length,
    latest === undefined ? 'your own questions' : 'your own questions, before the last one',
  );
  const redactionState = ownWorkState(
    redactions,
    caught?.meta,
    events.length,
    'secrets found in your own questions',
  );

  return (
    <section aria-label="Ask Meter">
      <FixtureBand source={exchanges.data?.source} />
      <FixtureBand source={redactions.data?.source} />

      <AskForm
        pending={ask.isPending}
        failure={ask.error}
        result={latest === undefined ? '' : arrived(latest)}
        onAsk={(question, answered) => {
          ask.mutate(question, {
            onSuccess: (envelope) => {
              // Only an answer clears the box. A refusal or a failure keeps the question, so
              // asking it again, narrower or a minute later, does not mean typing it again.
              if (envelope.data.outcome === 'ANSWERED') answered();
            },
          });
        }}
      />

      {latest === undefined ? null : (
        <div data-testid="assistant-latest">
          <h2>Your last question</h2>
          <Exchange exchange={latest} />
        </div>
      )}

      <h2>Earlier questions</h2>
      <StateBoundary state={historyState}>
        <div data-testid="assistant-history">
          {earlier.map((exchange) => (
            <Exchange key={exchange.exchange_id} exchange={exchange} />
          ))}
        </div>
      </StateBoundary>

      <h2>Kept out of a prompt</h2>
      <StateBoundary state={redactionState}>
        <DataTable
          rows={events}
          columns={redactionColumns(listed)}
          rowKey={(row) => row.event_id}
          caption="Secrets found in your own questions, by the rule that found each one. Never the secret itself."
        />
      </StateBoundary>
    </section>
  );
}
