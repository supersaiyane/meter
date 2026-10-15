"""gp2 to gp3, as an edit to the one block that declares the volume. FEAT-093, TASK-P15-005.

P15 spec section 5.4, OPEN-43. The fix for a gp2 volume is not a new file but a change to the
`resource "aws_ebs_volume"` block that declares it: `type = "gp3"`, and `iops` and `throughput`
where FEAT-074's rule found the volume needs more than gp3 includes. Pure text arithmetic over the
files the mapped folder holds, so it is tested on real Terraform without a repository.

**It refuses whatever it cannot read for certain, and says why.** Terraform written by hand varies,
and a change that may not plan is worse than none, spec section 10. So it refuses an address with
an instance key or inside a module, a block found in no file or in more than one, a block written
on one line, a `type`, `iops` or `throughput` set by a variable or any expression rather than a
literal, a block that is already gp3, an `iops` or `throughput` gp3 would not need, and a
recommendation that does not record what gp3 must give. Strings, comments and heredocs are skipped
when reading, so a brace or an attribute name inside one is never mistaken for code.

**It keeps the file as `terraform fmt` would.** A line it adds joins the run of one line
attributes it sits in, and the run's equals signs are aligned again, so a repository whose
pipeline checks formatting still passes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from finops_core.ports.pull_requests import FileChange, PullRequestDraft, RepositoryFile
from finops_query.remediation import INSTANCE_KEY, NotAuthored, RecommendationFacts
from finops_query.volumes import GP3_INCLUDED_IOPS, GP3_INCLUDED_MIBPS

RESOURCE: Final = "aws_ebs_volume"
#: The attributes the edit reads and writes, in the order it adds them.
ATTRIBUTES: Final = ("type", "iops", "throughput")

_HEADER = re.compile(r'resource\s+"aws_ebs_volume"\s+"(?P<name>[A-Za-z_][A-Za-z0-9_-]*)"\s*\{')
_ATTRIBUTE = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z_][A-Za-z0-9_-]*)[ \t]*=(?!=)")
_ASSIGNED = re.compile(r"^([ \t]*)([A-Za-z_][A-Za-z0-9_-]*)[ \t]*=[ \t]*(.*)$")
_VALUE = re.compile(r'^([^=]*=[ \t]*)("[^"]*"|[0-9]+)(.*)$')
_NUMBER = re.compile(r"^[0-9]+$")
_HEREDOC = re.compile(r"<<-?([A-Za-z_][A-Za-z0-9_]*)[ \t]*\n")


@dataclass(frozen=True)
class Gp3Figures:
    """What gp3 must give the volume, as FEAT-074's rule found it. None where not recorded."""

    iops: int | None
    mibps: int | None


@dataclass(frozen=True)
class Edited:
    """The one file changed, its new text, and each change in words for the pull request."""

    path: str
    content: str
    said: tuple[str, ...]


def edit_volume(
    files: Sequence[RepositoryFile], address: str, figures: Gp3Figures
) -> Edited | NotAuthored:
    """The block for `address` moved to gp3 in its file, or why it is not edited."""
    if figures.iops is None or figures.mibps is None:
        return NotAuthored(
            reason="The recommendation does not record the IOPS and throughput gp3 must give, so "
            "the edit would guess them. The volume collector records them on its next pass."
        )
    refused = _address_refused(address)
    if refused is not None:
        return NotAuthored(reason=refused)
    name = address.split(".", 1)[1]
    found = [(file, span) for file in files for span in _blocks(file.content) if span[0] == name]
    if not found:
        return NotAuthored(
            reason=f"No .tf file in the mapped folder declares {address}, so there is no block "
            "to edit. The mapping may name another folder than the one that declares it."
        )
    if len(found) > 1:
        paths = ", ".join(sorted(file.path for file, _span in found))
        return NotAuthored(reason=f"{address} is declared more than once, in {paths}.")
    file, (_name, open_at, close_at) = found[0]
    return _edit(file, open_at, close_at, address, figures)


def author_gp3(
    recommendation: RecommendationFacts, address: str, edited: Edited
) -> PullRequestDraft:
    """The pull request for an edit already made."""
    changes = "\n".join(f"- {line}" for line in edited.said)
    body = "\n".join(
        (
            f"Meter recommends moving `{recommendation.resource_id}` in account "
            f"`{recommendation.sub_account_id}`, region `{recommendation.region_id}`, from gp2 "
            "to gp3.",
            "",
            f"- Recommendation: `{recommendation.recommendation_id}`, "
            f"{recommendation.waste_class.value}",
            f"- Why: {recommendation.rationale}",
            f"- Estimated monthly saving: {recommendation.estimated_monthly_saving} USD, "
            f"modelled, as of {recommendation.as_of.isoformat()}",
            f"- Confidence: {recommendation.confidence}",
            f"- Changed in `{edited.path}`, the block for `{address}`:",
            changes,
            "",
            "The change is made in place and is reversible: a second change moves the volume "
            "back to gp2. Meter merges it only where the tenant's merge policy names gp2 to gp3 "
            "and the repository's own required checks and reviews have passed, ADR-0038.",
        )
    )
    return PullRequestDraft(
        title=f"Move {address} from gp2 to gp3",
        body=body,
        branch=f"meter/remediation/{recommendation.recommendation_id}",
        changes=(FileChange(path=edited.path, content=edited.content),),
        reference=recommendation.recommendation_id,
    )


