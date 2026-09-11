"""Emit the S4.0.1 design-canvas artboards from one shared token sheet.

Tokens are lifted from `frontend/app/globals.css` and the shell components (Geist, neutral
oklch greys, 10 px radius, 56 px header, 1024 px container, 32 px controls). Run
`python3 build.py`; the `.dc.html` files it writes are the working files the canvas is
seeded from. Status colours are a proposal (see the canvas note) - the app has none yet.
"""

from pathlib import Path

HERE = Path(__file__).parent

# ---- tokens (frontend/app/globals.css, :root) --------------------------------------
BG = "oklch(1 0 0)"
FG = "oklch(0.145 0 0)"
PRIMARY = "oklch(0.205 0 0)"
PRIMARY_FG = "oklch(0.985 0 0)"
MUTED = "oklch(0.97 0 0)"
MUTED_FG = "oklch(0.556 0 0)"
BORDER = "oklch(0.922 0 0)"
DESTRUCTIVE = "oklch(0.577 0.245 27.325)"
RADIUS = "10px"      # --radius 0.625rem
RADIUS_MD = "8px"
RADIUS_SM = "6px"

# ---- proposed semantic colours (shared lightness/chroma, hue varies) ------------------
MET = "oklch(0.55 0.14 150)"
MET_BG = "oklch(0.965 0.03 150)"
UNMET = DESTRUCTIVE
UNMET_BG = "oklch(0.965 0.03 27)"
UNCLEAR = "oklch(0.55 0.14 70)"
UNCLEAR_BG = "oklch(0.965 0.04 80)"
RUNNING = "oklch(0.55 0.14 250)"
RUNNING_BG = "oklch(0.965 0.03 250)"
NA = MUTED_FG
NA_BG = MUTED

BASE_CSS = f"""
    @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap');
    body {{ margin: 0; background: {BG}; color: {FG}; font-family: Geist, system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased; }}
    * {{ box-sizing: border-box; }}
    a {{ color: {FG}; text-decoration: none; }} a:hover {{ color: {MUTED_FG}; }}
    .mono {{ font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .muted {{ color: {MUTED_FG}; }}
    .pill {{ display: inline-flex; align-items: center; gap: 6px; height: 24px; padding: 0 9px; border-radius: 999px; font-size: 12px; font-weight: 500; white-space: nowrap; }}
    .dot {{ width: 7px; height: 7px; border-radius: 999px; background: currentColor; flex: none; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 32px; padding: 0 10px; border-radius: {RADIUS}; border: 1px solid transparent; font-size: 14px; font-weight: 500; white-space: nowrap; background: {PRIMARY}; color: {PRIMARY_FG}; }}
    .btn.lg {{ height: 36px; }}
    .btn.outline {{ background: {BG}; color: {FG}; border-color: {BORDER}; }}
    .btn.ghost {{ background: transparent; color: {FG}; }}
    .btn.destructive {{ background: {UNMET_BG}; color: {UNMET}; }}
    .card {{ background: {BG}; border: 1px solid {BORDER}; border-radius: {RADIUS}; }}
    .label {{ font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.02em; color: {MUTED_FG}; }}
    .th {{ font-size: 12px; font-weight: 500; color: {MUTED_FG}; text-align: left; padding: 8px 12px; border-bottom: 1px solid {BORDER}; white-space: nowrap; }}
    .td {{ padding: 12px; border-bottom: 1px solid {BORDER}; vertical-align: top; }}
    table {{ border-collapse: collapse; width: 100%; }}
    .quote {{ font-style: normal; color: {FG}; border-left: 2px solid {BORDER}; padding-left: 10px; }}
    input, textarea, select {{ font: inherit; }}
"""

def pill(text, fg, bg, dot=True):
    d = '<span class="dot"></span>' if dot else ""
    return f'<span class="pill" style="color: {fg}; background: {bg};">{d}{text}</span>'

def svg(path, size=16):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex: none;">{path}</svg>')

CHEVRON_DOWN = '<path d="m6 9 6 6 6-6"></path>'
CHEVRON_RIGHT = '<path d="m9 18 6-6-6-6"></path>'
CHEVRON_LEFT = '<path d="m15 18-6-6 6-6"></path>'
FILE = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><path d="M14 2v6h6"></path>'
CHECK = '<path d="M20 6 9 17l-5-5"></path>'
ALERT = '<path d="M12 9v4"></path><path d="M12 17h.01"></path><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"></path>'
UPLOAD = '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><path d="m17 8-5-5-5 5"></path><path d="M12 3v12"></path>'
SEARCH = '<circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path>'
MENU = '<path d="M4 6h16"></path><path d="M4 12h16"></path><path d="M4 18h16"></path>'
EXTERNAL = '<path d="M15 3h6v6"></path><path d="M10 14 21 3"></path><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>'
PAPERCLIP = '<path d="m21.4 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>'

