"""Emit the S4.0.1 canvas artboards from the CrossBid design system.

Everything visual comes from the design project synced at
`.claude/skills/CrossBid Design System/`: its token sheet is copied verbatim into
`tokens.css` and every inline style below uses those variables; the shell (260 px canvas
sidebar, one white content frame), NavItem, Button, Badge, Tag, MetricCard, VerdictChip,
Tabs, Radio and Card anatomy are reproduced from `components/**` and `ui_kits/app/**`.
Run `python3 build.py`; the `.dc.html` files are the working files the canvas is seeded from.
"""

from pathlib import Path

HERE = Path(__file__).parent
TOKENS = (HERE / "tokens.css").read_text()

BASE_CSS = TOKENS + """
@import url("https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap");
html{font-family:var(--font-sans);color:var(--text-primary);background:var(--surface-canvas);-webkit-font-smoothing:antialiased}
body{margin:0;font:var(--type-body)}
a{color:var(--text-link);text-decoration:none} a:hover{color:var(--cb-stone-600);text-decoration:underline}
*,*::before,*::after{box-sizing:border-box}
.mono{font:var(--type-mono)}
"""

# ------------------------------------------------------------------------------ primitives


def icon(path, size=18):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" style="flex: none;">{path}</svg>')


I = {
    "grid": '<rect width="7" height="7" x="3" y="3" rx="1"></rect><rect width="7" height="7" x="14" y="3" rx="1"></rect><rect width="7" height="7" x="14" y="14" rx="1"></rect><rect width="7" height="7" x="3" y="14" rx="1"></rect>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path>',
    "fileCheck": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path><path d="m9 15 2 2 4-4"></path>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"></path><path d="m9 12 2 2 4-4"></path>',
    "spark": '<path d="M9.9 2.1 12 8l5.9 2.1L12 12.2 9.9 18 7.8 12.2 2 10.1 7.8 8z"></path>',
    "db": '<ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M3 5v14a9 3 0 0 0 18 0V5"></path><path d="M3 12a9 3 0 0 0 18 0"></path>',
    "layers": '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"></path><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"></path><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"></path>',
    "sliders": '<path d="M21 4H3M21 12H3M21 20H3"></path>',
    "clock": '<circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path>',
    "ext": '<path d="M15 3h6v6"></path><path d="M10 14 21 3"></path><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>',
    "alert": '<circle cx="12" cy="12" r="10"></circle><path d="M12 8v4M12 16h.01"></path>',
    "search": '<circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path>',
    "plus": '<path d="M5 12h14"></path><path d="M12 5v14"></path>',
    "chev": '<path d="m6 9 6 6 6-6"></path>',
    "chevR": '<path d="m9 18 6-6-6-6"></path>',
    "chevL": '<path d="m15 18-6-6 6-6"></path>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><path d="m17 8-5-5-5 5"></path><path d="M12 3v12"></path>',
    "lang": '<path d="m5 8 6 6"></path><path d="m4 14 6-6 2-3"></path><path d="M2 5h12"></path><path d="M7 2h1"></path><path d="m22 22-5-10-5 10"></path><path d="M14 18h6"></path>',
    "arrow": '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>',
    "check": '<circle cx="12" cy="12" r="10"></circle><path d="m9 12 2 2 4-4"></path>',
    "x": '<path d="M18 6 6 18"></path><path d="m6 6 12 12"></path>',
    "menu": '<path d="M4 6h16"></path><path d="M4 12h16"></path><path d="M4 18h16"></path>',
}


def button(label, variant="primary", size="md", ic=None, icon_right=None, extra=""):
    v = {
        "primary": "background: var(--surface-brand); color: var(--text-inverse); border: 1px solid transparent;",
        "secondary": "background: var(--surface-card); color: var(--text-primary); border: 1px solid var(--border-default); box-shadow: var(--shadow-xs);",
        "ghost": "background: transparent; color: var(--text-primary); border: 1px solid transparent;",
        "danger": "background: var(--status-danger); color: var(--text-inverse); border: 1px solid transparent;",
    }[variant]
    s = {"sm": ("var(--control-sm)", 12, 13, 6), "md": ("var(--control-md)", 16, 14, 8), "lg": ("var(--control-lg)", 20, 15, 8)}[size]
    left = f'<span style="display: inline-flex; width: 16px; height: 16px;">{icon(I[ic], 16)}</span>' if ic else ""
    right = f'<span style="display: inline-flex; width: 16px; height: 16px;">{icon(I[icon_right], 16)}</span>' if icon_right else ""
    return (f'<a href="#" style="display: inline-flex; align-items: center; justify-content: center; gap: {s[3]}px; '
            f'height: {s[0]}; padding: 0 {s[1]}px; border-radius: var(--radius-md); {v} '
            f'font: var(--weight-medium) {s[2]}px/1 var(--font-sans); white-space: nowrap; {extra}">{left}{label}{right}</a>')


def badge(label, tone="neutral", size="md", pill=True):
    return (f'<span style="display: inline-flex; align-items: center; gap: 6px; padding: {"3px 8px" if size == "sm" else "5px 10px"}; '
            f'border-radius: {"var(--radius-pill)" if pill else "var(--radius-sm)"}; background: var(--status-{tone}-bg); '
            f'color: var(--status-{tone}-text); font: var(--weight-medium) {11 if size == "sm" else 12}px/1.2 var(--font-sans); white-space: nowrap;">'
            f'<span style="width: 7px; height: 7px; border-radius: 50%; background: var(--status-{tone}); flex: none;"></span>{label}</span>')


VERDICT = {"go": "Go", "nogo": "No-go", "conditional": "Conditional", "insufficient": "Insufficient evidence"}


def verdict_chip(v, size="md", confirmed=False):
    pad = {"lg": "10px 14px", "sm": "4px 8px", "md": "7px 12px"}[size]
    fs = {"lg": 16, "sm": 12, "md": 14}[size]
    conf = '<span style="font-weight: 400; opacity: .8;">· confirmed</span>' if confirmed else ""
    return (f'<span style="display: inline-flex; align-items: center; gap: 8px; padding: {pad}; border-radius: var(--radius-md); '
            f'background: var(--verdict-{v}-bg); color: var(--verdict-{v}-text); font: 600 {fs}px/1 var(--font-sans); white-space: nowrap;">'
            f'<span style="width: 8px; height: 8px; border-radius: 50%; background: var(--verdict-{v});"></span>{VERDICT[v]}{conf}</span>')


def tag(label, mono=False):
    font = "var(--type-mono)" if mono else "var(--weight-medium) 12px/1.2 var(--font-sans)"
    return (f'<span style="display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: var(--radius-sm); '
            f'border: 1px solid var(--border-default); background: var(--surface-sunken); color: var(--text-secondary); font: {font};">{label}</span>')


def metric(label, value, delta=None, tone="success", period=None):
    c = {"success": "var(--status-success-text)", "danger": "var(--status-danger-text)", "neutral": "var(--text-muted)"}[tone]
    foot = ""
    if delta or period:
        foot = '<div style="display: flex; gap: 8px; font: var(--type-body-sm); margin-top: 10px;">'
        if delta:
            foot += f'<span style="color: {c}; font-weight: 500;">{delta}</span>'
        if period:
            foot += f'<span style="color: var(--text-muted);">{period}</span>'
        foot += "</div>"
    return (f'<div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: var(--radius-lg); padding: 24px; box-shadow: var(--shadow-xs);">'
            f'<div style="font: var(--type-body); color: var(--text-secondary);">{label}</div>'
            f'<div style="font: 600 32px/1.1 var(--font-sans); letter-spacing: var(--tracking-tight); margin-top: 8px;">{value}</div>{foot}</div>')


def card(title, body, ic=None, actions="", padding=24, extra=""):
    head = ""
    if title:
        i = f'<span style="display: inline-flex; width: 20px; height: 20px; color: var(--text-primary);">{icon(I[ic], 20)}</span>' if ic else ""
        head = (f'<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">{i}'
                f'<div style="font: var(--type-h4); letter-spacing: var(--tracking-tight); flex: 1;">{title}</div>'
                f'<div style="display: flex; gap: 8px; align-items: center;">{actions}</div></div>')
    return (f'<div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: var(--radius-lg); '
            f'box-shadow: var(--shadow-xs); padding: {padding}px; {extra}">{head}{body}</div>')


