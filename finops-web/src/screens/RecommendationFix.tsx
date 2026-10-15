import { useId, useState } from 'react';

import { reasonOf } from '../api/client';
import { useAskForFix, useFixes } from '../api/remediation';
import type { ApiFix, ApiRecommendation } from '../api/types';

/**
 * A recommendation's fix, FEAT-092, TASK-P15-008: ask for it as a pull request, see the pull
 * request and every step, and read why where there is none.
 *
 * Rendered in the recommendation's detail on the recommendations screen, as the alternatives are,
 * so a person decides with the finding in front of them. A fix is asked for once the
 * recommendation is accepted with an owner, and one is live at a time; the API and the database
 * refuse anything else, and a refusal is shown in the API's own words.
 */

const LIVE = new Set(['REQUESTED', 'OPEN']);

/** What a fix's status means, in a reader's words. */
function said(fix: ApiFix): string {
  switch (fix.status) {
    case 'REQUESTED':
      return `Asked for by ${fix.requested_by}. Meter opens the pull request within ten minutes.`;
    case 'OPEN':
      return `Pull request #${String(fix.number)} is open in ${fix.repository ?? 'the repository'}.`;
    case 'MERGED':
      return (
        `Merged by ${fix.merged_by ?? 'the code host'}. The recommendation is done once the ` +
        'inventory sees the change.'
      );
    case 'CLOSED':
      return 'Closed without merging, so the recommendation is accepted again.';
    case 'NOT_AUTHORED':
      return `No pull request: ${fix.reason ?? 'no reason was recorded.'}`;
    case 'FAILED':
      return `No pull request, ${fix.failure_cause ?? 'failed'}: ${fix.reason ?? ''}`;
  }
}

function FixRecord({ fix }: { readonly fix: ApiFix }) {
  return (
    <div data-testid="fix-record" data-status={fix.status}>
      <p data-testid="fix-said">
        {said(fix)}{' '}
        {fix.url === null ? null : (
          <a href={fix.url} target="_blank" rel="noreferrer">
            Open the pull request
          </a>
        )}
      </p>
      <ol aria-label="Steps" data-testid="fix-steps">
        {fix.steps.map((step) => (
          <li key={`${step.at}-${step.to_status}-${step.principal}`}>
            <time dateTime={step.at}>{new Date(step.at).toLocaleString('en-GB')}</time>{' '}
            {step.to_status.toLowerCase().replace('_', ' ')} by {step.principal}
            {step.note === null ? null : `: ${step.note}`}
          </li>
        ))}
      </ol>
    </div>
  );
}

export function RecommendationFix({
  recommendation,
}: {
  readonly recommendation: ApiRecommendation;
}) {
  const noteId = useId();
  const [note, setNote] = useState('');
  const fixes = useFixes();
  const ask = useAskForFix();
  const mine = (fixes.data?.data.fixes ?? []).filter(
    (one) => one.recommendation_id === recommendation.recommendation_id,
  );
  const latest = mine[0];
  const live = mine.some((one) => LIVE.has(one.status));
  return (
    <section aria-label="The fix" data-testid="recommendation-fix">
      <h2>The fix</h2>
      {fixes.isError ? (
        <p role="alert" data-testid="fix-unread">
          {reasonOf(fixes.error)}
        </p>
      ) : null}
      {latest === undefined ? (
        <p data-testid="fix-none">No fix has been asked for.</p>
      ) : (
        <FixRecord fix={latest} />
      )}
      {live ? null : recommendation.lifecycle === 'ACCEPTED' ? (
        <form
          data-testid="fix-ask"
          aria-label="Ask for the fix"
          onSubmit={(event) => {
            event.preventDefault();
            ask.mutate(
              { recommendationId: recommendation.recommendation_id, note },
              {
                onSuccess: () => {
                  setNote('');
                },
              },
            );
          }}
        >
          <p>
            Meter writes the change to the Terraform that declares the resource and opens it as
            a pull request for review. A removal is never merged by Meter.
          </p>
          <label htmlFor={noteId}>A note for the reviewers, if any</label>
          <textarea
            id={noteId}
            value={note}
            maxLength={1000}
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
          <button type="submit" disabled={ask.isPending}>
            Ask for a pull request
          </button>
          {ask.isError ? (
            <p role="alert" data-testid="fix-ask-refused">
              {reasonOf(ask.error)}
            </p>
          ) : null}
        </form>
      ) : (
        <p data-testid="fix-accept-first">
          A fix is asked for once the recommendation is accepted with an owner, so somebody owns
          the pull request it opens. It is {recommendation.lifecycle.toLowerCase()}.
        </p>
      )}
    </section>
  );
}
