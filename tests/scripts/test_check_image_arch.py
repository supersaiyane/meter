"""The image architecture check, watched failing. ISS-254.

The check replaced a label as the evidence that an image runs on its platform, so it has to be
seen to catch what the label missed: an image labelled amd64 holding arm64 code. Every case builds
a small filesystem in memory, the shape `docker export` streams, with ELF headers written by hand.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
from pathlib import Path
from typing import Literal

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "scripts" / "ci" / "check_image_arch.py"

spec = importlib.util.spec_from_file_location("check_image_arch", SCRIPT)
assert spec and spec.loader
check_image_arch = importlib.util.module_from_spec(spec)
sys.modules["check_image_arch"] = check_image_arch
spec.loader.exec_module(check_image_arch)

AMD64 = 62
ARM64 = 183


def elf(machine: int, *, big_endian: bool = False) -> bytes:
    """An ELF header as far as the machine field, then a little padding."""
    order: Literal["little", "big"] = "big" if big_endian else "little"
    identification = b"\x7fELF" + bytes([2, 2 if big_endian else 1, 1]) + bytes(9)
    return identification + (3).to_bytes(2, order) + machine.to_bytes(2, order) + bytes(12)


def exported(files: dict[str, bytes], *, links: tuple[str, ...] = ()) -> io.BytesIO:
    """A tar stream of files and symbolic links, as `docker export` writes one."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, body in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
        for name in links:
            member = tarfile.TarInfo(name)
            member.type = tarfile.SYMTYPE
            member.linkname = "elsewhere"
            archive.addfile(member)
    buffer.seek(0)
    return buffer


def run(stream: io.BytesIO, expect: str = "linux/amd64") -> int:
    result: int = check_image_arch.main(["--expect", expect, "--image", "meter-api:test"], stream)
    return result


def test_passes_when_every_compiled_file_is_for_the_platform(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stream = exported(
        {
            "usr/bin/python3.13": elf(AMD64),
            "opt/venv/lib/x.so": elf(AMD64),
            "app/main.py": b"print('not compiled')\n" * 3,
            "etc/short": b"\x7fELF",
        },
        links=("opt/venv/bin/python",),
    )
    assert run(stream) == 0
    assert "every one of 2 compiled files in meter-api:test is amd64" in capsys.readouterr().out


def test_fails_on_arm64_code_inside_an_image_labelled_amd64(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fault itself: the interpreter is amd64 and an extension copied in is not."""
    stream = exported({"usr/bin/python3.13": elf(AMD64), "opt/venv/lib/_rust.so": elf(ARM64)})
    assert run(stream) == 1
    out = capsys.readouterr().out
    assert "1 of 2 compiled files are not" in out
    assert "opt/venv/lib/_rust.so is arm64" in out


def test_nothing_checked_is_a_failure_and_not_a_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(exported({"app/main.py": b"x" * 40})) == 1
    assert "nothing was checked" in capsys.readouterr().out


def test_names_ten_and_counts_the_rest(capsys: pytest.CaptureFixture[str]) -> None:
    stream = exported({f"opt/venv/lib/{index}.so": elf(ARM64) for index in range(13)})
    assert run(stream) == 1
    out = capsys.readouterr().out
    assert out.count(" is arm64") == 10
    assert "and 3 more" in out


def test_reads_a_big_endian_header_in_its_own_byte_order() -> None:
    assert check_image_arch.machine_of(elf(ARM64, big_endian=True)) == "arm64"


def test_names_a_machine_it_has_no_word_for_by_its_number() -> None:
    assert check_image_arch.machine_of(elf(40)) == "machine 40"


def test_is_not_fooled_by_a_file_that_is_not_elf() -> None:
    assert check_image_arch.machine_of(b"#!/bin/sh\n" + bytes(20)) is None
    assert check_image_arch.machine_of(b"\x7fELF") is None


def test_accepts_the_platform_with_or_without_its_os() -> None:
    assert run(exported({"x.so": elf(ARM64)}), expect="arm64") == 0
