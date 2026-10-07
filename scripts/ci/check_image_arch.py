"""Fail when a compiled file inside an image is built for another machine than the one asked for.

ISS-254. Reads `docker export` of a container created from the image, a tar stream, on standard
input, and checks the machine field of every ELF file in it against the platform asked for.

**The image's label is not evidence.** A builder stage that ran on the build machine can copy arm64
extensions into an image labelled amd64, and the label still says amd64, because the label
describes the stage the image was assembled in and not the files copied into it. `make
verify-platform` read the label alone, so the fault could pass it. This reads what is inside.

Standard library only, so it runs before any virtualenv exists.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from collections.abc import Sequence
from typing import IO, Literal

ELF_MAGIC = b"\x7fELF"
#: The byte in the ELF identification that says the data's byte order: 1 little, 2 big.
_LITTLE_ENDIAN = 1
#: e_machine values, by the platform word Docker uses for them.
MACHINES = {62: "amd64", 183: "arm64"}
#: Enough of an ELF header to read e_machine, which sits at bytes 18 and 19.
HEADER = 20
#: How many offending files a failure names before it counts the rest.
NAMED = 10


def machine_of(header: bytes) -> str | None:
    """The platform word for an ELF header, or None when the bytes are not an ELF file."""
    if len(header) < HEADER or not header.startswith(ELF_MAGIC):
        return None
    order: Literal["little", "big"] = "little" if header[5] == _LITTLE_ENDIAN else "big"
    machine = int.from_bytes(header[18:20], order)
    return MACHINES.get(machine, f"machine {machine}")


def mismatches(stream: IO[bytes], expected: str) -> tuple[int, list[tuple[str, str]]]:
    """How many ELF files the stream holds, and those built for another machine.

    Read as a stream, one member at a time, because an exported image is a few hundred megabytes
    and only the first twenty bytes of each file are needed.
    """
    checked = 0
    wrong: list[tuple[str, str]] = []
    with tarfile.open(fileobj=stream, mode="r|*") as archive:
        for member in archive:
            if not member.isfile() or member.size < HEADER:
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            found = machine_of(handle.read(HEADER))
            if found is None:
                continue
            checked += 1
            if found != expected:
                wrong.append((member.name, found))
    return checked, wrong


def main(argv: Sequence[str] | None = None, stream: IO[bytes] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--expect", required=True, help="the platform, such as linux/amd64")
    parser.add_argument("--image", default="the image", help="the image's name, for messages")
    args = parser.parse_args(argv)
    expected = args.expect.rsplit("/", 1)[-1]
    checked, wrong = mismatches(stream if stream is not None else sys.stdin.buffer, expected)
    if checked == 0:
        # Nothing checked is not a pass. An empty stream, or a tool that exported nothing, would
        # otherwise read as an image with no foreign code in it.
        print(f"FAIL: {args.image} held no compiled file, so nothing was checked.")
        return 1
    if wrong:
        print(
            f"FAIL: {args.image} is {args.expect}, "
            f"and {len(wrong)} of {checked} compiled files are not:"
        )
        for name, found in wrong[:NAMED]:
            print(f"  {name} is {found}")
        if len(wrong) > NAMED:
            print(f"  and {len(wrong) - NAMED} more")
        return 1
    print(f"OK: every one of {checked} compiled files in {args.image} is {expected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
