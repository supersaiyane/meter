import type { ApiCitation, ApiToolCall } from '../api/types';
import { stampUtc } from '../screens/enforcementTime';
import { DenseRegion } from './DenseRegion';
import { Figure } from './Figure';
import { TypedError } from './TypedError';
import {
  amountOf,
  callAnchor,
  citationAnchor,
  citeProse,
  decimalPlaces,
  figureUnit,
} from './citations';
import type { FigureValue } from './provenance';

/**
 * Prose whose every value is cited, and the citations it came with. P7 spec sections 5.2, 9.
 *
 * **The citations matter more than the prose.** Each value in the sentence carries a numbered
 * marker linked to its entry below, and each entry names the tool, the call, the field and the
 * moment the value was true, with the call linked to the list of calls the exchange made. A
 * reader who does not trust the sentence checks the number without leaving the page.
 *
 * **A figure is a Figure.** Its provenance is drawn the three ways it is drawn everywhere.
 * Dense, so no freshness line breaks the sentence: when a value was true is stated once, on its
 * own entry, which is where a reader checking it looks.
 *
 * **One component for answers and digests,** because a digest obeys the rule an answer obeys,
 * and two renderings of one rule is how the two come to disagree.
 */
export interface CitedProseProps {
  /** An exchange or digest id, so every anchor on the page belongs to one piece of prose. */
  readonly scope: string;
  readonly prose: string;
  readonly citations: readonly ApiCitation[];
  /** When the values were read: an exchange's `answered_at`, a digest's `composed_at`. */
  readonly readAt: string;
  /** The calls the exchange made, so each citation links to its own. A digest made none. */
  readonly calls?: readonly ApiToolCall[];
}

/** A figure's value by its provenance, or null for a provenance that is not one of the two. */
function figureValue(provenance: string, amount: number): FigureValue | null {
  if (provenance === 'measured') return { kind: 'measured', amount };
  if (provenance === 'modelled') return { kind: 'modelled', amount };
  return null;
}

/** Drift, said as drift: a value this screen cannot draw honestly is never drawn as another. */
function Unrecognised({ said }: { readonly said: string }) {
  return <TypedError cause="SchemaDrift" remediation={said} />;
}

/**
 * One cited value: a Figure for a figure, the text itself for a label.
 *
 * The kind and the provenance are read as strings, so a value the API should never send, a
 * third kind or a forecast, reaches the drift branch rather than being drawn as a measurement.
 */
function CitedValue({
  citation,
  readAt,
}: {
  readonly citation: ApiCitation;
  readonly readAt: string;
}) {
  const kind: string = citation.kind;
  const provenance: string = citation.provenance;
  const name = citation.placeholder;
  if (kind === 'label') {
    return <span data-testid="cited-label">{citation.value}</span>;
  }
  if (kind !== 'figure') {
    return (
      <Unrecognised
        said={`The value cited as ${name} is of a kind this screen does not know, so it is not shown.`}
      />
    );
  }
  const amount = amountOf(citation.value);
  if (amount === null) {
    // A figure that is not a number is never drawn as a zero.
    return (
      <Unrecognised said={`The value cited as ${name} is not a number, so it is not shown.`} />
    );
  }
  const value = figureValue(provenance, amount);
  if (value === null) {
    return (
      <Unrecognised
        said={`The value cited as ${name} is neither measured nor modelled, so it is not shown.`}
      />
    );
  }
  const unit = figureUnit(citation);
  return (
    <Figure
      value={value}
      unit={unit}
      // A count is drawn to the precision it was cited with, so a fraction is never a whole.
      {...(unit === 'count' ? { fractionDigits: decimalPlaces(citation.value) } : {})}
      freshness={{ asOf: new Date(citation.as_of), collectedAt: new Date(readAt) }}
    />
  );
}

/**
 * A numbered link to the value's entry. Bracketed, because copied out of the page a bare digit
 * runs into the value before it, and a date of 2026-09-27 followed by marker 1 reads as a day
 * that does not exist.
 */
function Marker({ scope, number }: { readonly scope: string; readonly number: number }) {
  return (
    <sup>
      <a
        href={`#${citationAnchor(scope, number)}`}
        data-testid="citation-marker"
        aria-label={`Citation ${String(number)}`}
      >
        {`[${String(number)}]`}
      </a>
    </sup>
  );
}