def shell_header(active, width_class="max-width: 1024px;"):
    def nav(label, is_active=False, primary=False):
        if primary:
            return f'<a class="btn" href="#">{label}</a>'
        bg = MUTED if is_active else "transparent"
        return f'<a class="btn ghost" href="#" style="background: {bg};">{label}</a>'
    return f"""
<header style="position: sticky; top: 0; border-bottom: 1px solid {BORDER}; background: {BG}; z-index: 10;">
  <div style="margin: 0 auto; {width_class} height: 56px; padding: 0 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px;">
    <a href="#" style="font-size: 16px; font-weight: 600; letter-spacing: -0.01em;">Crossbid</a>
    <nav style="display: flex; align-items: center; gap: 8px;">
      {nav("Dashboard", active == "dashboard")}
      {nav("Company", active == "company")}
      {nav("Settings", active == "settings")}
      {nav("New bid", primary=True)}
      <span class="muted" style="margin-left: 8px; font-size: 13px;">demo@it-services.example</span>
    </nav>
  </div>
</header>"""

FOOTER = f"""
<footer style="margin-top: auto; border-top: 1px solid {BORDER};">
  <div class="muted" style="margin: 0 auto; max-width: 1024px; padding: 24px 16px; font-size: 12px;">Advisory only. Crossbid never submits a bid, and a person confirms or overrides every verdict.</div>
</footer>"""

def doc(title, body, extra_css=""):
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
  <style>{BASE_CSS}{extra_css}</style>
</helmet>
{body}
</x-dc>
</body>
</html>
"""

# =============================================================================== Dashboard

def dashboard():
    def row(title, ref, lang, buyer, deadline, days, status_html, verdict_html, open_html, cta):
        return f"""
      <tr>
        <td class="td" style="max-width: 420px;">
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <a href="#" style="font-weight: 500;">{title}</a>
            <span class="muted mono" style="font-size: 12px;">{ref} · {lang}</span>
          </div>
        </td>
        <td class="td">{buyer}</td>
        <td class="td" style="white-space: nowrap;">
          <div style="display: flex; flex-direction: column; gap: 2px;">
            <span>{deadline}</span><span class="muted" style="font-size: 12px;">{days}</span>
          </div>
        </td>
        <td class="td">{status_html}</td>
        <td class="td">{verdict_html}</td>
        <td class="td">{open_html}</td>
        <td class="td" style="text-align: right;">{cta}</td>
      </tr>"""

    progress = f"""
          <div style="display: flex; flex-direction: column; gap: 6px; min-width: 180px;">
            {pill("Checking requirements", RUNNING, RUNNING_BG)}
            <div style="display: flex; align-items: center; gap: 8px;">
              <div style="flex: 1; height: 4px; border-radius: 999px; background: {MUTED}; overflow: hidden;"><div style="width: 66%; height: 100%; background: {RUNNING};"></div></div>
              <span class="muted mono" style="font-size: 12px;">41 / 62</span>
            </div>
          </div>"""

    body = f"""
<div style="min-height: 900px; display: flex; flex-direction: column; background: {BG};">
  {shell_header("dashboard")}
  <main style="margin: 0 auto; width: 100%; max-width: 1024px; padding: 32px 16px; display: flex; flex-direction: column; gap: 24px;">
    <div style="display: flex; align-items: flex-end; justify-content: space-between; gap: 16px;">
      <div style="display: flex; flex-direction: column; gap: 4px;">
        <h1 style="margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em;">Dashboard</h1>
        <p class="muted" style="margin: 0;">Every bid you have checked, and what needs you today.</p>
      </div>
      <a class="btn lg" href="#">New bid</a>
    </div>

    <section class="card" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 20px; border-color: {UNCLEAR}; background: {UNCLEAR_BG};">
      <div style="display: flex; align-items: center; gap: 12px; color: {UNCLEAR};">
        {svg(ALERT, 20)}
        <div style="display: flex; flex-direction: column; gap: 2px; color: {FG};">
          <span style="font-weight: 500;">1 bid is waiting for your review</span>
          <span class="muted" style="font-size: 13px;">The agent stopped before the verdict. Nothing is final until you confirm or override it.</span>
        </div>
      </div>
      <a class="btn" href="#">Review now</a>
    </section>

    <section class="card" style="overflow: hidden;">
      <table>
        <thead>
          <tr>
            <th class="th">Tender</th><th class="th">Buyer</th><th class="th">Deadline</th><th class="th">Status</th><th class="th">Verdict</th><th class="th">Open items</th><th class="th"></th>
          </tr>
        </thead>
        <tbody>
          {row("Prestations de conseil en architecture d'entreprise et d'expertise technique", "618320-2026", "FR → explained in DE",
               "Ministère de l'éducation nationale, FR", "9 Oct 2026, 16:00", "28 days left",
               pill("Awaiting your review", UNCLEAR, UNCLEAR_BG), '<span class="muted">—</span>',
               '<span>4 unclear · 3 not met</span>', '<a class="btn" href="#">Review</a>')}
          {row("Beratungs- und Unterstützungsleistungen für IPv6-Migrationen — Los 2", "614251-2026", "DE",
               "Beschaffungsamt des BMI, DE", "6 Oct 2026", "25 days left",
               progress, '<span class="muted">—</span>', '<span class="muted">—</span>', '<a class="btn outline" href="#">Open</a>')}
          {row("Digital Communications Services", "606362-2026", "EN → explained in DE",
               "EASA, Cologne (EU agency)", "12 Oct 2026, 10:00", "31 days left",
               pill("Complete", NA, NA_BG), pill("Go, with open items", MET, MET_BG),
               '<span>2 documents to attach</span>', '<a class="btn outline" href="#">Open</a>')}
        </tbody>
      </table>
    </section>
  </main>
  {FOOTER}