def eyebrow(text, extra=""):
    return f'<div style="font: 500 12px/1 var(--font-sans); letter-spacing: .06em; color: var(--text-muted); text-transform: uppercase; {extra}">{text}</div>'


def underline_tabs(items, active):
    out = '<div role="tablist" style="display: flex; gap: 24px; border-bottom: 1px solid var(--border-default); flex: 1;">'
    for label, count in items:
        on = label == active
        col = "var(--text-primary)" if on else "var(--text-muted)"
        bb = "var(--cb-blue-500)" if on else "transparent"
        out += (f'<a href="#" role="tab" style="padding: 10px 0; margin-bottom: -1px; font: var(--weight-medium) 14px/1 var(--font-sans); color: {col}; '
                f'border-bottom: 2px solid {bb};">{label}<span style="margin-left: 6px; color: var(--text-muted); font-weight: 400;">{count}</span></a>')
    return out + "</div>"


def select(label, extra=""):
    return (f'<span style="display: inline-flex; align-items: center; gap: 10px; height: var(--control-md); padding: 0 12px; border-radius: var(--radius-md); '
            f'border: 1px solid var(--border-default); background: var(--surface-card); font: var(--weight-medium) 14px/1 var(--font-sans); '
            f'box-shadow: var(--shadow-xs); min-width: 120px; justify-content: space-between; {extra}">{label}'
            f'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--text-muted);"><path d="m7 15 5 5 5-5"></path><path d="m7 9 5-5 5 5"></path></svg></span>')


# ------------------------------------------------------------------------------------ shell


def nav_item(ic, label, active=False, solid=False, trailing=False):
    bg = "var(--surface-card)" if active else "transparent"
    border = "var(--border-default)" if active else "transparent"
    shadow = "var(--shadow-active-nav)" if active else "none"
    tile_bg = "var(--surface-accent)" if solid else "var(--cb-blue-100)"
    tile_fg = "#fff" if solid else "var(--cb-blue-500)"
    tr = f'<span style="color: var(--text-muted); display: inline-flex;">{icon(I["chev"], 16)}</span>' if trailing else ""
    return (f'<a href="#" style="display: flex; align-items: center; gap: 12px; width: 100%; height: 44px; padding: 0 10px; border-radius: var(--radius-md); '
            f'background: {bg}; border: 1px solid {border}; box-shadow: {shadow};">'
            f'<span style="width: 32px; height: 32px; border-radius: 10px; display: inline-flex; align-items: center; justify-content: center; background: {tile_bg}; color: {tile_fg}; flex: none;">{icon(I[ic], 18)}</span>'
            f'<span style="font: var(--weight-medium) 15px/1 var(--font-sans); color: var(--text-primary); flex: 1;">{label}</span>{tr}</a>')


def sidebar(active):
    return f"""
  <aside style="width: var(--sidebar-width); flex: none; padding: 28px 20px; display: flex; flex-direction: column; height: 900px;">
    <div style="display: flex; align-items: center; padding: 4px 8px;"><img src="logo-lockup.svg" alt="CrossBid" style="height: 30px; display: block;"></div>
    {eyebrow("Workflow", "padding: 0 10px; margin: 24px 0 10px;")}
    <div style="display: flex; flex-direction: column; gap: 4px;">
      {nav_item("grid", "Dashboard", active == "dashboard")}
      {nav_item("file", "Tenders", active == "tenders")}
      {nav_item("fileCheck", "Compliance", active == "matrix")}
      {nav_item("layers", "Certificates")}
      {nav_item("shield", "Verdicts", active == "verdict", solid=True)}
    </div>
    <div style="height: 1px; background: var(--border-default); margin: 24px 0 0;"></div>
    {eyebrow("Platform", "padding: 0 10px; margin: 24px 0 10px;")}
    <div style="display: flex; flex-direction: column; gap: 4px;">
      {nav_item("spark", "Agent runs")}
      {nav_item("db", "Company profile", trailing=True)}
      {nav_item("sliders", "Settings")}
    </div>
    <div style="flex: 1;"></div>
    <div style="display: flex; align-items: center; gap: 10px; padding: 10px;">
      <span style="width: 32px; height: 32px; border-radius: 50%; background: var(--cb-stone-200); display: inline-flex; align-items: center; justify-content: center; font: 600 12px/1 var(--font-sans); color: var(--text-secondary);">LH</span>
      <div><div style="font: 500 14px/1.2 var(--font-sans);">Lena Hartmann</div><div style="font: 400 12px/1.2 var(--font-sans); color: var(--text-muted);">Beispiel IT Services GmbH</div></div>
    </div>
  </aside>"""


def shell(active, content, frame_extra=""):
    return f"""
<div style="width: 1440px; height: 900px; display: flex; background: var(--surface-canvas); overflow: hidden;">
  {sidebar(active)}
  <main style="flex: 1; min-width: 0; padding: 28px 28px 28px 0;">
    <div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: 14px; height: 844px; padding: 32px; box-shadow: var(--shadow-xs); overflow: auto; display: flex; flex-direction: column; {frame_extra}">
      {content}
    </div>
  </main>
</div>"""


def page_header(title, right=""):
    return (f'<div style="display: flex; align-items: center; gap: 12px; margin-bottom: 24px;">'
            f'<h1 style="font: 600 30px/1.1 var(--font-sans); letter-spacing: -0.03em; margin: 0; flex: 1;">{title}</h1>{right}</div>')


def section_head(title, link=None):
    l = (f'<a href="#" style="font: 500 14px/1 var(--font-sans); color: var(--text-secondary); display: inline-flex; gap: 6px; align-items: center;">{link} {icon(I["arrow"], 14)}</a>'
         if link else "")
    return (f'<div style="display: flex; align-items: center; justify-content: space-between; margin: 28px 0 14px;">'
            f'<div style="font: 600 18px/1.2 var(--font-sans); letter-spacing: -0.02em;">{title}</div>{l}</div>')


def doc(title, body):
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <title>{title}</title>
  <style>{BASE_CSS}</style>
