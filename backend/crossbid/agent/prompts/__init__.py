"""Versioned prompts, read from the `.md` files next to this one.

A prompt is a `.md` file rather than a string constant so that a change to it shows up as a
readable diff in review — the prompt *is* the behaviour of a node, and ADR-0003's two
iterations were both prompt edits. `extract.md` is S3.2.1's; `check.md`, `explain.md`,
`chat.md` and `guard.md` arrive with their stories.

The files hold no `{}` placeholders and are never `.format()`ted: a procurement prompt is
full of braces the moment it mentions JSON, and one stray brace would raise at run time in
the middle of a bid. Substitution is by explicit named marker (`load_prompt`'s `values`),
which is a plain `str.replace` and cannot fail on the document's own punctuation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Final

PROMPTS_DIR: Final = Path(__file__).resolve().parent
PROMPT_SUFFIX: Final = ".md"
PROMPT_NAME_PATTERN: Final = re.compile(r"\A[a-z][a-z0-9_]*\Z")
"""Prompt names come from our own code, so this is a boundary, not a defence: it keeps a
name from ever being a path, and it fails on the typo rather than on a missing file."""

MARKER_PATTERN: Final = re.compile(r"\{[a-z_]+\}")
"""The substitution markers, matched against the *template* and never against the result.

That direction matters. Checking the rendered text for leftover markers looks equivalent and
is not: a value can legitimately contain braces — a bidder language read out of a bid row, a
company name — and the check would then reject a prompt that substituted perfectly. Matching
the template instead means every marker is accounted for before anything is inserted, and a
value's own braces are just characters."""


class PromptError(RuntimeError):
    """A prompt could not be loaded or rendered. A packaging or programming fault."""


@cache
def load_prompt(name: str) -> str:
    """The text of `name.md`, read once per process.

    Cached because a bid runs one extraction call per section — 47 of them on the DE pack —
    and re-reading the same file 47 times is work nobody asked for.
    """
    if PROMPT_NAME_PATTERN.fullmatch(name) is None:
        raise PromptError(
            f"'{name}' is not a prompt name: expected lower-case letters, digits and "
            f"underscores matching {PROMPT_NAME_PATTERN.pattern}"
        )

    path = PROMPTS_DIR / f"{name}{PROMPT_SUFFIX}"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise PromptError(f"Cannot read the prompt at {path}: {exc}") from exc


def render(name: str, values: Mapping[str, str]) -> str:
    """`name.md` with each `{key}` replaced by its value.

    Raises `PromptError` if the template holds a marker `values` has nothing for — the
    failure that would otherwise reach the model as a literal `{bidder_language}` and be
    answered in whatever language it felt like.

    One pass, so an inserted value is never itself scanned for markers. Substituting key by
    key would make the result depend on the order of `values` and would let one value's
    braces be filled in by the next key, which is a way for a bid row to write part of a
    prompt.
    """
    missing: list[str] = []

    def substitute(match: re.Match[str]) -> str:
        marker = match.group(0)
        value = values.get(marker[1:-1])
        if value is None:
            missing.append(marker)
            return marker
        return value

    text = MARKER_PATTERN.sub(substitute, load_prompt(name))
    if missing:
        raise PromptError(
            f"The prompt '{name}' has no value for {sorted(set(missing))}; "
            f"values given: {sorted(values)}"
        )
    return text
