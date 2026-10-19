from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    StreamObject,
    TextStringObject,
)
from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Frame, Paragraph, Table, TableStyle

from .model import Puzzle
from .style import APP_NAME, MARK_COLORS, category_color, hex_to_rgb

PAGE_W, PAGE_H = letter
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN
TITLE_SIZE = 20
GAP = 14
MAX_CELL = 26.0
MIN_CELL = 6.0
MIN_SHARED_CELL = 13.0  # smallest square size before clues move to page 2
COLUMN_GUTTER = 18
CORNER_GAP = 8  # space between the grid and an answer table in its empty corner
THIN = 0.5
THICK = 1.6

LABEL_FONT = "Helvetica"
BAND_FONT = "Helvetica-Bold"

STORY_STYLE = ParagraphStyle("story", fontName="Helvetica", fontSize=10.5, leading=14.5)
HEADING_STYLE = ParagraphStyle("heading", fontName="Helvetica-Bold", fontSize=12, leading=15)
CLUE_STYLE = ParagraphStyle(
    "clue",
    fontName="Helvetica",
    fontSize=9.5,
    leading=12.5,
    leftIndent=17,
    bulletIndent=0,
    bulletFontName="Helvetica-Bold",
    spaceAfter=5,
)
CELL_STYLE = ParagraphStyle("cell", fontName="Helvetica", fontSize=9, leading=11)
HEAD_CELL_STYLE = ParagraphStyle("headcell", parent=CELL_STYLE, fontName="Helvetica-Bold")

FF_READ_ONLY = 1
FF_PUSH_BUTTON = 1 << 16
F_PRINT = 4


def _js_color(hex_color: str) -> str:
    r, g, b = hex_to_rgb(hex_color)
    return f'["RGB", {r:.3f}, {g:.3f}, {b:.3f}]'


CYCLE_SCRIPT = (
    "var f = event.target;"
    "var v = f.buttonGetCaption();"
    f'if (v == "") {{ f.textColor = {_js_color(MARK_COLORS["X"])}; f.buttonSetCaption("X"); }}'
    f'else if (v == "X") {{ f.textColor = {_js_color(MARK_COLORS["O"])}; f.buttonSetCaption("O"); }}'
    'else { f.buttonSetCaption(""); }'
)
INSTRUCTIONS = "Click a square to mark it: X, then O, then blank."


#grid
@dataclass
class _Layout:
    cell: float
    font: float
    band: float
    left_label_w: float
    top_label_h: float
    x0: float  # left edge of the left-side category band
    header_top: float  # distance from the page top to the top-side category band
    grid_x: float  # left edge of the first square column
    grid_top: float  # distance from the page top to the first square row
    span: int  # squares along each side of the grid

    @property
    def bottom(self) -> float:
        return self.grid_top + self.span * self.cell


def _grid_layout(puzzle: Puzzle, top: float, avail_h: float) -> _Layout:
    k = puzzle.size
    span = len(puzzle.top_categories) * k
    left_values = []
    for c in puzzle.left_categories:
        left_values.extend(c.values)
    top_values = []
    for c in puzzle.top_categories:
        top_values.extend(c.values)

    cell = MAX_CELL
    while True:
        font = max(5.0, min(11.0, cell * 0.5))
        pad = font * 0.6
        band = font + 8
        widest_left = max(stringWidth(v, LABEL_FONT, font) for v in left_values)
        widest_top = max(stringWidth(v, LABEL_FONT, font) for v in top_values)
        left_w = widest_left + 2 * pad
        top_h = widest_top + 2 * pad
        fits = (
            band + left_w + span * cell <= CONTENT_W
            and band + top_h + span * cell <= avail_h
        )
        if fits or cell <= MIN_CELL:
            break
        cell -= 0.5

    x0 = (PAGE_W - (band + left_w + span * cell)) / 2
    return _Layout(
        cell=cell,
        font=font,
        band=band,
        left_label_w=left_w,
        top_label_h=top_h,
        x0=x0,
        header_top=top,
        grid_x=x0 + band + left_w,
        grid_top=top + band + top_h,
        span=span,
    )