</helmet>
{body}
</x-dc>
</body>
</html>
"""


# ------------------------------------------------------------------------------- content

TENDERS = [
    ("Prestations de conseil en architecture d'entreprise et d'expertise technique", "618320-2026", "9 Oct · 28 days", "Review", "warning", "Ministère de l'éducation nationale", "FR → DE", "€3.9M", "nogo", "recommended · awaiting your confirmation"),
    ("Beratungs- und Unterstützungsleistungen für IPv6-Migrationen — Los 2", "614251-2026", "6 Oct · 25 days", "Analysis", "info", "Beschaffungsamt des BMI", "DE", "—", "insufficient", "Checking 41 of 62"),
    ("Digital Communications Services", "606362-2026", "12 Oct · 31 days", "Confirmed", "success", "EASA, Cologne", "EN → DE", "€8.0M", "go", "20 requirements · all supported"),
]

REQS = [
    # id, category, translation (DE), source, state, evidence, original FR
    ("REQ-001", "Exclusion", "Keine rechtskräftige Verurteilung wegen Korruption, Betrug oder Geldwäsche in den letzten fünf Jahren.", "RC p. 6 §4.1", "supported", "Eigenerklärung im ESPD — an dieser Stelle wird kein Nachweis verlangt", "Le candidat ne doit pas avoir fait l'objet d'une condamnation définitive pour corruption, fraude ou blanchiment au cours des cinq dernières années."),
    ("REQ-002", "Exclusion", "Steuern und Sozialabgaben sind zum 31. Dezember des Vorjahres vollständig entrichtet.", "RC p. 7 §4.2", "supported", "Bescheinigung in Steuersachen (Finanzamt, 03/2026) · Unbedenklichkeitsbescheinigung (Krankenkasse)", "Le candidat doit être à jour de ses obligations fiscales et sociales au 31 décembre de l'année précédant la consultation."),
    ("REQ-009", "Selection", "Durchschnittlicher Jahresumsatz der letzten drei Geschäftsjahre von mindestens 2 000 000 € (netto).", "RC p. 9 §5.1", "unsupported", "Jahresabschluss 2025: 1 450 000 € — unter der Schwelle", "Chiffre d'affaires annuel moyen sur les trois derniers exercices disponibles au moins égal à 2 000 000 € HT."),
    ("REQ-011", "Selection", "Berufshaftpflichtversicherung, die die Risiken der Leistung abdeckt; die Deckungssumme ist nachzuweisen.", "RC p. 9 §5.2", "partial", "Police gefunden (Allianz); Deckungssumme fehlt im Profil", "Attestation d'assurance responsabilité civile professionnelle couvrant les risques liés aux prestations."),
    ("REQ-014", "Technical", "Zertifizierung des Informationssicherheits-Managementsystems nach ISO/IEC 27001 oder gleichwertig.", "RC p. 11 §5.4", "supported", "ISO/IEC 27001:2022 · TÜV Süd · gültig bis 14.03.2027", "Certification ISO/IEC 27001 du système de management de la sécurité de l'information, ou équivalent."),
    ("REQ-017", "Technical", "Drei Referenzen vergleichbarer Leistungen aus den letzten drei Jahren mit Auftraggeber, Umfang und Zeitraum.", "RC p. 12 §5.5", "partial", "Zwei Referenzen gefunden (Stadt Bonn, Bundesagentur); dritte fehlt", "Trois références de prestations similaires exécutées au cours des trois dernières années, précisant le client, le montant et la période."),
]
STATE = {"supported": ("success", "Supported"), "partial": ("warning", "Partially supported"), "unsupported": ("danger", "Unsupported")}


# ----------------------------------------------------------------------------- Dashboard


def dashboard():
    ask = f"""
  <div style="border: 1px solid var(--border-default); border-radius: 14px; padding: 18px 22px 16px; box-shadow: var(--shadow-xs);">
    <div style="display: flex; align-items: center; gap: 12px; color: var(--text-muted);">{icon(I["search"], 20)}<span style="flex: 1; font: 400 17px/1 var(--font-sans); color: var(--text-placeholder);">Ask about any tender, @ to add a document</span></div>
    <div style="display: flex; align-items: center; gap: 8px; margin-top: 14px;">{button("Upload tender", "secondary", "sm", ic="plus")}{button("Bidder language: DE", "secondary", "sm", ic="lang")}<span style="flex: 1;"></span>{button("Thorough", "secondary", "sm", icon_right="chev")}</div>
  </div>"""
    quick = ""
    for label, ic, solid in [("Analyse tender", "file", True), ("Upload documents", "upload", False), ("Map certificates", "layers", False), ("Check evidence", "fileCheck", False), ("Review verdict", "shield", False), ("Company profile", "db", False)]:
        bg = "var(--surface-accent)" if solid else "var(--cb-blue-100)"
        fg = "#fff" if solid else "var(--cb-blue-500)"
        quick += (f'<a href="#" style="display: flex; flex-direction: column; align-items: center; gap: 10px;">'
                  f'<span style="width: 60px; height: 60px; border-radius: 14px; background: {bg}; color: {fg}; display: inline-flex; align-items: center; justify-content: center;">{icon(I[ic], 24)}</span>'
                  f'<span style="font: 400 14px/1 var(--font-sans); color: var(--text-secondary);">{label}</span></a>')
    cols = "minmax(0, 2.2fr) 140px 130px minmax(0, 1.5fr) 90px 190px"
    rows = ""
    for i, (title, ref, due, phase, tone, buyer, lang, value, verdict, note) in enumerate(TENDERS):
        border = "border-bottom: 1px solid var(--border-default);" if i < len(TENDERS) - 1 else ""
        rows += f"""
      <div style="display: grid; grid-template-columns: {cols}; padding: 0 20px; height: 60px; align-items: center; {border} font: 400 14px/1.2 var(--font-sans);">
        <span style="display: flex; flex-direction: column; gap: 3px; min-width: 0; padding-right: 16px;"><a href="#" style="font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{title}</a><span class="mono" style="color: var(--text-muted);">{ref} · {lang}</span></span>
        <span style="display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary);">{icon(I["clock"], 15)}{due}</span>
        <span>{badge(phase, tone, pill=False)}</span>
        <span style="color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 16px;">{buyer}</span>
        <span style="color: var(--text-secondary);">{value}</span>
        <span style="display: flex; flex-direction: column; gap: 4px; align-items: flex-start;">{verdict_chip(verdict, "sm")}<span style="font-size: 12px; color: var(--text-muted);">{note}</span></span>
      </div>"""
    content = f"""
  {page_header("Good afternoon, Lena", button("Customize", "secondary", ic="grid"))}
  {ask}
  <div style="display: flex; justify-content: center; gap: 28px; margin: 28px 0 4px;">{quick}</div>
  {section_head("Key metrics", "View reports")}
  <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px;">
    {metric("Open tenders", "3", "↑ 1", "success", "This week")}{metric("Requirements checked", "113", "↑ 31", "success", "Last 7 days")}{metric("Verdicts awaiting review", "1", "▲ 1", "neutral", "Current")}{metric("Go rate", "50%", "↑ 8.3%", "success", "YTD")}
  </div>
  {section_head("Next 30 days", "View all tenders")}
  <div style="border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden;">
    <div style="display: grid; grid-template-columns: {cols}; padding: 0 20px; height: 46px; align-items: center; font: 500 13px/1 var(--font-sans); color: var(--text-secondary); border-bottom: 1px solid var(--border-default);"><span>Tender</span><span>Due</span><span>Phase</span><span>Buyer</span><span>Value</span><span>Verdict</span></div>
    {rows}
  </div>"""
    return doc("Dashboard", shell("dashboard", content))


# --------------------------------------------------------------------------- Analyse tender


def new_bid():
    def file_row(name, meta, status_html, last=False):
        return (f'<div style="display: flex; align-items: center; gap: 12px; padding: 14px 0; {"" if last else "border-bottom: 1px solid var(--border-default);"}">'
                f'<span style="color: var(--text-muted);">{icon(I["file"], 18)}</span>'
                f'<div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px;"><span style="font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{name}</span><span style="font: var(--type-body-sm); color: var(--text-muted);">{meta}</span></div>{status_html}</div>')
    tender = f"""
    <div style="display: flex; align-items: flex-start; gap: 16px; padding: 16px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--surface-sunken);">
      <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px;">
        <span style="font-weight: 500;">Prestations de conseil en architecture d'entreprise et d'expertise technique — pour les ministères de l'éducation nationale, des sports, de la jeunesse et de la vie associative</span>
        <div style="display: flex; gap: 8px; flex-wrap: wrap;">{tag("618320-2026", mono=True)}{tag("Ministère de l'éducation nationale")}{tag("France → Germany")}{tag("Due 9 Oct 2026, 16:00")}{tag("Language FR · offers in FR")}{tag("Framework · €3.9M")}</div>
      </div>
      {button("Change", "secondary", "sm")}
    </div>"""
    docs_body = f"""
    <p style="margin: 0 0 16px; color: var(--text-secondary);">The notice points at the buyer's platform, and CrossBid never fetches from there. Download the pack yourself and drop it here — the RC, the CCTP, the DUME if the buyer published one, and any annexes.</p>
    <div style="padding: 28px; border: 1px dashed var(--border-strong); border-radius: var(--radius-lg); background: var(--surface-sunken); display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center;">
      <span style="color: var(--text-muted);">{icon(I["upload"], 24)}</span>
      <span style="font-weight: 500;">Drop PDF or ESPD/DUME XML files here, or <a href="#" style="text-decoration: underline;">choose files</a></span>
      <span style="font: var(--type-body-sm); color: var(--text-muted);">Up to 50 MB per file. Pages without a text layer are counted and shown, never guessed.</span>
    </div>
    <div style="margin-top: 8px;">
      {file_row("26023_AOO_Conseil_Architecure_SI_RC_v1.pdf", "Règlement de la consultation · 25 pages · 2 pages without a text layer (19, 23)", badge("Ready", "success"))}
      {file_row("DUME_acheteur.xml", "Buyer's ESPD form · 30 criteria read directly — no inference needed for these", badge("Ready · structured", "success"))}
      {file_row("618320-2026.notice.fr.pdf", "TED notice · added from TED", badge("Ready", "success"))}
      {file_row("CCTP_conseil_architecture.pdf", "Uploading · 4.1 MB", badge("In progress", "info"), last=True)}
    </div>"""
    start = f"""
    <div style="display: flex; align-items: center; gap: 16px;">
      <div style="flex: 1; display: flex; flex-direction: column; gap: 4px;">
        <span style="font-weight: 500;">Explain the requirements in German</span>
        <span style="font: var(--type-body-sm); color: var(--text-muted);">From your company profile. About 4 minutes for a 200-page pack. The agent stops before any verdict and waits for your confirmation.</span>
      </div>
      {select("Bidder language: DE")}
      {button("Start analysis", "primary", "lg", ic="spark")}
    </div>"""
    content = f"""
  <div style="display: flex; align-items: center; gap: 8px; font: 400 13px/1 var(--font-sans); color: var(--text-muted); margin-bottom: 12px;"><a href="#" style="color: var(--text-muted);">Tenders</a><span>/</span><span>Analyse tender</span></div>
  {page_header("Analyse tender", badge("Step 2 of 3 · Upload the pack", "info", pill=False))}
  <div style="display: flex; flex-direction: column; gap: 20px;">
    {card("Tender", tender, ic="file", actions=badge("Found on TED", "success", "sm"))}
    {card("Procurement documents", docs_body, ic="upload", actions=tag("4 files · 3 ready"))}
    {card("Start", start, ic="spark")}
  </div>"""
    return doc("Analyse tender", shell("tenders", content))


# ------------------------------------------------------------------------ Compliance matrix


def req_row(r, open_=False):
    rid, cat, trans, src, state, ev, orig = r
    tone, label = STATE[state]
    cols = "92px 92px minmax(0, 1fr) 130px 180px"
    row = f"""
    <div style="display: grid; grid-template-columns: {cols}; gap: 16px; padding: 14px 20px; align-items: center; font: 400 14px/1.4 var(--font-sans); background: {"var(--surface-sunken)" if open_ else "transparent"};">
      {tag(rid, mono=True)}<span style="color: var(--text-secondary);">{cat}</span>
      <span style="overflow: hidden; text-overflow: ellipsis; white-space: {"normal" if open_ else "nowrap"};">{trans}</span>
      <a href="#" class="mono" style="display: inline-flex; gap: 5px; align-items: center; color: var(--text-link);">{src}{icon(I["ext"], 12)}</a>
      {badge(label, tone)}
    </div>"""
    if open_:
        row += f"""
    <div style="padding: 0 20px 18px 128px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; background: var(--surface-sunken);">
      <div>{eyebrow("Source (FR) · RC p. 7 §4.2", "margin-bottom: 6px;")}<div style="font: 400 14px/1.5 var(--font-sans); color: var(--text-secondary); font-style: italic;">“{orig}”</div></div>
      <div>{eyebrow("Evidence in your profile", "margin-bottom: 6px;")}<div style="font: 400 14px/1.5 var(--font-sans);">{ev}</div>
        <div style="margin-top: 10px; padding: 10px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--surface-card); font: var(--type-body-sm); color: var(--text-secondary); display: flex; gap: 8px;">{icon(I["layers"], 14)}<span><b style="color: var(--text-primary); font-weight: 500;">eCertis · Paiement d'impôts et taxes.</b> In Germany this criterion is evidenced by a Bescheinigung in Steuersachen from the Finanzamt and an Unbedenklichkeitsbescheinigung from the Krankenkasse.</span></div>
        <div style="margin-top: 10px; display: flex; gap: 8px;">{button("Confirm", "secondary", "sm", ic="check")}{button("Change status", "secondary", "sm", icon_right="chev")}{button("Add evidence", "ghost", "sm", ic="upload")}</div></div>
    </div>"""
    return f'<div style="border-bottom: 1px solid var(--border-default);">{row}</div>'


def source_panel():
    lines = "".join(f'<div style="height: 8px; width: {w}%; background: var(--cb-stone-100); border-radius: 2px;"></div>' for w in (92, 88, 95, 60))
    lines2 = "".join(f'<div style="height: 8px; width: {w}%; background: var(--cb-stone-100); border-radius: 2px;"></div>' for w in (90, 84, 93, 40, 89, 91, 70))
    body = f"""
    <div style="display: flex; align-items: center; gap: 6px; margin: -6px 0 12px;">
      {button("RC v1", "secondary", "sm")}{button("Notice", "ghost", "sm")}{button("DUME", "ghost", "sm")}{button("CCTP", "ghost", "sm")}
      <span style="flex: 1;"></span>
      <a href="#" style="width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); border: 1px solid var(--border-default);">{icon(I["chevL"], 16)}</a>
      <span class="mono" style="font-size: 12px;">p. 7 / 25</span>
      <a href="#" style="width: 32px; height: 32px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); border: 1px solid var(--border-default);">{icon(I["chevR"], 16)}</a>
    </div>
    <div style="background: var(--surface-sunken); border: 1px solid var(--border-default); border-radius: var(--radius-md); padding: 16px; display: flex; justify-content: center;">
      <div style="width: 100%; background: var(--surface-card); border: 1px solid var(--border-default); padding: 28px 26px; display: flex; flex-direction: column; gap: 9px; box-shadow: var(--shadow-sm);">
        <div class="mono" style="font-size: 10px; color: var(--text-muted);">26023-AOO · Règlement de la consultation · 7</div>
        <div style="height: 10px; width: 55%; background: var(--cb-stone-200); border-radius: 2px;"></div>
        {lines}
        <div style="margin-top: 6px; height: 10px; width: 40%; background: var(--cb-stone-200); border-radius: 2px;"></div>
        <div style="border: 2px solid var(--status-warning); background: var(--status-warning-bg); border-radius: 4px; padding: 8px 10px; font: 400 11px/1.45 var(--font-sans);">4.2 — Le candidat doit être à jour de ses obligations fiscales et sociales au 31 décembre de l'année précédant la consultation. Il produit à cet effet les attestations…</div>
        {lines2}
      </div>
    </div>
    <div style="display: flex; align-items: center; gap: 8px; margin-top: 12px; font: var(--type-body-sm); color: var(--text-muted);">{icon(I["alert"], 14)}<span>Pages 19 and 23 have no text layer and were not read.</span></div>"""
    return card("Source", body, ic="file", actions=f'<a href="#" style="display: inline-flex; gap: 6px; align-items: center; font: 500 13px/1 var(--font-sans); color: var(--text-secondary);">Open source page {icon(I["ext"], 14)}</a>', padding=20)


def matrix():
    rows = "".join(req_row(r, open_=(r[0] == "REQ-002")) for r in REQS)
    cols = "92px 92px minmax(0, 1fr) 130px 180px"
    table = f"""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 14px;">
      {underline_tabs([("All requirements", 31), ("Needs evidence", 7), ("Certificates", 5), ("Formal", 16)], "All requirements")}
      {select("Category", "height: var(--control-sm); font-size: 13px;")}
    </div>
    <div style="border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden;">
      <div style="display: grid; grid-template-columns: {cols}; gap: 16px; padding: 0 20px; height: 44px; align-items: center; font: 500 13px/1 var(--font-sans); color: var(--text-secondary); border-bottom: 1px solid var(--border-default); background: var(--surface-sunken);"><span>ID</span><span>Category</span><span>Requirement (explained in DE)</span><span>Source</span><span>Evidence</span></div>
      {rows}
      <div style="padding: 12px 20px; font: 400 13px/1 var(--font-sans); color: var(--text-muted);">Showing 6 of 31 · every line links to its page in the tender · 1 passage flagged as an instruction to the AI and kept out</div>
    </div>"""
    content = f"""
  <div style="display: flex; align-items: center; gap: 8px; font: 400 13px/1 var(--font-sans); color: var(--text-muted); margin-bottom: 12px;"><a href="#" style="color: var(--text-muted);">Tenders</a><span>/</span><span class="mono">618320-2026</span></div>
  {page_header("Prestations de conseil en architecture d'entreprise et d'expertise technique", badge("Awaiting your confirmation", "warning") + button("Review verdict", "primary", ic="shield"))}
  <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 24px;">{tag("Ministère de l'éducation nationale")}{tag("France → Germany")}{tag("25 pages · FR")}{tag("Due 9 Oct 2026 · 28 days")}{tag("618320-2026", mono=True)}</div>
  <div style="display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 28px;">
    {metric("Requirements extracted", "31", None, "neutral", "all cited")}{metric("Supported", "24", "77%", "success", "of requirements")}{metric("Partially supported", "4", "▲ –", "neutral", "need evidence from you")}{metric("Unsupported", "3", "▼ 0", "danger", "since last run")}
  </div>
  <div style="display: grid; grid-template-columns: minmax(0, 1fr) 400px; gap: 20px; align-items: start;">
    <div>{table}</div>
    {source_panel()}
  </div>"""
    return doc("Compliance matrix", shell("matrix", content))


# --------------------------------------------------------------------------------- Verdict


def verdict():
    cite = lambda t: f'<a href="#" class="mono" style="font-size: 13px;">{t}</a>'
    recommends = f"""
    <div style="display: flex; align-items: center; gap: 14px; margin-bottom: 14px;">{verdict_chip("nogo", "lg")}<span style="font: 400 14px/1.4 var(--font-sans); color: var(--text-secondary);">24 of 31 requirements supported. 3 cannot be met from your profile as it stands.</span></div>
    <p style="font: 400 15px/1.6 var(--font-sans); margin: 0;">Der Mindestumsatz von 2 Mio. € wird mit 1,45 Mio. € nicht erreicht ({cite("REQ-009 · RC p. 9 §5.1")}). Das ist eine Mindestanforderung an die Eignung, die der Auftraggeber nicht ermessensabhängig prüft: ohne einen Nachweis über einen höheren Umsatz oder eine Bietergemeinschaft ist das Angebot nicht zulässig. Zwei formale Regeln sind ebenfalls nicht erfüllt — Einreichung ausschließlich über PLACE ({cite("REQ-025 · RC p. 4 §2.3")}) und eine qualifizierte elektronische Signatur ({cite("REQ-026 · RC p. 5 §2.4")}); beide sind lösbar, ändern das Urteil aber erst, wenn der Umsatz nachgewiesen ist.</p>
    <div style="margin-top: 16px; padding: 12px 14px; border: 1px solid var(--border-default); border-radius: 10px; background: var(--surface-sunken); font: 400 13px/1.5 var(--font-sans); color: var(--text-secondary); display: flex; gap: 10px;">{icon(I["alert"], 16)}<span>Advisory only. CrossBid never submits and never asserts compliance without a source. This verdict does not move forward until you confirm it.</span></div>"""
    changes = ""
    for rid, txt, eff, col in [("REQ-009", "Nachweis eines Umsatzes ≥ 2 Mio. € — z. B. als Bietergemeinschaft mit Konsortialvertrag.", "→ Conditional if added", "var(--status-success-text)"),
                               ("REQ-025", "Angebot über die Plattform PLACE einreichen (Registrierung vorab).", "Formal — resolvable", "var(--text-muted)"),
                               ("REQ-026", "Qualifizierte elektronische Signatur einer vertretungsberechtigten Person.", "Formal — resolvable", "var(--text-muted)"),
                               ("REQ-011", "Deckungssumme der Berufshaftpflicht nachtragen.", "Strengthens position", "var(--text-muted)")]:
        changes += f'<div style="display: grid; grid-template-columns: 90px minmax(0, 1fr) auto; gap: 14px; align-items: center; font: 400 14px/1.4 var(--font-sans);">{tag(rid, mono=True)}<span>{txt}</span><span style="color: {col}; font-weight: 500; font-size: 13px;">{eff}</span></div>'
    radio_off = '<span style="width: 18px; height: 18px; flex: none; margin-top: 1px; border-radius: 50%; border: 1px solid var(--border-strong); background: #fff;"></span>'
    radio_on = '<span style="width: 18px; height: 18px; flex: none; margin-top: 1px; border-radius: 50%; border: 5px solid var(--cb-blue-500); background: #fff;"></span>'

    def opt(label, desc, on):
        return (f'<label style="display: flex; gap: 10px; align-items: flex-start; font: var(--type-body);">{radio_on if on else radio_off}'
                f'<span><span style="display: block; font-weight: 500; line-height: 20px;">{label}</span><span style="display: block; font: var(--type-body-sm); color: var(--text-muted);">{desc}</span></span></label>')
    decision = f"""
    <div role="radiogroup" style="display: flex; flex-direction: column; gap: 12px;">
      {opt("Go", "Proceed to the bid. Only when every unsupported row is resolved.", False)}
      {opt("Conditional", "Proceed while evidence for REQ-009 is collected. Recorded as your override.", True)}
      {opt("No-go", "Confirm the agent's verdict. Archive this tender; reasons are kept for reporting.", False)}
      {opt("Insufficient evidence", "Hold — request documents from your team before deciding.", False)}
    </div>
    <div style="margin-top: 14px; display: flex; flex-direction: column; gap: 6px;">
      <span style="font: var(--weight-medium) 13px/1 var(--font-sans);">Reason for overriding <span style="color: var(--status-danger-text);">*</span></span>
      <div style="min-height: 84px; padding: 10px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-xs); font: 400 14px/1.5 var(--font-sans);">Wir bieten als Bietergemeinschaft mit der Muster Consulting GmbH an; der gemeinsame Umsatz 2023–2025 liegt bei 3,1 Mio. €. Der Konsortialvertrag folgt vor Abgabe.</div>
      <span style="font: var(--type-body-sm); color: var(--text-muted);">Required when your decision differs from the agent's. Both stay visible on the tender.</span>
    </div>
    <div style="height: 1px; background: var(--border-default); margin: 18px 0;"></div>
    <label style="display: flex; gap: 10px; align-items: flex-start; font: var(--type-body);"><span style="width: 18px; height: 18px; flex: none; margin-top: 1px; border-radius: var(--radius-xs); background: var(--cb-blue-500); display: inline-flex; align-items: center; justify-content: center; color: #fff;">{icon('<path d="M20 6 9 17l-5-5"></path>', 12)}</span><span><span style="display: block; font-weight: 500; line-height: 20px;">I have reviewed the compliance matrix</span><span style="display: block; font: var(--type-body-sm); color: var(--text-muted);">Required. Verdicts are never confirmed automatically.</span></span></label>
    <div style="display: flex; gap: 8px; margin-top: 18px;">{button("Confirm verdict", "primary", extra="flex: 1;")}{button("Back to matrix", "secondary")}</div>"""
    content = f"""
  <div style="display: flex; align-items: center; gap: 8px; font: 400 13px/1 var(--font-sans); color: var(--text-muted); margin-bottom: 12px;"><a href="#" style="color: var(--text-muted);">Tenders</a><span>/</span><a href="#" class="mono" style="color: var(--text-muted);">618320-2026</a><span>/</span><span>Verdict</span></div>
  {page_header("Review verdict", badge("Awaiting your confirmation", "warning"))}
  <div style="display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 20px; align-items: start;">
    <div style="display: flex; flex-direction: column; gap: 20px;">
      {card("CrossBid recommends", recommends, ic="spark", actions=tag("run 3 · 11 Sep 14:32", mono=True))}
      {card("What would change the verdict", f'<div style="display: flex; flex-direction: column; gap: 12px;">{changes}</div>', ic="fileCheck")}
    </div>
    {card("Your decision", decision, ic="shield")}
  </div>"""
    return doc("Review verdict", shell("verdict", content))


# ---------------------------------------------------------------------------------- Phone


def phone():
    def seg(label, on):
        return (f'<a href="#" style="height: 44px; flex: 1; display: flex; align-items: center; justify-content: center; font: var(--weight-medium) 14px/1 var(--font-sans); '
                f'background: {"var(--surface-brand)" if on else "transparent"}; color: {"#fff" if on else "var(--text-primary)"};">{label}</a>')
    cards = ""
    groups = [("Exclusion · 6", REQS[:2]), ("Selection · 4", REQS[2:4]), ("Technical · 5", REQS[4:6])]
    for head, rows in groups:
        cards += eyebrow(head, "padding-top: 4px;")
        for rid, cat, trans, src, state, ev, orig in rows:
            tone, label = STATE[state]
            cards += (f'<a href="#" style="display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; border: 1px solid var(--border-default); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-xs); min-height: 44px;">'
                      f'<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">{badge(label, tone, "sm")}<span class="mono" style="font-size: 12px; color: var(--text-muted);">{rid} · {src}</span></div>'
                      f'<span style="font: 400 14px/1.45 var(--font-sans); color: var(--text-primary);">{trans}</span>'
                      f'<span style="font: var(--type-body-sm); color: var(--text-secondary);">{ev}</span></a>')
    body = f"""
