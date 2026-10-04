"""What must not reach a prompt: a secret in a question, redacted or blocked. FEAT-046.

TASK-P7-013, P7 spec section 6.3. ADR-0028 put the model inside the account, so this is no
longer the control standing between customer data and a third party. It is built anyway,
because a secret in a prompt is a secret in a log whoever receives it, and because the day
somebody reopens ADR-0028 this is the thing that has to exist already.

**The rules are gitleaks', not a second list.** Seven of the default rules gitleaks 8.30.1
ships, the version `make security-scan` runs, copied with their identifiers, patterns and
entropy floors. `tests/query/test_redaction.py` runs the real binary over planted samples
and asserts it names the same rule, so the two cannot drift apart unnoticed.

**One difference, on purpose.** gitleaks allowlists an AWS key ending in EXAMPLE, because
documentation is full of them and a code scanner would otherwise flag every README. A
question is not documentation. A string shaped like a credential is withheld whether or not
it looks like an example, because a false positive costs a rephrased question and a false
negative is a credential in a log.

**Blocked or redacted, per rule.** A credential that grants access, a cloud key, a private
key or an access token, blocks the question: it is sent nowhere, and the asker is told to
rotate it, because it has already left the place it was safe. A secret whose removal leaves
the question whole, a webhook URL or a pasted token, is redacted and the rest is sent.

**Nothing of the secret is kept.** The question is kept with the secret replaced by the
rule's name, and a hit is the rule and the action, never the secret, its position or its
length, because a table of what was redacted is a worse leak than the prompt would have
been.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    BLOCKED = "BLOCKED"
    REDACTED = "REDACTED"


@dataclass(frozen=True)
class Rule:
    """One gitleaks rule, by its own identifier, and what this product does on a match."""

    rule_id: str
    pattern: re.Pattern[str]
    #: gitleaks' Shannon entropy floor for the secret, where the rule sets one.
    entropy: float | None
    action: Action


def _gitleaks(pattern: str) -> re.Pattern[str]:
    # ASCII, because gitleaks is Go RE2, whose \w and \s are ASCII only.
    return re.compile(pattern, re.ASCII)


#: From gitleaks 8.30.1's default configuration, `config/gitleaks.toml`, unchanged.
RULES: tuple[Rule, ...] = (
    Rule(
        "private-key",
        _gitleaks(
            r"(?i)-----BEGIN[ A-Z0-9_-]{0,100}PRIVATE KEY(?: BLOCK)?-----[\s\S-]{64,}?"
            r"KEY(?: BLOCK)?-----"
        ),
        None,
        Action.BLOCKED,
    ),
    Rule(
        "aws-access-token",
        _gitleaks(r"\b((?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z2-7]{16})\b"),
        3.0,
        Action.BLOCKED,
    ),
    Rule("github-pat", _gitleaks(r"ghp_[0-9a-zA-Z]{36}"), 3.0, Action.BLOCKED),
    Rule("gitlab-pat", _gitleaks(r"glpat-[\w-]{20}"), 3.0, Action.BLOCKED),
    Rule(
        "stripe-access-token",
        _gitleaks(
            r"""\b((?:sk|rk)_(?:test|live|prod)_[a-zA-Z0-9]{10,99})(?:[\x60'"\s;]|\\[nr]|$)"""
        ),
        2.0,
        Action.BLOCKED,
    ),
    Rule(
        "slack-webhook-url",
        _gitleaks(
            r"(?:https?://)?hooks.slack.com/(?:services|workflows|triggers)/[A-Za-z0-9+/]{43,56}"
        ),
        None,
        Action.REDACTED,
    ),
    Rule(
        "jwt",
        _gitleaks(
            r"""\b(ey[a-zA-Z0-9]{17,}\.ey[a-zA-Z0-9\/\\_-]{17,}\.(?:[a-zA-Z0-9\/\\_-]{10,}={0,2})?)"""
            r"""(?:[\x60'"\s;]|\\[nr]|$)"""
        ),
        3.0,
        Action.REDACTED,
    ),
)


@dataclass(frozen=True)
class Hit:
    """One secret found: which rule found it and what was done. Nothing of the secret."""

    rule_id: str
    action: Action


@dataclass(frozen=True)
class Scan:
    """The question with every secret replaced, and what was found."""

    text: str
    hits: tuple[Hit, ...]

    @property
    def blocked(self) -> bool:
        return any(hit.action is Action.BLOCKED for hit in self.hits)


def shannon(text: str) -> float:
    """Bits per character, the measure gitleaks' `entropy` floor is written in."""
    if not text:
        return 0.0
    total = len(text)
    return -sum(count / total * math.log2(count / total) for count in Counter(text).values())


def scan(question: str) -> Scan:
    """Every secret in `question` replaced by the name of the rule that found it."""
    text = question
    hits: list[Hit] = []
    for rule in RULES:
        group = 1 if rule.pattern.groups else 0

        def replace(match: re.Match[str], rule: Rule = rule, group: int = group) -> str:
            secret = match.group(group)
            if rule.entropy is not None and shannon(secret) < rule.entropy:
                return match.group(0)
            hits.append(Hit(rule_id=rule.rule_id, action=rule.action))
            start, end = match.span(group)
            whole, offset = match.group(0), match.start(0)
            return f"{whole[: start - offset]}[redacted: {rule.rule_id}]{whole[end - offset :]}"

        text = rule.pattern.sub(replace, text)
    return Scan(text=text, hits=tuple(hits))


def blocked_reason(found: Scan) -> str:
    """What a blocked question is told. Names the rules, never the secret."""
    rules = ", ".join(sorted({hit.rule_id for hit in found.hits if hit.action is Action.BLOCKED}))
    return (
        f"The question held what looks like a credential, by the rule {rules}, so it was sent "
        f"nowhere and kept only with the credential removed. Treat that credential as exposed "
        f"and rotate it."
    )
