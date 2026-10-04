"""What the assistant tells a person to do about a failure, for every cause there is.

Each cause's own remediation text is about re running a collector, which a person who asked
a question cannot do, and until 2026-10-04 the assistant passed that text through. Every
cause now has a sentence written for the assistant, and this holds that none is missing and
none falls back to a collector's advice.
"""

from __future__ import annotations

import pytest

from finops_api.routes.assistant import REMEDIATION
from finops_core.domain.insight import CAUSES


def test_every_cause_has_advice_written_for_the_assistant() -> None:
    assert set(REMEDIATION) == set(CAUSES)


@pytest.mark.parametrize("cause", sorted(CAUSES))
def test_no_advice_tells_a_person_to_run_a_collector(cause: str) -> None:
    assert "collector" not in REMEDIATION[cause].lower()
