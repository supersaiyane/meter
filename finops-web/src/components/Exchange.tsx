import type { ApiAssistantRefusal, ApiExchange, ApiExchangeFailure } from '../api/types';
import { stampUtc } from '../screens/enforcementTime';
import { Link } from '../shell/links';
import { GROUPS, REDIRECTS } from '../shell/sections';
import { CitedProse, ToolCalls } from './CitedProse';
import { DenseRegion } from './DenseRegion';
import { Figure } from './Figure';
import { TypedError } from './TypedError';
import { amountOf } from './citations';
import { CAUSE_LABEL, type Cause } from './provenance';

/**
 * One question and what came back, as one of three shapes. P7 spec sections 5.3 and 9.
 *
 * **Three, and they are three.** An answer is prose with every value cited and the calls behind
 * them. A refusal names what is missing and, where one exists, links the screen that would show
 * it once the gap closes. A failure is a typed cause, drawn the way every other failure in this
 * product is drawn. A refusal drawn as an error teaches a reader the assistant is broken when
 * it is being careful, and one drawn as an answer teaches them to distrust the answers.
 *
 * **What it cost is on the page.** Tokens and the estimated cost, every exchange, including the
 * ones that reached no model and so cost nothing, because a FinOps product that hides what its
 * own assistant costs has picked the one figure it is not allowed to be coy about.
 */

/** What each gap is called on screen. The reason beside it says the particulars. */
const GAP: Readonly<Record<string, string>> = {
  tool: 'no tool reads this, so no screen does either',
  figure: 'the figure is not there to cite',
  scope: 'it is outside what you can see',
  budget: "this month's assistant budget is spent",
  secret: 'the question held a secret, so it was sent nowhere',
};

/** Half a cent, the most a figure drawn to the cent can hold and still read as nothing. */
const HALF_CENT = 0.005;

function gapOf(gap: string): string {
  // Own properties only. `__proto__` or `constructor` would otherwise read the prototype, and
  // an object drawn as text stops the whole page. A gap this screen has no words for is still
  // shown, by its own name, rather than hidden.
  const named = Object.hasOwn(GAP, gap) ? GAP[gap] : undefined;
  return named ?? `the gap reported is ${gap}, which this screen has no words for`;
}

function hasLabel(cause: string): cause is Exclude<Cause, 'NoData'> {
  return Object.hasOwn(CAUSE_LABEL, cause);
}

/**
 * The navigation's own entry for a path, matched exactly, or undefined for any other string.
 *
 * The one test a refusal's screen has to pass to become a link. A prefix test cannot be made
 * safe: a slash followed by a backslash, a tab or a newline and then another slash all resolve
 * to another host under the URL parser browsers use. An exact match against the list of screens
 * this application has cannot point anywhere else, and the link goes to the list's own path
 * rather than to the text the API sent.
 */
function navEntry(path: string): { readonly path: string; readonly name: string } | undefined {
  // A screen that moved in P8 is followed to where it went, so an answer stored
  // before the move keeps its link. Still exact: the redirect table is a list
  // of whole paths, and the link goes to the navigation's own path.
  const target = REDIRECTS[path] ?? path;
  for (const group of GROUPS) {
    const screen = group.screens.find((one) => one.path === target);
    if (screen !== undefined) {
      const name =
        group.label === screen.label ? screen.label : `${group.label}, ${screen.label}`;
      return { path: screen.path, name };
    }
  }
  return undefined;
}

/** A shape the exchange should carry and does not. The API refuses to send one, so drift. */
function Drift({ said }: { readonly said: string }) {
  return <TypedError cause="SchemaDrift" remediation={said} />;
}

function missing(outcome: string): string {
  return `The exchange says ${outcome} and carries nothing in that shape, so nothing is shown as one.`;
}

function Refused({ refusal }: { readonly refusal: ApiAssistantRefusal }) {
  // An empty path names no screen, so it is drawn as no screen rather than as an empty one.
  const screen =
    refusal.screen === null || refusal.screen.trim() === '' ? null : refusal.screen;
  const known = screen === null ? undefined : navEntry(screen);
  return (
    <div data-testid="refusal" data-gap={refusal.gap}>
      <p data-testid="refusal-gap">
        <strong>Not answered:</strong> {gapOf(refusal.gap)}.
      </p>
      <p data-testid="refusal-reason">{refusal.reason}</p>
      {screen === null ? null : (
        <p data-testid="refusal-screen">
          The screen that would show it once the gap closes:{' '}
          {known === undefined ? (
            // Not a screen this application has, so shown as text and never followed.
            <code>{screen}</code>
          ) : (
            <Link to={known.path}>{known.name}</Link>
          )}
          .
        </p>
      )}
    </div>
  );
}

