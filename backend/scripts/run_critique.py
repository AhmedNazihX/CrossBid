"""S7.5 — ask a model that did not write this system to find what is wrong with it.

    uv run python scripts/run_critique.py                       # default: gemini-2.5-flash
    uv run python scripts/run_critique.py --model anthropic/claude-haiku-4.5

Writes `docs/critique.raw.json` — the model's findings, exactly as returned. **That file is
not the deliverable.** `docs/critique.md` is, and every finding in it has been checked against
the code by a person first: this repository has already learned that a report names a symptom
and not a cause (ADR-0065), and a critique from a model that has never run the code will
produce confident findings about things that are not there. Each one is either reproduced and
fixed, or declined on the record with the reason.

**The model may not be the one under test.** Extraction, checking and chat all run on OpenAI
slugs, so the critic is Google's or Anthropic's — the same rule S7.1 applies to the eval judge,
for the same reason: a model grading its own family's output is not an outside opinion.

**It is given the accepted risks up front.** Not to excuse them, but so it can disagree with
them explicitly — a critique that rediscovers four things already recorded in ADRs and misses
everything else is worth less than one that says "you accepted this and you were wrong". The
list comes from `HANDOVER.md` and the ADRs it names.

**What it sees, and therefore what it can speak to.** The three agent prompts verbatim, the
security surfaces (the data-block wrapper, the injection heuristics, the guard that decides
what is withheld, auth, rate limits), and the user guide, which is the product's own account
of what a bidder does. It does not see the running UI, so its usability findings are about
copy, flow and what the guide has to explain — which is where usability problems show up in
writing — and not about layout or contrast. `docs/critique.md` says so rather than letting a
reader assume the screens were reviewed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    # `[tool.uv] package = false`, so `crossbid` is importable only via the project root.
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import BaseModel, Field  # noqa: E402

from crossbid.llm import chat_model  # noqa: E402
from crossbid.settings import ModelRole, Settings, SettingsError, load_settings  # noqa: E402

DEFAULT_CRITIC = "google/gemini-2.5-flash"
"""More capable than the eval judge and still not an OpenAI slug. The judge role is tuned for
scoring one short thing many times; a critique is one long thing once."""

OUT_PATH = REPO_DIR / "docs" / "critique.raw.json"
INPUT_ERROR = 2

BUNDLE: Sequence[tuple[str, Path]] = (
    ("PROMPT: extraction", BACKEND_DIR / "crossbid/agent/prompts/extract.md"),
    ("PROMPT: per-requirement checking", BACKEND_DIR / "crossbid/agent/prompts/check.md"),
    ("PROMPT: ask the tender", BACKEND_DIR / "crossbid/agent/prompts/chat.md"),
    ("SECURITY: the untrusted-data block wrapper", BACKEND_DIR / "crossbid/guards/wrap.py"),
    ("SECURITY: injection heuristics", BACKEND_DIR / "crossbid/guards/injection.py"),
    ("SECURITY: what a flagged chunk costs", BACKEND_DIR / "crossbid/ingestion/guarding.py"),
    ("SECURITY: authentication", BACKEND_DIR / "crossbid/auth.py"),
    ("SECURITY: rate limits", BACKEND_DIR / "crossbid/rate_limit.py"),
    ("USABILITY: the user guide", REPO_DIR / "docs" / "user-guide.md"),
)

ACCEPTED_RISKS = """\
Risks the team has already recorded and accepted. Say so if you think any is wrong:

1. Supabase's `signInWithOtp` allows user enumeration — asking for a magic link reveals
   whether an address has an account. There is no toggle for it (supabase/auth#1955), and
   registration and reset were written to leak nothing. Accepted in ADR-0053.
2. No route reads the chat thread back, so reloading the page loses the visible conversation
   while the agent still remembers it on its thread. Accepted in ADR-0058.
3. The single `app_settings` row is last-write-wins: two operators saving at once, the second
   wins silently. Accepted in ADR-0059.
4. On a phone, tapping a citation moves focus to `body` rather than to the opened page.
5. Tenancy is application-level, not RLS: the API connects with BYPASSRLS and the
   `company_id` predicate in each statement is the whole boundary between two companies.
   Accepted in ADR-0009.
"""

INSTRUCTIONS = """\
You are reviewing Crossbid, an advisory agent that tells a small European company whether it
can qualify for a public tender. It never submits a bid; a human confirms every verdict.

Review it on three axes and nothing else:

- **prompt_engineering** — the three prompts. Are the instructions unambiguous, in conflict,
  or exploitable? Would a model follow them the way the author intends? Is anything asked for
  that a model cannot reliably do?
- **security** — prompt injection through tender documents (which are written by a third
  party and are the attack surface), authentication, tenant isolation, rate limiting,
  information leakage in errors.
- **usability** — what the guide has to explain is usually what the product does not. Where
  would a bidder go wrong, misread a result, or trust something they should not?

Rules for your findings:

- Be specific. Quote the line or the sentence you are objecting to. A finding nobody can
  locate cannot be acted on.
- Say what an attacker or a confused user actually *does*, and what happens. "Could be
  improved" is not a finding.
- Do not report the absence of something you were not shown: you have the prompts, some
  security code and the user guide, not the whole repository or the running UI.
- Severity: `critical` (security hole or data loss), `high` (a real defect a user will hit),
  `medium` (worth fixing), `low` (style or polish).
- It is more useful to find three real problems than fifteen plausible ones.
"""


class Finding(BaseModel):
    """One thing the critic thinks is wrong."""

    area: str = Field(description="usability, security, or prompt_engineering")
    severity: str = Field(description="critical, high, medium, or low")
    title: str = Field(description="One line, specific")
    locator: str = Field(description="The file, prompt, or sentence being objected to")
    finding: str = Field(description="What is wrong, and what a user or attacker does")
    suggested_fix: str


class Critique(BaseModel):
    findings: list[Finding]
    disagreements: list[str] = Field(
        default_factory=list,
        description="Accepted risks the critic thinks should not have been accepted, and why",
    )


def _as_critic(settings: Settings, slug: str) -> Settings:
    """`settings` with the extract role repointed at the critic, re-validated on the way.

    Re-validated rather than patched, so the `available_models` rule still holds: a slug
    nobody probed is refused here instead of failing mid-call (ADR-0005). The role is a
    vehicle — `chat_model` takes a role, not a slug, and adding a slug parameter to it for
    one script would put a second way to choose a model into production code.
    """
    data = settings.model_dump()
    data["runtime"]["models"]["extract"] = slug
    return Settings.model_validate(data)


def _bundle() -> str:
    parts: list[str] = []
    for label, path in BUNDLE:
        if not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            continue
        parts.append(f"===== {label} — {path.relative_to(REPO_DIR)} =====\n{path.read_text()}")
    return "\n\n".join(parts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask an outside model to critique the system.")
    parser.add_argument("--model", default=DEFAULT_CRITIC)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"settings: {exc}", file=sys.stderr)
        return INPUT_ERROR

    under_test = {settings.runtime.models.extract, settings.runtime.models.cheap}
    if args.model in under_test:
        print(
            f"{args.model} is a model under test ({', '.join(sorted(under_test))}). "
            "S7.5 wants an outside opinion; pick another vendor.",
            file=sys.stderr,
        )
        return INPUT_ERROR

    critic = chat_model(ModelRole.EXTRACT, _as_critic(settings, args.model))
    structured = critic.with_structured_output(Critique)
    prompt = f"{INSTRUCTIONS}\n\n{ACCEPTED_RISKS}\n\nThe material:\n\n{_bundle()}"
    print(f"critic: {args.model} — {len(prompt):,} characters of material", flush=True)

    result = structured.invoke([("human", prompt)])
    assert isinstance(result, Critique)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"critic": args.model, **result.model_dump()}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"{len(result.findings)} finding(s), {len(result.disagreements)} disagreement(s)")
    print(f"wrote {args.out.relative_to(REPO_DIR)}")
    print("Verify every finding against the code before it reaches docs/critique.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
