# Reference material

Source that Meter was built from or against, kept because reading it answers
questions the code it became cannot. Nothing here is imported, executed or
tested. It is not part of the product.

## sample_lambda.py.txt

The prototype P2 was planned against. One AWS Lambda, 2,740 lines, doing the
whole job in a single file: discovering Grafana workspaces, minting a temporary
service account token, listing dashboards and alert rules, parsing their time
ranges and refresh intervals, pricing the result, and rendering an HTML report.

Imported byte identical as `TASK-P2-001` on 2026-09-02, sha256 beginning
`80854e42`. `TASK-P2-002` extracted the cost model from it and `TASK-P2-003`
decomposed the rest and deleted the copy, which is why it is not in
`finops_query/` any more. This restores it for reading.

### Why the file name ends in .txt

`make check-writing` greps every `*.py` in the repository for em dashes, and
this file contains twelve of them, in HTML it emits and in two of its comments.
That rule exists so the product's own writing stays consistent, and it should
not be weakened for a file nobody maintains. Editing the prototype was the
other option and is worse: its value is that it is exactly what was handed
over, and a corrected copy is no longer evidence of anything.

So the extension keeps it out of every Python tool and the content is
untouched. Confirm that at any time:

```bash
shasum -a 256 docs/reference/sample_lambda.py.txt   # begins 80854e42
```

### What still holds it to account

The prototype was frozen before a line of it was changed, so its behaviour is
still enforced even though the file left the package.

| What | Where |
| --- | --- |
| Its outputs, 15 of them | `tests/query/fixtures/golden/` |
| The dashboards fed to it, 14 | `tests/query/fixtures/dashboards/` |
| The alert rules fed to it, 4 | `tests/query/fixtures/alerts/alert-rules.json` |
| The offline harness | `tests/query/conftest.py` |

`finops_query` has to reproduce those golden outputs. That is the sense in
which this file is still the reference: not as code to consult, but as the
answer key the extracted cost model is graded against.

### What became of it

| In the prototype | In the product |
| --- | --- |
| `discover_workspaces`, `list_dashboards`, `list_alert_rules` | the `QuerySurface` port and its AWS adapter |
| `parse_relative_range_seconds` and the duration regexes | window parsing in `finops_query` |
| the pricing arithmetic | the cost model, under the golden files |
| the HTML report it rendered | the findings and groups screens |

The git history has it too, at commit `a2304cf`, if a diff against the original
import is ever needed.