function Failed({ failure }: { readonly failure: ApiExchangeFailure }) {
  if (failure.cause === 'NotOptedIn') {
    // The normal state of a deployment with no model, ADR-0028. A setting, not a fault, so it
    // is said calmly and not in the failure colour. The detail says what is missing and the
    // remediation, the API's own words for the assistant, says how to switch it on.
    return (
      <div data-testid="exchange-failure" data-cause={failure.cause} data-state="not-enabled">
        <p data-testid="not-enabled">
          <strong>Not enabled.</strong> The assistant is not switched on here, which is a
          setting rather than a fault.
        </p>
        {failure.detail === null ? null : <p data-testid="failure-detail">{failure.detail}</p>}
        <p data-testid="failure-remediation">{failure.remediation}</p>
      </div>
    );
  }
  return (
    <div data-testid="exchange-failure" data-cause={failure.cause} data-state="failed">
      {hasLabel(failure.cause) ? (
        <TypedError cause={failure.cause} remediation={failure.remediation} />
      ) : (
        // A cause the frontend does not know is still shown, as the trust strip shows one.
        <span className="meter-failure" role="status">
          {failure.cause}. {failure.remediation}
        </span>
      )}
      {failure.detail === null ? null : <p data-testid="failure-detail">{failure.detail}</p>}
    </div>
  );
}

function Outcome({ exchange }: { readonly exchange: ApiExchange }) {
  const scope = exchange.exchange_id;
  // Widened to a string, so an outcome the API should never send still reaches the default
  // below and is drawn as drift, rather than as nothing at all.
  const outcome: string = exchange.outcome;
  switch (outcome) {
    case 'ANSWERED':
      return exchange.answer === null ? (
        <Drift said={missing(outcome)} />
      ) : (
        <div data-testid="answer">
          <p data-testid="answer-label">
            <strong>Answered.</strong> Every value is cited below to the call it was read from.
          </p>
          <CitedProse
            scope={scope}
            prose={exchange.answer.prose}
            citations={exchange.answer.citations}
            readAt={exchange.answered_at}
            calls={exchange.tool_calls}
          />
          <ToolCalls scope={scope} calls={exchange.tool_calls} />
        </div>
      );
    case 'REFUSED':
      return exchange.refusal === null ? (
        <Drift said={missing(outcome)} />
      ) : (
        <>
          <Refused refusal={exchange.refusal} />
          {exchange.tool_calls.length > 0 ? (
            <ToolCalls scope={scope} calls={exchange.tool_calls} />
          ) : null}
        </>
      );
    case 'FAILED':
      return exchange.failure === null ? (
        <Drift said={missing(outcome)} />
      ) : (
        <>
          <Failed failure={exchange.failure} />
          {exchange.tool_calls.length > 0 ? (
            <ToolCalls scope={scope} calls={exchange.tool_calls} />
          ) : null}
        </>
      );
    default:
      return (
        <Drift
          said={`The exchange says ${outcome}, which is none of answered, refused and failed, so nothing is shown as one.`}
        />
      );
  }
}

/**
 * What the exchange cost. Tokens are what the provider reported, so measured. The cost is
 * worked out from them at list prices, so modelled: the bill is the measurement.
 *
 * Dense, so three figures do not repeat one freshness line three times. When the exchange
 * happened is said once, above, and these were true at that moment.
 */
function Usage({ exchange }: { readonly exchange: ApiExchange }) {
  const at = new Date(exchange.answered_at);
  const freshness = { asOf: at, collectedAt: at };
  const cost = amountOf(exchange.est_cost);
  return (
    <DenseRegion>
      <dl data-testid="exchange-usage">
        <dt>Model</dt>
        <dd data-testid="exchange-model">
          {exchange.model_id ?? 'none, the question reached no model and spent nothing'}
        </dd>
        <dt>Input tokens</dt>
        <dd data-testid="exchange-input-tokens">
          <Figure
            value={{ kind: 'measured', amount: exchange.input_tokens }}
            unit="count"
            freshness={freshness}
          />
        </dd>
        <dt>Output tokens</dt>
        <dd data-testid="exchange-output-tokens">
          <Figure
            value={{ kind: 'measured', amount: exchange.output_tokens }}
            unit="count"
            freshness={freshness}
          />
        </dd>
        <dt>Estimated cost, at list prices</dt>
        <dd data-testid="exchange-cost">
          {cost === null ? (
            <TypedError
              cause="SchemaDrift"
              remediation="The estimated cost is not a number, so it is not shown."
            />
          ) : (
            <>
              <Figure
                value={{ kind: 'modelled', amount: cost }}
                unit="usd"
                freshness={freshness}
              />
              {/* Drawn to the cent, a fraction of one reads as nothing at all. It is not
                  nothing, and the words say so where the digits cannot. */}
              {cost > 0 && cost < HALF_CENT ? (
                <span data-testid="exchange-cost-small">, under a cent</span>
              ) : null}
            </>
          )}
        </dd>
      </dl>
    </DenseRegion>
  );
}

export function Exchange({ exchange }: { readonly exchange: ApiExchange }) {
  const question = `question-${exchange.exchange_id}`;
  return (
    <article
      id={`exchange-${exchange.exchange_id}`}
      data-testid="exchange"
      data-outcome={exchange.outcome}
      aria-labelledby={question}
    >
      {/* The question as typed, because the wording is evidence when an answer is wrong. */}
      <h3 id={question} data-testid="exchange-question">
        {exchange.question}
      </h3>
      <p data-testid="exchange-asked">
        Asked <time dateTime={exchange.asked_at}>{stampUtc(exchange.asked_at)}</time>.
      </p>
      <Outcome exchange={exchange} />
      <Usage exchange={exchange} />
    </article>
  );
}
