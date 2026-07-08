"""Generate RegView architecture PDF (professional template).

Run from project root (with .venv active):
    pip install reportlab
    python scripts/generate_architecture_pdf.py

Output:  docs/RegView_Architecture.pdf
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path("docs/RegView_Architecture.pdf")
OUT.parent.mkdir(parents=True, exist_ok=True)

# ---- page geometry ----
PAGE_W, PAGE_H = A4
MARGIN_L = MARGIN_R = 1.8 * cm
MARGIN_T = 2.2 * cm
MARGIN_B = 2.0 * cm
USABLE_W = PAGE_W - MARGIN_L - MARGIN_R          # ~493 pt (17.4 cm)
DIAGRAM_W = 15.8 * cm                            # fits comfortably inside usable width

# ---- palette ----
NAVY = colors.HexColor("#0F2A44")
NAVY_LIGHT = colors.HexColor("#1E3A5F")
SLATE = colors.HexColor("#475569")
SLATE_LIGHT = colors.HexColor("#94A3B8")
RULE = colors.HexColor("#CBD5E1")

C_CLIENT_FILL = colors.HexColor("#FEF3C7"); C_CLIENT_STROKE = colors.HexColor("#B45309")
C_APP_FILL    = colors.HexColor("#E8F1FB"); C_APP_STROKE    = colors.HexColor("#2A6DB0")
C_SVC_FILL    = colors.HexColor("#DCFCE7"); C_SVC_STROKE    = colors.HexColor("#166534")
C_STORE_FILL  = colors.HexColor("#EDE9FE"); C_STORE_STROKE  = colors.HexColor("#6D28D9")
C_EXT_FILL    = colors.HexColor("#FEE2E2"); C_EXT_STROKE    = colors.HexColor("#B91C1C")
C_INGEST_FILL = colors.HexColor("#FDF2F8"); C_INGEST_STROKE = colors.HexColor("#BE185D")


# ---------- drawing helpers ----------

def _wrap_line(c: _canvas.Canvas, text: str, max_w: float, font: str, size: float) -> list[str]:
    """Break `text` into lines whose stringWidth fits within max_w."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _box(c: _canvas.Canvas, x, y, w, h, label, sub=None,
         fill=C_APP_FILL, stroke=C_APP_STROKE):
    """Draw a rounded box with a bold title and up to N wrapped sub-lines.

    Text is auto-wrapped to (w - 2*pad). Title is truncated only if a single
    word is too wide; sub-lines wrap naturally.
    """
    pad = 6
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(1.1)
    c.roundRect(x, y, w, h, 5, fill=1, stroke=1)

    inner_w = w - 2 * pad

    # Title
    t_font, t_size = "Helvetica-Bold", 9.5
    title_lines = _wrap_line(c, label, inner_w, t_font, t_size)[:2]
    c.setFillColor(NAVY)
    c.setFont(t_font, t_size)
    title_line_h = t_size + 2
    title_top_y = y + h - (t_size + 4)   # baseline of first title line
    for i, line in enumerate(title_lines):
        c.drawCentredString(x + w / 2, title_top_y - i * title_line_h, line)

    if sub:
        s_font, s_size = "Helvetica", 7.8
        sub_line_h = s_size + 2.2
        # Starting y for first sub line (baseline)
        first_sub_y = title_top_y - len(title_lines) * title_line_h - 2
        c.setFillColor(SLATE)
        c.setFont(s_font, s_size)
        for entry in sub:
            for line in _wrap_line(c, entry, inner_w, s_font, s_size):
                if first_sub_y < y + pad:      # ran out of vertical room
                    return
                c.drawCentredString(x + w / 2, first_sub_y, line)
                first_sub_y -= sub_line_h


def _arrow(c: _canvas.Canvas, x1, y1, x2, y2, label=None, dash=False):
    c.setStrokeColor(SLATE)
    c.setLineWidth(0.9)
    c.setDash(3, 3) if dash else c.setDash()
    c.line(x1, y1, x2, y2)
    c.setDash()
    ang = math.atan2(y2 - y1, x2 - x1)
    size = 5
    c.setFillColor(SLATE)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - size * math.cos(ang - 0.4), y2 - size * math.sin(ang - 0.4))
    p.lineTo(x2 - size * math.cos(ang + 0.4), y2 - size * math.sin(ang + 0.4))
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    if label:
        c.setFont("Helvetica-Oblique", 7)
        c.setFillColor(SLATE)
        # label positioned slightly right of arrow midpoint
        c.drawString((x1 + x2) / 2 + 4, (y1 + y2) / 2 + 3, label)


