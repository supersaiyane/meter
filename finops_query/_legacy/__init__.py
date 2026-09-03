"""The prototype, exactly as it arrived, and deliberately not improved.

`sample_lambda.py` is a byte identical copy of the file from
`publicsampledashboard.zip`. It is 2,740 lines and it does everything: config,
credentials, HTTP, classification, cost modelling, CloudTrail attribution,
severity, HTML rendering and delivery.

It is here to be a baseline, not to be read as an example. TASK-P2-001 pins its
current output as golden files, TASK-P2-002 extracts the cost model under those
files, and TASK-P2-003 removes this directory. Until then the rule is simple:
this code is not edited, including its obvious bugs. A baseline that already
contains your fixes is not a baseline, and a golden file regenerated in the same
commit as the change it was meant to catch proves nothing.

Anything that looks wrong is recorded as an ISS entry and fixed in a later task,
where the change to the golden file is visible in the diff.
"""