</div>"""
    return doc("Dashboard", body)

# ================================================================================= New bid

def new_bid():
    def step(n, label, state):
        if state == "done":
            circle = f'<span style="width: 24px; height: 24px; border-radius: 999px; background: {PRIMARY}; color: {PRIMARY_FG}; display: inline-flex; align-items: center; justify-content: center;">{svg(CHECK, 14)}</span>'
            colour = FG
        elif state == "active":
            circle = f'<span style="width: 24px; height: 24px; border-radius: 999px; background: {PRIMARY}; color: {PRIMARY_FG}; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600;">{n}</span>'
            colour = FG
        else:
            circle = f'<span style="width: 24px; height: 24px; border-radius: 999px; border: 1px solid {BORDER}; color: {MUTED_FG}; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600;">{n}</span>'
            colour = MUTED_FG
        return f'<div style="display: flex; align-items: center; gap: 10px; color: {colour}; font-weight: 500;">{circle}<span>{label}</span></div>'

    def file_row(icon, name, meta, status_html):
        return f"""
        <div style="display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-top: 1px solid {BORDER};">
          <span class="muted">{icon}</span>
          <div style="flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0;">
            <span style="font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{name}</span>
            <span class="muted" style="font-size: 12px;">{meta}</span>
          </div>
          {status_html}
        </div>"""

    body = f"""
<div style="min-height: 900px; display: flex; flex-direction: column; background: {BG};">
  {shell_header("bids")}
  <main style="margin: 0 auto; width: 100%; max-width: 1024px; padding: 32px 16px; display: flex; flex-direction: column; gap: 24px;">
    <div style="display: flex; flex-direction: column; gap: 4px;">
      <h1 style="margin: 0; font-size: 24px; font-weight: 600; letter-spacing: -0.02em;">New bid</h1>
      <p class="muted" style="margin: 0;">Find the tender on TED, upload the documents the buyer published, and start the check.</p>
    </div>

    <div style="display: flex; align-items: center; gap: 24px;">
      {step(1, "Find the tender", "done")}
      <span style="flex: 1; height: 1px; background: {BORDER};"></span>
      {step(2, "Upload the pack", "active")}
      <span style="flex: 1; height: 1px; background: {BORDER};"></span>
      {step(3, "Start", "todo")}
    </div>

    <section class="card" style="display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 16px 20px; background: {MUTED};">
      <div style="display: flex; flex-direction: column; gap: 6px; min-width: 0;">
        <span class="label">Chosen tender</span>
        <span style="font-weight: 500;">Prestations de conseil en architecture d'entreprise et d'expertise technique — pour les ministères de l'éducation nationale, des sports, de la jeunesse et de la vie associative</span>
        <div class="muted" style="display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px;">
          <span class="mono">618320-2026</span>
          <span>Ministère de l'éducation nationale · FR</span>
          <span>Deadline 9 Oct 2026, 16:00</span>
          <span>Language FR · offers in FR</span>
          <span>Framework, single supplier · €3.9 M</span>
        </div>
      </div>
      <a class="btn outline" href="#">Change</a>
    </section>

    <section class="card" style="overflow: hidden;">
      <div style="padding: 20px; display: flex; flex-direction: column; gap: 6px;">
        <h2 style="margin: 0; font-size: 16px; font-weight: 600;">Upload the procurement documents</h2>
        <p class="muted" style="margin: 0;">The notice points at the buyer's platform, and Crossbid never fetches from there. Download the pack yourself and drop it here — the RC, the CCTP, the DUME if the buyer published one, and any annexes.</p>
      </div>
      <div style="margin: 0 20px 20px; padding: 32px; border: 1px dashed {BORDER}; border-radius: {RADIUS}; display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; background: {MUTED};">
        <span class="muted">{svg(UPLOAD, 24)}</span>
        <span style="font-weight: 500;">Drop PDF or ESPD/DUME XML files here, or <a href="#" style="text-decoration: underline;">choose files</a></span>
        <span class="muted" style="font-size: 12px;">Up to 15 MB per file. Scanned pages without a text layer are counted and shown, not guessed.</span>
      </div>
      {file_row(svg(FILE), "26023_AOO_Conseil_Architecure_SI_RC_v1.pdf", "Règlement de la consultation · 25 pages · 2 pages without a text layer (19, 23)", pill("Ready", MET, MET_BG))}
      {file_row(svg(FILE), "DUME_acheteur.xml", "ESPD form from the buyer · 30 criteria read directly — no guessing needed for these", pill("Ready · structured", MET, MET_BG))}
      {file_row(svg(FILE), "618320-2026.notice.fr.pdf", "TED notice · added automatically from TED", pill("Ready", MET, MET_BG))}
      {file_row(svg(FILE), "CCTP_conseil_architecture.pdf", "Uploading · 4.1 MB", pill("Parsing", RUNNING, RUNNING_BG))}
    </section>

    <section class="card" style="display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 20px;">
      <div style="display: flex; flex-direction: column; gap: 2px;">
        <span style="font-weight: 500;">Explain the requirements in <strong>German</strong> <span class="muted" style="font-weight: 400;">(from your company profile)</span></span>
        <span class="muted" style="font-size: 13px;">About 4 minutes for a 200-page pack. The agent stops before any verdict and waits for your review.</span>
      </div>
      <a class="btn lg" href="#" style="opacity: 0.5;">Start the check</a>
    </section>
  </main>
  {FOOTER}