def _fit_font(text: str, font: str, size: float, max_width: float) -> float:
    width = stringWidth(text, font, size)
    if width <= max_width:
        return size
    return max(4.0, size * max_width / width)


class _Page:
    def __init__(self, canvas: Canvas):
        self.c = canvas

    def rect(self, x, top, w, h, fill=None, width=THIN):
        self.c.setLineWidth(width)
        if fill:
            self.c.setFillColor(HexColor(fill))
        bottom = PAGE_H - top - h  # reportlab measures up from the bottom
        self.c.rect(x, bottom, w, h, stroke=1, fill=1 if fill else 0)

    def line(self, x1, top1, x2, top2, width=THIN):
        self.c.setLineWidth(width)
        self.c.line(x1, PAGE_H - top1, x2, PAGE_H - top2)

    def text_centered(self, text, cx, cy, font, size, color=black):
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        self.c.drawCentredString(cx, PAGE_H - cy - size * 0.35, text)

    def text_right(self, text, right, cy, font, size):
        self.c.setFillColor(black)
        self.c.setFont(font, size)
        self.c.drawRightString(right, PAGE_H - cy - size * 0.35, text)

    def text_up(self, text, cx, bottom, font, size, centered=False):
        self.c.saveState()
        self.c.setFillColor(black)
        self.c.setFont(font, size)
        self.c.translate(cx + size * 0.35, PAGE_H - bottom)
        self.c.rotate(90)
        if centered:
            self.c.drawCentredString(0, 0, text)
        else:
            self.c.drawString(0, 0, text)
        self.c.restoreState()

    def flowable(self, item, top, width=CONTENT_W, x=MARGIN) -> float:
        _, h = item.wrapOn(self.c, width, PAGE_H)
        item.drawOn(self.c, x, PAGE_H - top - h)
        return h


def _new_canvas(buf: BytesIO, title: str) -> Canvas:
    canvas = Canvas(buf, pagesize=letter)
    canvas.setTitle(title)
    canvas.setAuthor("")
    canvas.setSubject("Grid logic puzzle")
    canvas.setCreator(APP_NAME)
    return canvas


def _draw_title(page: _Page, title: str) -> float:
    page.text_centered(title, PAGE_W / 2, MARGIN + TITLE_SIZE / 2, BAND_FONT, TITLE_SIZE)
    return MARGIN + TITLE_SIZE + GAP


def _draw_grid(page: _Page, puzzle: Puzzle, lay: _Layout, solution: bool = False) -> None:
    k = puzzle.size
    cell = lay.cell
    font = lay.font
    block = k * cell
    pad = font * 0.6

    for c, cat in enumerate(puzzle.top_categories):
        color = category_color(puzzle.color_index(cat))
        bx = lay.grid_x + c * block
        page.rect(bx, lay.header_top, block, lay.band, fill=color)
        size = _fit_font(cat.name, BAND_FONT, font, block - 4)
        band_middle = lay.header_top + lay.band / 2
        page.text_centered(cat.name, bx + block / 2, band_middle, BAND_FONT, size)
        label_top = lay.header_top + lay.band
        for j, value in enumerate(cat.values):
            x = bx + j * cell
            page.rect(x, label_top, cell, lay.top_label_h, fill=color)
            page.text_up(value, x + cell / 2, lay.grid_top - pad, LABEL_FONT, font)
        page.rect(bx, lay.header_top, block, lay.band + lay.top_label_h, width=THICK)

    for r, cat in enumerate(puzzle.left_categories):
        color = category_color(puzzle.color_index(cat))
        by = lay.grid_top + r * block
        page.rect(lay.x0, by, lay.band, block, fill=color)
        size = _fit_font(cat.name, BAND_FONT, font, block - 4)
        band_middle = lay.x0 + lay.band / 2
        page.text_up(cat.name, band_middle, by + block / 2, BAND_FONT, size, centered=True)
        for i, value in enumerate(cat.values):
            y = by + i * cell
            page.rect(lay.x0 + lay.band, y, lay.left_label_w, cell, fill=color)
            page.text_right(value, lay.grid_x - pad, y + cell / 2, LABEL_FONT, font)
        page.rect(lay.x0, by, lay.band + lay.left_label_w, block, width=THICK)

    for r, left in enumerate(puzzle.left_categories):
        by = lay.grid_top + r * block
        li = puzzle.color_index(left)
        for c in range(puzzle.blocks_in_row(r)):
            bx = lay.grid_x + c * block
            page.rect(bx, by, block, block, fill="#FFFFFF")
            for n in range(1, k):
                page.line(bx + n * cell, by, bx + n * cell, by + block)
                page.line(bx, by + n * cell, bx + block, by + n * cell)
            page.rect(bx, by, block, block, width=THICK)
            if solution:
                ti = puzzle.color_index(puzzle.top_categories[c])
                for i in range(k):
                    for j in range(k):
                        mark = "O" if puzzle.matches(li, i, ti, j) else "X"
                        page.text_centered(
                            mark,
                            bx + j * cell + cell / 2,
                            by + i * cell + cell / 2,
                            BAND_FONT,
                            cell * 0.6,
                            HexColor(MARK_COLORS[mark]),
                        )