class Diagram(Flowable):
    def __init__(self, width, height):
        Flowable.__init__(self)
        self.width = width
        self.height = height

    def wrap(self, availW, availH):
        return self.width, self.height


# ---------- diagrams ----------

class ArchitectureOverview(Diagram):
    """4-layer vertical stack. Straight arrows, no crossings."""

    W = DIAGRAM_W
    H = 11.55 * cm

    def __init__(self):
        super().__init__(self.W, self.H)

    def draw(self):
        c = self.canv
        W, H = self.W, self.H
        row_h = 1.9 * cm
        gap_v = 1.15 * cm

        y1 = 0.2 * cm
        y2 = y1 + row_h + gap_v
        y3 = y2 + row_h + gap_v
        y4 = y3 + row_h + gap_v

        # Layer 4: Client
        cw = 6.0 * cm
        _box(c, (W - cw) / 2, y4, cw, row_h, "Web / API Client",
             ["Browser  ·  curl  ·  your app"],
             fill=C_CLIENT_FILL, stroke=C_CLIENT_STROKE)

        # Layer 3: FastAPI (full width)
        _box(c, 0, y3, W, row_h, "FastAPI Gateway (RegView)",
             ["Routes:  /chat   /sessions   /ingest/*   /sources/*",
              "async endpoints  ·  lifespan-managed singletons"])

        # Layer 2: 3 services in 3 columns
        col_gap = 0.5 * cm
        col_w = (W - 2 * col_gap) / 3
        col_x = [0, col_w + col_gap, 2 * (col_w + col_gap)]
        _box(c, col_x[0], y2, col_w, row_h, "Retriever",
             ["embed  ->  search  ->  filter"],
             fill=C_SVC_FILL, stroke=C_SVC_STROKE)
        _box(c, col_x[1], y2, col_w, row_h, "Claude Client",
             ["Anthropic SDK  ·  tenacity retry"],
             fill=C_SVC_FILL, stroke=C_SVC_STROKE)
        _box(c, col_x[2], y2, col_w, row_h, "Session Store",
             ["SQLAlchemy async  ·  last 50 msgs"],
             fill=C_SVC_FILL, stroke=C_SVC_STROKE)

        # Layer 1: data stores under each service
        _box(c, col_x[0], y1, col_w, row_h, "ChromaDB",
             ["Vector database",
              "PubMedBERT vectors (768d)"],
             fill=C_STORE_FILL, stroke=C_STORE_STROKE)
        _box(c, col_x[1], y1, col_w, row_h, "Anthropic API",
             ["api.anthropic.com",
              "Claude 3.5 Haiku"],
             fill=C_EXT_FILL, stroke=C_EXT_STROKE)
        _box(c, col_x[2], y1, col_w, row_h, "SQLite",
             ["Session database",
              "conversation history"],
             fill=C_STORE_FILL, stroke=C_STORE_STROKE)

        # Arrows: all vertical
        _arrow(c, W / 2, y4, W / 2, y3 + row_h + 2)
        for cx in col_x:
            _arrow(c, cx + col_w / 2, y3, cx + col_w / 2, y2 + row_h + 2)
        for cx in col_x:
            _arrow(c, cx + col_w / 2, y2, cx + col_w / 2, y1 + row_h + 2, dash=True)