</div>"""
    return doc("New bid", body)

# ======================================================================= Workspace (desktop)

REQ_ROWS = [
    # (status, translation_de, source_fr, doc, page, evidence, ecertis, expanded)
    ("met", "Keine rechtskräftige Verurteilung wegen Korruption, Betrug oder Geldwäsche in den letzten fünf Jahren.",
     "Le candidat ne doit pas avoir fait l'objet d'une condamnation définitive pour corruption, fraude ou blanchiment au cours des cinq dernières années.",
     "RC v1", 6, None, None, False),
    ("met", "Steuern und Sozialabgaben sind zum 31. Dezember des Vorjahres vollständig entrichtet.",
     "Le candidat doit être à jour de ses obligations fiscales et sociales au 31 décembre de l'année précédant la consultation.",
     "RC v1", 7,
     ("Bescheinigung_in_Steuersachen_Finanzamt_2026.pdf", 1, "…bestehen keine Steuerrückstände. Gültig bis 31.03.2027."),
     ("Paiement d'impôts et taxes", "In Germany this is proven by a Bescheinigung in Steuersachen from the Finanzamt, and for social security by an Unbedenklichkeitsbescheinigung from the Krankenkasse."),
     True),
    ("unmet", "Durchschnittlicher Jahresumsatz der letzten drei Geschäftsjahre von mindestens 2 000 000 € (netto).",
     "Chiffre d'affaires annuel moyen sur les trois derniers exercices disponibles au moins égal à 2 000 000 € HT.",
     "RC v1", 9, ("Jahresabschluss_2025.pdf", 3, "Umsatzerlöse 2025: 1.450.000 €"), None, False),
    ("unclear", "Berufshaftpflichtversicherung, die die Risiken der Leistung abdeckt; die Deckungssumme ist nachzuweisen.",
     "Attestation d'assurance responsabilité civile professionnelle couvrant les risques liés aux prestations.",
     "RC v1", 9, None, None, False),
    ("met", "Zertifizierung des Informationssicherheits-Managementsystems nach ISO/IEC 27001 oder gleichwertig.",
     "Certification ISO/IEC 27001 du système de management de la sécurité de l'information, ou équivalent.",
     "RC v1", 11, ("ISO_27001_Zertifikat.pdf", 1, "…erfüllt die Anforderungen der ISO/IEC 27001:2022. Gültig bis 14.03.2027."), None, False),
    ("unclear", "Drei Referenzen vergleichbarer Leistungen aus den letzten drei Jahren mit Angabe von Auftraggeber, Umfang und Zeitraum.",
     "Trois références de prestations similaires exécutées au cours des trois dernières années, précisant le client, le montant et la période.",
     "RC v1", 12, None, None, False),
]

STATUS_LABEL = {"met": ("Met", MET, MET_BG), "unmet": ("Not met", UNMET, UNMET_BG),
                "unclear": ("Unclear", UNCLEAR, UNCLEAR_BG), "na": ("Not applicable", NA, NA_BG)}

def matrix_row(status, de, fr, docname, page, evidence, ecertis, expanded, lang="de"):
    label, fg, bg = STATUS_LABEL[status]
    shown = de if lang == "de" else fr
    ev = ""
    if evidence:
        ev = f"""<div style="display: flex; align-items: flex-start; gap: 6px; font-size: 13px;">
              <span class="muted">{svg(FILE, 14)}</span>
              <span><a href="#" style="text-decoration: underline;">{evidence[0]} · p. {evidence[1]}</a> <span class="muted">“{evidence[2]}”</span></span>
            </div>"""
    else:
        ev = (f'<span class="muted" style="font-size: 13px;">Self-declared in the ESPD — no certificate is asked for at this stage</span>'
          if status == "met" else f'<span class="muted" style="font-size: 13px;">No evidence found in your documents</span>')
    chevron = svg(CHEVRON_DOWN if expanded else CHEVRON_RIGHT, 16)
    detail = ""
    if expanded:
        eterms = ""
        if ecertis:
            eterms = f"""
          <div class="card" style="padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; background: {MUTED};">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
              <span class="label">eCertis · {ecertis[0]}</span>
              <a href="#" class="muted" style="display: inline-flex; align-items: center; gap: 4px; font-size: 12px;">Open on eCertis {svg(EXTERNAL, 12)}</a>
            </div>
            <span style="font-size: 13px;">{ecertis[1]}</span>
          </div>"""
        detail = f"""
        <div style="grid-column: 1 / -1; display: flex; flex-direction: column; gap: 12px; padding: 0 16px 16px 44px;">
          <div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px;">
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <span class="label">Source · français · {docname} p. {page}</span>
              <p class="quote" style="margin: 0; font-size: 13px;">{fr}</p>
            </div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              <span class="label">Why the agent says “{label}”</span>
              <p class="muted" style="margin: 0; font-size: 13px;">The Bescheinigung in Steuersachen is dated within the last 12 months and states no arrears; a matching Krankenkasse certificate is attached. Both are what eCertis names as the German evidence for this French criterion.</p>
            </div>
          </div>
          {eterms}
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
            <a class="btn outline" href="#">{svg(CHECK, 14)} Confirm</a>
            <a class="btn outline" href="#">Change status {svg(CHEVRON_DOWN, 14)}</a>
            <a class="btn outline" href="#">{svg(PAPERCLIP, 14)} Attach a document</a>
            <span class="muted" style="margin-left: auto; font-size: 12px;">Edits stay on this screen until you submit the review.</span>
          </div>
        </div>"""
    bgrow = MUTED if expanded else BG
    return f"""
      <div style="display: grid; grid-template-columns: 28px minmax(0, 1fr) 120px 260px; gap: 0 16px; align-items: start; padding: 12px 16px 12px 16px; border-bottom: 1px solid {BORDER}; background: {bgrow};">
        <span class="muted" style="padding-top: 2px;">{chevron}</span>
        <div style="display: flex; flex-direction: column; gap: 4px; min-width: 0;">
          <span>{shown}</span>
          <a href="#" class="muted" style="font-size: 12px; display: inline-flex; align-items: center; gap: 4px;">{docname} · p. {page} {svg(EXTERNAL, 11)}</a>
        </div>
        <div>{pill(label, fg, bg)}</div>
        <div>{ev}</div>
        {detail}
      </div>"""

def group_header(title, counts):
    return f"""
      <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: {MUTED}; border-bottom: 1px solid {BORDER};">
        <span style="font-weight: 600; font-size: 13px;">{title}</span>
        <span class="muted" style="font-size: 12px;">{counts}</span>
      </div>"""

def pdf_pane():
    return f"""
    <aside class="card" style="display: flex; flex-direction: column; overflow: hidden; min-height: 0;">
      <div style="display: flex; align-items: center; gap: 4px; padding: 8px 12px; border-bottom: 1px solid {BORDER};">
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px; background: {MUTED};">RC v1</a>
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px;">Notice</a>
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px;">DUME</a>
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px;">CCTP</a>
        <span style="margin-left: auto; display: flex; align-items: center; gap: 4px;">
          <a class="btn ghost" href="#" style="width: 28px; height: 28px; padding: 0;">{svg(CHEVRON_LEFT, 16)}</a>
          <span class="mono" style="font-size: 12px;">p. 7 / 25</span>
          <a class="btn ghost" href="#" style="width: 28px; height: 28px; padding: 0;">{svg(CHEVRON_RIGHT, 16)}</a>
        </span>
      </div>
      <div style="flex: 1; background: {MUTED}; padding: 20px; display: flex; justify-content: center; overflow: hidden;">
        <div style="width: 100%; max-width: 440px; background: {BG}; border: 1px solid {BORDER}; padding: 40px 36px; display: flex; flex-direction: column; gap: 10px; box-shadow: 0 1px 2px oklch(0 0 0 / 6%);">
          <div class="mono" style="font-size: 10px; color: {MUTED_FG};">26023-AOO · Règlement de la consultation · 7</div>
          <div style="height: 10px; width: 55%; background: {BORDER}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 92%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 88%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 95%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 60%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="margin-top: 8px; height: 10px; width: 40%; background: {BORDER}; border-radius: 2px;"></div>
          <div style="border: 2px solid {UNCLEAR}; background: {UNCLEAR_BG}; border-radius: 4px; padding: 8px 10px; font-size: 11px; line-height: 1.45;">
            4.2 — Le candidat doit être à jour de ses obligations fiscales et sociales au 31 décembre de l'année précédant la consultation. Il produit à cet effet les attestations…
          </div>
          <div style="height: 8px; width: 90%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 84%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 93%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 40%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="margin-top: 8px; height: 8px; width: 89%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 91%; background: {MUTED}; border-radius: 2px;"></div>
          <div style="height: 8px; width: 70%; background: {MUTED}; border-radius: 2px;"></div>
        </div>
      </div>
      <div class="muted" style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-top: 1px solid {BORDER}; font-size: 12px;">
        {svg(ALERT, 14)} <span>Pages 19 and 23 of this file have no text layer and were not read.</span>
      </div>
    </aside>"""

def workspace():
    rows = "".join(matrix_row(*r) for r in REQ_ROWS)
    body = f"""
