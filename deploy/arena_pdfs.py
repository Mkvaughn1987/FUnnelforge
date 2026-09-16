"""
arena_pdfs.py — PDF generator for DripDrop
Builds branded PDF attachments:
  1. Market Pulse
  2. Micro Scorecard
  3. Bench Snapshot / Salary Guide / Interview Guide
  4. Tenure Snapshot

Supports per-user branding: company logo, name, and colors are read
from the user's Company Profile (stored in dripdrop_config.json).
Falls back to a text-based wordmark if no logo is uploaded.
"""
import os, json
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, HRFlowable,
)

# ── Brand ──────────────────────────────────────────────────────────────────
NAVY     = colors.HexColor("#122742")
BLUE     = colors.HexColor("#2C65AC")
ORANGE   = colors.HexColor("#F77331")
GRAY     = colors.HexColor("#686861")
SILVER   = colors.HexColor("#B5B5B2")
LIGHT    = colors.HexColor("#EDF3FA")
WHITE    = colors.white
GREEN    = colors.HexColor("#22c55e")
RED      = colors.HexColor("#ef4444")
DARK_RED = colors.HexColor("#991b1b")
W, H     = letter   # 612 × 792

# ── Config reader ──────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        candidates = [
            Path(os.getenv("LOCALAPPDATA", "")) / "FlowDrip" / "config.json",
            Path.home() / "AppData" / "Local" / "FlowDrip" / "config.json",
        ]
        for cp in candidates:
            if cp.is_file():
                with open(cp, encoding="utf-8") as f:
                    return json.load(f)
    except Exception:
        pass
    return {}

def get_sender(cfg: dict | None = None) -> tuple[str, str]:
    """Return (sender_name, sender_firm) from config."""
    c = cfg or _load_config()
    name = (c.get("ai_sender_name") or c.get("sig_name")
            or c.get("username", "").split(".")[0].capitalize())
    firm = (c.get("company_name") or c.get("ai_sender_firm")
            or c.get("company", ""))
    return name or "Your Company", firm or "Your Company"

# ── Base document ──────────────────────────────────────────────────────────
def _text_logo_fallback(canv, H, BAR_H, NAVY, ORANGE, WHITE, SILVER, company_name=""):
    canv.setFillColor(WHITE)
    canv.setFont("Helvetica-Bold", 15)
    canv.drawString(0.60*inch, H - BAR_H*0.55, company_name or "Your Company")

class ArenaDoc(BaseDocTemplate):
    def __init__(self, filename, badge_text="DOCUMENT",
                 logo_path="", company_name="", brand_color="", **kw):
        self.badge_text = badge_text
        self.user_logo_path = logo_path or ""
        self.user_company_name = company_name or "Your Company"
        self.user_brand_color = brand_color or ""
        super().__init__(filename, **kw)
        # Frame: content starts below logo area, ends above footer
        frame = Frame(0.55*inch, 0.60*inch,
                      W - 1.1*inch, H - 1.60*inch, id="main")
        self.addPageTemplates([
            PageTemplate(id="arena", frames=[frame], onPage=self._chrome)
        ])

    def _chrome(self, canv, doc):
        canv.saveState()

        # Logo — user's uploaded logo ONLY. No fallback to a default logo
        # so that other companies don't accidentally show Arena's branding.
        import os as _os
        _user_logo = getattr(doc, 'user_logo_path', '') or ''
        LOGO = _user_logo if (_user_logo and _os.path.isfile(_user_logo)) else ""
        LOGO_H = 0.55*inch
        if LOGO:
            try:
                lh = LOGO_H
                lw = lh * (1600/497)
                ly = H - 0.45*inch - lh  # top margin
                canv.drawImage(LOGO, 0.55*inch, ly,
                               width=lw, height=lh,
                               preserveAspectRatio=True,
                               mask='auto')
            except Exception:
                # Text fallback if image fails
                canv.setFillColor(NAVY)
                canv.setFont("Helvetica-Bold", 20)
                _cn = getattr(doc, 'user_company_name', '') or 'Your Company'
                canv.drawString(0.55*inch, H - 0.82*inch, _cn)
        else:
            # Same text fallback as the image-failure branch above. This used to
            # draw the literal "ARENA / DIRECT HIRE" wordmark, which contradicted
            # the comment above it: any user who had not uploaded a logo — the
            # default state for every new account on a white-label instance —
            # got Arena's branding on client-facing PDFs.
            canv.setFillColor(NAVY)
            canv.setFont("Helvetica-Bold", 20)
            _cn = getattr(doc, 'user_company_name', '') or 'Your Company'
            canv.drawString(0.55*inch, H - 0.82*inch, _cn)

        # Footer — simple gray text, no colored bar
        canv.setFillColor(SILVER)
        canv.setFont("Helvetica", 7)
        canv.drawCentredString(W/2, 0.30*inch,
                               "Prepared for consultative business development use")

        canv.restoreState()


