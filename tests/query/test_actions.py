"""The risk table, and the two things it exists to stop.

FEAT-052. Pure, because all of it is.

The cases worth having are not a row by row restatement of the table, which would be the
table written twice. They are the properties the table exists to hold: that it covers the
closed set, that no regret means both halves, and that the classes which disturb nothing are
mostly still permanent, which is the intuition this feature was built to correct.
"""

from __future__ import annotations

import pytest

from finops_core.domain.waste import WasteClass
from finops_query.actions import NO_REGRET_CLASSES, RISK_OF, risk_of


def test_every_waste_class_has_a_risk() -> None:
    """A class added to the domain without a row here would reach a screen with no risk
    statement, and every default the screen could pick is a lie in one direction: reversible
    understates a deletion, irreversible overstates a resize."""
    missing = set(WasteClass) - set(RISK_OF)
    assert not missing, f"these classes have no risk row: {sorted(one.value for one in missing)}"


def test_no_risk_row_names_a_class_that_does_not_exist() -> None:
    """The other direction. A row for a class nobody can produce is a row that is never read,
    which looks exactly like a row that works."""
    assert set(RISK_OF) <= set(WasteClass)


def test_every_risk_explains_itself() -> None:
    """ADR-0012's argument applied to a flag rather than a cadence: a flag nobody can argue
    with is a flag nobody can safely change."""
    for waste_class, risk in RISK_OF.items():
        assert len(risk.why) > 40, waste_class.value
        assert risk.why.strip().endswith("."), waste_class.value


# --- no regret means both halves --------------------------------------------


def test_no_regret_needs_reversible_and_undisturbing() -> None:
    for waste_class in NO_REGRET_CLASSES:
        risk = risk_of(waste_class)
        assert risk.reversible
        assert not risk.disturbs_running_work


def test_a_reversible_change_that_restarts_a_workload_is_not_no_regret() -> None:
    """The half a confidence score would hide. Rightsizing an instance can be undone and
    still stops the workload to do it."""
    risk = risk_of(WasteClass.RIGHTSIZE_INSTANCE)
    assert risk.reversible
    assert risk.disturbs_running_work
    assert not risk.is_no_regret


def test_an_undisturbing_change_that_cannot_be_undone_is_not_no_regret() -> None:
    """The half that matters more, and the reason this module exists. Nothing is running, and
    the address is still gone forever."""
    risk = risk_of(WasteClass.ELASTIC_IP_UNASSOCIATED)
    assert not risk.reversible
    assert not risk.disturbs_running_work
    assert not risk.is_no_regret


# --- the finding this feature was built to correct ---------------------------


def test_most_classes_that_disturb_nothing_are_still_permanent() -> None:
    """The intuition being corrected, asserted as a ratio rather than described.

    A reader scanning a list treats "nothing is running" as "safe to try". Of the classes
    where nothing is running, most cannot be undone, so a surface that flagged them on the
    first test alone would be recommending irreversible deletions as the easy wins.
    """
    quiet = {one for one, risk in RISK_OF.items() if not risk.disturbs_running_work}
    permanent = {one for one in quiet if not risk_of(one).reversible}
    assert len(quiet) > len(permanent) > 0
    assert len(permanent) > len(quiet - permanent), (
        "the premise of this test has changed: most quiet classes are now reversible, so the "
        "warning in the module docstring needs rewriting rather than this assertion relaxing"
    )


def test_no_regret_is_a_small_minority() -> None:
    """Three of eighteen at the time of writing. Asserted as a bound rather than an exact
    count so adding a class does not fail here, and bounded above because a surface promising
    a page of safe wins would be inventing most of them."""
    assert 0 < len(NO_REGRET_CLASSES) <= len(RISK_OF) // 4


@pytest.mark.parametrize(
    "waste_class",
    [
        WasteClass.EBS_UNATTACHED,
        WasteClass.ELASTIC_IP_UNASSOCIATED,
        WasteClass.LOG_GROUP_NO_RETENTION,
        WasteClass.SNAPSHOT_AGED,
    ],
    ids=lambda one: one.value,
)
def test_the_traps_are_marked_irreversible(waste_class: WasteClass) -> None:
    """Named individually on purpose. These four are the ones a reader is most likely to apply
    without thinking, and each one destroys something: a volume's data, an address nothing
    reissues, every log line past the new retention, or a restore path."""
    assert not risk_of(waste_class).reversible
    assert not risk_of(waste_class).is_no_regret


def test_an_unknown_class_raises_rather_than_defaulting() -> None:
    with pytest.raises(KeyError):
        RISK_OF["NOT_A_CLASS"]  # type: ignore[index]


def test_the_two_questions_are_independent_of_each_other() -> None:
    """All four combinations occur, which is what makes two fields rather than one label the
    right shape. A table where reversible always tracked disturbing would be one field with
    two names, and the first draft of the route test tried to assert this against seeded rows
    instead, which tested the fixture: the first party source produces only rightsizings and
    an unassociated address, so it could never have shown more than two of the four."""
    seen = {(risk.reversible, risk.disturbs_running_work) for risk in RISK_OF.values()}
    assert seen == {(True, True), (True, False), (False, True), (False, False)}