<div style="height: 900px; display: flex; flex-direction: column; background: {BG}; overflow: hidden;">
  {shell_header("bids", "max-width: 1408px;")}
  <div style="border-bottom: 1px solid {BORDER};">
    <div style="margin: 0 auto; max-width: 1408px; padding: 14px 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px;">
      <div style="display: flex; flex-direction: column; gap: 4px; min-width: 0;">
        <div style="display: flex; align-items: center; gap: 10px;">
          <h1 style="margin: 0; font-size: 18px; font-weight: 600; letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Prestations de conseil en architecture d'entreprise et d'expertise technique</h1>
          {pill("Awaiting your review", UNCLEAR, UNCLEAR_BG)}
        </div>
        <div class="muted" style="display: flex; gap: 16px; font-size: 13px;">
          <span class="mono">618320-2026</span><span>Ministère de l'éducation nationale · FR</span><span>Deadline 9 Oct 2026, 16:00 · 28 days</span>
          <span style="display: inline-flex; align-items: center; gap: 6px;">Explained in
            <span style="display: inline-flex; border: 1px solid {BORDER}; border-radius: 999px; overflow: hidden;">
              <a href="#" style="padding: 0 8px; font-size: 12px; background: {PRIMARY}; color: {PRIMARY_FG};">DE</a><a href="#" style="padding: 0 8px; font-size: 12px;">FR</a>
            </span>
          </span>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 20px;">
        <div style="display: flex; gap: 20px;">
          <div style="display: flex; flex-direction: column; align-items: flex-end;"><span style="font-size: 18px; font-weight: 600;">24<span class="muted" style="font-weight: 400; font-size: 13px;"> / 31</span></span><span class="label">mandatory met</span></div>
          <div style="display: flex; flex-direction: column; align-items: flex-end;"><span style="font-size: 18px; font-weight: 600; color: {UNMET};">3</span><span class="label">not met</span></div>
          <div style="display: flex; flex-direction: column; align-items: flex-end;"><span style="font-size: 18px; font-weight: 600; color: {UNCLEAR};">4</span><span class="label">unclear</span></div>
        </div>
        <a class="btn lg" href="#">Review verdict</a>
      </div>
    </div>
  </div>

  <main style="flex: 1; min-height: 0; margin: 0 auto; width: 100%; max-width: 1408px; padding: 16px; display: grid; grid-template-columns: 520px minmax(0, 1fr); gap: 16px;">
    {pdf_pane()}
    <section class="card" style="display: flex; flex-direction: column; overflow: hidden; min-height: 0;">
      <div style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid {BORDER};">
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px; background: {MUTED};">All 31</a>
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px; color: {UNMET};">Not met 3</a>
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px; color: {UNCLEAR};">Unclear 4</a>
        <a class="btn ghost" href="#" style="height: 28px; font-size: 13px;">To attach 6</a>
        <span class="muted" style="margin-left: auto; font-size: 12px; display: inline-flex; align-items: center; gap: 6px;">{svg(ALERT, 13)} 1 passage flagged as an instruction to the AI and kept out</span>
      </div>
      <div style="flex: 1; overflow: auto;">
        {group_header("Exclusion grounds", "6 requirements · 6 met")}
        {rows[:0]}{matrix_row(*REQ_ROWS[0])}{matrix_row(*REQ_ROWS[1])}
        {group_header("Economic and financial standing", "4 requirements · 1 met · 1 not met · 2 unclear")}
        {matrix_row(*REQ_ROWS[2])}{matrix_row(*REQ_ROWS[3])}
        {group_header("Technical and professional ability", "5 requirements · 3 met · 2 unclear")}
        {matrix_row(*REQ_ROWS[4])}{matrix_row(*REQ_ROWS[5])}
        {group_header("Formal and submission rules", "16 requirements · 14 met · 2 not met")}
      </div>
    </section>
  </main>