# -- the address ---------------------------------------------------------------------------


def _address_refused(address: str) -> str | None:
    if INSTANCE_KEY.search(address):
        return (
            f"{address} names one instance of a resource, and an edit to its block would change "
            "every instance, which is not what was recommended."
        )
    if address.startswith("module."):
        return (
            f"{address} is declared inside a module, whose source is not the mapped folder, and "
            "a change to the module changes every caller of it."
        )
    kind, _dot, name = address.partition(".")
    if kind != RESOURCE or not name or "." in name:
        return f"{address} is not an {RESOURCE} block this edit can find."
    return None


# -- reading Terraform: what is code, and where each block is -------------------------------


#: What each character is: code, inside a string, or inside a comment or heredoc.
CODE: Final = "c"
STRING: Final = "s"
OTHER: Final = "o"


def _kinds(text: str) -> list[str]:
    """For each character, whether it is code, inside a string, or a comment or heredoc."""
    kinds = [CODE] * len(text)
    i, length = 0, len(text)
    while i < length:
        if text[i] == '"':
            end, kind = _string_end(text, i) + 1, STRING
        elif text[i] == "#" or text.startswith("//", i):
            found = text.find("\n", i)
            end, kind = (length if found == -1 else found), OTHER
        elif text.startswith("/*", i):
            found = text.find("*/", i + 2)
            end, kind = (length if found == -1 else found + 2), OTHER
        elif text.startswith("<<", i):
            end, kind = _heredoc_end(text, i), OTHER
        else:
            i += 1
            continue
        kinds[i:end] = [kind] * (end - i)
        i = end
    return kinds


def _string_end(text: str, start: int) -> int:
    """The index of the quote closing the string opened at `start`, interpolations included."""
    i, depth = start + 1, 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text.startswith("${", i):
            depth += 1
            i += 2
            continue
        if text[i] == "}" and depth:
            depth -= 1
        elif text[i] == '"' and not depth:
            return i
        i += 1
    return len(text) - 1


def _heredoc_end(text: str, start: int) -> int:
    opened = _HEREDOC.match(text, start)
    if opened is None:
        return start + 2
    closing = re.compile(rf"^[ \t]*{re.escape(opened.group(1))}[ \t]*$", re.MULTILINE)
    found = closing.search(text, opened.end())
    return len(text) if found is None else found.end()


def _blocks(text: str) -> list[tuple[str, int, int]]:
    """Each aws_ebs_volume block: its name, its opening brace and its closing brace."""
    kinds = _kinds(text)
    found = []
    for match in _HEADER.finditer(text):
        if kinds[match.start()] != CODE:
            continue
        open_at = match.end() - 1
        close_at = _closing(text, kinds, open_at)
        if close_at is not None:
            found.append((match.group("name"), open_at, close_at))
    return found


def _closing(text: str, kinds: list[str], open_at: int) -> int | None:
    depth = 0
    for i in range(open_at, len(text)):
        if kinds[i] != CODE:
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


# -- the edit ------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Line:
    """One line of the block's body: a top level, one line attribute where `value` is set."""

    text: str
    key: str | None
    #: The attribute's value, its trailing comment removed, where it fits on its line.
    value: str | None
    #: True for a line the edit added, so alignment can tell the file's own lines apart.
    added: bool = False


def _body(text: str, kinds: list[str], start: int, stop: int) -> list[_Line]:
    """The lines from `start` up to `stop`, each read for a top level attribute."""
    lines, depth, at = [], 0, start
    for line in text[start:stop].split("\n"):
        own = kinds[at : at + len(line)]
        code = "".join(ch if kind == CODE else " " for ch, kind in zip(line, own, strict=True))
        key = value = None
        matched = _ATTRIBUTE.match(code)
        if depth == 0 and matched is not None:
            key = matched.group("key")
            rest = range(matched.end(), len(line))
            said = "".join(line[i] for i in rest if own[i] != OTHER).strip()
            heredoc = any(own[i] == OTHER and line.startswith("<<", i) for i in rest)
            value = said if said and not heredoc and _balanced(code[matched.end() :]) else None
        depth += sum(code.count(o) for o in "{[(") - sum(code.count(c) for c in "}])")
        lines.append(_Line(line, key, value))
        at += len(line) + 1
    return lines


