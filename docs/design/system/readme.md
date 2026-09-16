# CrossBid Design System

## Context

**CrossBid** is an AI agent for EU public-tender bidding. Given a tender in any EU language and a company profile, it:

1. Extracts every requirement, each with a citation to the source page.
2. Translates and explains each requirement in the bidder's language.
3. Maps requested certificates to their equivalents in the bidder's home country.
4. Checks each requirement against what the company can actually prove.
5. Returns a **go / no-go verdict** with a compliance matrix.

A human reviews and confirms every verdict before anything moves forward; only then does the agent help draft the response. The agent is **advisory by design** — it never submits, never asserts compliance without a source, and refuses a verdict when documents don't support one.

### Surfaces
- **Marketing website** (`ui_kits/website/`) — landing page.
- **Web app** (`ui_kits/app/`) — the bidder's workspace: tender runs, requirement matrix, verdict review, certificate mapping.

### Sources given
- Company description (pasted brief).
- Reference: https://www.govdash.com.
- Screenshots in `uploads/`: three GovDash "Agents › Runs" app views, one GovDash platform-overview dashboard, three generic SaaS landing/dashboard references (Deflexai, Salse, Twisty — Dribbble-style shots).
- No Figma, codebase, logo, or font files were provided.

### Logo
`assets/logo-lockup.png` (mark + wordmark, transparent bg), `assets/logo-mark.png` (mark alone), `assets/logo-original.png` (as supplied). Ink chevron-mark with orange facets; wordmark "Cross" in ink, "Bid" in orange. Use the lockup at 28–32px tall in nav/sidebar; the mark alone below 24px. On dark grounds, set the wordmark in type: Cross (white) + Bid (orange-500) — no reversed PNG was provided.

---

## Content fundamentals

**Voice:** calm, precise, evidential. CrossBid talks like a careful bid manager, not a hype machine. Every claim is checkable; the product never says "compliant" without pointing at a page.

- **Person:** "you / your company" for the bidder; "CrossBid" or "the agent" for the product. Never "I".
- **Casing:** sentence case everywhere — headings, buttons, nav, table headers ("View run", "Needs attention", "Compliance matrix"). ALL-CAPS only for small eyebrow labels (`WORKFLOW`, `PLATFORM`) at 12px with wide tracking.
- **Punctuation:** no exclamation marks. Em dashes for asides. Oxford comma.
- **Numbers:** always precise, always sourced. "47 requirements · 3 unsupported" not "dozens of requirements".
- **Emoji:** never.
- **Verdict language** is fixed vocabulary: **Go**, **No-go**, **Conditional**, **Insufficient evidence**. Never "Pass/Fail", never "Approved".
- **Hedging is a feature:** "CrossBid could not verify ISO 27001 — no certificate found in your profile" beats "Missing certificate".
- **Buttons:** verb + object, ≤3 words: "Start analysis", "Confirm verdict", "Open source page", "Request evidence".
- **Empty/refusal states** explain why: "No verdict — the tender's selection criteria (p. 14–17) are not machine-readable. Upload a text version."

Examples:
- Hero: **"Know if you can win before you write a word."** / "CrossBid reads the tender, maps every requirement to your evidence, and gives you a go / no-go you can defend."
- Feature: "Every requirement, cited." / "Each extracted line links to the exact page in the tender."
- Trust line: "Advisory by design. CrossBid never submits, never asserts compliance without a source."

---

## Visual foundations

Modeled on GovDash's product structure: warm-white canvas, white bordered cards, **ink as the primary accent** (black buttons, segments) with **orange from the logo as a secondary accent** (eyebrow labels, the one "agent"/primary tile per screen, highlight pills), and semantic green/amber/red reserved strictly for status. (Token names keep the `--cb-blue-*` prefix for compatibility; values are the ink/stone ramp.)

