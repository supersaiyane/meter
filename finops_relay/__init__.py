"""The relay outside the hub's VPC. TASK-P9-001, ADR-0035.

A package of its own, below every other, importing nothing of Meter's and nothing beyond botocore,
because it runs as a Lambda function whose runtime provides boto3 and nothing else. A contract in
`pyproject.toml` holds it to that.
"""
