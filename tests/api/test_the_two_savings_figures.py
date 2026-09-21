"""The estimate and the realization, and why nothing can add them.

TASK-P3-014. ISS-029 names one failure mode: every FinOps tool inflates identified
savings, and the inflation always happens the same way, by adding a modelled number
to a measured one and reporting the total. Neither number is wrong on its own. The
sum is, and it is the number that reaches a board slide.

`tests/api/test_waste_routes.py` already asserts that the two routes return disjoint
payloads. This file asserts the stronger thing: that the sum cannot be written. One
test checks the response models hold at most one kind of money each, derived over
every model rather than over the two that exist today, and one test asks mypy to
reject the sum and fails if mypy accepts it.

A test asserting something cannot be done reads as ceremony. It is the cheapest
guard available against the one mistake this feature exists to avoid, and it costs a
second of mypy.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from mypy import api
from pydantic import BaseModel

from finops_api import schemas

#: Fields carrying a modelled figure, and fields carrying a measured one. Matched on
#: name because the shape of the guard has to survive a model nobody has written
#: yet: a future response holding `estimated_annual_saving` beside `cost_after` is
#: the same mistake under a different spelling.
MODELLED = ("estimated_",)
MEASURED = ("cost_before", "cost_after", "realized_")

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]

#: A caller doing the arithmetic the product refuses to do. `RealizedSavingOut` has
#: no estimated field, so mypy rejects the attribute, which is the point: the
#: measured response cannot be made to carry the modelled figure.
FORBIDDEN_SUM = """
from decimal import Decimal

from finops_api.schemas import RealizedSavingOut


def total(realized: RealizedSavingOut) -> Decimal:
    return realized.cost_before - realized.cost_after + realized.estimated_monthly_saving
"""


def response_models() -> dict[str, type[BaseModel]]:
    """Every Pydantic response model in `finops_api.schemas`.

    Enumerated rather than listed, so a model added tomorrow is covered by the test
    the day it is added rather than the day somebody remembers this file.
    """
    return {
        name: value
        for name, value in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(value, BaseModel) and value is not BaseModel
    }


def kinds_of_money(model: type[BaseModel]) -> tuple[list[str], list[str]]:
    fields = tuple(model.model_fields)
    modelled = [field for field in fields if field.startswith(MODELLED)]
    measured = [field for field in fields if field.startswith(MEASURED)]
    return modelled, measured


def test_the_enumeration_finds_the_models_that_exist() -> None:
    """The guard's own input, checked before the guard is trusted.

    An enumeration that found nothing would make the test below pass for every
    possible schema, which is how a derived check quietly stops checking.
    """
    found = response_models()
    assert len(found) > 20, f"only found {sorted(found)}"
    assert "RecommendationOut" in found
    assert "RealizedSavingOut" in found


def test_the_two_kinds_of_money_are_recognised_where_they_live() -> None:
    # If the name matching stopped working, every model would look clean and the
    # real test would pass by finding nothing anywhere.
    modelled, measured = kinds_of_money(schemas.RecommendationOut)
    assert modelled == ["estimated_monthly_saving"]
    assert measured == []
    modelled, measured = kinds_of_money(schemas.RealizedSavingOut)
    assert modelled == []
    assert sorted(measured) == ["cost_after", "cost_before"]


@pytest.mark.parametrize("name", sorted(response_models()))
def test_no_response_model_carries_both_kinds_of_money(name: str) -> None:
    """The structural half of the guard.

    A response holding an estimate beside a realization is the first place somebody
    writes the sum, and they write it because the object made it easy. So the object
    does not exist, and this is checked for every model rather than for the two that
    happen to matter today.
    """
    modelled, measured = kinds_of_money(response_models()[name])
    assert not (modelled and measured), (
        f"{name} carries a modelled figure {modelled} beside a measured one {measured}. "
        f"An estimate and a realization in one object is how identified savings get "
        f"inflated. Serve them from different routes with different types"
    )


def test_summing_them_fails_to_type_check(tmp_path: Path) -> None:
    """The name says which of the two ways the plan allows: it fails to type check.

    mypy is asked to check a module that reads an estimated saving off the measured
    response. If mypy ever accepts it, the measured response has grown a modelled
    field and this test is the thing that says so.
    """
    snippet = tmp_path / "attempted_sum.py"
    snippet.write_text(FORBIDDEN_SUM)
    stdout, _, status = api.run(
        [
            "--no-error-summary",
            "--no-incremental",
            "--follow-imports=silent",
            str(snippet),
        ]
    )
    assert status != 0, f"mypy accepted the sum, which means it is now writable:\n{stdout}"
    assert 'has no attribute "estimated_monthly_saving"' in stdout, stdout


def test_the_routes_are_separate_modules_of_work_rather_than_one_handler() -> None:
    """Asserted against the source, because the separation is the feature.

    Two routes returning two types is what makes the sum somebody's deliberate act
    rather than a field they found already filled in. A single handler returning both
    would satisfy every runtime test in `test_waste_routes.py` and undo the point.
    """
    routes = (REPOSITORY_ROOT / "finops_api" / "routes" / "waste.py").read_text()
    assert "response_model=Envelope[RecommendationsOut]" in routes
    assert "response_model=Envelope[RealizedSavingsOut]" in routes
    # The realized route never mentions the estimate, so there is nothing to carry
    # across even if a later handler were tempted to join the two reads.
    # The field name rather than the word, because the handler's own docstring
    # explains that it carries no estimate and a prose match would flag that.
    realized = routes[routes.index("/waste/savings") :]
    assert "estimated_monthly_saving" not in realized, (
        "the savings handler now reads the estimated figure, which is the field "
        "somebody adds to the realization"
    )