# ── Style helpers ──────────────────────────────────────────────────────────
def S(name, **kw): return ParagraphStyle(name, **kw)

CW = W - 1.3*inch   # usable content width


def _clean(text: str) -> str:
    """Sanitize text: no em dashes, no asterisks, no double spaces."""
    return (str(text)
            .replace("\u2014", "-").replace("\u2013", "-")   # em/en dash → hyphen
            .replace("—", "-").replace("–", "-")
            .replace("*", "").replace("**", "")              # no asterisks
            .replace("  ", " ").strip())


def section_header(text):
    """Blue bold section header with thin gray line underneath."""
    return [
        Paragraph(f"<b>{_clean(text)}</b>",
                  S("sh", fontName="Helvetica-Bold", fontSize=11,
                    textColor=BLUE, leading=14, spaceAfter=1)),
        HRFlowable(width="100%", thickness=0.5, color=SILVER,
                   spaceBefore=0, spaceAfter=4),
    ]

def bullet_item(text):
    """Standard bullet point with bullet prefix."""
    return Paragraph(
        f'<font color="#2C65AC"><b>\u2022</b></font>  {_clean(text)}',
        S("bp", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
          leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

def band(text, color=NAVY):
    """Colored band header (kept for bench_snapshot compatibility)."""
    t = Table([[Paragraph(text, S("bh", fontName="Helvetica-Bold", fontSize=9,
                                  textColor=WHITE, leading=12))]],
              colWidths=[CW])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), color),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ("RIGHTPADDING",  (0,0),(-1,-1), 10),
    ]))
    return t

def bullet(text, icon="\u25b8", c=BLUE):
    """Legacy bullet helper (kept for bench_snapshot compatibility)."""
    hx = c.hexval()[2:]
    return Paragraph(f'<font color="#{hx}"><b>{icon}</b></font>  {text}',
                     S("bp", fontName="Helvetica", fontSize=9, textColor=NAVY,
                       leading=13, spaceAfter=3, leftIndent=12, firstLineIndent=-12))

def div(before=8, after=8):
    return HRFlowable(width="100%", thickness=0.5, color=LIGHT,
                      spaceBefore=before, spaceAfter=after)

def alt_table(rows, widths, header=True):
    t = Table(rows, colWidths=widths)
    base = [
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 7),
        ("RIGHTPADDING",  (0,0),(-1,-1), 7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LIGHT]),
        ("LINEBELOW",     (0,0),(-1,-1), 0.5, SILVER),
        ("BOX",           (0,0),(-1,-1), 0.5, SILVER),
    ]
    if header:
        base += [
            ("BACKGROUND", (0,0),(-1,0), LIGHT),
            ("FONTNAME",   (0,0),(-1,0), "Helvetica-Bold"),
            ("FONTSIZE",   (0,0),(-1,0), 8),
            ("TEXTCOLOR",  (0,0),(-1,0), NAVY),
            ("VALIGN",     (0,0),(-1,0), "MIDDLE"),
        ]
    t.setStyle(TableStyle(base))
    return t


def _title_block(story, title, subtitle, badge_label):
    """Shared title block: large navy title, italic gray subtitle, blue badge tag."""
    story.append(Paragraph(_clean(title),
                           S("t", fontName="Helvetica-Bold", fontSize=16,
                             textColor=NAVY, leading=19, spaceAfter=2)))
    story.append(Paragraph(f"<i>{_clean(subtitle)}</i>",
                           S("s", fontName="Helvetica-Oblique", fontSize=9,
                             textColor=GRAY, leading=12, spaceAfter=4)))
    story.append(Paragraph(
        f'<font color="#2C65AC"><b>{_clean(badge_label)}</b></font>',
        S("badge", fontName="Helvetica-Bold", fontSize=7,
          textColor=BLUE, leading=10, spaceAfter=1)))
    story.append(Spacer(1, 6))


