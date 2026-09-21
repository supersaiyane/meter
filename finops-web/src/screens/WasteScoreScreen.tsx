import { Link } from 'react-router';

import { useFinopsScore } from '../api/queries';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiScore, ApiScoreComponent } from '../api/types';
import type { Freshness } from '../components/provenance';

/**
 * A posture score, with the parts it is made of. FEAT-043.
 *
 * This feature was adopted over an objection, and the objection became its ship
 * condition: a composite number nobody can take apart is an opinion with a number
 * on it. So the components are on this page, under the score, not behind a link,
 * and each one names the findings that moved it.
 *
 * **A component that could not be computed is not a zero.** It says so and is
 * excluded from the denominator, which is why the score is rendered as a total
 * out of its available weight rather than out of a hundred. Fifty four out of
 * eighty five is a different claim from fifty four out of a hundred, and a reader
 * cannot tell without being told.
 *
 * **An account with no score is listed by name.** Not omitted, and not shown as
 * nought. An account nobody could assess is different from an account assessed
 * and found wanting, and a shorter league table is not something anybody notices.
 *
 * Worst first, because a list sorted best first is a list nobody scrolls and the
 * account at the bottom is the one the reader came for.
 */

function points(component: ApiScoreComponent): number {
  return Number(component.points ?? 0);
}

function ScoreComponent({ component }: { readonly component: ApiScoreComponent }) {
  return (
    <li data-testid={`component-${component.name}`}>
      <h4>
        {component.name}
        {component.points === null ? (
          // Excluded rather than scored. A nought here would report the worst
          // possible posture for a dimension nobody measured.
          <span data-testid={`component-absent-${component.name}`}>
            {' '}
            could not be computed, so it is excluded from the score rather than counted as
            nought
          </span>
        ) : (
          <span data-testid={`component-points-${component.name}`}>
            {' '}
            {points(component)} of {component.weight}
          </span>
        )}
      </h4>
      <p>{component.why}</p>
      {component.findings.length > 0 ? (
        <ul data-testid={`component-findings-${component.name}`}>
          {component.findings.map((finding) => (
            <li key={finding}>
              {/* Each component links to what moved it. The ship condition, at
                  the level a reader actually uses. */}
              <Link to={`/waste?finding=${finding}`}>{finding}</Link>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function ScoreCard({
  score,
  freshness,
}: {
  readonly score: ApiScore;
  readonly freshness: Freshness;
}) {
  return (
    <article
      aria-label={`Score for ${score.account_id}`}
      data-testid={`score-${score.account_id}`}
    >
      <h3>{score.account_id}</h3>
      <Figure
        value={{ kind: 'measured', amount: score.total }}
        freshness={freshness}
        unit="count"
        // Out of the weight that was actually available, not out of a hundred.
        label={`out of ${String(score.available_weight)} available weight`}
      />
      <p data-testid={`score-why-${score.account_id}`}>{score.why}</p>
      <ul>
        {score.components.map((component) => (
          <ScoreComponent key={component.name} component={component} />
        ))}
      </ul>
    </article>
  );
}

export function WasteScoreScreen() {
  const query = useFinopsScore();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const scores = found?.scores ?? [];
  const unscored = found?.unscored ?? [];

  useReportMeta('waste-score', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, scores.length, 'none', 'finops_score');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  return (
    <section aria-label="FinOps Score">
      <StateBoundary state={state}>
        <div data-testid="score-list">
          {scores.map((score) => (
            <ScoreCard key={score.account_id} score={score} freshness={freshness} />
          ))}
        </div>
      </StateBoundary>

      {/*
        Outside the boundary, because this is a fact about the estate rather than
        about the request, and it is the one the boundary would swallow on an
        estate where nothing could be scored at all.
      */}
      {unscored.length > 0 ? (
        <section aria-label="Not assessed" data-testid="score-unscored">
          <h3>Not assessed</h3>
          <p>
            No waste collection reached these accounts, so they have no score. That is different
            from a bad score and they are listed rather than left out of the table
          </p>
          <ul>
            {unscored.map((account) => (
              <li key={account} data-testid={`unscored-${account}`}>
                {account}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
