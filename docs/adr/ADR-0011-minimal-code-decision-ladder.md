# ADR-0011: A decision ladder before any new code, and token economy in agent work

Date: 2026-08-23
Status: Accepted

## Context

Implementation will be carried out largely by coding agents. Agents
over produce. They install a library where the standard library suffices, wrap
a platform capability that needed no wrapper, and build a component that
already exists three directories away.

Two projects address this directly and are adopted as ground rules.

- **Ponytail** injects a decision ladder before code generation. Reported
  results on a FastAPI and React repository: 54 percent fewer lines, 20 percent
  lower cost, 27 percent faster, with safety preserved.
- **Caveman** compresses agent output and context. Its measured value is
  mostly readability and speed rather than raw cost.

Two more are adopted as pipeline stages: an automated code review agent and a
documentation writer agent.

## Decision

**The ladder, walked in order before writing any new code.**

1. Does this need to exist at all? Delete the requirement if it does not.
2. Does it already exist in this repository? Reuse it.
3. Is it in the Python or TypeScript standard library? Use that.
4. Does AWS already provide it? See ADR-0006, which is this same rung applied
   to recommendations.
5. Is there a maintained dependency that scans clean? See ADR-0010.
6. Only now, write it, and write the smallest version that satisfies the test.

**Output discipline.** Agent responses stay compressed: no preamble, no recap,
no restating the request. One sentence of status, then the work.

**Two pipeline stages.**

- **Review.** An automated review runs on every merge request across
  correctness, security, performance and style, writing a severity ranked
  report. Critical and high findings block the merge.
- **Documentation.** An API reference is generated from source rather than
  written by hand, and docstring coverage is a gate.

## Consequences

Positive.

- Rung four is already the project's stance in ADR-0006. Making the whole
  ladder explicit means the same reasoning applies at every scale, not only to
  recommendation engines.
- Less code means less to review, less to scan, and fewer dependencies, which
  compounds directly into ADR-0010.
- A generated API reference cannot drift from the code the way a handwritten
  one does.

Negative.

- The ladder adds friction to genuinely novel work. Accepted: rungs one to five
  are quick to answer when the answer is no.
- Compressed output is harder to skim for a reader who wants narrative. The
  documents carry the narrative, the agent output does not need to.
- Generated documentation is only as good as the docstrings, which is why
  coverage is a gate rather than a suggestion.

## Alternatives rejected

**Trusting a style guide.** Rejected. Every project has one, and agents do not
follow guidance that is not enforced at a gate.

**Installing the tools as agent plugins only.** Rejected as insufficient on its
own. A plugin shapes one agent's behaviour. The gates in the pipeline hold
regardless of who or what wrote the code.

## Guarded

The ladder never removes input validation, error handling, security controls,
accessibility, or the tests that encode this project's hard rules. Minimal
means no unnecessary code, not no necessary code.