**Color**
- Canvas `--surface-canvas` #fafaf9 (warm off-white). Cards `--surface-card` #fff with 1px `--border-default` #e7e5e4. Neutrals are warm stone greys, never cool/blue greys.
- Brand accent = ink `--cb-blue-500` #111 (hover #292524): primary buttons, active nav icon tiles, selected segment. Links are ink, underlined on hover.
- Soft tiles `--cb-blue-50/100` are stone-50/100 with ink glyphs.
- Accent orange `--cb-orange-500` #f97316 / text `--cb-orange-600`: use once per screen region at most; never as a status color — amber (`--status-warning` #d9a400) stays visibly yellower.
- Info/"In progress" status is a distinct blue (`--status-info` #2f6fdb) — the only blue in the system.
- Status: green = Succeeded/Go, amber = Needs attention/Conditional, red = Failed/No-go, stone = Insufficient / In progress-neutral. Each has a 50-tint background + 700 text pairing for chips.
- Text: ink #111 primary, stone-600 secondary, stone-500 muted, stone-400 placeholder.

**Type**
- Single family: **Geist** (sans) + **Geist Mono** for citations, page refs, IDs, and requirement codes. Substitution for GovDash's Inter-like UI face — see caveats.
- Headings semibold (600), tight tracking (-0.025em). Marketing display 60px; app page title 32px; card title 17–20px; body 14px; meta 12–13px.
- App density is comfortable, not cramped: 14px body, 40px controls, 24px card padding.

**Spacing & layout**
- 4px base grid. Card padding 24px, gaps 16–24px between cards, 32px page padding.
- App: fixed 260px left sidebar on canvas color; content area is a single large white card with 1px border and 12px radius, inset 32px from the sidebar/top.
- Marketing: centered 1160px column, generous 96–128px vertical section rhythm, hero centered.

**Radii**
- Buttons/inputs/chips 8px; cards 12px; content frame 12–16px; icon tiles 10–12px; segmented control 8px; pills only for status chips (`--radius-pill`).

**Borders, shadows**
- Borders do the work: 1px stone-200 on every card and control. Shadows are near-invisible: `--shadow-xs/sm` on cards, `--shadow-md` on popovers/dropdowns, `--shadow-lg` only for dialogs. No inner shadows.
- Active sidebar item: white background + 1px border + `--shadow-active-nav`.

**Backgrounds & imagery**
- No photography in the app. Marketing hero may use a product screenshot inside a bordered, rounded frame with a soft protection gradient fading into canvas. Optional faint concentric-ring / grid decoration behind hero (very light stone-200 lines). No gradients on text, no purple.

**Motion**
- Restrained: 120–180ms `--ease-standard` on hover/focus color changes; 280ms for panel/dialog entrance (fade + 8px rise). No bounces.

**States**
- Hover: buttons darken one step (blue-500 → blue-600; ghost gets `--surface-hover`). Rows get `--surface-sunken`.
- Press: one step darker again, no scale.
- Focus: 3px `--shadow-focus` ring, ink at 20%.
- Disabled: 50% opacity, no pointer.

**Transparency / blur**
- Dialog scrim `--overlay-scrim` at 40%. Sticky marketing nav uses white at 80% + `--blur-glass`. Nothing else is translucent.

**Cards**
- White, 1px border, 12px radius, 24px padding, optional header row (icon 20px + 17px semibold title + right-aligned actions). Metric cards: 14px muted label, 32px semibold value, 12px delta with ▲/↑ in status color.

**Data display**
- Tables: 48px rows, 1px stone-200 dividers, no zebra, header 13px muted, first column is a blue link. Chips inside cells.
- Charts: thin 2px lines in `--chart-*`, dashed stone-200 gridlines, no fills, no drop shadows. Donut ring 14px stroke with center total.

---

## Iconography

- **Icon set:** [Lucide](https://lucide.dev) via CDN (`https://unpkg.com/lucide@latest`) — 1.5–2px stroke, rounded joins, matches the GovDash reference (`layout-grid`, `box`, `file-text`, `bar-chart-3`, `sparkles`, `database`, `calendar`, `clock`, `external-link`, `check-circle-2`, `chevrons-up-down`, `sliders-horizontal`). Substitution: GovDash's own icons are proprietary; Lucide is the closest CDN match.
- **Sizes:** 16px inline with text, 20px in card headers / buttons, 24px in nav tiles.
- **Nav tiles:** 32px rounded (10px) square, `--cb-blue-100` background with blue-500 glyph; active/primary items use solid blue-500 tile with white glyph. Quick-action tiles are 64px, radius 12px, same color logic.
- **Status glyphs:** 8px filled dots in status color inside chips and legends; `check-circle-2` inside Succeeded chips.
- **Emoji:** never. **Unicode-as-icon:** only ▲/↑/→ in metric deltas and "View reports →" links.
- **Logos:** none provided. Client/partner logos on the marketing page are text placeholders.

---

## Components (intentional standard set — no source inventory existed)
`components/core/` — Button, IconButton, Badge, Tag, Card, Tabs, Tooltip
`components/forms/` — Input, Select, Checkbox, Radio, Switch
`components/feedback/` — Dialog, Toast
`components/app/` — NavItem, MetricCard, StatusChip, VerdictChip, RunCard (CrossBid-specific patterns lifted from the GovDash reference; listed as intentional additions because the app kit needs them).

---

## Index
- `styles.css` — entry; imports `tokens/*.css`
- `tokens/` — fonts, colors, typography, spacing, effects, base
- `guidelines/` — specimen cards (Type, Colors, Spacing, Brand)
- `components/` — see above; each dir has `.jsx`, `.d.ts`, `.prompt.md`, and a card `.html`
- `ui_kits/website/` — landing page kit (`index.html`, Nav/Hero/Sections/Footer.jsx)
- `ui_kits/app/` — web-app kit (`index.html#dashboard|runs|matrix|verdict`, Shell/Dashboard/Runs/Matrix/Verdict.jsx, data.js)
- `ui_kits/loader.js` — loads DS components (bundle, or compiles `components/*.jsx` as fallback) then kit files
- `assets/` — logo-lockup.png, logo-mark.png, logo-original.png
- `thumbnail.html` — homepage tile
- `SKILL.md` — agent skill entry

## Caveats
- **Fonts:** no files provided. Geist (Google Fonts) substitutes for the Inter-style face GovDash uses. Send brand font files to replace.
- **Icons:** Lucide via CDN as a substitute.
- Everything visual is inferred from screenshots + govdash.com; no code or Figma source of truth.