/** What kind of value a citation is, in words, for its entry. */
function describe(citation: ApiCitation): string {
  const kind: string = citation.kind;
  if (kind === 'figure') return 'a figure';
  if (kind === 'label') return `a label, ${citation.provenance},`;
  return 'a value of a kind this screen does not know,';
}

/** Where one citation came from, in the order a reader checks it. */
function Trace({
  citation,
  scope,
  calls,
}: {
  readonly citation: ApiCitation;
  readonly scope: string;
  readonly calls: readonly ApiToolCall[];
}) {
  const index = calls.findIndex((call) => call.call_id === citation.call_id);
  const call = <code data-testid="citation-call">{citation.call_id}</code>;
  return (
    <span data-testid="citation-trace">
      {' '}
      <code>{citation.placeholder}</code>, {describe(citation)} read by{' '}
      <code data-testid="citation-tool">{citation.tool}</code> in call{' '}
      {index === -1 ? call : <a href={`#${callAnchor(scope, index)}`}>{call}</a>}, field{' '}
      <code data-testid="citation-field">{citation.field}</code>, true as of{' '}
      <time dateTime={citation.as_of} data-testid="citation-as-of">
        {stampUtc(citation.as_of)}
      </time>
      .
    </span>
  );
}

export function CitedProse({ scope, prose, citations, readAt, calls = [] }: CitedProseProps) {
  const { parts, numbered } = citeProse(prose, citations);
  const heading = `sources-${scope}`;
  return (
    <DenseRegion>
      <div data-testid="cited-answer">
        <p data-testid="cited-prose">
          {parts.map((part, index) => {
            switch (part.kind) {
              case 'text':
                return <span key={index}>{part.text}</span>;
              case 'cited':
                return (
                  <span
                    key={index}
                    data-testid="cited-value"
                    data-placeholder={part.citation.placeholder}
                    data-kind={part.citation.kind}
                  >
                    <CitedValue citation={part.citation} readAt={readAt} />
                    <Marker scope={scope} number={part.number} />
                  </span>
                );
              case 'uncited':
                return (
                  <TypedError
                    key={index}
                    cause="SchemaDrift"
                    remediation={`The value named ${part.name} arrived with no citation, so it is not shown.`}
                  />
                );
            }
          })}
        </p>
        <h4 id={heading}>Where each value came from</h4>
        <ol data-testid="citations" aria-labelledby={heading}>
          {numbered.map(({ citation, number }) => (
            <li
              key={citation.placeholder}
              id={citationAnchor(scope, number)}
              data-testid="citation"
              data-kind={citation.kind}
              data-provenance={citation.provenance}
            >
              <span data-testid="citation-value">
                <CitedValue citation={citation} readAt={readAt} />
              </span>
              <Trace citation={citation} scope={scope} calls={calls} />
            </li>
          ))}
        </ol>
      </div>
    </DenseRegion>
  );
}

/**
 * Every call an exchange made, in order, and whether each one came back.
 *
 * A call that did not return is listed rather than dropped. Nothing it would have said is in
 * the answer, and a reader replaying the answer needs to know the model tried.
 */
export function ToolCalls({
  scope,
  calls,
}: {
  readonly scope: string;
  readonly calls: readonly ApiToolCall[];
}) {
  const heading = `calls-${scope}`;
  return (
    <div data-testid="tool-calls-block">
      <h4 id={heading}>Tool calls, in the order the model made them</h4>
      {calls.length === 0 ? (
        <p data-testid="tool-calls-none">None. The model read no route for this.</p>
      ) : (
        <ol data-testid="tool-calls" aria-labelledby={heading}>
          {calls.map((call, index) => (
            <li
              key={callAnchor(scope, index)}
              id={callAnchor(scope, index)}
              data-testid="tool-call"
              data-returned={call.returned ? 'true' : 'false'}
            >
              <code data-testid="tool-call-tool">{call.tool}</code>, call{' '}
              <code data-testid="tool-call-id">{call.call_id}</code>,{' '}
              {call.returned
                ? 'returned'
                : 'did not return, so nothing it would have said is used'}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