<div style="width: 390px; height: 844px; display: flex; flex-direction: column; background: var(--surface-canvas); overflow: hidden;">
  <header style="height: 56px; padding: 0 12px 0 16px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-default); background: var(--surface-card);">
    <img src="logo-lockup.svg" alt="CrossBid" style="height: 26px; display: block;">
    <span style="display: flex; gap: 6px;">{button("Analyse", "primary", "md", ic="spark", extra="height: 44px;")}<a href="#" style="width: 44px; height: 44px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); border: 1px solid var(--border-default);">{icon(I["menu"], 20)}</a></span>
  </header>
  <div style="padding: 14px 16px 0; display: flex; flex-direction: column; gap: 10px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;"><span class="mono" style="font-size: 12px; color: var(--text-muted);">618320-2026 · FR → DE</span>{badge("Awaiting your confirmation", "warning", "sm")}</div>
    <h1 style="margin: 0; font: 600 18px/1.3 var(--font-sans); letter-spacing: -0.02em;">Prestations de conseil en architecture d'entreprise et d'expertise technique</h1>
    <div style="font: var(--type-body-sm); color: var(--text-secondary);">Ministère de l'éducation nationale · Due 9 Oct, 28 days</div>
    <div role="tablist" style="display: flex; border: 1px solid var(--border-default); border-radius: var(--radius-md); background: var(--surface-card); overflow: hidden;">{seg("Matrix", True)}{seg("Source", False)}{seg("Verdict", False)}</div>
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;"><span style="font-size: 13px;"><b>24</b><span style="color: var(--text-muted);"> / 31 supported</span> · <span style="color: var(--status-danger-text);">3 unsupported</span> · <span style="color: var(--status-warning-text);">4 partial</span></span><a href="#" style="font-size: 13px; color: var(--text-secondary); display: inline-flex; align-items: center; gap: 4px; min-height: 44px; padding: 0 8px; margin-right: -8px;">Filter {icon(I["chev"], 14)}</a></div>
  </div>
  <div style="flex: 1; overflow: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px;">{cards}</div>
  <div style="border-top: 1px solid var(--border-default); padding: 12px 16px 24px; background: var(--surface-card);">{button("Review verdict", "primary", "lg", ic="shield", extra="width: 100%; height: 48px;")}</div>