</div>"""
    return doc("Bid workspace", body)

# ============================================================================ Phone workspace

def phone():
    def card(status, de, docname, page, evidence):
        label, fg, bg = STATUS_LABEL[status]
        ev = (f'<span class="muted" style="font-size: 12px;">{svg(FILE, 12)} {evidence[0]} · p. {evidence[1]}</span>'
              if evidence else f'<span class="muted" style="font-size: 12px;">No evidence found</span>')
        return f"""
      <a href="#" class="card" style="display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; min-height: 44px;">
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">{pill(label, fg, bg)}<span class="muted" style="font-size: 12px;">{docname} · p. {page}</span></div>
        <span style="font-size: 14px;">{de}</span>
        {ev}
      </a>"""
    def cards_for(rows):
        return "".join(card(r[0], r[1], r[3], r[4], r[5]) for r in rows)
    cards = (f'<span class="label">Exclusion grounds · 6</span>{cards_for(REQ_ROWS[:2])}'
             f'<span class="label" style="padding-top: 6px;">Economic and financial standing · 4</span>{cards_for(REQ_ROWS[2:4])}'
             f'<span class="label" style="padding-top: 6px;">Technical and professional ability · 5</span>{cards_for(REQ_ROWS[4:6])}')
    body = f"""
<div style="width: 390px; height: 844px; display: flex; flex-direction: column; background: {BG}; overflow: hidden;">
  <header style="border-bottom: 1px solid {BORDER}; padding: 0 16px; height: 56px; display: flex; align-items: center; justify-content: space-between;">
    <span style="font-size: 16px; font-weight: 600;">Crossbid</span>
    <span style="display: flex; gap: 8px;"><a class="btn" href="#" style="height: 44px;">New bid</a><a class="btn ghost" href="#" style="width: 44px; height: 44px; padding: 0;">{svg(MENU, 20)}</a></span>
  </header>
  <div style="padding: 14px 16px 0; display: flex; flex-direction: column; gap: 8px;">
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
      <span class="muted mono" style="font-size: 12px;">618320-2026 · FR</span>{pill("Awaiting your review", UNCLEAR, UNCLEAR_BG)}
    </div>
    <h1 style="margin: 0; font-size: 17px; font-weight: 600; line-height: 1.3; letter-spacing: -0.01em;">Prestations de conseil en architecture d'entreprise et d'expertise technique</h1>
    <div class="muted" style="font-size: 13px;">Ministère de l'éducation nationale · Deadline 9 Oct, 28 days</div>
    <div style="display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 2px; margin-top: 4px; padding: 2px; background: {MUTED}; border-radius: {RADIUS};">
      <a href="#" style="height: 44px; display: flex; align-items: center; justify-content: center; border-radius: {RADIUS_MD}; background: {BG}; font-weight: 500; box-shadow: 0 1px 2px oklch(0 0 0 / 6%);">Matrix</a>
      <a href="#" class="muted" style="height: 44px; display: flex; align-items: center; justify-content: center; border-radius: {RADIUS_MD}; font-weight: 500;">Document</a>
      <a href="#" class="muted" style="height: 44px; display: flex; align-items: center; justify-content: center; border-radius: {RADIUS_MD}; font-weight: 500;">Verdict</a>
    </div>
    <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 4px;">
      <span style="font-size: 13px;"><strong>24</strong><span class="muted"> / 31 met</span> · <span style="color: {UNMET};">3 not met</span> · <span style="color: {UNCLEAR};">4 unclear</span></span>
      <a href="#" class="muted" style="font-size: 13px; display: inline-flex; align-items: center; gap: 4px;">Filter {svg(CHEVRON_DOWN, 14)}</a>
    </div>
  </div>
  <div style="flex: 1; overflow: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px;">
    {cards}
  </div>
  <div style="border-top: 1px solid {BORDER}; padding: 12px 16px 24px; background: {BG};">
    <a class="btn" href="#" style="width: 100%; height: 48px; font-size: 15px;">Review verdict</a>
  </div>
