import { useParams } from 'react-router';

import { useQuotaDetail } from '../api/queries';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type {
  ApiDraftRefusal,
  ApiQuotaDraft,
  ApiQuotaRequest,
  ApiRequestTransition,
} from '../api/types';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * One quota, the increase Meter would ask for, and what became of the last one. FEAT-034.
 *
 * **Meter does not submit the request, and the screen says so where the request is.** Not in a
 * footnote and not on a help page: the sentence sits beside the command, because that is the
 * moment a reader forms an expectation about what happens next. Spec section 6 argues the
 * decision, which is that a product that has never written into a customer account can say so
 * in one sentence and every security review after that is shorter.
 *
 * **The working is shown, not just the number.** A suggested limit with no derivation is one a
 * reader either accepts on faith or ignores, and both are failures: accepting it means raising
 * a limit on somebody's say so, and ignoring it means the draft was pointless. The sentence
 * names the observed peak, the target headroom and the rounding, so a reader who thinks forty
 * percent is too generous knows which part to argue with.
 *
 * **A refusal to draft is shown as plainly as a draft.** Four reasons, and each is a different
 * thing to do: a hard limit needs a different architecture, an unmeasured quota needs a usage
 * source, and a comfortable quota needs nothing at all. A screen showing only the drafts would
 * leave a reader wondering whether the rest had been forgotten.
 *
 * Reached from the list rather than from the navigation, like the query finding detail and the
 * entity page. A quota code is not something anybody types.
 */

function Draft({ draft }: { readonly draft: ApiQuotaDraft }) {
  return (
    <article data-testid="quota-draft">
      <h4>
        {draft.account_id}
        <span> {draft.region_id ?? 'all regions'}</span>
      </h4>
      <p data-testid="draft-figures">
        <span>Now {draft.current_limit}</span>
        <span>, peak {draft.observed_usage}</span>
        <span>
          , ask for <strong>{draft.suggested_value}</strong>
        </span>
      </p>
      {/* The working, whole. A shortened derivation is one nobody can disagree with. */}
      <p data-testid="draft-working">{draft.working}</p>

      <p data-testid="draft-not-submitted">
        Meter will not submit this. It makes no write call into any account, which is what lets
        this product say it has never changed anything in yours.
      </p>

      <dl>
        <dt>Console</dt>
        <dd>
          <a data-testid="draft-console" href={draft.console_url}>
            {draft.console_url}
          </a>
        </dd>
        <dt>Command</dt>
        <dd>
          {/* A code element rather than a button, so it is selectable and copyable without
              clipboard permission and a fallback nobody tests. */}
          <code data-testid="draft-command">{draft.cli_command}</code>
        </dd>
      </dl>
    </article>
  );
}

function Refusal({ refusal }: { readonly refusal: ApiDraftRefusal }) {
  return (
    <article data-testid="quota-draft-refused">
      <h4>
        {refusal.account_id}
        <span> {refusal.region_id ?? 'all regions'}</span>
      </h4>
      <p data-testid="draft-refused-reason">{refusal.reason}</p>
    </article>
  );
}

function Request({
  request,
  history,
}: {
  readonly request: ApiQuotaRequest;
  readonly history: readonly ApiRequestTransition[];
}) {
  return (
    <article data-testid="quota-request" data-status={request.status}>
      <h4>
        {request.request_id}
        <span data-testid="request-status"> {request.status.replace('_', ' ').toLowerCase()}</span>
      </h4>
      <p data-testid="request-desired">Asked for {request.desired_value}</p>
      {/* When, not only what. The current status can say a request was approved and not when,
          and how long an increase has been waiting is the question FEAT-034 exists for. */}
      {history.length > 0 ? (
        <ol data-testid="request-history">
          {history.map((step) => (
            <li key={`${step.status}:${step.changed_at}`}>
              {step.status.replace('_', ' ').toLowerCase()} on {step.changed_at.slice(0, 10)}
            </li>
          ))}
        </ol>
      ) : (
        <p data-testid="request-history-absent" data-state="never-collected">
          No status changes have been read for this request yet, which is not the same as it
          never having moved.
        </p>
      )}
      <p data-testid="request-not-ours">
        {request.submitted_by_meter
          ? 'Submitted by Meter.'
          : 'Submitted outside Meter. This product reads the history and never adds to it.'}
      </p>
    </article>
  );
}

export function QuotaDetailScreen() {
  const { serviceCode = '', quotaCode = '' } = useParams();
  const query = useQuotaDetail(serviceCode, quotaCode);
  const envelope = query.data?.data;
  useReportMeta('governance-quota', envelope?.meta);

  const found = envelope?.data;
  const slices = (found?.measurable.length ?? 0) + (found?.unmeasurable.length ?? 0);
  const state = surfaceStateFor(query, envelope?.meta, slices, 'none', 'slices');
  const drafts = found?.drafts ?? [];
  const refusals = found?.draft_refusals ?? [];
  const requests = found?.requests ?? [];

  return (
    <section aria-label="Quota">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        <>
          <h2 data-testid="quota-heading">
            {found?.quota_name ?? quotaCode}
            <span data-testid="quota-detail-code"> {found?.quota_code ?? quotaCode}</span>
          </h2>

          {found?.is_adjustable === false ? (
            <p data-testid="quota-hard-limit">
              AWS does not raise this limit, so there is nothing to request. The way past it is a
              different architecture rather than a bigger number.
            </p>
          ) : null}

          <h3>The increase Meter would ask for</h3>
          {drafts.length === 0 && refusals.length === 0 ? (
            <p data-testid="quota-no-drafts" data-state="never-collected">
              Nothing has been collected for this quota yet, so there is nothing to size a
              request from.
            </p>
          ) : null}
          {drafts.map((draft) => (
            <Draft key={`${draft.account_id}:${draft.region_id ?? 'global'}`} draft={draft} />
          ))}
          {refusals.map((refusal) => (
            <Refusal
              key={`${refusal.account_id}:${refusal.region_id ?? 'global'}`}
              refusal={refusal}
            />
          ))}

          <h3>Requests against this quota</h3>
          {requests.length === 0 ? (
            <p data-testid="quota-no-requests" data-state="never-collected">
              No increase has been requested for this quota, or none has been read yet. Those are
              different facts and this screen cannot tell them apart.
            </p>
          ) : null}
          {requests.map((request) => (
            <Request
              key={request.request_id}
              request={request}
              history={found?.history[request.request_id] ?? []}
            />
          ))}
        </>
      </StateBoundary>
    </section>
  );
}