</div>"""
    return doc("Compliance matrix · phone", body)



# --------------------------------------------------------------------------------- Landing

MARKETING_MAX = "1160px"


def wrap(inner, extra=""):
    return f'<div style="max-width: {MARKETING_MAX}; margin: 0 auto; padding: 0 24px; {extra}">{inner}</div>'


def m_eyebrow(text):
    return f'<div style="font: 500 12px/1 var(--font-sans); letter-spacing: .08em; text-transform: uppercase; color: var(--text-accent); margin-bottom: 14px;">{text}</div>'


def m_h2(text):
    return f'<h2 style="font: 600 40px/1.1 var(--font-sans); letter-spacing: -0.03em; margin: 0; text-wrap: balance;">{text}</h2>'


def m_lead(text, center=False):
    margin = "16px auto 0" if center else "16px 0 0"
    return f'<p style="font: 400 17px/1.6 var(--font-sans); color: var(--text-secondary); margin: {margin}; max-width: 560px; text-wrap: pretty;">{text}</p>'


def inverse_button(label, size="lg", icon_right=None):
    return button(label, "primary", size, icon_right=icon_right, extra="background: var(--surface-inverse);")


def product_frame():
    rows = [("REQ-002", "Steuern und Sozialabgaben vollständig entrichtet", "RC p. 7 §4.2", "success", "Supported"),
            ("REQ-009", "Durchschnittsumsatz ≥ 2 Mio. € (netto)", "RC p. 9 §5.1", "danger", "Unsupported"),
            ("REQ-014", "ISO/IEC 27001 oder gleichwertig", "RC p. 11 §5.4", "success", "Supported"),
            ("REQ-017", "Drei vergleichbare Referenzen aus drei Jahren", "RC p. 12 §5.5", "warning", "Partially supported")]
    table = ""
    for i, (rid, t, src, tone, label) in enumerate(rows):
        table += (f'<div style="display: grid; grid-template-columns: 82px minmax(0, 1fr) 110px 150px; gap: 12px; align-items: center; padding: 11px 14px; '
                  f'{"border-top: 1px solid var(--border-default);" if i else ""} font: 400 13px/1.3 var(--font-sans);">{tag(rid, mono=True)}'
                  f'<span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{t}</span>'
                  f'<span class="mono" style="font-size: 11px; color: var(--text-link);">{src}</span>{badge(label, tone, "sm")}</div>')
    return f"""
    <div style="max-width: 980px; margin: 56px auto 0; position: relative;">
      <div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: 16px; box-shadow: var(--shadow-lg); overflow: hidden;">
        <div style="display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--border-default); background: var(--surface-sunken);">
          <span style="width: 10px; height: 10px; border-radius: 50%; background: var(--cb-stone-300);"></span><span style="width: 10px; height: 10px; border-radius: 50%; background: var(--cb-stone-300);"></span><span style="width: 10px; height: 10px; border-radius: 50%; background: var(--cb-stone-300);"></span>
          <span class="mono" style="margin-left: 12px; color: var(--text-muted);">app.crossbid.eu / tenders / 618320-2026</span>
        </div>
        <div style="padding: 28px; display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 24px; text-align: left;">
          <div>
            <div style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap;">{tag("Ministère de l'éducation nationale")}{tag("France → Germany")}{tag("25 pages · FR")}</div>
            <div style="font: 600 20px/1.25 var(--font-sans); letter-spacing: -0.02em; margin-bottom: 18px;">Prestations de conseil en architecture d'entreprise et d'expertise technique</div>
            <div style="border: 1px solid var(--border-default); border-radius: 10px; overflow: hidden;">{table}</div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <div style="border: 1px solid var(--border-default); border-radius: 12px; padding: 18px;"><div style="font: 400 13px/1 var(--font-sans); color: var(--text-secondary); margin-bottom: 10px;">CrossBid recommends</div>{verdict_chip("nogo", "lg")}<div style="font: 400 13px/1.5 var(--font-sans); color: var(--text-secondary); margin-top: 12px;">24 of 31 requirements supported. One selection minimum is not met and decides the verdict.</div></div>
            <div style="border: 1px solid var(--border-default); border-radius: 12px; padding: 18px; background: var(--surface-sunken);"><div style="font: 400 13px/1 var(--font-sans); color: var(--text-secondary); margin-bottom: 10px;">Awaiting review</div>{button("Confirm verdict", "primary", "sm", extra="width: 100%;")}<div style="font: 400 12px/1.4 var(--font-sans); color: var(--text-muted); margin-top: 8px;">Nothing moves forward until a person confirms.</div></div>
          </div>
        </div>
      </div>
      <div style="position: absolute; left: 0; right: 0; bottom: -1px; height: 140px; background: var(--protect-gradient); pointer-events: none;"></div>
    </div>"""


def landing():
    nav_links = "".join(f'<a href="#" style="font: 500 14px/1 var(--font-sans); color: var(--text-secondary);">{l}</a>' for l in ("Product", "How it works", "Certificates", "Pricing", "Customers"))
    nav = f"""
  <header style="position: sticky; top: 0; z-index: 50; background: rgba(250, 250, 249, 0.8); backdrop-filter: var(--blur-glass); -webkit-backdrop-filter: var(--blur-glass); border-bottom: 1px solid var(--border-subtle);">
    {wrap(f'<a href="#" style="display: flex; align-items: center;"><img src="logo-lockup.svg" alt="CrossBid" style="height: 30px; display: block;"></a><nav style="display: flex; gap: 28px; flex: 1; justify-content: center;">{nav_links}</nav><div style="display: flex; gap: 8px;">{button("Sign in", "secondary", "sm")}{inverse_button("Book a demo", "sm")}</div>', "height: 68px; display: flex; align-items: center; gap: 32px;")}
  </header>"""
    hero = f"""
  <section style="position: relative; overflow: hidden; padding: 96px 24px 0; text-align: center;">
    <div aria-hidden="true" style="position: absolute; inset: 0; background-image: linear-gradient(var(--cb-stone-200) 1px, transparent 1px), linear-gradient(90deg, var(--cb-stone-200) 1px, transparent 1px); background-size: 72px 72px; opacity: .35; mask-image: radial-gradient(ellipse 70% 60% at 50% 20%, #000 30%, transparent 100%); -webkit-mask-image: radial-gradient(ellipse 70% 60% at 50% 20%, #000 30%, transparent 100%); pointer-events: none;"></div>
    <div style="position: relative; max-width: {MARKETING_MAX}; margin: 0 auto;">
      <div style="display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px 6px 8px; border-radius: 999px; border: 1px solid var(--border-default); background: var(--surface-card); font: 500 13px/1 var(--font-sans); color: var(--text-secondary); margin-bottom: 28px;"><span style="padding: 3px 8px; border-radius: 999px; background: var(--cb-orange-500); color: #fff; font: 600 11px/1.2 var(--font-sans);">New</span>Certificate equivalence via eCertis for all 27 member states</div>
      <h1 style="font: 600 64px/1.05 var(--font-sans); letter-spacing: -0.035em; margin: 0 auto; max-width: 820px; text-wrap: balance;">Know if you can win before you write a word.</h1>
      <p style="font: 400 19px/1.55 var(--font-sans); color: var(--text-secondary); max-width: 620px; margin: 24px auto 0; text-wrap: pretty;">CrossBid reads any EU tender, maps every requirement to your evidence, and gives you a go / no-go verdict you can defend — with a citation for each line.</p>
      <div style="display: flex; gap: 10px; justify-content: center; margin-top: 32px;">{inverse_button("Analyse a tender", "lg", icon_right="arrow")}{button("Book a demo", "secondary", "lg")}</div>
      <div style="font: 400 13px/1 var(--font-sans); color: var(--text-muted); margin-top: 16px;">Advisory by design — CrossBid never submits on your behalf.</div>
      {product_frame()}
    </div>
  </section>"""
    trust = f"""
  <section style="padding: 72px 0 0;">{wrap('<div style="font: 400 14px/1 var(--font-sans); color: var(--text-muted); margin-bottom: 24px;">Used by bid teams tendering across borders</div><div style="display: flex; justify-content: center; gap: 44px; flex-wrap: wrap; opacity: .6;">' + "".join(f'<span style="font: 600 17px/1 var(--font-sans); letter-spacing: -0.02em; color: var(--text-secondary); border: 1px dashed var(--border-strong); border-radius: 6px; padding: 6px 12px;">[Customer {i}]</span>' for i in range(1, 6)) + '</div>', "text-align: center;")}</section>"""
    steps_data = [("Read", "Upload the tender in any EU language. CrossBid extracts every requirement — exclusion, selection, technical, formal — each with a link to its source page.", "file"),
                  ("Translate and explain", "Each requirement is translated into your language and explained in plain terms, including what the buyer will accept as proof.", "lang"),
                  ("Map certificates", "Requested certificates are matched to their equivalents in your home country through eCertis — Attestation URSSAF to Unbedenklichkeitsbescheinigung — with the legal basis.", "layers"),
                  ("Check evidence", "Every requirement is checked against your company documents. Supported, partially supported, or unsupported — never assumed.", "fileCheck"),
                  ("Verdict", "Go, No-go, Conditional, or Insufficient evidence — with the compliance matrix behind it. A person confirms before anything proceeds.", "shield")]
    steps = ""
    for i, (t, d, ic) in enumerate(steps_data):
        last = i == 4
        steps += (f'<div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: 14px; padding: 22px; box-shadow: var(--shadow-xs);">'
                  f'<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px;"><span style="width: 44px; height: 44px; border-radius: 12px; background: {"var(--cb-ink)" if last else "var(--surface-accent-soft)"}; color: {"#fff" if last else "var(--text-accent)"}; display: inline-flex; align-items: center; justify-content: center;">{icon(I[ic], 22)}</span><span class="mono" style="color: var(--text-muted);">0{i + 1}</span></div>'
                  f'<div style="font: 600 17px/1.2 var(--font-sans); letter-spacing: -0.02em; margin-bottom: 8px;">{t}</div><div style="font: 400 14px/1.55 var(--font-sans); color: var(--text-secondary);">{d}</div></div>')
    how = f"""
  <section style="padding: 128px 0 0;">{wrap(m_eyebrow("How it works") + m_h2("Judgement work, done before the bid is written.") + m_lead("Five steps, each one traceable to the tender and to your own documents.") + f'<div style="display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px; margin-top: 48px;">{steps}</div>')}</section>"""
    checks = "".join(f'<div style="display: flex; gap: 12px;"><span style="width: 22px; height: 22px; border-radius: 50%; background: var(--status-success-bg); color: var(--status-success); display: inline-flex; align-items: center; justify-content: center; flex: none; margin-top: 1px;">{icon(I["check"], 14)}</span><div><div style="font: 500 15px/1.3 var(--font-sans);">{t}</div><div style="font: 400 14px/1.5 var(--font-sans); color: var(--text-secondary);">{d}</div></div></div>'
                     for t, d in [("Source-linked extraction", "Page and clause reference on every requirement."), ("Translated, not paraphrased", "The original text stays alongside the explanation."), ("Refuses when unsure", "If the documents do not support a verdict, CrossBid says so.")])
    req_card = f"""
      <div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: 16px; padding: 24px; box-shadow: var(--shadow-md);">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">{tag("REQ-002", mono=True)}<span style="font: 500 13px/1 var(--font-sans); color: var(--text-secondary);">Exclusion ·</span><a href="#" class="mono" style="display: inline-flex; gap: 5px; align-items: center;">RC p. 7 §4.2{icon(I["ext"], 12)}</a></div>
        {eyebrow("Source (FR)", "margin-bottom: 6px;")}<div style="font: italic 400 14px/1.5 var(--font-sans); color: var(--text-secondary); margin-bottom: 16px;">“Le candidat doit être à jour de ses obligations fiscales et sociales au 31 décembre de l'année précédant la consultation.”</div>
        {eyebrow("Explained (DE)", "margin-bottom: 6px;")}<div style="font: 400 14px/1.5 var(--font-sans); margin-bottom: 16px;">Steuern und Sozialabgaben sind zum 31. Dezember des Vorjahres vollständig entrichtet. In Deutschland belegt das eine Bescheinigung in Steuersachen des Finanzamts und eine Unbedenklichkeitsbescheinigung der Krankenkasse — so ordnet eCertis dieses Kriterium zu.</div>
        <div style="display: flex; align-items: center; gap: 10px; padding-top: 16px; border-top: 1px solid var(--border-default);">{badge("Supported", "success")}<span style="font: 400 13px/1.3 var(--font-sans); color: var(--text-secondary);">Bescheinigung in Steuersachen, 03/2026 · Krankenkasse, 02/2026</span></div>
      </div>"""
    features = f"""
  <section style="padding: 128px 0 0;">{wrap(f'<div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 64px; align-items: center;"><div>{m_eyebrow("Every requirement, cited")}{m_h2("No claim without a page number.")}{m_lead("Each extracted line links to the exact page and clause in the tender. Reviewers check the source, not the summary.")}<div style="display: flex; flex-direction: column; gap: 14px; margin-top: 32px;">{checks}</div></div>{req_card}</div>')}</section>"""
    cert_rows = [("FR", "Attestation de régularité fiscale", "DE", "Bescheinigung in Steuersachen", "Dir. 2014/24 Art. 60 · eCertis"),
                 ("FR", "Attestation URSSAF", "DE", "Unbedenklichkeitsbescheinigung", "Dir. 2014/24 Art. 60 · eCertis"),
                 ("FR", "Extrait Kbis", "DE", "Handelsregisterauszug", "Dir. 2014/24 Ann. XI"),
                 ("DE", "Auszug Gewerbezentralregister", "FR", "Extrait de casier judiciaire (bulletin n° 3)", "Dir. 2014/24 Art. 60 · eCertis")]
    cert_table = ('<div style="display: grid; grid-template-columns: 36px minmax(0, 1fr) 36px minmax(0, 1fr) minmax(0, 1fr); gap: 12px; padding: 12px 18px; font: 500 12px/1 var(--font-sans); color: var(--text-secondary); background: var(--surface-sunken); border-bottom: 1px solid var(--border-default);"><span></span><span>Requested</span><span></span><span>Your equivalent</span><span>Basis</span></div>'
                  + "".join(f'<div style="display: grid; grid-template-columns: 36px minmax(0, 1fr) 36px minmax(0, 1fr) minmax(0, 1fr); gap: 12px; padding: 13px 18px; align-items: center; {"border-top: 1px solid var(--border-default);" if i else ""} font: 400 13px/1.3 var(--font-sans); overflow-wrap: anywhere;">{tag(a, mono=True)}<span>{b}</span>{tag(c, mono=True)}<span>{d}</span><span class="mono" style="font-size: 11px; color: var(--text-muted); line-height: 1.4;">{e}</span></div>'
                            for i, (a, b, c, d, e) in enumerate(cert_rows)))
    certificates = f"""
  <section style="padding: 128px 0 0;">{wrap(f'<div style="display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); gap: 56px; align-items: center;"><div style="background: var(--surface-card); border: 1px solid var(--border-default); border-radius: 14px; overflow: hidden; box-shadow: var(--shadow-xs); min-width: 0;">{cert_table}</div><div>{m_eyebrow("Certificate equivalence")}{m_h2("The buyer asks in their system. You answer in yours.")}{m_lead("CrossBid maps requested certificates and registrations to their equivalents in your home country through the EU's eCertis service, and cites the directive or national rule that makes the equivalence valid.")}</div></div>')}</section>"""
    pillars = "".join(f'<div style="border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; padding: 16px 18px; background: rgba(255, 255, 255, 0.04);"><div style="font: 500 15px/1.3 var(--font-sans);">{t}</div><div style="font: 400 14px/1.5 var(--font-sans); color: var(--cb-stone-400); margin-top: 4px;">{d}</div></div>'
                      for t, d in [("Never submits", "Every verdict is confirmed by a person before anything proceeds."), ("Never asserts without a source", "Each compliance claim points at a page in the tender and a document in your profile."), ("Refuses when unsupported", "“Insufficient evidence” is a first-class verdict, not a failure state.")])
    advisory = f"""
  <section style="padding: 128px 0 0;">{wrap(f'<div style="background: var(--surface-inverse); color: #fff; border-radius: 24px; padding: 72px 64px; display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 56px; align-items: center;"><div><div style="font: 500 12px/1 var(--font-sans); letter-spacing: .08em; text-transform: uppercase; color: var(--cb-orange-500); margin-bottom: 14px;">Advisory by design</div><h2 style="font: 600 40px/1.1 var(--font-sans); letter-spacing: -0.03em; margin: 0; text-wrap: balance;">An agent that knows what it does not know.</h2><p style="font: 400 17px/1.6 var(--font-sans); color: var(--cb-stone-300); margin: 16px 0 0; max-width: 520px;">CrossBid never submits a bid, never asserts compliance without a source, and withholds a verdict when the documents do not support one. Every verdict is confirmed by a person.</p></div><div style="display: grid; gap: 12px;">{pillars}</div></div>')}</section>"""
    cta = f"""
  <section style="padding: 128px 0;">{wrap(m_h2("Bring a tender. Leave with a verdict.") + m_lead("Upload one tender and see the compliance matrix in minutes. No integration required.", center=True) + f'<div style="display: flex; gap: 10px; justify-content: center; margin-top: 32px;">{inverse_button("Analyse a tender", "lg", icon_right="arrow")}{button("Talk to the team", "secondary", "lg")}</div>', "text-align: center;")}</section>"""
    cols = [("Product", ["How it works", "Certificate equivalence", "Compliance matrix", "Pricing"]), ("Company", ["About", "Customers", "Careers", "Contact"]), ("Resources", ["Documentation", "EU procurement guide", "Security", "Status"]), ("Legal", ["Privacy", "Terms", "Data processing", "Imprint"])]
    footer_cols = "".join(f'<div><div style="font: 500 13px/1 var(--font-sans); margin-bottom: 14px;">{h}</div><div style="display: flex; flex-direction: column; gap: 10px;">' + "".join(f'<a href="#" style="font: 400 14px/1 var(--font-sans); color: var(--text-secondary);">{l}</a>' for l in ls) + "</div></div>" for h, ls in cols)
    footer = f"""
  <footer style="border-top: 1px solid var(--border-default); padding: 56px 24px 40px;">
    <div style="max-width: {MARKETING_MAX}; margin: 0 auto; display: grid; grid-template-columns: 1.4fr repeat(4, minmax(0, 1fr)); gap: 32px;">
      <div><img src="logo-lockup.svg" alt="CrossBid" style="height: 28px; display: block;"><div style="font: 400 14px/1.55 var(--font-sans); color: var(--text-secondary); margin-top: 14px; max-width: 280px;">Go / no-go for EU public tenders, with a citation for every line.</div></div>
      {footer_cols}
    </div>
    <div style="max-width: {MARKETING_MAX}; margin: 40px auto 0; padding-top: 24px; border-top: 1px solid var(--border-default); display: flex; justify-content: space-between; font: 400 13px/1 var(--font-sans); color: var(--text-muted);"><span>© 2026 CrossBid</span><span>Made in the EU · Data stays in the EU</span></div>
  </footer>"""
    body = f'<div style="width: 1440px; min-height: 4200px; background: var(--surface-canvas);">{nav}{hero}{trust}{how}{features}{certificates}{advisory}{cta}{footer}</div>'
    return doc("CrossBid — landing page", body)

CANVAS = """{
  "artboards": [
    { "file": "Dashboard.dc.html", "x": 0, "y": 0, "w": 1440, "h": 900, "title": "Dashboard" },
    { "file": "NewBid.dc.html", "x": 1560, "y": 0, "w": 1440, "h": 900, "title": "Analyse tender — upload the pack" },
    { "file": "Main.dc.html", "x": 0, "y": 1080, "w": 1440, "h": 900, "title": "Compliance matrix — with the source page open" },
    { "file": "Verdict.dc.html", "x": 1560, "y": 1080, "w": 1440, "h": 900, "title": "Review verdict — override with a reason" },
    { "file": "WorkspacePhone.dc.html", "x": 3120, "y": 1080, "w": 390, "h": 844, "title": "Compliance matrix — phone" },
    { "file": "Landing.dc.html", "x": 0, "y": 2120, "w": 1440, "h": 4200, "title": "Landing page — website", "expand": "fill" }
  ],
  "annotations": [
    { "id": "brief", "x": 0, "y": -300, "w": 720, "text": "S4.0.1, draft 2 — built on the CrossBid design system (project b81312f6): its shell, its website kit (the landing page below), tokens, Geist, NavItem / Button / Badge / Tag / MetricCard / VerdictChip / Tabs / Radio / Card anatomy, and the SVG logo lockup. Static mockups. UI in English; requirements explained in German; source quotes in French (the real TED 618320-2026 fixture). Company documents and figures are sample data.\\n\\nVocabulary: adopted from the design system on 2026-09-11 (ADR-0013). Verdicts are Go / Conditional / No-go / Insufficient evidence and rows are Supported / Partially supported / Unsupported / Not applicable in the backend enums, the SQL constraints and the generated TypeScript.\\n\\nThe source page (S4.5.1's PDF-beside-the-matrix) opens as a 400 px panel to the right of the matrix rather than a permanent split — that is the one screen the system did not have." },
    { "id": "gate", "x": 780, "y": -300, "w": 440, "text": "The gate (docs/project-plan.md S4.0.1): nothing under components/matrix, components/pdf or components/verdict is coded until you confirm this canvas. Accepted changes are recorded in an ADR, and later UI stories cite the artboard they implement." }
  ],
  "launch": { "view": "canvas" }
}
"""

if __name__ == "__main__":
    (HERE / "Dashboard.dc.html").write_text(dashboard(), encoding="utf-8")
    (HERE / "NewBid.dc.html").write_text(new_bid(), encoding="utf-8")
    (HERE / "Main.dc.html").write_text(matrix(), encoding="utf-8")
    (HERE / "Verdict.dc.html").write_text(verdict(), encoding="utf-8")
    (HERE / "WorkspacePhone.dc.html").write_text(phone(), encoding="utf-8")
    (HERE / "Landing.dc.html").write_text(landing(), encoding="utf-8")
    (HERE / "canvas.json").write_text(CANVAS, encoding="utf-8")
    print("wrote 5 artboards + canvas.json")
