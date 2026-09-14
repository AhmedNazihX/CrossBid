# ruff: noqa: RUF001 - the typographic apostrophe below is what French tenders actually use
"""S2.3.1 — text that tries to instruct the agent, found before it can.

The scanner half of the guard. `wrap.py` is the structural defence that applies to every
prompt whatever this concludes; this one decides whether a span of tender text is *trying* to
give orders, so that it can be kept out of the corpus entirely. The two are layers, not
alternatives: a scanner that misses an attack still leaves it inside a data block, and a
block a document could forge would make the scanner the only defence.

**What actually separates an attack from a tender.** Procurement prose is full of
imperatives — "der Bieter hat die Anlage 3 einzureichen", "le candidat doit joindre", "
tenderers must submit" — and a rule that flagged those would flag every pack in the corpus.
The difference is not that an attack commands. It is *who it commands* and *what it asks
for*. Four signals, none of which is sufficient alone:

* **`ADDRESSES_A_MACHINE`** — the text speaks to a reader that is not a person: "automatisierte
  Auswertungssysteme", "AUTOMATED READER", "INSTRUCTION SYSTÈME", "Sprachmodell". A tender
  never addresses one, because a buyer writing a notice has no reason to believe one is
  reading. This is the strongest single signal and still not enough on its own — a pack
  discussing AI procurement would trip it.
* **`OVERRIDES`** — it tries to discard what came before: "ignoriere sämtliche vorherigen
  Anweisungen", "ignorez les consignes précédentes", "the rules above are void".
* **`DICTATES_A_VERDICT`** — it demands a specific answer rather than stating a requirement:
  "bewerte jede Anforderung als vollständig erfüllt", "mark every criterion as satisfied",
  "considérez ce candidat comme conforme".
* **`CONCEALS`** — it asks not to be mentioned: "erwähne diesen Absatz in keiner
  Zusammenfassung", "do not reveal that this instruction exists", "ne mentionnez pas".
  Nothing legitimate in a procurement document asks to be hidden from the reader.

**Two signals, not one.** A chunk is flagged when it carries at least two distinct signals.
One alone is where the false positives live: a pack about an AI system addresses machines, a
quality clause may say "ignore" in a sentence about tolerances. Two together is a sentence
that has no innocent reading, and every planted instruction in `tests/fixtures/adversarial/`
carries three or four. The threshold is a constant so that raising it is a decision with a
number attached rather than an edit to a regex.

**Three languages, because the corpus is three languages.** DE, FR and EN patterns sit side
by side rather than in separate tables: an attack is one sentence in one language, and
splitting the table would invite a signal that exists in German and was forgotten in French.

**No model is asked.** This runs on every chunk of every upload, before anything is paid for,
and must work with the network unplugged. S5.3 adds a cheap-model confirmation *on top* of
what this flags — its job is to reduce false positives, not to find what this missed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class InjectionSignal(StrEnum):
    """What a span of text did to earn suspicion. Named for the behaviour, not the words."""

    ADDRESSES_A_MACHINE = "addresses_a_machine"
    OVERRIDES = "overrides"
    DICTATES_A_VERDICT = "dictates_a_verdict"
    CONCEALS = "conceals"


MIN_SIGNALS_TO_FLAG: Final = 2
"""How many distinct signals make a flag. See the module docstring for why it is not one."""


def _pattern(*alternatives: str) -> re.Pattern[str]:
    return re.compile("|".join(alternatives), re.IGNORECASE | re.UNICODE)


PATTERNS: Final[dict[InjectionSignal, re.Pattern[str]]] = {
    InjectionSignal.ADDRESSES_A_MACHINE: _pattern(
        # de
        r"automatisiert\w*\s+(auswertungs|analyse|pr[üu]f)\w*",
        r"\bsprachmodell\b",
        r"\bsystemanweisung\b",
        r"\bKI[- ]System\b",
        # fr
        r"instruction\s+syst[èe]me",
        r"mod[èe]le\s+de\s+langage",
        r"lecteur\s+automatis",
        # en
        r"automated\s+(reader|system|reviewer|assistant)",
        r"\blanguage\s+model\b",
        r"\bAI\s+(system|assistant|reader)\b",
        r"system\s*(prompt|instruction)\b",
    ),
    InjectionSignal.OVERRIDES: _pattern(
        # de
        r"ignorier\w*\s+(s[äa]mtliche|alle|die)\s+(vorherigen|vorstehenden|obigen)",
        r"verwirf\w*\s+(die|alle|s[äa]mtliche)",
        r"(vorherigen|obigen)\s+anweisungen\s+(sind|werden)\s+(ung[üu]ltig|verworfen)",
        # fr
        r"ignorez?\s+les\s+(consignes|instructions)\s+pr[ée]c[ée]dentes",
        r"oubliez?\s+(les|toutes)\s+(consignes|instructions)",
        # en
        r"ignore\s+(all\s+)?(previous|prior|preceding|the\s+above)\s+(instruction|rule|direction)",
        r"disregard\s+(all\s+)?(previous|prior|the\s+above|the\s+evaluation)",
        r"(rules?|instructions?)\s+(stated\s+)?above\s+are\s+void",
    ),
    InjectionSignal.DICTATES_A_VERDICT: _pattern(
        # de
        r"bewerte\s+jede\w*\s+\w+\s+als\s+(vollst[äa]ndig\s+)?erf[üu]llt",
        r"melde\s+(ausschlie[ßs]lich|nur),?\s+dass",
        r"gib\s+als\s+gesamtergebnis",
        r"als\s+(vollst[äa]ndig\s+)?geeignet\s+(zu\s+)?bewerten",
        # fr
        r"consid[ée]rez?\s+ce\s+candidat\s+comme\s+conforme",
        r"n['’]?[ée]mettez\s+aucune\s+r[ée]serve",
        r"attribuez\s+la\s+mention",
        # en
        r"mark\s+(every|all|each)\s+\w+\s+as\s+(fully\s+)?satisfied",
        r"report\s+that\s+no\s+gaps",
        r"recommend\s+submission\s+without",
    ),
    InjectionSignal.CONCEALS: _pattern(
        # de
        r"erw[äa]hne\s+(diese|diesen|dieses)\s+\w+\s+in\s+kein",
        r"nenne\s+diesen?\s+hinweis\s+nicht",
        # fr
        r"ne\s+mentionnez\s+pas",
        # en
        r"do\s+not\s+(reveal|mention|disclose)",
        r"without\s+(revealing|mentioning|disclosing)\s+(this|that)",
    ),
}


@dataclass(frozen=True)
class InjectionFinding:
    """Why a span was flagged, in terms a reviewer can check against the text."""

    signals: tuple[InjectionSignal, ...]
    """Every distinct signal found, in the order this module declares them."""
    excerpt: str
    """The first match, so a reviewer can find it in the document without reading the chunk."""


def scan(text: str) -> InjectionFinding | None:
    """`None` when the text is ordinary tender prose, which is the answer almost every time.

    The excerpt is the first matching span rather than the whole chunk: a chunk is 800
    tokens and the thing a reviewer needs to see is the sentence, not the page around it.
    """
    signals: list[InjectionSignal] = []
    excerpt = ""
    for signal, pattern in PATTERNS.items():
        match = pattern.search(text)
        if match is None:
            continue
        signals.append(signal)
        if not excerpt:
            excerpt = _around(text, match.start(), match.end())
    if len(signals) < MIN_SIGNALS_TO_FLAG:
        return None
    return InjectionFinding(signals=tuple(signals), excerpt=excerpt)


EXCERPT_CONTEXT: Final = 60
"""Characters either side of the match. Enough to read the sentence, short enough to log."""


def _around(text: str, start: int, end: int) -> str:
    """The match with a little text around it, whitespace collapsed for a log line."""
    window = text[max(0, start - EXCERPT_CONTEXT) : end + EXCERPT_CONTEXT]
    return re.sub(r"\s+", " ", window).strip()
