# The CrossBid design system, in the repository

This directory is a tracked copy of the design system the UI is built from. It was added on
2026-09-16 because it had not been: the system lived only in `.claude/skills/`, which
`.gitignore` excludes, so a fresh clone had none of it while roughly thirty component
docstrings cited files inside it. A reader could not open the thing the code said it was
implementing, and one local directory on one machine was the only copy.

## What is authoritative

`docs/design/canvas/tokens.css` and the six `*.dc.html` artboards beside it are the confirmed
screen designs (ADR-0014) and were always tracked. **This directory is the system those
artboards are drawn from**: the token sheet, the type and colour guidelines, the component
kit, and the two UI kits (`ui_kits/app`, `ui_kits/website`) whose `.jsx` files the frontend's
docstrings name.

`frontend/app/globals.css` is a verbatim copy of `tokens/` mapped into Tailwind's namespace.
Where the two disagree, the sheet wins and the divergence is recorded in the component that
makes it, as ADR-0014 requires.

## What is a copy, and what that costs

The working copy stays at `.claude/skills/CrossBid Design System/`, because that is where the
tooling reads it. This directory is a snapshot, so the two can drift. That is a worse
arrangement than a single source and a better one than no source at all; if the system is
edited, re-sync with:

```
rsync -a --delete --exclude='.DS_Store' --exclude='.thumbnail' \
  ".claude/skills/CrossBid Design System/" docs/design/system/
```

## `uploads/`

Reference images gathered while the system was designed, including screenshots of other
products. Kept because `readme.md` links them and a guideline page without its illustration
is not a guideline; they are inspiration material, not CrossBid assets, and nothing in the
product ships them.
