"""Guards: what stands between an untrusted document and a prompt.

`wrap` is the structural defence (S2.3.2) — document text only ever reaches a model inside a
tagged data block, so a tender that tries to instruct the agent is quoted rather than obeyed.
The heuristic injection scanner (S2.3.1) is here as `injection.py`, and the two are layers:
the scanner decides whether text is *suspicious* — and what it flags never reaches the
corpus at all — while the wrapper never trusts text whether or not it is. The third layer
is the `system_prompt` in `settings.default.yaml`, which states the data-block rule to the
model at the system level.

Nothing here imports from anywhere else in `crossbid`; a test asserts it.
"""

from __future__ import annotations

from crossbid.guards.injection import (
    MIN_SIGNALS_TO_FLAG,
    InjectionFinding,
    InjectionSignal,
    scan,
)
from crossbid.guards.wrap import (
    DATA_BLOCK_BEGIN,
    DATA_BLOCK_END,
    DATA_BLOCK_ITEM,
    DATA_BLOCK_POSTAMBLE,
    DATA_BLOCK_PREAMBLE,
    DataBlock,
    DataWrapError,
    TextFragment,
    WrappedData,
    block_from_fragment,
    wrap_as_data,
)

__all__ = [
    "DATA_BLOCK_BEGIN",
    "DATA_BLOCK_END",
    "DATA_BLOCK_ITEM",
    "DATA_BLOCK_POSTAMBLE",
    "DATA_BLOCK_PREAMBLE",
    "MIN_SIGNALS_TO_FLAG",
    "DataBlock",
    "DataWrapError",
    "InjectionFinding",
    "InjectionSignal",
    "TextFragment",
    "WrappedData",
    "block_from_fragment",
    "scan",
    "wrap_as_data",
]