def _clue_paragraphs(puzzle: Puzzle) -> list[Paragraph]:
    return [
        Paragraph(escape(clue.text), CLUE_STYLE, bulletText=f"{i}.")
        for i, clue in enumerate(puzzle.clues, 1)
    ]


def _column_height(heights: list[float], max_h: float) -> float | None:
    def fits(h: float) -> bool:
        columns = 1
        used = 0.0
        for item in heights:
            if used + item > h:
                columns += 1
                used = 0.0
                if item > h or columns > 2:
                    return False
            used += item
        return True

    lo = max(heights)
    hi = sum(heights)
    if not fits(min(hi, max_h)):
        return None
    hi = min(hi, max_h)
    while hi - lo > 1:
        mid = (lo + hi) / 2
        if fits(mid):
            hi = mid
        else:
            lo = mid
    return hi + 2


def _draw_columns(
    canvas: Canvas, items: list, top: float, height: float
) -> tuple[list, float]:
    col_w = (CONTENT_W - COLUMN_GUTTER) / 2
    remaining = list(items)
    reached = top
    for col in range(2):
        x = MARGIN + col * (col_w + COLUMN_GUTTER)
        frame = Frame(
            x, PAGE_H - top - height, col_w, height,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        frame.addFromList(remaining, canvas)
        reached = max(reached, PAGE_H - frame._y)
        if not remaining:
            break
    return remaining, reached


# answer table
@dataclass
class _Table:
    font: float
    widths: list[float]
    row_h: float
    rows: int

    @property
    def width(self) -> float:
        return sum(self.widths)

    @property
    def height(self) -> float:
        return self.row_h * (self.rows + 1)


@dataclass
class _TextField:
    page: int
    name: str
    rect: tuple[float, float, float, float]
    font: float


def _fit_table(puzzle: Puzzle, max_w: float, max_h: float) -> _Table | None:
    for font in (10.0, 9.5, 9.0, 8.5, 8.0, 7.5, 7.0, 6.5, 6.0):
        pad = font * 0.8
        widths = []
        for cat in puzzle.categories:
            text_w = stringWidth(cat.name, BAND_FONT, font)
            for v in cat.values:
                text_w = max(text_w, stringWidth(v, LABEL_FONT, font))
            widths.append(max(text_w + 2 * pad, font * 5))
        table = _Table(font, widths, font * 2.2, puzzle.size)
        if table.width <= max_w and table.height <= max_h:
            return table
    return None


def _draw_answer_table(
    page: _Page, puzzle: Puzzle, table: _Table, x: float, top: float, page_no: int
) -> list[_TextField]:
    font, row_h = table.font, table.row_h
    pad = font * 0.8
    fields = []
    col_x = x
    for n, (cat, width) in enumerate(zip(puzzle.categories, table.widths)):
        color = category_color(n)
        page.rect(col_x, top, width, row_h, fill=color)
        page.c.setFillColor(black)
        page.c.setFont(BAND_FONT, font)
        baseline = PAGE_H - top - row_h / 2 - font * 0.35
        page.c.drawString(col_x + pad, baseline, cat.name)
        for e in range(puzzle.size):
            y = top + row_h * (e + 1)
            if n == 0:
                page.rect(col_x, y, width, row_h, fill=color)
                page.c.setFillColor(black)
                page.c.setFont(LABEL_FONT, font)
                baseline = PAGE_H - y - row_h / 2 - font * 0.35
                page.c.drawString(col_x + pad, baseline, cat.values[e])
            else:
                page.rect(col_x, y, width, row_h, fill="#FFFFFF")
                rect = (
                    col_x + 1.5,
                    PAGE_H - y - row_h + 1.5,
                    col_x + width - 1.5,
                    PAGE_H - y - 1.5,
                )
                fields.append(_TextField(page_no, f"answer_{e}_{n}", rect, font))
        col_x += width
    page.rect(x, top, table.width, row_h * (puzzle.size + 1), width=THICK)
    page.line(x, top + row_h, x + table.width, top + row_h, width=THICK)
    return fields


def _place_table(
    page: _Page, puzzle: Puzzle, lay: _Layout | None, free_top: float, page_no: int
) -> list[_TextField] | None:
    spots = []  # (table, x, top)
    if lay is not None:
        n = len(puzzle.categories)
        block = puzzle.size * lay.cell
        for m in range(1, n - 1):
            x0 = lay.grid_x + m * block + CORNER_GAP
            y0 = lay.grid_top + (n - 1 - m) * block + CORNER_GAP
            room_w = PAGE_W - MARGIN - x0
            room_h = lay.bottom - y0
            table = _fit_table(puzzle, room_w, room_h)
            if table:
                x = x0 + (room_w - table.width) / 2
                top = y0 + (room_h - table.height) / 2
                spots.append((table, x, top))
    room_below = PAGE_H - MARGIN - free_top - GAP
    table = _fit_table(puzzle, CONTENT_W, room_below)
    if table:
        x = MARGIN + (CONTENT_W - table.width) / 2
        spots.append((table, x, free_top + GAP))
    if not spots:
        return None
    table, x, top = max(spots, key=lambda spot: spot[0].font)
    return _draw_answer_table(page, puzzle, table, x, top, page_no)


# notes page
NOTE_LINE_GAP = 26

def _draw_notes_page(page: _Page, title: str) -> None:
    top = _draw_title(page, "Notes")
    page.text_centered(title, PAGE_W / 2, top, LABEL_FONT, 10, HexColor("#5F6368"))
    page.c.setStrokeColor(HexColor("#B8BCC2"))
    y = top + 12 + NOTE_LINE_GAP
    while y <= PAGE_H - MARGIN:
        page.line(MARGIN, y, PAGE_W - MARGIN, y, width=0.6)
        y += NOTE_LINE_GAP


# puzzle
def _draw_puzzle(puzzle: Puzzle) -> tuple[bytes, _Layout, list[_TextField]]:
    buf = BytesIO()
    canvas = _new_canvas(buf, puzzle.title)
    page = _Page(canvas)
    bottom = PAGE_H - MARGIN
    page_no = 0

    def new_page():
        nonlocal page_no
        canvas.showPage()
        page_no += 1

    top = _draw_title(page, puzzle.title)
    top += page.flowable(Paragraph(escape(puzzle.story), STORY_STYLE), top) + GAP

    clues = _clue_paragraphs(puzzle)
    col_w = (CONTENT_W - COLUMN_GUTTER) / 2
    heights = []
    for p in clues:
        _, h = p.wrap(col_w, PAGE_H)
        heights.append(h + CLUE_STYLE.spaceAfter)
    heading_h = HEADING_STYLE.leading + 4

    shared = None
    clue_h = _column_height(heights, bottom - top)
    if clue_h is not None:
        grid_room = bottom - top - GAP - heading_h - clue_h
        candidate = _grid_layout(puzzle, top, grid_room)
        big_enough = candidate.cell >= MIN_SHARED_CELL
        leaves_room = candidate.bottom <= bottom - heading_h - clue_h
        if big_enough and leaves_room:
            shared = candidate

    if shared:
        lay = shared
        _draw_grid(page, puzzle, lay)
        clue_top = lay.bottom + GAP
        page.flowable(Paragraph("Clues", HEADING_STYLE), clue_top)
        _, free_top = _draw_columns(canvas, clues, clue_top + heading_h, clue_h)
        table_fields = _place_table(page, puzzle, lay, free_top, page_no)
    else:
        lay = _grid_layout(puzzle, top, bottom - top)
        _draw_grid(page, puzzle, lay)
        table_fields = _place_table(page, puzzle, lay, lay.bottom, page_no)
        remaining = clues
        first = True
        while remaining:
            new_page()
            clue_top = MARGIN
            if first:
                page.flowable(Paragraph(f"{escape(puzzle.title)}: Clues", HEADING_STYLE), clue_top)
                clue_top += heading_h + 4
                first = False
            left = heights[len(clues) - len(remaining):]
            room = bottom - clue_top
            height = _column_height(left, room) or room
            remaining, free_top = _draw_columns(canvas, remaining, clue_top, height)
        if table_fields is None:
            table_fields = _place_table(page, puzzle, None, free_top, page_no)

    new_page()
    _draw_notes_page(page, puzzle.title)
    canvas.showPage()
    canvas.save()
    return buf.getvalue(), lay, table_fields or []


# squares
def _widget(
    name: str,
    rect: tuple[float, float, float, float],
    field_type: str,
    da: str,
    flags: int,
    annot_flags: int,
) -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject(field_type),
            NameObject("/T"): TextStringObject(name),
            NameObject("/Rect"): ArrayObject([FloatObject(round(v, 2)) for v in rect]),
            NameObject("/F"): NumberObject(annot_flags),
            NameObject("/Ff"): NumberObject(flags),
            NameObject("/DA"): TextStringObject(da),
        }
    )


