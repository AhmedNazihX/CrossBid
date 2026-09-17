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

## Where the app deliberately does not follow it

The app is what gets measured against WCAG, so where a kit value fails the standard the app
diverges and records it. Two so far, both in `frontend/app/globals.css`:

- **The focus ring** (ADR-0092). `readme.md` line 90 and `tokens/effects.css` ask for a 3 px
  `--shadow-focus` ring, ink at 20 %. Measured in Chrome it is **1.5517:1** where SC 1.4.11
  asks for 3:1, and because it is a `box-shadow` any `shadow-*` utility deletes it outright —
  which is how every `<select>` in the app came to have no ring at all. The app draws a 2 px
  ink `outline` instead, measured at 18.88:1. `--shadow-focus` is still applied, as decoration.
- **The placeholder token** (ADR-0094). `readme.md` line 62 asks for `stone-400`, which
  measures **2.52:1** on the white input box where SC 1.4.3 asks 4.5:1 — under the 3:1 asked
  of things that are not text at all. The app uses `stone-500`, measured at 4.80:1. It is the
  same colour as `--text-muted`, because the palette has no step between them.

A re-sync with the command above overwrites this directory, not the app's sheet, so neither
divergence is undone by it. They are listed here so a re-sync does not look like it should.

## `uploads/`

Reference images gathered while the system was designed, including screenshots of other
products. Kept because `readme.md` links them and a guideline page without its illustration
is not a guideline; they are inspiration material, not CrossBid assets, and nothing in the
product ships them.
