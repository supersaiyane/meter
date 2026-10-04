"""TASK-P6-012, the server half. A `forecast` is a word nothing on this side may say yet.

ADR-0015 sets four conditions on showing a forecast, and the third provenance value is
only the last. The interface carries the word so the vocabulary lands alone; this file
holds the line on the server, where a forecast would have to be produced: the database
vocabulary refuses one, and no production module assigns one to a provenance field.
When a forecast is finally allowed, the decision is made by editing this file.
"""

from __future__ import annotations

import re
from pathlib import Path

from finops_api.db import models

ROOT = Path(__file__).resolve().parent.parent.parent
PRODUCERS = ("finops_api", "finops_query", "finops_ingest", "finops_core", "finops_providers")

#: A provenance field set to the word, in either keyword or mapping form.
ASSIGNED = re.compile(r"""provenance["']?\s*[=:]\s*["']forecast["']""")


def test_the_database_vocabulary_refuses_a_forecast_today() -> None:
    assert "forecast" not in models.PROVENANCES
    assert set(models.PROVENANCES) == {"measured", "modelled"}


def test_no_production_module_assigns_forecast_to_a_provenance() -> None:
    sources = [path for package in PRODUCERS for path in (ROOT / package).rglob("*.py")]
    assert len(sources) > 100, "the scan found almost nothing, so it would pass vacuously"
    offenders = [
        f"{path.relative_to(ROOT)}"
        for path in sources
        if ASSIGNED.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_pattern_would_catch_one() -> None:
    """A scan whose pattern matches nothing proves nothing, so it is shown to match."""
    assert ASSIGNED.search('provenance="forecast"')
    assert ASSIGNED.search("{'provenance': 'forecast'}")
    assert not ASSIGNED.search('provenance="modelled"')