class ChatFlow(Diagram):
    """7 numbered steps, top to bottom, arrows in the vertical gap."""

    W = DIAGRAM_W
    STEP_H = 1.25 * cm
    GAP = 0.35 * cm
    STEPS = [
        ("1. POST /chat", "user message + optional session_id"),
        ("2. Load / create session", "SQLite: fetch last 50 messages for continuity"),
        ("3. Retrieve", "PubMedBERT embed  ->  Chroma top-5  ->  distance <= 0.55"),
        ("4. Build context block", "numbered [1][2][3] snippets + titles + URLs"),
        ("5. Call Claude", "SYSTEM_PROMPT + history + context + user question"),
        ("6. Relevance check", "Claude ignores off-topic hits; downgrades grounded flag"),
        ("7. Persist + return", "save user msg + assistant reply  ·  return JSON"),
    ]

    def __init__(self):
        n = len(self.STEPS)
        h = n * self.STEP_H + (n - 1) * self.GAP + 0.4 * cm
        super().__init__(self.W, h)

    def draw(self):
        c = self.canv
        box_w = self.W - 3.5 * cm
        box_x = (self.W - box_w) / 2
        top_y = self.height - 0.2 * cm

        for i, (title, sub) in enumerate(self.STEPS):
            y = top_y - (i + 1) * self.STEP_H - i * self.GAP
            _box(c, box_x, y, box_w, self.STEP_H, title, [sub])
            if i < len(self.STEPS) - 1:
                _arrow(c, self.W / 2, y - 2, self.W / 2, y - self.GAP + 2)


class IngestFlow(Diagram):
    """5-box horizontal pipeline. Widths computed to fit exactly."""

    W = DIAGRAM_W
    H = 3.8 * cm
    STAGES = [
        ("Input", ["PDF · DOCX · URL", "openFDA · CT.gov"]),
        ("Parse", ["extract text", "normalise"]),
        ("Chunk", ["800 chars", "120 overlap"]),
        ("Embed", ["PubMedBERT", "768-dim"]),
        ("Store", ["ChromaDB", "dedup by hash"]),
    ]

    def __init__(self):
        super().__init__(self.W, self.H)

    def draw(self):
        c = self.canv
        n = len(self.STAGES)
        gap = 0.45 * cm
        box_w = (self.W - (n - 1) * gap) / n
        box_h = 2.2 * cm
        y = (self.H - box_h) / 2
        for i, (label, sub) in enumerate(self.STAGES):
            x = i * (box_w + gap)
            _box(c, x, y, box_w, box_h, label, sub,
                 fill=C_INGEST_FILL, stroke=C_INGEST_STROKE)
            if i < n - 1:
                _arrow(c, x + box_w + 1, y + box_h / 2,
                       x + box_w + gap - 1, y + box_h / 2)


class DecisionMatrix(Diagram):
    """2x2 grid: distance-passed x claude-relevant."""

    W = DIAGRAM_W
    H = 6.4 * cm

    def __init__(self):
        super().__init__(self.W, self.H)

    def draw(self):
        c = self.canv
        pad_left = 1.6 * cm
        pad_top = 0.9 * cm
        pad_bottom = 0.9 * cm
        grid_x = pad_left
        grid_y = pad_bottom
        grid_w = self.W - pad_left - 0.2 * cm
        grid_h = self.H - pad_top - pad_bottom

        col_w = grid_w / 2
        row_h = grid_h / 2

        # Top axis label
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(grid_x + grid_w / 2, self.H - 12,
                            "Chunks passed distance threshold?")

        # Column headers (inside padding, above grid)
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(SLATE)
        c.drawCentredString(grid_x + col_w / 2, grid_y + grid_h + 6, "NO")
        c.drawCentredString(grid_x + col_w + col_w / 2, grid_y + grid_h + 6, "YES")

        # Left axis label (rotated)
        c.saveState()
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 9)
        c.translate(10, grid_y + grid_h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, "Claude judged relevant?")
        c.restoreState()

        # Row headers (rotated, in gutter between axis and grid)
        c.setFillColor(SLATE)
        c.setFont("Helvetica-Bold", 8.5)
        c.saveState()
        c.translate(grid_x - 8, grid_y + row_h + row_h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, "YES")
        c.restoreState()
        c.saveState()
        c.translate(grid_x - 8, grid_y + row_h / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, "N/A")
        c.restoreState()

        cell_pad = 0.15 * cm
        cells = [
            (0, 1, "Fallback",
             ["grounded = false",
              "Claude uses general knowledge",
              "prefixed with disclaimer"],
             C_CLIENT_FILL, C_CLIENT_STROKE),
            (1, 1, "Grounded answer",
             ["grounded = true",
              "citations [1][2][3]",
              "answered from local KB"],
             C_SVC_FILL, C_SVC_STROKE),
            (0, 0, "No results",
             ["no chunks + no Claude",
              "\"no results\" message"],
             C_EXT_FILL, C_EXT_STROKE),
            (1, 0, "Raw snippets",
             ["no Claude configured",
              "chunks returned as-is"],
             C_STORE_FILL, C_STORE_STROKE),
        ]
        for col, row, title, sub, fill, stroke in cells:
            x = grid_x + col * col_w + cell_pad
            y = grid_y + row * row_h + cell_pad
            _box(c, x, y,
                 col_w - 2 * cell_pad, row_h - 2 * cell_pad,
                 title, sub, fill=fill, stroke=stroke)