</div>"""
    return doc("Bid workspace · phone", body)

# ================================================================================ Verdict

def verdict():
    def gap(sev, title, required, actual, doc):
        if sev == "blocking":
            p = pill("Blocking", UNMET, UNMET_BG)
        else:
            p = pill("Open item", UNCLEAR, UNCLEAR_BG)
        ra = ""
        if required:
            ra = f"""<div style="display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; font-size: 13px;">
              <div><span class="label">Required</span><div>{required}</div></div>
              <div><span class="label">Found in your documents</span><div>{actual}</div></div>
            </div>"""
        return f"""
        <div style="display: flex; flex-direction: column; gap: 8px; padding: 12px 0; border-top: 1px solid {BORDER};">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">{p}<a href="#" class="muted" style="font-size: 12px;">{doc}</a></div>
          <span style="font-weight: 500;">{title}</span>
          {ra}
        </div>"""
    radio_off = f'<span style="width: 18px; height: 18px; border-radius: 999px; border: 1px solid {MUTED_FG}; flex: none; margin-top: 2px;"></span>'
    radio_on = f'<span style="width: 18px; height: 18px; border-radius: 999px; border: 6px solid {PRIMARY}; background: {BG}; flex: none; margin-top: 2px;"></span>'
    body = f"""
<div style="width: 640px; min-height: 900px; padding: 24px; background: {MUTED}; display: flex; flex-direction: column;">
  <section class="card" style="display: flex; flex-direction: column; overflow: hidden;">
    <div style="padding: 20px 24px; border-bottom: 1px solid {BORDER}; display: flex; flex-direction: column; gap: 12px;">
      <div style="display: flex; align-items: center; justify-content: space-between;">
        <span class="label">The agent's verdict · for you to confirm</span>
        <span class="muted" style="font-size: 12px;">Checked 11 Sep 2026, 14:32</span>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <span style="display: inline-flex; align-items: center; gap: 8px; height: 36px; padding: 0 14px; border-radius: 999px; background: {UNMET_BG}; color: {UNMET}; font-size: 16px; font-weight: 600;"><span class="dot"></span>No-go</span>
        <span style="font-size: 14px;"><strong>24</strong><span class="muted"> / 31 mandatory met</span> · <span style="color: {UNMET};">3 blocking</span> · <span style="color: {UNCLEAR};">4 open items</span></span>
      </div>
      <p style="margin: 0; font-size: 14px;">Der Mindestumsatz von 2 Mio. € wird mit 1,45 Mio. € nicht erreicht. Das ist eine Mindestanforderung an die Eignung, die der Auftraggeber nicht ermessensabhängig prüft; ohne einen Nachweis über einen höheren Umsatz oder eine Bietergemeinschaft ist das Angebot nicht zulässig.</p>
      <p class="muted" style="margin: 0; font-size: 13px;">Rules, not a guess: one unmet mandatory requirement is a no-go. All three not-met rows are listed below; the four unclear rows are open items in the matrix.</p>
    </div>

    <div style="padding: 8px 24px 12px; display: flex; flex-direction: column;">
      <span class="label" style="padding: 8px 0;">What stands in the way</span>
      {gap("blocking", "Durchschnittlicher Jahresumsatz von mindestens 2 000 000 € HT", "€ 2 000 000 average, last 3 years", "€ 1 450 000 (Jahresabschluss 2025, p. 3)", "RC v1 · p. 9")}
      {gap("blocking", "Angebot ausschließlich über die Plattform PLACE bis 9. Okt. 2026, 16:00 Uhr einreichen", None, None, "RC v1 · p. 4")}
      {gap("blocking", "Qualifizierte elektronische Signatur durch eine vertretungsberechtigte Person", None, None, "RC v1 · p. 5")}
      {gap("open", "Berufshaftpflichtversicherung mit nachgewiesener Deckungssumme", None, None, "RC v1 · p. 9")}
      {gap("open", "Drei Referenzen vergleichbarer Leistungen aus den letzten drei Jahren", None, None, "RC v1 · p. 12")}
      <a href="#" class="muted" style="padding: 10px 0; font-size: 13px; border-top: 1px solid {BORDER};">2 more open items in the matrix →</a>
    </div>

    <div style="padding: 20px 24px; border-top: 1px solid {BORDER}; background: {MUTED}; display: flex; flex-direction: column; gap: 14px;">
      <span style="font-weight: 600;">Your decision</span>
      <label style="display: flex; gap: 12px; align-items: flex-start; padding: 12px 14px; border: 1px solid {BORDER}; border-radius: {RADIUS}; background: {BG};">
        {radio_off}
        <span style="display: flex; flex-direction: column; gap: 2px;"><span style="font-weight: 500;">Confirm the verdict — No-go</span><span class="muted" style="font-size: 13px;">Record the agent's verdict as your own.</span></span>
      </label>
      <label style="display: flex; flex-direction: column; gap: 12px; padding: 12px 14px; border: 1px solid {PRIMARY}; border-radius: {RADIUS}; background: {BG};">
        <span style="display: flex; gap: 12px; align-items: flex-start;">
          {radio_on}
          <span style="display: flex; flex-direction: column; gap: 2px;"><span style="font-weight: 500;">Override with a different decision</span><span class="muted" style="font-size: 13px;">Your decision is recorded next to the agent's; both stay visible.</span></span>
        </span>
        <div style="display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 12px; padding-left: 30px;">
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <span class="label">New decision</span>
            <span style="display: flex; align-items: center; justify-content: space-between; height: 36px; padding: 0 12px; border: 1px solid {BORDER}; border-radius: {RADIUS};">Go, with open items {svg(CHEVRON_DOWN, 14)}</span>
          </div>
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <span class="label">Reason <span style="color: {UNMET};">*</span></span>
            <div style="min-height: 84px; padding: 8px 12px; border: 1px solid {BORDER}; border-radius: {RADIUS}; font-size: 13px; line-height: 1.5;">Wir bieten als Bietergemeinschaft mit der Muster Consulting GmbH an; der gemeinsame Umsatz 2023–2025 liegt bei 3,1 Mio. €. Nachweis folgt mit dem Konsortialvertrag.</div>
          </div>
        </div>
      </label>
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 4px;">
        <span class="muted" style="font-size: 12px; max-width: 340px;">Submitted once. 2 rows you changed and 1 document you attached are submitted with it.</span>
        <a class="btn lg" href="#">Submit review</a>
      </div>
    </div>
  </section>