def _blank_appearance(writer: PdfWriter, width: float, height: float):
    stream = StreamObject()
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Form")
    box = [0, 0, round(width, 2), round(height, 2)]
    stream[NameObject("/BBox")] = ArrayObject([FloatObject(v) for v in box])
    return writer._add_object(stream)


def _js_action(script: str) -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject(script),
        }
    )


def _font_resources(writer: PdfWriter) -> DictionaryObject:
    def font_ref(base: str):
        return writer._add_object(
            DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject(base),
                    NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                }
            )
        )

    return DictionaryObject(
        {
            NameObject("/Helv"): font_ref("/Helvetica"),
            NameObject("/HeBo"): font_ref("/Helvetica-Bold"),
        }
    )


def _metadata(writer: PdfWriter, title: str) -> None:
    writer.add_metadata(
        {
            "/Title": title,
            "/Subject": "Grid logic puzzle",
            "/Creator": APP_NAME,
            "/Producer": APP_NAME,
        }
    )


def _add_fields(
    pdf_bytes: bytes, puzzle: Puzzle, lay: _Layout, table_fields: list[_TextField]
) -> PdfWriter:
    writer = PdfWriter(clone_from=PdfReader(BytesIO(pdf_bytes)))
    fonts = _font_resources(writer)

    k = puzzle.size
    cell = lay.cell
    block = k * cell
    inset = THICK / 2 + 0.3
    mark_da = f"/HeBo {cell * 0.7:.1f} Tf 0 g"
    blank = _blank_appearance(writer, cell - 2 * inset, cell - 2 * inset)
    fields: list = []

    for r in range(len(puzzle.left_categories)):
        for c in range(puzzle.blocks_in_row(r)):
            for i in range(k):
                for j in range(k):
                    left = lay.grid_x + c * block + j * cell
                    top = lay.grid_top + r * block + i * cell
                    rect = (
                        left + inset,
                        PAGE_H - top - cell + inset,
                        left + cell - inset,
                        PAGE_H - top - inset,
                    )
                    button = _widget(
                        f"cell_{r}_{c}_{i}_{j}", rect, "/Btn", mark_da, FF_PUSH_BUTTON, F_PRINT
                    )
                    button[NameObject("/MK")] = DictionaryObject(
                        {NameObject("/CA"): TextStringObject("")}
                    )
                    button[NameObject("/H")] = NameObject("/N")
                    button[NameObject("/AP")] = DictionaryObject({NameObject("/N"): blank})
                    button[NameObject("/A")] = _js_action(CYCLE_SCRIPT)
                    fields.append(button)

    hint = _widget(
        "instructions",
        (MARGIN, 14, PAGE_W - MARGIN, 28),
        "/Tx",
        "/Helv 8 Tf 0.4 g",
        FF_READ_ONLY,
        0,
    )
    hint[NameObject("/Q")] = NumberObject(1)
    hint[NameObject("/V")] = TextStringObject(INSTRUCTIONS)
    fields.append(hint)

    by_page: dict[int, list] = {0: fields}
    for spec in table_fields:
        da = f"/Helv {spec.font:.1f} Tf 0 g"
        field = _widget(spec.name, spec.rect, "/Tx", da, 0, F_PRINT)
        field[NameObject("/MK")] = DictionaryObject()
        by_page.setdefault(spec.page, []).append(field)

    refs = []
    for page_no, page_fields in by_page.items():
        page = writer.pages[page_no]
        page_refs = []
        for field in page_fields:
            field[NameObject("/P")] = page.indirect_reference
            page_refs.append(writer._add_object(field))
        annots = page.get("/Annots")
        if annots is None:
            annots = ArrayObject()
        else:
            annots = annots.get_object()
        annots.extend(page_refs)
        page[NameObject("/Annots")] = annots
        refs.extend(page_refs)

    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject(refs),
            NameObject("/NeedAppearances"): BooleanObject(True),
            NameObject("/DR"): DictionaryObject({NameObject("/Font"): fonts}),
            NameObject("/DA"): TextStringObject("/Helv 0 Tf 0 g"),
        }
    )
    _metadata(writer, puzzle.title)
    return writer