# ─────────────────────────────────────────────────────────────────────────
# 1. MARKET PULSE
# ─────────────────────────────────────────────────────────────────────────
def build_market_pulse(output_path, d, cfg=None):
    """
    d: company, location, roles, date,
       market_temp_bullets [str x3],
       project_env_bullets [str x2],
       comp_bullets [str x3],
       timing_bullets [str x3],
       what_wins [str x4],
       cta str
    """
    doc = ArenaDoc(output_path, badge_text="ONE-PAGE MARKET PULSE",
                   logo_path=d.get("logo_path",""), company_name=d.get("prepared_by",""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Title block — avoid repeating location if it's already in the company/niche label
    _co = d.get('company', '')
    _loc = d.get('location', '')
    if _loc and _loc.lower() in _co.lower():
        title = f"60-Second Market Pulse - {_co}"
    else:
        title = f"60-Second Market Pulse - {_co} | {_loc}"
    _prep = d.get("prepared_by", "Your Company")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "One-page market pulse")

    # Market temperature
    story.extend(section_header("Market temperature"))
    for b in d.get("market_temp_bullets", []):
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # Company-relevant project environment
    company = d.get("company", "Company")
    story.extend(section_header(f"{company}-relevant project environment"))
    for b in d.get("project_env_bullets", []):
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # Compensation snapshot
    story.extend(section_header("Compensation snapshot"))
    for b in d.get("comp_bullets", []):
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # Timing reality
    story.extend(section_header("Timing reality"))
    for b in d.get("timing_bullets", []):
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # What is winning candidates right now
    story.extend(section_header("What is winning candidates right now"))
    for b in d.get("what_wins", []):
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # Want to learn more?
    if d.get("cta"):
        story.extend(section_header("Want to learn more?"))
        story.append(bullet_item(d["cta"]))

    doc.build(story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 2. MICRO SCORECARD
# ─────────────────────────────────────────────────────────────────────────
def build_scorecard(output_path, d, cfg=None):
    """
    Clean single-column scorecard matching Market Pulse layout.
    d: role, company, location, date,
       outcomes [str x3],
       competencies [str x4],
       red_flags [str x3],
       questions [str x4],
    """
    doc = ArenaDoc(output_path, badge_text="INTERVIEW ALIGNMENT TOOL",
                   logo_path=d.get("logo_path",""), company_name=d.get("prepared_by",""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Title block — matches Market Pulse style
    _co = d.get('company', ''); _loc = d.get('location', '')
    title = f"Candidate Scorecard - {d['role']} | {_co}" if _loc.lower() in _co.lower() else f"Candidate Scorecard - {d['role']} | {_co}, {_loc}"
    _prep = d.get("prepared_by", "Your Company")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Interview alignment tool")

    # What great looks like (90 days) — top 3 only
    story.extend(section_header("What great looks like in the first 90 days"))
    for b in d.get("outcomes", [])[:3]:
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # Core competencies — 4 max, one-line each
    comps = d.get("competencies", [])
    comps = [c[0] if isinstance(c, (list, tuple)) else c for c in comps][:4]
    story.extend(section_header("Core competencies to verify"))
    for b in comps:
        story.append(bullet_item(b))
    story.append(Spacer(1, 4))

    # High-signal interview questions — 4 max
    questions = d.get("questions", [])
    questions = [q[0] if isinstance(q, (list, tuple)) else q for q in questions][:4]
    story.extend(section_header("High-signal interview questions"))
    for q in questions:
        story.append(bullet_item(q))
    story.append(Spacer(1, 4))

    # Red flags — 3 max
    story.extend(section_header("Red flags"))
    for b in d.get("red_flags", [])[:3]:
        story.append(bullet_item(b))

    doc.build(story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 3. SALARY GUIDE
# ─────────────────────────────────────────────────────────────────────────

def build_salary_guide(output_path, d, cfg=None):
    """
    Clean single-column salary guide matching Market Pulse layout.
    d: role, company, location, date, prepared_by, prepared_email,
       overview str,
       roles [{ title, range_low, range_high, notes }],
       factors [str x3-4],
       trends [str x3],
       cta str
    """
    doc = ArenaDoc(output_path, badge_text="SALARY GUIDE",
                   logo_path=d.get("logo_path",""), company_name=d.get("prepared_by",""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    title = f"Salary Guide - {d.get('role', '')} | {d['location']}"
    _prep = d.get("prepared_by", "Your Company")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Compensation benchmark")

    # Market overview
    if d.get("overview"):
        story.extend(section_header("Market overview"))
        story.append(Paragraph(_clean(d["overview"]),
                     S("ov", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
                       leading=11, spaceAfter=4)))

    # Compensation by role — table
    roles = d.get("roles", [])
    if roles:
        story.extend(section_header("Compensation by role"))
        header = [
            Paragraph("<b>Role</b>", S("th", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY)),
            Paragraph("<b>Low</b>", S("th", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY)),
            Paragraph("<b>High</b>", S("th", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY)),
            Paragraph("<b>Notes</b>", S("th", fontName="Helvetica-Bold", fontSize=8, textColor=NAVY)),
        ]
        rows = [header]
        for r in roles[:5]:  # max 5 roles to fit one page
            rows.append([
                Paragraph(_clean(r.get("title", "")), S("td", fontName="Helvetica", fontSize=8, textColor=NAVY, leading=10)),
                Paragraph(_clean(r.get("range_low", "")), S("td", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE, leading=10)),
                Paragraph(_clean(r.get("range_high", "")), S("td", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE, leading=10)),
                Paragraph(_clean(r.get("notes", "")), S("td", fontName="Helvetica", fontSize=7.5, textColor=GRAY, leading=10)),
            ])
        t = alt_table(rows, [CW*0.28, CW*0.15, CW*0.15, CW*0.42])
        story.append(t)
        story.append(Spacer(1, 4))

    # What's driving comp
    if d.get("factors"):
        story.extend(section_header("What's driving compensation"))
        for b in d["factors"][:3]:
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # Trends to watch
    if d.get("trends"):
        story.extend(section_header("Trends to watch"))
        for b in d["trends"][:3]:
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # CTA
    if d.get("cta"):
        story.extend(section_header("Want the full picture?"))
        story.append(bullet_item(d["cta"]))

    doc.build(story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 4. INTERVIEW GUIDE
# ─────────────────────────────────────────────────────────────────────────

def build_interview_guide(output_path, d, cfg=None):
    """
    Clean single-column interview guide matching Market Pulse layout.
    d: role, company, location, date, prepared_by, prepared_email,
       intro str,
       must_ask [str x4-5],
       what_to_listen_for [str x3-4],
       green_flags [str x3],
       watch_outs [str x3],
       closing_questions [str x2]
    """
    doc = ArenaDoc(output_path, badge_text="INTERVIEW GUIDE",
                   logo_path=d.get("logo_path",""), company_name=d.get("prepared_by",""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    title = f"Interview Guide - {d.get('role', '')} | {d.get('company', '')}, {d['location']}"
    _prep = d.get("prepared_by", "Your Company")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Interview preparation tool")

    # Role context
    if d.get("intro"):
        story.extend(section_header("Role context"))
        story.append(Paragraph(_clean(d["intro"]),
                     S("intro", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
                       leading=11, spaceAfter=4)))

    # Must-ask questions
    if d.get("must_ask"):
        story.extend(section_header("Must-ask questions"))
        for i, q in enumerate(d["must_ask"][:4], 1):
            story.append(bullet_item(f"<b>Q{i}:</b> {q}"))
        story.append(Spacer(1, 4))

    # What to listen for
    if d.get("what_to_listen_for"):
        story.extend(section_header("What to listen for"))
        for b in d["what_to_listen_for"][:3]:
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # Green flags
    if d.get("green_flags"):
        story.extend(section_header("Green flags"))
        for b in d["green_flags"][:3]:
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # Watch-outs
    if d.get("watch_outs"):
        story.extend(section_header("Watch-outs"))
        for b in d["watch_outs"][:3]:
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # Closing questions
    if d.get("closing_questions"):
        story.extend(section_header("Strong closing questions"))
        for q in d["closing_questions"][:2]:
            story.append(bullet_item(q))

    doc.build(story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 5. BENCH SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────
def build_bench_snapshot(output_path, d, cfg=None):
    """
    d: role, company, location, date,
       intro str (1-sentence context from research),
       candidates: [
         { label:"A", title, years_exp, location, highlights[3],
           best_fit str, availability str, comp_target str }
       ]
    """
    sn, _ = get_sender(cfg)
    prepared = d.get("prepared_by") or sn

    doc = ArenaDoc(output_path, badge_text="BENCH SNAPSHOT",
                   logo_path=d.get("logo_path",""), company_name=d.get("prepared_by",""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    s_t  = S("t",  fontName="Helvetica-Bold",  fontSize=19, textColor=NAVY,  leading=23, spaceAfter=2)
    s_s  = S("s",  fontName="Helvetica",        fontSize=10, textColor=GRAY,  leading=14, spaceAfter=4)
    s_m  = S("m",  fontName="Helvetica",         fontSize=8,  textColor=SILVER,leading=11, spaceAfter=12)
    s_b  = S("b",  fontName="Helvetica",          fontSize=9,  textColor=NAVY,  leading=13, spaceAfter=3)
    s_l  = S("l",  fontName="Helvetica-Bold",     fontSize=8,  textColor=BLUE,  leading=11, spaceAfter=2)
    s_cl = S("cl", fontName="Helvetica-Bold",     fontSize=12, textColor=NAVY,  leading=15, spaceAfter=2)
    s_ct = S("ct", fontName="Helvetica-Bold",     fontSize=10, textColor=BLUE,  leading=13, spaceAfter=1)

    story = []
    story.append(Paragraph("Redacted Bench Snapshot", s_t))
    story.append(Paragraph(f"{d['role']}  \u00b7  {d['location']}", s_s))
    _email = d.get("prepared_email", "")
    _prep_line = f"Prepared by {prepared}" + (f"  \u00b7  {_email}" if _email else "") + f"  \u00b7  {d['date']}"
    story.append(Paragraph(_prep_line, s_m))
    story.append(div(4,6))

    if d.get("intro"):
        story.append(Paragraph(d["intro"], S("intro",fontName="Helvetica-Oblique",
                                              fontSize=9,textColor=GRAY,leading=13,spaceAfter=10)))
    story.append(Paragraph(
        "All candidates are redacted. Reply to request full profiles.",
        S("disc",fontName="Helvetica",fontSize=8,textColor=SILVER,leading=11,spaceAfter=12)))

    cand_colors = [BLUE, ORANGE]

    for idx, c in enumerate(d.get("candidates",[])):
        cc = cand_colors[idx % len(cand_colors)]
        hx = cc.hexval()[2:]

        # Header band with candidate label
        hdr = Table([[
            Paragraph(f"<b>CANDIDATE {c.get('label','?')}</b>",
                      S("ch",fontName="Helvetica-Bold",fontSize=11,
                        textColor=WHITE,leading=14)),
            Paragraph(c.get("title",""), S("ctt",fontName="Helvetica",
                                            fontSize=11,textColor=WHITE,leading=14,
                                            alignment=TA_RIGHT)),
        ]], colWidths=[CW*0.5, CW*0.5])
        hdr.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),cc),
            ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
            ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ]))
        story.append(hdr)

        # Key metrics row
        meta_items = [
            ("Experience", c.get("years_exp","\u2014")),
            ("Location",   c.get("location","\u2014")),
            ("Available",  c.get("availability","\u2014")),
            ("Target Comp",c.get("comp_target","\u2014")),
        ]
        mcols = [CW/4]*4
        meta_tbl = Table([[
            Paragraph(f"<font size='7' color='#686861'>{label}</font><br/>"
                      f"<b>{val}</b>",
                      S("mv2",fontName="Helvetica",fontSize=10,textColor=NAVY,
                        leading=14,alignment=TA_CENTER))
            for label, val in meta_items
        ]], colWidths=mcols)
        meta_tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),LIGHT),
            ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LINEAFTER",(0,0),(-2,-1),0.5,SILVER),
        ]))
        story.append(meta_tbl)

        # Highlights
        hi_rows = []
        for h in c.get("highlights",[]):
            hi_rows.append([Paragraph(
                f'<font color="#{hx}"><b>\u25b8</b></font>  {h}',
                S("hi",fontName="Helvetica",fontSize=9,textColor=NAVY,
                  leading=13,leftIndent=12,firstLineIndent=-12)
            )])
        hi_t = Table(hi_rows, colWidths=[CW])
        hi_t.setStyle(TableStyle([
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[WHITE,LIGHT]),
        ]))
        story.append(hi_t)

        # Best fit note
        best_tbl = Table([[
            Paragraph("Best Fit For:",
                      S("bfl",fontName="Helvetica-Bold",fontSize=8,
                        textColor=cc,leading=11)),
            Paragraph(c.get("best_fit",""),
                      S("bfv",fontName="Helvetica",fontSize=9,
                        textColor=NAVY,leading=13)),
        ]], colWidths=[0.85*inch, CW-0.85*inch])
        best_tbl.setStyle(TableStyle([
            ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
            ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#0d1e33")),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ]))
        story.append(best_tbl)
        story.append(Spacer(1, 14 if idx < len(d.get("candidates",[]))-1 else 10))

    # CTA footer box
    cta_tbl = Table([[Paragraph(
        "Interested in either profile? Reply with the letter or request full details. "
        "Full resumes and references available within 24 hours.",
        S("cta",fontName="Helvetica",fontSize=9,textColor=NAVY,leading=14)
    )]], colWidths=[CW])
    cta_tbl.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),LIGHT),
        ("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14),
        ("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10),
        ("BOX",(0,0),(-1,-1),1.5,ORANGE),
    ]))
    story.append(div(6,6))
    story.append(cta_tbl)

    doc.build(story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 4. TENURE SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────
def build_tenure_snapshot(output_path, d, cfg=None):
    """
    d: company, location, roles, date,
       market_context str (opening paragraph),
       tenure_rows [[role, market, talent_pool, median_tenure, hiring_demand] x N],
       what_means [str x3],
       stability_screen [str x4],
       recommendation str (italic paragraph)
    """
    doc = ArenaDoc(output_path, badge_text="CLIENT-FACING MARKET INSIGHT",
                   logo_path=d.get("logo_path",""), company_name=d.get("prepared_by",""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    s_b = S("b", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
            leading=11, spaceAfter=2)
    s_l = S("l", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE,
            leading=11, spaceAfter=2)

    story = []

    # Title block
    _co = d.get('company', ''); _loc = d.get('location', '')
    title = f"{_loc} Tenure + Stability Snapshot" if _loc.lower() in _co.lower() else f"{_loc} Tenure + Stability Snapshot for {_co}-Style Hires"
    _prep = d.get("prepared_by", "Your Company")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Client-facing market insight")

    # Opening paragraph (market_context)
    if d.get("market_context"):
        story.append(Paragraph(_clean(d["market_context"]), s_b))
        story.append(Spacer(1, 4))

    # Data table
    if d.get("tenure_rows"):
        story.extend(section_header("Tenure data"))
        # Header row
        hdr_style = S("th", fontName="Helvetica-Bold", fontSize=8,
                       textColor=NAVY, leading=11)
        th = [
            Paragraph("<b>Role</b>", hdr_style),
            Paragraph("<b>Market</b>", hdr_style),
            Paragraph("<b>Talent Pool</b>", hdr_style),
            Paragraph("<b>Median Tenure</b>", hdr_style),
            Paragraph("<b>Hiring Demand</b>", hdr_style),
        ]
        rows = [th]
        for row in d.get("tenure_rows", []):
            rows.append([
                Paragraph(_clean(str(row[0])), s_b),
                Paragraph(_clean(str(row[1])), s_b),
                Paragraph(_clean(str(row[2])), s_b),
                Paragraph(_clean(str(row[3])), s_b),
                Paragraph(_clean(str(row[4])), s_b),
            ])
        col_w = CW / 5
        story.append(alt_table(rows, [col_w]*5))
        story.append(Spacer(1, 4))

    # What this means
    if d.get("what_means"):
        story.extend(section_header("What this means"))
        for b in d.get("what_means", []):
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # Market-aligned stability screen
    if d.get("stability_screen"):
        story.extend(section_header("Market-aligned stability screen"))
        for b in d.get("stability_screen", []):
            story.append(bullet_item(b))
        story.append(Spacer(1, 4))

    # Suggested client language
    if d.get("recommendation"):
        story.extend(section_header("Suggested client language"))
        story.append(Paragraph(
            f"<i>{_clean(d['recommendation'])}</i>",
            S("rec", fontName="Helvetica-Oblique", fontSize=8.5,
              textColor=GRAY, leading=11, spaceAfter=2)))

    doc.build(story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# TEST — build all four with sample data
# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    out = os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(out, exist_ok=True)

    # 1. Market Pulse
    build_market_pulse(f"{out}/test_market_pulse.pdf", {
        "company": "Pacific Building Group",
        "location": "San Diego, CA",
        "roles": "Project Managers + Superintendents",
        "date": "March 18, 2026",
        "market_temp_bullets": [
            "San Diego commercial construction hiring is candidate-driven with 2.3 qualified candidates per open Superintendent role",
            "Healthcare TI and data center pipelines are absorbing senior field leaders faster than firms can backfill",
            "Counter-offer rates have climbed to 38% in Q1 2026, up from 24% a year ago",
        ],
        "project_env_bullets": [
            "PBG's healthcare TI pipeline aligns with the highest-demand segment — expect direct competition from Scripps, Sharp, and UCSD project teams",
            "Commercial GCs in the $15M-$50M project range are losing Superintendents to larger firms offering project continuity guarantees",
        ],
        "comp_bullets": [
            "Superintendents with healthcare TI experience command $120K-$145K base in San Diego, up 8% year-over-year",
            "Senior Superintendents with 10+ years and occupied facility experience are landing $150K-$175K with signing bonuses now standard",
            "Truck allowances and project bonuses have become table stakes — candidates expect them, not treat them as differentiators",
        ],
        "timing_bullets": [
            "Two-week notice periods are now standard; three-week processes lose 60% of finalists to faster-moving competitors",
            "Counter-offers are arriving within 48 hours of resignation — have a retention plan ready before extending",
            "First conversations matter more than final offers: candidates form their top-two list after the initial phone screen",
        ],
        "what_wins": [
            "Speed to first interview — candidates rank this above comp in exit surveys",
            "Named project assignments communicated before the offer, not after",
            "A defined 90-day onboarding plan that signals organizational maturity",
            "Decision-makers in the interview — candidates disengage when they sense layers of approval",
        ],
        "cta": "Reply to this email and I'll send two anonymized Superintendent profiles matched to your current project pipeline within 24 hours.",
    })
    print("OK Market Pulse")

    # 2. Scorecard
    build_scorecard(f"{out}/test_scorecard.pdf", {
        "role": "Superintendent",
        "company": "Pacific Building Group",
        "location": "San Diego, CA",
        "date": "March 18, 2026",
        "outcomes": [
            "Delivers commercial TI and healthcare projects on schedule with zero rework loops",
            "Maintains subcontractor relationships that bring subs back to the next bid",
            "Catches scope gaps before they reach the owner as change orders",
            "Runs a clean daily log that holds the full schedule narrative",
            "Transitions between projects without a pipeline gap",
        ],
        "competencies": [
            "Field execution and trade coordination",
            "CPM schedule management and float analysis",
            "Safety leadership and OSHA compliance",
            "Subcontractor sourcing and accountability",
            "Client presence on walkthroughs and OAC calls",
        ],
        "fit_markers": [
            "Led healthcare or commercial TI projects over $10M from permit to punch",
            "5+ years as a Superintendent at a GC, not CM or owner-side",
            "Occupied facility experience with infection control protocols",
            "Can describe a specific schedule recovery they engineered in the field",
        ],
        "red_flags": [
            "No GC experience — owner-side or sub-only background",
            "Cannot name last three projects without notes or prompting",
            "Two or more roles under 18 months with vague explanations",
            "No answer to 'When did you catch a scope gap before it became a CO?'",
        ],
        "questions": [
            "Walk me through a project where the schedule was off and you recovered it without a change order.",
            "How do you manage your daily log and RFI flow on a live occupied project?",
            "Tell me about your hardest subcontractor relationship and how you fixed it.",
            "What does a good OAC meeting look like from your side?",
            "PM and owner are aligned on something wrong in the field. What do you do?",
            "How do you onboard a new trade to site on day one?",
        ],
        "scoring_guide": [
            "5 = Specific, verifiable, detailed — names trades, durations, outcomes",
            "3 = Generally competent answer but lacks concrete specifics",
            "1 = Vague, concerning, or no relevant experience demonstrated",
        ],
    })
    print("OK Scorecard")

    # 3. Bench Snapshot (unchanged data)
    build_bench_snapshot(f"{out}/test_bench_snapshot.pdf", {
        "role": "Superintendent",
        "company": "Pacific Building Group",
        "location": "San Diego, CA",
        "date": "March 19, 2026",
        "prepared_by": "Stacey Carroll",
        "intro": (
            "Both profiles are actively exploring based on project pipeline and "
            "growth trajectory — not comp-driven moves. Matched to PBG's healthcare "
            "TI and commercial delivery environment."
        ),
        "candidates": [
            {
                "label": "A",
                "title": "Senior Superintendent — Healthcare & TI",
                "years_exp": "14 years GC experience",
                "location": "San Diego, CA",
                "availability": "Available 30 days",
                "comp_target": "$140K-$155K base",
                "highlights": [
                    "Led $28M occupied hospital TI at Scripps — delivered 6 days ahead of schedule",
                    "Managed 18-trade coordination on live patient floor without a single ICRA violation",
                    "Built a sub roster of 12 preferred trades across SoCal; 9 follow him to new GCs",
                    "Zero OSHA recordables across last four projects spanning 7 years",
                ],
                "best_fit": "Healthcare TI, occupied facilities, multi-trade coordination",
            },
            {
                "label": "B",
                "title": "Superintendent — Commercial TI & Industrial",
                "years_exp": "9 years GC experience",
                "location": "Chula Vista, CA (open to SD)",
                "availability": "Available 45 days",
                "comp_target": "$120K-$135K base",
                "highlights": [
                    "Ran $15M commercial TI portfolio simultaneously — three concurrent projects, all delivered on time",
                    "Strong CPM schedule management; recovered a 3-week float burn without CO",
                    "Promoted from APM to Super in 4 years — fastest in firm history",
                    "Bilingual (English/Spanish) — significant advantage with SoCal sub base",
                ],
                "best_fit": "Commercial TI, multi-project management, high-output mid-tier builds",
            },
        ],
    })
    print("OK Bench Snapshot")

    # 4. Tenure Snapshot
    build_tenure_snapshot(f"{out}/test_tenure_snapshot.pdf", {
        "company": "Pacific Building Group",
        "location": "San Diego, CA",
        "roles": "Project Managers + Superintendents",
        "date": "March 18, 2026",
        "market_context": (
            "The commercial construction market in San Diego has shifted materially since 2020. "
            "Project complexity, compressed timelines, and post-COVID ownership changes have "
            "accelerated career movement across the Superintendent pool. The result: average tenure "
            "at a single GC has dropped from 6.2 years (2019) to 3.8 years (2025). "
            "Filtering for 5+ years at one company now disqualifies approximately 67% of the "
            "qualified candidate pool in this market."
        ),
        "tenure_rows": [
            ["Superintendent",      "San Diego",    "~320 active",  "3.4 yrs", "High"],
            ["Sr. Superintendent",  "San Diego",    "~140 active",  "4.1 yrs", "Very High"],
            ["Project Manager",     "San Diego",    "~280 active",  "3.1 yrs", "Moderate"],
            ["Sr. Project Manager", "San Diego",    "~110 active",  "4.6 yrs", "High"],
        ],
        "what_means": [
            "A 5-year tenure filter eliminates roughly 67% of the qualified Superintendent pool in San Diego",
            "The most active and available candidates sit in the 2-4 year tenure band — not because of instability, but because of project-cycle-driven moves",
            "Firms enforcing rigid tenure screens are consistently losing searches to competitors with more flexible criteria",
        ],
        "stability_screen": [
            "Replace tenure minimums with project completion verification — did they finish what they started?",
            "Ask for references from the last two direct supervisors, regardless of how long the tenure was",
            "Weight consistency of project scale and complexity over years-at-one-firm",
            "Use our Superintendent scorecard to evaluate readiness rather than filtering on resume tenure alone",
        ],
        "recommendation": (
            "We recommend adjusting the tenure filter from 5 years to 3 years for this search, "
            "while adding two targeted interview questions about reasons for transition and "
            "project completion context. This expands the qualified pool from approximately "
            "22% to 64% of active candidates in the San Diego market without increasing "
            "quality risk."
        ),
    })
    print("OK Tenure Snapshot")
    print("\nAll four PDFs built successfully.")
