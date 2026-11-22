# finops-web

The Meter frontend. Vite, React and TypeScript.

Run it through the Makefile at the repository root rather than directly, so the
same commands run here and in the pipeline.

```bash
make setup     # npm ci
make lint      # eslint, zero warnings tolerated
make test-all  # vitest
```

## Why the versions are pinned where they are

**TypeScript is held below 6.** The current major is 7, and `typescript-eslint`
declares a peer range of `>=4.8.4 <6.1.0`. Installing TypeScript 7 produces a
lint step that cannot parse the code it is meant to check. This pin lifts when
`typescript-eslint` supports 7.

**ESLint uses flat config**, in `eslint.config.js`. The task listed
`.eslintrc.cjs`, which ESLint 9 and later do not read. That file would have
produced a lint step that silently checked nothing, which is worse than no lint
step: it reports success over code it never looked at.

## What is deliberately absent

No component library. The product's central requirement is a bespoke rendering
of every number, and the components a library gives you are exactly the ones we
have to control. See ADR-0019 and `docs/12-UI-DESIGN.md` section 12.

No state management library. React Query covers server state, and P0 has no
client state worth managing.