def _balanced(value: str) -> bool:
    return all(value.count(o) == value.count(c) for o, c in ("{}", "[]", "()"))


def _edit(
    file: RepositoryFile, open_at: int, close_at: int, address: str, figures: Gp3Figures
) -> Edited | NotAuthored:
    text = file.content
    head_end = text.find("\n", open_at, close_at)
    if head_end == -1:
        return NotAuthored(
            reason=f"{address} is written on one line, which this edit leaves alone."
        )
    start, last = head_end + 1, text.rfind("\n", open_at, close_at)
    lines = _body(text, _kinds(text), start, last) if start <= last else []
    wanted = {
        "type": '"gp3"',
        "iops": str(figures.iops) if (figures.iops or 0) > GP3_INCLUDED_IOPS else None,
        "throughput": str(figures.mibps) if (figures.mibps or 0) > GP3_INCLUDED_MIBPS else None,
    }
    present = {line.key: line for line in lines if line.key in ATTRIBUTES}
    for key, line in present.items():
        refused = _refusal(key, line.value, wanted[key], address)
        if refused is not None:
            return NotAuthored(reason=refused)
    out, said = list(lines), []
    anchor = next((i for i, line in enumerate(out) if line.key == "type"), None)
    for key in ATTRIBUTES:
        value = wanted[key]
        if value is None:
            continue
        index = next((i for i, line in enumerate(out) if line.key == key), None)
        if index is not None:
            out[index] = _Line(_with_value(out[index].text, value), key, value)
            said.append(f"`{key}` set to {value}")
            anchor = index
            continue
        anchor = 0 if anchor is None else anchor + 1
        out.insert(anchor, _Line(f"{_indent(lines)}{key} = {value}", key, value, added=True))
        said.append(f"`{key}` added, {value}")
    content = text[:start] + "\n".join(_aligned(out)) + text[last:]
    return Edited(path=file.path, content=content, said=tuple(said))


def _refusal(key: str, value: str | None, wanted: str | None, address: str) -> str | None:
    if value is None:
        return f"`{key}` in {address} spans lines, which this edit cannot read for certain."
    if key == "type":
        if value == '"gp3"':
            return (
                f"{address} already says gp3 in Terraform; the volume may have been changed "
                "outside it, which is a question to ask, not a pull request to open."
            )
        if value != '"gp2"':
            return (
                f"`type` in {address} is set by {value}, not the literal gp2, so the edit would "
                "change what decides it rather than the volume."
            )
        return None
    if wanted is None:
        return (
            f"{address} sets `{key}`, which the gp3 FEAT-074 priced does not need; a person "
            "decides whether to keep it."
        )
    if not _NUMBER.match(value):
        return f"`{key}` in {address} is set by {value}, not a number, so the edit would guess."
    return None


def _with_value(line: str, value: str) -> str:
    """The line with its value replaced and anything after it, a comment, kept."""
    matched = _VALUE.match(line)
    return line if matched is None else f"{matched.group(1)}{value}{matched.group(3)}"


def _indent(lines: Sequence[_Line]) -> str:
    for line in lines:
        if line.key is not None:
            return line.text[: len(line.text) - len(line.text.lstrip())]
    return "  "


def _aligned(lines: Sequence[_Line]) -> list[str]:
    """Each run of one line attributes as `terraform fmt` aligns it, where the file already was.

    A run the file had aligned is aligned again with the added line in it, so a pipeline that
    checks formatting still passes. A run the file had not aligned is left as it was, and the
    added line written plainly, so the change touches no line it did not mean to.
    """
    out: list[str] = []
    run: list[_Line] = []

    def flush() -> None:
        own = [line for line in run if not line.added]
        width = max((len(line.key or "") for line in run), default=0)
        if own and not _was_aligned(own):
            out.extend(line.text for line in run)
            run.clear()
            return
        for line in run:
            matched = _ASSIGNED.match(line.text)
            if matched is None:
                out.append(line.text)
                continue
            indent, key, rest = matched.groups()
            out.append(f"{indent}{key.ljust(width)} = {rest}")
        run.clear()

    for line in lines:
        if line.key is not None and line.value is not None:
            run.append(line)
            continue
        flush()
        out.append(line.text)
    flush()
    return out


def _was_aligned(run: Sequence[_Line]) -> bool:
    """Whether a run's equals signs stand where `terraform fmt` puts them."""
    width = max(len(line.key or "") for line in run)
    for line in run:
        matched = _ASSIGNED.match(line.text)
        if matched is None:
            return False
        indent, key, rest = matched.groups()
        if line.text != f"{indent}{key.ljust(width)} = {rest}":
            return False
    return True
