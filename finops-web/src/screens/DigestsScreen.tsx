import { useDigests } from '../api/queries';
import type { ApiDigest, ApiMeta } from '../api/types';
import { CitedProse } from '../components/CitedProse';
import { FixtureBand } from '../components/FixtureBand';
import { StateBoundary } from '../components/StateBoundary';
import type { SurfaceState } from '../components/surfaceState';
import { useReportMeta } from '../shell/metaRegistry';
import { stampUtc } from './enforcementTime';
import { surfaceStateFor, type QueryLike } from './surfaceStateFor';

/**
 * A week of spend, said in sentences whose every figure is cited. FEAT-041, TASK-P7-012.
 *
 * **Composed whether or not anybody can send it.** Where a digest goes is OPEN-11, and until it
 * is answered every digest is composed and kept here. That is a real state and the screen says
 * it, with the reason the collector stored, rather than leaving a reader to wonder why nothing
 * arrived in their inbox.
 *
 * **The same citations as an answer.** A digest obeys the rule an answer obeys, no figure in
 * the prose, so it is drawn by the same component: a reader checks a digest's numbers exactly
 * the way they check an answer's.
 *
 * **Payer wide.** A digest sums the whole payer, so a reader whose scope is narrower is shown
 * none, and the coverage says why rather than an empty list saying nothing.
 */

/** The collector that composes the digests, `finops_ingest/collectors/digests.py`. */
const COLLECTOR = 'team_digests';

/** The bill's own word for spend no team tag claims, `finops_core/domain/platform.py`. */
const UNALLOCATED = 'unallocated';

/**
 * Which of the seven states the list is in.
 *
 * The shared rule, with one case ahead of it. A narrowed reader is sent no digests, so the
 * envelope holds no `as_of`, and the shared rule would read that as never collected. The
 * coverage is what explains the empty list, so a partial view is decided first.
 */
function digestsState(query: QueryLike, meta: ApiMeta | undefined, rows: number): SurfaceState {
  const shared = surfaceStateFor(query, meta, rows, 'none', COLLECTOR);
  if (shared.kind === 'loading' || shared.kind === 'failed' || meta === undefined)
    return shared;
  if (meta.scope_coverage.is_partial) {
    return {
      kind: 'partial',
      missing: meta.scope_coverage.total - meta.scope_coverage.visible,
      reason: 'A digest sums the whole payer, so reading one needs organization wide scope.',
    };
  }
  return shared;
}

/** Who a digest is for, in words. Spend no team claims is never called a team. */
function audienceOf(digest: ApiDigest): string {
  if (digest.audience === 'executive') return 'The organization';
  if (digest.team === null) return 'A team digest with no team recorded';
  return digest.team === UNALLOCATED ? 'Spend no team tag claims' : `Team ${digest.team}`;
}

function Digest({ digest }: { readonly digest: ApiDigest }) {
  const heading = `digest-${digest.digest_id}`;
  return (
    <article
      data-testid="digest"
      data-audience={digest.audience}
      data-sent={digest.sent_at === null ? 'false' : 'true'}
      aria-labelledby={heading}
    >
      <h3 id={heading} data-testid="digest-audience">
        {audienceOf(digest)}
      </h3>
      <p data-testid="digest-week">
        {digest.audience === 'executive' ? 'Executive digest' : 'Team digest'} for the week{' '}
        <time dateTime={digest.period_start}>{digest.period_start}</time> to{' '}
        <time dateTime={digest.period_end}>{digest.period_end}</time>, composed{' '}
        <time dateTime={digest.composed_at}>{stampUtc(digest.composed_at)}</time>.
      </p>
      {digest.sent_at === null ? (
        // Not an absence to hide. The first run and every send failure end here, and a reader
        // waiting for a digest that never arrived needs to read why.
        <p data-testid="digest-unsent" data-state="unsent">
          <strong>Composed and not sent.</strong>{' '}
          {digest.unsent_reason ?? 'No reason was stored with it.'}
        </p>
      ) : (
        <p data-testid="digest-sent" data-state="sent">
          <strong>Sent</strong>{' '}
          <time dateTime={digest.sent_at}>{stampUtc(digest.sent_at)}</time>.
        </p>
      )}
      <CitedProse
        scope={digest.digest_id}
        prose={digest.prose}
        citations={digest.citations}
        readAt={digest.composed_at}
      />
    </article>
  );
}

export function DigestsScreen() {
  const query = useDigests();
  const envelope = query.data?.data;
  useReportMeta('assistant-digests', envelope?.meta);

  const digests = envelope?.data ?? [];
  const state = digestsState(query, envelope?.meta, digests.length);

  return (
    <section aria-label="Digests">
      <FixtureBand source={query.data?.source} />
      <StateBoundary state={state}>
        {digests.length === 0 ? null : (
          <div data-testid="digests">
            {/* The level between the shell's page heading and each digest's own, so a reader
                moving by heading meets every level in order. */}
            <h2>Weekly digests, newest first</h2>
            {digests.map((digest) => (
              <Digest key={digest.digest_id} digest={digest} />
            ))}
          </div>
        )}
      </StateBoundary>
    </section>
  );
}