</div>"""
    return doc("Verdict panel", body)

# ================================================================================ canvas

CANVAS = """{
  "artboards": [
    { "file": "Dashboard.dc.html", "x": 0, "y": 0, "w": 1440, "h": 900, "title": "Dashboard" },
    { "file": "NewBid.dc.html", "x": 1560, "y": 0, "w": 1440, "h": 900, "title": "New bid — step 2 of 3" },
    { "file": "Main.dc.html", "x": 0, "y": 1080, "w": 1440, "h": 900, "title": "Bid workspace — desktop" },
    { "file": "WorkspacePhone.dc.html", "x": 1560, "y": 1080, "w": 390, "h": 844, "title": "Bid workspace — phone" },
    { "file": "Verdict.dc.html", "x": 2070, "y": 1080, "w": 640, "h": 900, "title": "Verdict — confirm or override" }
  ],
  "annotations": [
    { "id": "brief", "x": 0, "y": -260, "w": 640, "text": "S4.0.1 first draft — static mockups, not a prototype.\\n\\nMatches the shipped shell: Geist, the shadcn neutral tokens from app/globals.css, 10 px radius, 56 px header, 32 px controls. UI language English; requirements explained in the bidder's language (German here). Content is the real FR fixture (TED 618320-2026); the company documents and figures are sample data.\\n\\nThree things the app has no answer for yet, proposed here — tell me what to change:\\n1. Status colours: met green · not met red (= the theme's destructive) · unclear amber · running blue, all one lightness/chroma.\\n2. Workspace split: PDF left (520 px), matrix right, one row expanded at a time.\\n3. Phone: the PDF moves behind a Document tab; the verdict button stays pinned." },
    { "id": "gate", "x": 700, "y": -260, "w": 420, "text": "The gate (docs/project-plan.md S4.0.1): nothing under components/matrix, components/pdf or components/verdict is coded until you confirm this canvas. Accepted changes are recorded in an ADR, and later UI stories cite the artboard they implement." }
  ],
  "launch": { "view": "canvas" }
}
"""

if __name__ == "__main__":
    (HERE / "Dashboard.dc.html").write_text(dashboard(), encoding="utf-8")
    (HERE / "NewBid.dc.html").write_text(new_bid(), encoding="utf-8")
    (HERE / "Main.dc.html").write_text(workspace(), encoding="utf-8")
    (HERE / "WorkspacePhone.dc.html").write_text(phone(), encoding="utf-8")
    (HERE / "Verdict.dc.html").write_text(verdict(), encoding="utf-8")
    (HERE / "canvas.json").write_text(CANVAS, encoding="utf-8")
    print("wrote 5 artboards + canvas.json")