# ---------- typography ----------

styles = getSampleStyleSheet()
COVER_TITLE = ParagraphStyle("CoverTitle", parent=styles["Title"],
    fontSize=34, leading=40, textColor=NAVY, alignment=TA_CENTER, spaceAfter=8)
COVER_SUB = ParagraphStyle("CoverSub", parent=styles["Normal"],
    fontSize=13, leading=18, textColor=SLATE, alignment=TA_CENTER, spaceAfter=4)

H1 = ParagraphStyle("H1", parent=styles["Heading1"],
    fontSize=17, leading=22, spaceBefore=4, spaceAfter=10, textColor=NAVY)
H2 = ParagraphStyle("H2", parent=styles["Heading2"],
    fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=6, textColor=NAVY_LIGHT)
H3 = ParagraphStyle("H3", parent=styles["Heading3"],
    fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=4, textColor=SLATE)
BODY = ParagraphStyle("Body", parent=styles["BodyText"],
    fontSize=9.8, leading=13.6, alignment=TA_LEFT, spaceAfter=5,
    textColor=colors.HexColor("#1F2937"))
SMALL = ParagraphStyle("Small", parent=BODY,
    fontSize=8.5, leading=11.5, textColor=SLATE, spaceAfter=4)
CAPTION = ParagraphStyle("Caption", parent=SMALL,
    alignment=TA_CENTER, textColor=SLATE, spaceBefore=6, spaceAfter=12,
    fontName="Helvetica-Oblique")


_CELL_STYLE = ParagraphStyle(
    "Cell", fontName="Helvetica", fontSize=8.8, leading=11.5,
    textColor=colors.HexColor("#1F2937"), spaceAfter=0, spaceBefore=0,
)
_CELL_HEADER_STYLE = ParagraphStyle(
    "CellHeader", parent=_CELL_STYLE,
    fontName="Helvetica-Bold", fontSize=9, textColor=colors.white,
)


def _wrap_cells(data):
    """Wrap every string cell in a Paragraph so long text auto-wraps."""
    out = []
    for r, row in enumerate(data):
        new_row = []
        style = _CELL_HEADER_STYLE if r == 0 else _CELL_STYLE
        for cell in row:
            if isinstance(cell, str):
                new_row.append(Paragraph(cell, style))
            else:
                new_row.append(cell)
        out.append(new_row)
    return out


def _table(data, col_widths=None):
    t = Table(_wrap_cells(data), colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8.8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
            [colors.white, colors.HexColor("#F8FAFC")]),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY_LIGHT),
        ("INNERGRID", (0, 1), (-1, -1), 0.2, RULE),
    ]))
    return t


# ---------- page decoration ----------

DOC_TITLE = "RegView — Architecture Overview"
DOC_VERSION = "v1.0"


def _draw_page_chrome(canvas, doc):
    """Header + footer on every page except the cover (page 1)."""
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(MARGIN_L, PAGE_H - MARGIN_T + 14, DOC_TITLE)
        canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 14, DOC_VERSION)
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN_L, PAGE_H - MARGIN_T + 8,
                    PAGE_W - MARGIN_R, PAGE_H - MARGIN_T + 8)
        canvas.setFillColor(SLATE_LIGHT)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(MARGIN_L, MARGIN_B - 16,
                          "Confidential — for internal review")
        canvas.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 16, f"Page {page}")
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN_L, MARGIN_B - 8,
                    PAGE_W - MARGIN_R, MARGIN_B - 8)
    canvas.restoreState()