def write_pdf(puzzle: Puzzle, path: Path) -> Path:
    pdf_bytes, layout, table_fields = _draw_puzzle(puzzle)
    writer = _add_fields(pdf_bytes, puzzle, layout, table_fields)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


# answer key
def _solution_table(puzzle: Puzzle) -> Table:
    cats = puzzle.categories
    data = [[Paragraph(escape(c.name), HEAD_CELL_STYLE) for c in cats]]
    for row in puzzle.solution:
        cells = []
        for j, v in enumerate(row):
            cells.append(Paragraph(escape(cats[j].values[v]), CELL_STYLE))
        data.append(cells)
    col_w = CONTENT_W / len(cats)
    table = Table(data, colWidths=[col_w] * len(cats), repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), THIN, black),
        ("BOX", (0, 0), (-1, -1), THICK, black),
        ("LINEBELOW", (0, 0), (-1, 0), THICK, black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for j in range(len(cats)):
        style.append(("BACKGROUND", (j, 0), (j, 0), HexColor(category_color(j))))
    table.setStyle(TableStyle(style))
    return table


def write_answer_key(puzzle: Puzzle, path: Path) -> Path:
    buf = BytesIO()
    title = f"{puzzle.title}: Answer Key"
    canvas = _new_canvas(buf, title)
    page = _Page(canvas)
    bottom = PAGE_H - MARGIN

    top = _draw_title(page, title)
    top += page.flowable(_solution_table(puzzle), top) + GAP * 1.5
    lay = _grid_layout(puzzle, top, bottom - top)
    if lay.cell < MIN_SHARED_CELL:
        canvas.showPage()
        lay = _grid_layout(puzzle, MARGIN, bottom - MARGIN)
    _draw_grid(page, puzzle, lay, solution=True)
    canvas.showPage()
    canvas.save()

    writer = PdfWriter(clone_from=PdfReader(BytesIO(buf.getvalue())))
    _metadata(writer, title)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path
