"""
arena_pdfs.py
Builds all four Arena Direct Hire PDF attachments:
  1. Market Pulse
  2. Micro Scorecard
  3. Bench Snapshot
  4. Tenure Snapshot

All use text-based ARENA wordmark — no image dependency.
Colors: #122742 navy · #2C65AC blue · #F77331 orange
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
    KeepInFrame,
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
    name = c.get("ai_sender_name") or c.get("username", "").split(".")[0].capitalize()
    firm = c.get("ai_sender_firm") or c.get("company", "Arena Direct Hire")
    return name or "Arena Direct Hire", firm or "Arena Direct Hire"

# ── Base document ──────────────────────────────────────────────────────────
def _text_logo_fallback(canv, H, BAR_H, NAVY, ORANGE, WHITE, SILVER):
    canv.setFillColor(WHITE)
    canv.setFont("Helvetica-Bold", 17)
    canv.drawString(0.60*inch, H - BAR_H*0.45, "ARENA")
    canv.setFillColor(ORANGE)
    canv.setFont("Helvetica-Bold", 7)
    canv.drawString(0.60*inch, H - BAR_H*0.65, "DIRECT HIRE")

class ArenaDoc(BaseDocTemplate):
    def __init__(self, filename, badge_text="DOCUMENT", prepared_by="", prepared_email="", **kw):
        self.badge_text = badge_text
        self.prepared_by = prepared_by or ""
        self.prepared_email = prepared_email or ""
        super().__init__(filename, **kw)
        # Frame: content starts below logo area, ends above footer
        frame = Frame(0.55*inch, 0.60*inch,
                      W - 1.1*inch, H - 1.60*inch, id="main")
        self.addPageTemplates([
            PageTemplate(id="arena", frames=[frame], onPage=self._chrome)
        ])

    def _chrome(self, canv, doc):
        canv.saveState()

        # Logo — white background, top-left (no navy bar, no orange)
        import os as _os
        _here = _os.path.dirname(_os.path.abspath(__file__))
        _candidates = [
            _os.path.join(_here, "..", "assets", "arena_logo.png"),
            _os.path.join(_here, "..", "arena_logo.png"),
            _os.path.join(_here, "arena_logo.png"),
        ]
        LOGO = next((p for p in _candidates if _os.path.isfile(p)), "")
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
                canv.drawString(0.55*inch, H - 0.75*inch, "ARENA")
                canv.setFillColor(BLUE)
                canv.setFont("Helvetica-Bold", 8)
                canv.drawString(0.55*inch, H - 0.92*inch, "DIRECT HIRE")
        else:
            canv.setFillColor(NAVY)
            canv.setFont("Helvetica-Bold", 20)
            canv.drawString(0.55*inch, H - 0.75*inch, "ARENA")
            canv.setFillColor(BLUE)
            canv.setFont("Helvetica-Bold", 8)
            canv.drawString(0.55*inch, H - 0.92*inch, "DIRECT HIRE")

        # Footer — Arena Direct Hire | {recruiter name} | {recruiter email}
        canv.setFillColor(SILVER)
        canv.setFont("Helvetica", 7)
        _parts = ["Arena Direct Hire"]
        if getattr(self, "prepared_by", ""):
            _parts.append(self.prepared_by)
        if getattr(self, "prepared_email", ""):
            _parts.append(self.prepared_email)
        canv.drawCentredString(W/2, 0.30*inch, " | ".join(_parts))

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
    """Blue bold section header with thin gray line underneath.
    Font bumped +2 2026-05-02 per user readability request."""
    return [
        Paragraph(f"<b>{_clean(text)}</b>",
                  S("sh", fontName="Helvetica-Bold", fontSize=13,
                    textColor=BLUE, leading=16, spaceAfter=1)),
        HRFlowable(width="100%", thickness=0.5, color=SILVER,
                   spaceBefore=0, spaceAfter=4),
    ]

def bullet_item(text):
    """Standard bullet point with bullet prefix.
    Font bumped +2 2026-05-02 per user readability request."""
    return Paragraph(
        f'<font color="#2C65AC"><b>\u2022</b></font>  {_clean(text)}',
        S("bp", fontName="Helvetica", fontSize=10.5, textColor=NAVY,
          leading=13, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

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


def _build_one_page(doc, story, top_margin_inches=1.15, bottom_margin_inches=0.65):
    """Build a PDF, letting ReportLab paginate naturally if content
    overflows a single page (2026-05-02 user request: "allow it to
    be 2 pages if it needs to be"). Previously wrapped in
    KeepInFrame(mode='shrink') which scaled content down to force
    one page — that was causing tiny, hard-to-read text on dense
    PDFs. Function name kept for callsite stability across all 7
    builders (build_market_pulse, build_salary_guide, etc.)."""
    doc.build(story)


def _title_block(story, title, subtitle, badge_label):
    """Shared title block: large navy title, italic gray subtitle, blue
    badge tag. Body font sizes bumped +2 2026-05-02 per user request
    for better readability on the recruiting PDFs (titles already
    large enough to leave alone)."""
    story.append(Paragraph(_clean(title),
                           S("t", fontName="Helvetica-Bold", fontSize=16,
                             textColor=NAVY, leading=19, spaceAfter=2)))
    story.append(Paragraph(f"<i>{_clean(subtitle)}</i>",
                           S("s", fontName="Helvetica-Oblique", fontSize=11,
                             textColor=GRAY, leading=14, spaceAfter=4)))
    story.append(Paragraph(
        f'<font color="#2C65AC"><b>{_clean(badge_label)}</b></font>',
        S("badge", fontName="Helvetica-Bold", fontSize=9,
          textColor=BLUE, leading=12, spaceAfter=1)))
    story.append(Spacer(1, 6))


# ─────────────────────────────────────────────────────────────────────────
# 1. MARKET PULSE
# ─────────────────────────────────────────────────────────────────────────
def build_market_pulse(output_path, d, cfg=None):
    """
    Redesigned Market Pulse - scannable in 15 seconds.
    d: company, location, role, date,
       stat_comp str, stat_ttf str, stat_supply str,
       market_temp_bullets [str x3],
       comp_bullets [str x3],
       timing_bullets [str x3],
       what_wins [str x3],
       cta str
    """
    doc = ArenaDoc(output_path, badge_text="MARKET PULSE",
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Title - Market/Niche + Location, always both when available.
    # Pulls directly from what the user typed in the Campaign Builder's
    # Target Details panel (Market/Niche and Location fields).
    _niche = d.get('niche', '') or d.get('industry', '')
    _loc = d.get('location', '')
    _role = d.get('role', '')
    _label = _niche or _role  # fall back to role only if no niche/industry
    if _label and _loc:
        title = f"{_label} — {_loc}"
    elif _label:
        title = _label
    elif _loc:
        title = f"{_loc} Market"
    else:
        title = "Market Pulse"
    _prep = d.get("prepared_by", "Arena Direct Hire")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Market pulse")

    # 3 stat boxes in a row
    _stat_comp = _clean(str(d.get("stat_comp", "")))
    _stat_ttf = _clean(str(d.get("stat_ttf", "")))
    _stat_supply = _clean(str(d.get("stat_supply", "")))
    # Build from legacy fields if new stat fields aren't provided
    # Treat generic placeholder values ("Market Rate", "Varies", etc.) the
    # same as empty so we fall through to the bullet-extraction path and
    # give the PDF a concrete number whenever the bullets have one.
    if _stat_comp.lower().strip() in ("market rate", "market", "competitive",
                                       "varies", "tbd", "n/a", "na", "see below"):
        _stat_comp = ""
    if not _stat_comp:
        # Try to extract a dollar amount from comp bullets. Accept ranges
        # written with one OR two dollar signs ("$85K-$110K" and "$85K-110K"),
        # hourly ranges ("$42-$58/hr"), and single values ("$95K").
        import re as _re
        _cb = d.get("comp_bullets", [])
        _found = ""
        for _b in _cb:
            _bs = str(_b)
            _m = _re.search(r'\$\s*[\d,]+\s*[Kk]?\s*[-–to]+\s*\$?\s*[\d,]+\s*[Kk]?(?:\s*/\s*hr)?', _bs)
            if _m: _found = _m.group(); break
            _m = _re.search(r'\$\s*[\d,]+\s*[Kk]?(?:\s*/\s*hr)?', _bs)
            if _m: _found = _m.group(); break
        # Only fall through to a generic label if bullets gave us nothing.
        _stat_comp = (_found or "See comp below").replace(" ", "")
    if not _stat_ttf:
        import re as _re
        _tb = d.get("timing_bullets", [])
        _found = ""
        for _b in _tb:
            _m = _re.search(r'(\d+[-\s]*\d*)\s*days?', str(_b), _re.IGNORECASE)
            if _m: _found = _m.group(); break
        _stat_ttf = _found or "30-45 Days"
    if not _stat_supply:
        _stat_supply = "Moderate"
    # Cap stat values to keep boxes clean
    _stat_comp = _stat_comp[:20]
    _stat_ttf = _stat_ttf[:20]
    _stat_supply = _stat_supply[:15]

    _stat_size = 12 if max(len(_stat_comp), len(_stat_ttf), len(_stat_supply)) > 12 else 14
    _stat_style = S("stat_val", fontName="Helvetica-Bold", fontSize=_stat_size,
                     textColor=BLUE, alignment=TA_CENTER, leading=_stat_size+2, spaceAfter=0)
    _stat_label = S("stat_lbl", fontName="Helvetica", fontSize=7,
                     textColor=GRAY, alignment=TA_CENTER, leading=9, spaceAfter=0)
    _stat_cells = [
        [Paragraph(f"<b>{_stat_comp}</b>", _stat_style),
         Paragraph(f"<b>{_stat_ttf}</b>", _stat_style),
         Paragraph(f"<b>{_stat_supply}</b>", _stat_style)],
        [Paragraph("Comp Range", _stat_label),
         Paragraph("Time to Fill", _stat_label),
         Paragraph("Talent Supply", _stat_label)],
    ]
    _stat_w = CW / 3
    _stat_table = Table(_stat_cells, colWidths=[_stat_w, _stat_w, _stat_w])
    _stat_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT),
        ("BOX", (0,0), (-1,-1), 0.5, SILVER),
        ("LINEAFTER", (0,0), (-2,-1), 0.5, SILVER),
        ("TOPPADDING", (0,0), (-1,0), 8),
        ("BOTTOMPADDING", (0,0), (-1,0), 2),
        ("TOPPADDING", (0,1), (-1,1), 0),
        ("BOTTOMPADDING", (0,1), (-1,1), 8),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(_stat_table)
    story.append(Spacer(1, 8))

    # Accent bullet - colored left border for visual hierarchy
    def _accent_bullet(text, accent=BLUE):
        return Paragraph(
            f'<font color="#{accent.hexval()[2:]}"><b>-</b></font>  {_clean(text)}',
            S("ab", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
              leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

    # Section 1: What You Need to Know
    _know = d.get("market_temp_bullets", [])[:3]
    if _know:
        story.extend(section_header("What you need to know"))
        for b in _know:
            story.append(_accent_bullet(b))
        story.append(Spacer(1, 4))

    # Section 2: What You Need to Pay
    _pay = d.get("comp_bullets", [])[:3]
    if _pay:
        story.extend(section_header("What you need to pay"))
        for b in _pay:
            story.append(_accent_bullet(b, BLUE))
        story.append(Spacer(1, 4))

    # Section 3: How Fast You Need to Move
    _speed = d.get("timing_bullets", [])[:3]
    if _speed:
        story.extend(section_header("How fast you need to move"))
        for b in _speed:
            story.append(_accent_bullet(b, ORANGE))
        story.append(Spacer(1, 4))

    # Section 4: What Closes Candidates
    _wins = d.get("what_wins", [])[:3]
    if _wins:
        story.extend(section_header("What closes candidates"))
        for b in _wins:
            story.append(_accent_bullet(b, GREEN))
        story.append(Spacer(1, 4))

    # CTA - one line, no section header
    if d.get("cta"):
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=0.5, color=SILVER,
                                spaceBefore=0, spaceAfter=6))
        story.append(Paragraph(
            f'<font color="#2C65AC"><b>{_clean(d["cta"])}</b></font>',
            S("cta", fontName="Helvetica", fontSize=8.5, textColor=BLUE,
              leading=11, spaceAfter=0)))

    _build_one_page(doc, story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 2. MICRO SCORECARD
# ─────────────────────────────────────────────────────────────────────────
def build_scorecard(output_path, d, cfg=None):
    """
    Role Scorecard - helps hiring managers define what great looks like.
    """
    doc = ArenaDoc(output_path, badge_text="ROLE SCORECARD",
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Market-focused title
    _niche = d.get('niche', '') or d.get('industry', '')
    _loc = d.get('location', ''); _role = d.get('role', '')
    _label = _niche or _role
    title = f"{_loc} {_label}" if _loc and _label else (_label or "Role Scorecard")
    _prep = d.get("prepared_by", "Arena Direct Hire")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Role scorecard")

    # Accent bullet helper
    def _ab(text, accent=BLUE):
        return Paragraph(
            f'<font color="#{accent.hexval()[2:]}"><b>-</b></font>  {_clean(text)}',
            S("ab", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
              leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

    # 90-day outcomes
    story.extend(section_header("What great looks like in 90 days"))
    for b in d.get("outcomes", [])[:3]:
        story.append(_ab(b, GREEN))
    story.append(Spacer(1, 4))

    # Core competencies
    comps = d.get("competencies", [])
    comps = [c[0] if isinstance(c, (list, tuple)) else c for c in comps][:4]
    story.extend(section_header("Must-have competencies"))
    for b in comps:
        story.append(_ab(b, BLUE))
    story.append(Spacer(1, 4))

    # Interview questions
    questions = d.get("questions", [])
    questions = [q[0] if isinstance(q, (list, tuple)) else q for q in questions][:4]
    story.extend(section_header("Questions that reveal the truth"))
    for q in questions:
        story.append(_ab(q, ORANGE))
    story.append(Spacer(1, 4))

    # Red flags
    story.extend(section_header("Red flags to watch for"))
    for b in d.get("red_flags", [])[:3]:
        story.append(_ab(b, RED))

    _build_one_page(doc, story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 3. SALARY GUIDE
# ─────────────────────────────────────────────────────────────────────────

def build_salary_guide(output_path, d, cfg=None):
    """
    Salary Guide - comp ranges at a glance for hiring managers.
    """
    doc = ArenaDoc(output_path, badge_text="SALARY GUIDE",
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Market-focused title
    _niche = d.get('niche', '') or d.get('industry', '')
    _loc = d.get('location', ''); _role = d.get('role', '')
    _label = _niche or _role
    title = f"{_loc} {_label} Compensation" if _loc and _label else f"Salary Guide - {_label}"
    _prep = d.get("prepared_by", "Arena Direct Hire")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Salary guide")

    # Comp table - the star of this PDF
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
        for r in roles[:5]:
            rows.append([
                Paragraph(_clean(r.get("title", "")), S("td", fontName="Helvetica", fontSize=8, textColor=NAVY, leading=10)),
                Paragraph(_clean(r.get("range_low", "")), S("td", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE, leading=10)),
                Paragraph(_clean(r.get("range_high", "")), S("td", fontName="Helvetica-Bold", fontSize=8, textColor=BLUE, leading=10)),
                Paragraph(_clean(r.get("notes", "")), S("td", fontName="Helvetica", fontSize=7.5, textColor=GRAY, leading=10)),
            ])
        t = alt_table(rows, [CW*0.28, CW*0.15, CW*0.15, CW*0.42])
        story.append(t)
        story.append(Spacer(1, 6))

    # Accent bullet helper
    def _ab(text, accent=BLUE):
        return Paragraph(
            f'<font color="#{accent.hexval()[2:]}"><b>-</b></font>  {_clean(text)}',
            S("ab", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
              leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

    # What's driving comp
    if d.get("factors"):
        story.extend(section_header("What is driving comp"))
        for b in d["factors"][:3]:
            story.append(_ab(b, ORANGE))
        story.append(Spacer(1, 4))

    # Trends
    if d.get("trends"):
        story.extend(section_header("Trends to watch"))
        for b in d["trends"][:3]:
            story.append(_ab(b, GREEN))
        story.append(Spacer(1, 4))

    # CTA
    if d.get("cta"):
        story.append(HRFlowable(width="100%", thickness=0.5, color=SILVER,
                                spaceBefore=4, spaceAfter=6))
        story.append(Paragraph(
            f'<font color="#2C65AC"><b>{_clean(d["cta"])}</b></font>',
            S("cta", fontName="Helvetica", fontSize=8.5, textColor=BLUE,
              leading=11, spaceAfter=0)))

    _build_one_page(doc, story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 4. INTERVIEW GUIDE
# ─────────────────────────────────────────────────────────────────────────

def build_interview_guide(output_path, d, cfg=None):
    """
    Interview Guide - ready-to-use framework for hiring managers.
    """
    doc = ArenaDoc(output_path, badge_text="INTERVIEW GUIDE",
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Market-focused title
    _niche = d.get('niche', '') or d.get('industry', '')
    _loc = d.get('location', ''); _role = d.get('role', '')
    _label = _niche or _role
    title = f"{_loc} {_label} Interview Guide" if _loc and _label else f"Interview Guide - {_label}"
    _prep = d.get("prepared_by", "Arena Direct Hire")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Interview guide")

    # Accent bullet helper
    def _ab(text, accent=BLUE):
        return Paragraph(
            f'<font color="#{accent.hexval()[2:]}"><b>-</b></font>  {_clean(text)}',
            S("ab", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
              leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

    # Must-ask questions
    if d.get("must_ask"):
        story.extend(section_header("Questions to ask"))
        for q in d["must_ask"][:4]:
            story.append(_ab(q, BLUE))
        story.append(Spacer(1, 4))

    # What strong answers sound like
    if d.get("what_to_listen_for"):
        story.extend(section_header("What strong answers sound like"))
        for b in d["what_to_listen_for"][:3]:
            story.append(_ab(b, GREEN))
        story.append(Spacer(1, 4))

    # Green flags
    if d.get("green_flags"):
        story.extend(section_header("Green flags"))
        for b in d["green_flags"][:3]:
            story.append(_ab(b, GREEN))
        story.append(Spacer(1, 4))

    # Red flags
    if d.get("watch_outs"):
        story.extend(section_header("Red flags"))
        for b in d["watch_outs"][:3]:
            story.append(_ab(b, RED))
        story.append(Spacer(1, 4))

    # Closing questions
    if d.get("closing_questions"):
        story.extend(section_header("Strong closing questions"))
        for q in d["closing_questions"][:2]:
            story.append(_ab(q, ORANGE))

    _build_one_page(doc, story)
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
                   prepared_by=d.get("prepared_by", "") or prepared,
                   prepared_email=d.get("prepared_email", ""),
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

    _build_one_page(doc, story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 4. TENURE SNAPSHOT
# ─────────────────────────────────────────────────────────────────────────
def build_tenure_snapshot(output_path, d, cfg=None):
    """
    Tenure Snapshot - why hard tenure cutoffs shrink the talent pool.
    """
    doc = ArenaDoc(output_path, badge_text="TENURE SNAPSHOT",
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Market-focused title
    _niche = d.get('niche', '') or d.get('industry', '')
    _loc = d.get('location', ''); _role = d.get('role', '')
    _label = _niche or _role
    title = f"{_loc} {_label} Tenure + Stability" if _loc and _label else (f"{_loc} Tenure + Stability" if _loc else "Tenure + Stability Snapshot")
    _prep = d.get("prepared_by", "Arena Direct Hire")
    _email = d.get("prepared_email", "")
    subtitle = f"Prepared by {_prep}" + (f" | {_email}" if _email else "") + f" | {d.get('date', '')}"
    _title_block(story, title, subtitle, "Tenure snapshot")

    # Accent bullet helper
    def _ab(text, accent=BLUE):
        return Paragraph(
            f'<font color="#{accent.hexval()[2:]}"><b>-</b></font>  {_clean(text)}',
            S("ab", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
              leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

    s_b = S("b", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
            leading=11, spaceAfter=2)

    # Data table
    if d.get("tenure_rows"):
        story.extend(section_header("Tenure data by role"))
        hdr_style = S("th", fontName="Helvetica-Bold", fontSize=8,
                       textColor=NAVY, leading=11)
        th = [
            Paragraph("<b>Role</b>", hdr_style),
            Paragraph("<b>Market</b>", hdr_style),
            Paragraph("<b>Pool</b>", hdr_style),
            Paragraph("<b>Median Tenure</b>", hdr_style),
            Paragraph("<b>Demand</b>", hdr_style),
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
        story.append(Spacer(1, 6))

    # What this means
    if d.get("what_means"):
        story.extend(section_header("What this means for your hiring"))
        for b in d.get("what_means", [])[:3]:
            story.append(_ab(b, BLUE))
        story.append(Spacer(1, 4))

    # How to screen for stability
    if d.get("stability_screen"):
        story.extend(section_header("How to screen for stability"))
        for b in d.get("stability_screen", [])[:3]:
            story.append(_ab(b, GREEN))
        story.append(Spacer(1, 4))

    # Bottom line
    if d.get("recommendation"):
        story.append(HRFlowable(width="100%", thickness=0.5, color=SILVER,
                                spaceBefore=4, spaceAfter=6))
        story.append(Paragraph(
            f'<font color="#2C65AC"><b>{_clean(d["recommendation"])}</b></font>',
            S("rec", fontName="Helvetica", fontSize=8.5, textColor=BLUE,
              leading=11, spaceAfter=0)))

    _build_one_page(doc, story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 5. WHY USE A STAFFING FIRM — client-facing value pitch
# ─────────────────────────────────────────────────────────────────────────
def build_why_staffing(output_path, d, cfg=None):
    """
    Why Use [Your Company] - personalized value pitch for hiring managers.
    """
    doc = ArenaDoc(output_path, badge_text="WHY WORK WITH US",
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Title uses the user's company name, not generic "staffing firm"
    _prep_company = d.get("prepared_by", "Arena Direct Hire")
    _role = d.get('role', '')
    _loc = d.get('location', '')
    title = f"Why Use {_prep_company}"
    _email = d.get("prepared_email", "")
    subtitle = f"{_email}" + (f" | {d.get('date', '')}" if d.get('date') else "")
    _title_block(story, title, subtitle, f"Your hiring partner for {_role} in {_loc}" if _role and _loc else "Your hiring partner")

    # Accent bullet helper
    def _ab(text, accent=BLUE):
        return Paragraph(
            f'<font color="#{accent.hexval()[2:]}"><b>-</b></font>  {_clean(text)}',
            S("ab", fontName="Helvetica", fontSize=8.5, textColor=NAVY,
              leading=11, spaceAfter=2, leftIndent=12, firstLineIndent=-12))

    # The real cost of hiring in-house
    story.extend(section_header("The real cost of hiring in-house"))
    for b in d.get("hidden_costs", [])[:3]:
        story.append(_ab(b, RED))
    story.append(Spacer(1, 4))

    # What we do differently
    story.extend(section_header(f"What {_prep_company} does differently"))
    for b in d.get("what_agencies_do", [])[:3]:
        story.append(_ab(b, BLUE))
    story.append(Spacer(1, 4))

    # Speed
    story.extend(section_header("Speed advantage"))
    for b in d.get("time_to_fill_bullets", [])[:3]:
        story.append(_ab(b, GREEN))
    story.append(Spacer(1, 4))

    # Risk transfer
    story.extend(section_header("Your risk, transferred"))
    for b in d.get("risk_bullets", [])[:3]:
        story.append(_ab(b, ORANGE))
    story.append(Spacer(1, 4))

    # CTA
    if d.get("cta"):
        story.append(HRFlowable(width="100%", thickness=0.5, color=SILVER,
                                spaceBefore=4, spaceAfter=6))
        story.append(Paragraph(
            f'<font color="#2C65AC"><b>{_clean(d["cta"])}</b></font>',
            S("cta", fontName="Helvetica", fontSize=8.5, textColor=BLUE,
              leading=11, spaceAfter=0)))

    _build_one_page(doc, story)
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# 6. CUSTOM PDF — generic "Create Your Own" renderer
# ─────────────────────────────────────────────────────────────────────────
def build_custom_pdf(output_path, d, cfg=None):
    """Generic branded one-pager built from a flexible section list.

    d:
      title: str (large navy header at top)
      subtitle: str (optional italic subhead — if missing, built from prepared_by/date)
      badge: str (small blue tag under the subtitle)
      prepared_by, prepared_email, date: same as other templates
      intro: str (optional opening paragraph)
      sections: list of dicts, each with:
        - heading: str (required — blue section header)
        - type: one of:
            "bullets" → items is a list[str]
            "paragraph" → items is a list[str] (joined paragraphs)
            "table" → items is list[list[str]] (first row = header)
            "qa" → items is list[{"q": str, "a": str}]
        - items: per-type payload above
      cta: str (optional closing CTA paragraph)
    """
    doc = ArenaDoc(output_path, badge_text=d.get("badge", "CUSTOM"),
                   prepared_by=d.get("prepared_by", ""),
                   prepared_email=d.get("prepared_email", ""),
                   pagesize=letter,
                   leftMargin=0.65*inch, rightMargin=0.65*inch,
                   topMargin=1.15*inch, bottomMargin=0.65*inch)

    story = []

    # Title block
    title = d.get("title") or "Custom One-Pager"
    _prep = d.get("prepared_by", "")
    _email = d.get("prepared_email", "")
    _date = d.get("date", "")
    subtitle = d.get("subtitle")
    if not subtitle:
        _sub_bits = []
        if _prep:
            _sub_bits.append(f"Prepared by {_prep}")
        if _email:
            _sub_bits.append(_email)
        if _date:
            _sub_bits.append(_date)
        subtitle = " | ".join(_sub_bits) or "Custom document"
    _title_block(story, title, subtitle, d.get("badge", "Custom document"))

    # Optional intro paragraph
    if d.get("intro"):
        story.append(Paragraph(
            _clean(d["intro"]),
            S("intro", fontName="Helvetica", fontSize=11, textColor=NAVY,
              leading=14, spaceAfter=6)))

    # Sections — body font sizes bumped +2 (2026-05-02 user request)
    _qa_q = S("qa_q", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY,
              leading=14, spaceAfter=1, leftIndent=0)
    _qa_a = S("qa_a", fontName="Helvetica", fontSize=10.5, textColor=NAVY,
              leading=13, spaceAfter=6, leftIndent=12)
    _para = S("p", fontName="Helvetica", fontSize=11, textColor=NAVY,
              leading=14, spaceAfter=6)

    for sec in (d.get("sections") or []):
        heading = sec.get("heading") or ""
        stype = (sec.get("type") or "bullets").lower()
        items = sec.get("items") or []

        if heading:
            story.extend(section_header(heading))

        if stype == "bullets":
            for b in items:
                if isinstance(b, str) and b.strip():
                    story.append(bullet_item(b))
            story.append(Spacer(1, 4))

        elif stype == "paragraph":
            for p in items:
                if isinstance(p, str) and p.strip():
                    story.append(Paragraph(_clean(p), _para))
            story.append(Spacer(1, 2))

        elif stype == "table":
            rows = [[_clean(c) for c in row] for row in items if row]
            if rows:
                n_cols = max(len(r) for r in rows)
                # Pad rows to n_cols so reportlab doesn't crash on ragged rows
                rows = [r + [""] * (n_cols - len(r)) for r in rows]

                # Proportional column widths — weight by the longest token in
                # each column (clamped). Narrow-content columns shrink, wide
                # columns grow, so 5+ column tables stay on one page instead
                # of forcing headers like "Professional Development" to wrap
                # onto 3 lines under equal-width distribution.
                def _col_weight(col_idx):
                    max_word = 0
                    max_cell = 0
                    for r in rows:
                        cell = r[col_idx] if col_idx < len(r) else ""
                        for w in cell.split():
                            max_word = max(max_word, len(w))
                        max_cell = max(max_cell, len(cell))
                    # Weight leans on the worst-wrap case, not total length
                    return max(max_word, min(max_cell, 18))
                weights = [_col_weight(i) for i in range(n_cols)]
                total_w = sum(weights) or 1
                min_col = CW * 0.10
                raw = [CW * (w / total_w) for w in weights]
                # Enforce minimums, then rescale to exactly fit CW
                cols = [max(min_col, x) for x in raw]
                scale = CW / sum(cols)
                cols = [c * scale for c in cols]

                # Wrap header cells in Paragraphs so long labels break cleanly.
                # Font sizes bumped +2 (2026-05-02 user request).
                _hdr_fs = 9.5 if n_cols >= 5 else 10
                _cell_fs = 9.5 if n_cols >= 5 else 10
                hdr_style = S("th", fontName="Helvetica-Bold", fontSize=_hdr_fs,
                              textColor=NAVY, leading=_hdr_fs + 2)
                cell_style = S("tc", fontName="Helvetica", fontSize=_cell_fs,
                               textColor=NAVY, leading=_cell_fs + 2)
                wrapped = []
                for ri, r in enumerate(rows):
                    style = hdr_style if ri == 0 else cell_style
                    wrapped.append([Paragraph(c or "", style) for c in r])

                story.append(alt_table(wrapped, cols, header=True))
                story.append(Spacer(1, 6))

        elif stype == "qa":
            for qa in items:
                if not isinstance(qa, dict):
                    continue
                q = qa.get("q") or qa.get("question") or ""
                a = qa.get("a") or qa.get("answer") or ""
                if q:
                    story.append(Paragraph(f"<b>{_clean(q)}</b>", _qa_q))
                if a:
                    story.append(Paragraph(_clean(a), _qa_a))
            story.append(Spacer(1, 2))

        else:
            # Unknown type — fall back to bullets so no content is lost
            for b in items:
                if isinstance(b, str) and b.strip():
                    story.append(bullet_item(b))
            story.append(Spacer(1, 4))

    # Optional closing CTA
    if d.get("cta"):
        story.extend(section_header("Want to learn more?"))
        story.append(bullet_item(d["cta"]))

    _build_one_page(doc, story)
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