# ---------- document ----------

def build():
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title=DOC_TITLE,
        author="RegView",
    )
    s = []

    # ============ COVER ============
    s.append(Spacer(1, 5.0 * cm))
    s.append(Paragraph("RegView", COVER_TITLE))
    s.append(Paragraph("AI-Powered Regulatory Search Platform", COVER_SUB))
    s.append(Spacer(1, 0.5 * cm))
    s.append(Paragraph("Architecture &amp; Implementation Overview", COVER_SUB))
    s.append(Spacer(1, 6.5 * cm))

    meta = [
        ["Version", DOC_VERSION],
        ["Date", date.today().strftime("%B %d, %Y")],
        ["Audience", "Engineering · Product · Stakeholders"],
    ]
    meta_t = Table(meta, colWidths=[3.5 * cm, 9 * cm], hAlign="CENTER")
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), SLATE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
    ]))
    s.append(meta_t)
    s.append(PageBreak())

    # ============ 1. OVERVIEW ============
    s.append(Paragraph("1.  Overview", H1))
    s.append(Paragraph(
        "RegView answers plain-English questions about FDA drugs, patents, clinical trials, and recalls. "
        "It ingests public regulatory data (openFDA, ClinicalTrials.gov, FDA Orange Book) plus any PDFs or URLs "
        "you provide, stores everything as searchable vectors in a local database (ChromaDB), retrieves the most "
        "relevant snippets for each question, and asks Anthropic's Claude to write a short, cited answer.",
        BODY))
    s.append(Paragraph(
        "If nothing relevant is found in the local library, Claude falls back to its own general knowledge "
        "and clearly labels the answer. This makes the system safe by default: users always know whether an "
        "answer came from the regulatory library or from the model's training data.",
        BODY))

    s.append(Paragraph("Design goals", H3))
    for line in [
        "<b>Local-first.</b>  Vectors, documents, and session history live on disk — no third-party data store required.",
        "<b>Auditable.</b>  Every grounded answer cites the exact chunks it used.",
        "<b>Cost-controlled.</b>  Retrieval trims LLM context to only relevant snippets; Haiku is the default model.",
        "<b>Swappable.</b>  Vector DB, LLM, and session store are all behind small interfaces.",
    ]:
        s.append(Paragraph("&bull;  " + line, BODY))

    # ============ 2. SYSTEM ARCHITECTURE ============
    s.append(KeepTogether([
        Paragraph("2.  System Architecture", H1),
        Paragraph(
            "Four layers, top to bottom: <b>Client</b>, <b>Gateway</b>, <b>Services</b>, and "
            "<b>Storage / External APIs</b>. Solid arrows show the live request path; dashed arrows show data access.",
            BODY),
        ArchitectureOverview(),
        Paragraph("Figure 1 — System architecture (four-layer view)", CAPTION),
    ]))

    # ============ 3. COMPONENTS ============
    comp = [
        ["Layer", "Responsibility"],
        ["FastAPI gateway", "HTTP endpoints; wires everything together at startup via lifespan-managed singletons."],
        ["Retriever", "Embeds the question, queries the vector store, filters by distance, returns top-K chunks."],
        ["Embedding model", "PubMedBERT (biomedical BERT), loaded once and cached. 768-dim vectors."],
        ["Vector store", "ChromaDB with cosine distance and metadata filters."],
        ["Claude client", "Anthropic SDK wrapper with tenacity retries and structured response parsing."],
        ["Session store", "SQLAlchemy 2.x async persists the last N messages per session."],
        ["Ingestion pipeline", "Chunker (800 chars / 120 overlap) then embedder then vector store. Deduplicates by content hash."],
        ["Connectors", "One module per source: openFDA labels, FAERS, 510(k), enforcement, ClinicalTrials.gov, Orange Book."],
    ]
    s.append(KeepTogether([
        Paragraph("3.  Components", H1),
        _table(comp, col_widths=[3.6 * cm, 13.4 * cm]),
    ]))

    # ============ 4. CHAT REQUEST FLOW ============
    s.append(KeepTogether([
        Paragraph("4.  Chat Request Flow", H1),
        Paragraph(
            "The end-to-end path taken by every user question. Steps 3 and 6 form a two-tier relevance filter "
            "(mechanical distance cutoff, then Claude's semantic check) that keeps off-topic content out of the final answer.",
            BODY),
        ChatFlow(),
        Paragraph("Figure 2 — /chat request flow (7 steps)", CAPTION),
    ]))

    # ============ 5. INGESTION PIPELINE ============
    s.append(KeepTogether([
        Paragraph("5.  Ingestion Pipeline", H1),
        Paragraph(
            "Every source — user-provided PDFs, URLs, or bulk feeds from openFDA and ClinicalTrials.gov — flows through "
            "the same five stages. Chunk and document IDs are deterministic content hashes, so re-ingesting is safe: "
            "existing content is skipped and only new material is added.",
            BODY),
        IngestFlow(),
        Paragraph("Figure 3 — Ingestion pipeline (five stages)", CAPTION),
    ]))

    # ============ 6. RELEVANCE FILTERING ============
    s.append(Paragraph("6.  Relevance Filtering", H1))
    s.append(Paragraph(
        "<b>Tier 1 — Distance threshold (mechanical).</b>  Every retrieved chunk gets a cosine distance score. "
        "Chunks with <font face='Courier'>distance &gt; RAG_DISTANCE_THRESHOLD</font> are dropped before Claude ever sees them.",
        BODY))
    s.append(Paragraph(
        "<b>Tier 2 — Claude relevance check (semantic).</b>  The system prompt instructs Claude to judge each "
        "surviving snippet on its own merits and silently ignore topically-irrelevant hits (for example, a drug label "
        "mentioning 'PM' for post-meridiem dosing when the user asked about a Prime Minister). If every snippet fails, "
        "Claude uses the fallback disclaimer and the API downgrades the response to "
        "<font face='Courier'>grounded: false, citations: []</font>.",
        BODY))

    s.append(Paragraph("Distance intuition (cosine)", H3))
    dist = [
        ["Distance", "Meaning", "What happens"],
        ["0.00 – 0.15", "Near-identical", "Cited with high confidence"],
        ["0.15 – 0.30", "Very relevant", "Cited"],
        ["0.30 – 0.55", "Loosely related", "Sent to Claude; Claude may still ignore"],
        ["> 0.55 (default cutoff)", "Unrelated", "Dropped by retriever"],
        ["1.0 – 2.0", "Opposite meaning", "Never seen — filtered long before"],
    ]
    s.append(_table(dist, col_widths=[3.7 * cm, 4.5 * cm, 8.8 * cm]))

    # ============ 7. LOCAL-FIRST / FALLBACK ============
    s.append(KeepTogether([
        Paragraph("7.  Local-First, Claude-Fallback Logic", H1),
        Paragraph(
            "Every question tries the local library first. The final behaviour depends on two questions: did any chunks "
            "pass the distance threshold, and (when Claude is configured) did Claude judge them relevant?",
            BODY),
        DecisionMatrix(),
        Paragraph("Figure 4 — Local-first / Claude-fallback decision matrix", CAPTION),
    ]))

    # ============ 8. TECH STACK ============
    stack = [
        ["Concern", "Technology", "Why chosen"],
        ["Web framework", "FastAPI + Uvicorn", "Async, auto-generated OpenAPI documentation"],
        ["LLM", "Anthropic Claude (Haiku / Sonnet / Opus)", "Strong reasoning + long context; SDK with streaming support"],
        ["Embeddings", "PubMedBERT via sentence-transformers", "Biomedical vectors outperform generic BERT on FDA text"],
        ["Vector DB", "ChromaDB", "Cosine distance, metadata filters, embeddable"],
        ["Session DB", "SQLite via SQLAlchemy 2.x async", "Lightweight persistence for conversation history"],
        ["HTTP client", "httpx (async)", "For openFDA / ClinicalTrials.gov fetches"],
        ["Retries", "tenacity", "Exponential backoff around Claude and openFDA"],
        ["Config", "pydantic-settings", "Type-checked, environment-driven configuration"],
        ["Logging", "loguru", "Structured, colour-coded application logs"],
    ]
    s.append(KeepTogether([
        Paragraph("8.  Technology Stack", H1),
        _table(stack, col_widths=[3.4 * cm, 5.4 * cm, 8.2 * cm]),
    ]))

    # ============ 9. DATA SOURCES ============
    src = [
        ["Source", "Endpoint", "Volume (bulk)"],
        ["openFDA drug labels", "api.fda.gov/drug/label.json", "Up to 25,000 (API cap)"],
        ["openFDA FAERS (adverse events)", "api.fda.gov/drug/event.json", "Per-drug aggregated summary"],
        ["openFDA 510(k) devices", "api.fda.gov/device/510k.json", "Up to 25,000"],
        ["openFDA enforcement / recalls", "api.fda.gov/{drug,device,food}/enforcement.json", "Up to 25,000 per kind"],
        ["FDA Orange Book", "Public FDA archive (products, patents, exclusivity)", "~34,000 products"],
        ["ClinicalTrials.gov v2", "clinicaltrials.gov/api/v2/studies", "Unlimited (paginated)"],
        ["User documents", "PDF / DOCX uploads and seed URLs", "Ad-hoc"],
    ]
    s.append(KeepTogether([
        Paragraph("9.  Data Sources", H1),
        _table(src, col_widths=[4.0 * cm, 8.5 * cm, 4.5 * cm]),
    ]))

    # ============ 10. OUT OF SCOPE ============
    scope_lines = [
        "<b>No Model Context Protocol (MCP) server.</b>  Direct SDK calls are simpler and faster for a fixed RAG pipeline.",
        "<b>No authentication or rate-limiting</b> at the API layer. A gateway is expected in front for production use.",
        "<b>No streaming responses yet.</b>  Non-streaming responses keep the code simple; streaming can be added later.",
        "<b>No FAERS bulk ingest.</b>  Millions of raw events are not useful as vectors; we aggregate per drug instead.",
        "<b>No hosted vector DB.</b>  ChromaDB covers current volumes; larger corpora can move to Qdrant or Pinecone.",
    ]
    scope_block = [Paragraph("10.  Out of Scope (by design)", H1)]
    scope_block += [Paragraph("&bull;  " + line, BODY) for line in scope_lines]
    scope_block += [
        Spacer(1, 0.6 * cm),
        Paragraph(
            "<b>Disclaimer.</b>  RegView is for research and informational use only. It is not medical, legal, "
            "or regulatory advice. Always verify important findings against the primary sources "
            "(FDA.gov, ClinicalTrials.gov, FDA Orange Book).",
            SMALL),
    ]
    s.append(KeepTogether(scope_block))

    # ============ 11. GLOSSARY ============
    gloss = [
        ["Term", "Meaning"],
        ["RAG", "Retrieval-Augmented Generation. The pattern of retrieving relevant snippets from a private library and passing them to an LLM as extra context."],
        ["Embedding", "A high-dimensional numeric vector representing the meaning of a piece of text. Similar meanings sit close together in vector space."],
        ["Cosine distance", "Distance metric used by ChromaDB: 0.0 means identical direction, 1.0 means orthogonal, 2.0 means opposite. Lower is better."],
        ["Chunk", "A ~800-character slice of a source document. Each chunk is embedded and stored as an independent search unit."],
        ["Grounded answer", "An answer supported by citations to retrieved chunks. Marked <font face='Courier'>grounded: true</font> in the API response."],
        ["Fallback answer", "An answer produced from Claude's general knowledge because the local library had no relevant material. Always prefixed with a disclaimer."],
        ["openFDA", "The FDA's public JSON API for drugs, devices, foods, and recalls. See open.fda.gov."],
    ]
    s.append(KeepTogether([
        Paragraph("11.  Glossary", H1),
        _table(gloss, col_widths=[3.6 * cm, 13.4 * cm]),
    ]))

    doc.build(s, onFirstPage=_draw_page_chrome, onLaterPages=_draw_page_chrome)
    print(f"Wrote {OUT.resolve()}")


if __name__ == "__main__":
    build()
