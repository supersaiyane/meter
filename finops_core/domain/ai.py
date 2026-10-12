"""What a line of AI spend bought, in the words FOCUS does not have yet. P13, FEAT-081.

FOCUS has no column for a model or a token, so Meter carries them in `x_` columns, the prefix FOCUS
reserves for a producer's own, until FOCUS 1.5 names them, OPEN-34. The kinds of token are the
same for every source; how a source spells its model is the source's own, and an adapter reads it,
which is why nothing here names a vendor, ADR-0028.
"""

from __future__ import annotations

from typing import Final

INPUT: Final = "input"
OUTPUT: Final = "output"
CACHE_READ: Final = "cache_read"
CACHE_WRITE: Final = "cache_write"

#: Every token type a row can carry, which the table's constraint also holds.
TOKEN_TYPES: Final = frozenset({INPUT, OUTPUT, CACHE_READ, CACHE_WRITE})
