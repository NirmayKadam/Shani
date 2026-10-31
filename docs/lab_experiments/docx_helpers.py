"""
Helpers for filling the department's .docx lab templates with python-docx.

The templates keep their VESIT header, logo, title block and styles; these helpers only
locate paragraphs/tables and insert content next to them. Tables wrapped in content controls
(w:sdt) are not listed in Document.tables, so they are located through the XML.
"""

import copy
from typing import Iterable, List, Optional, Sequence

from docx.document import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

STUDENTS = ["Hirdhay Jadhwani", "Siddharth Jogi", "Sumanyu Joshi", "Nirmay Kadam"]
HEADER_FILL = "D9E2F3"  # light blue-grey header shading, as used in the templates' tables


# ----------------------------------------------------------------------------- locating

def find_paragraph(doc: Document, startswith: str, occurrence: int = 1, exact: bool = False) -> Paragraph:
    """The n-th body paragraph whose stripped text starts with (or, if exact, equals) the given text."""
    seen = 0
    for el in doc.element.body.iterchildren():
        if el.tag == qn("w:p"):
            p = Paragraph(el, doc)
            txt = p.text.strip()
            if (txt == startswith) if exact else txt.startswith(startswith):
                seen += 1
                if seen == occurrence:
                    return p
    raise KeyError(f"paragraph starting with {startswith!r} (occurrence {occurrence}) not found")


def sdt_tables(doc: Document) -> List[Table]:
    """Tables wrapped in content controls (w:sdt) at body level, in document order."""
    out = []
    for el in doc.element.body.iterchildren():
        if el.tag == qn("w:sdt"):
            for tbl in el.iter(qn("w:tbl")):
                out.append(Table(tbl, doc))
    return out


# ----------------------------------------------------------------------------- text

def set_text(p: Paragraph, text: str, bold: Optional[bool] = None) -> Paragraph:
    """Replace a paragraph's text, keeping the first run's formatting."""
    runs = p.runs
    if not runs:
        r = p.add_run(text)
        if bold is not None:
            r.bold = bold
        return p
    runs[0].text = text
    if bold is not None:
        runs[0].bold = bold
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    return p


def set_label_value(p: Paragraph, label: str, value: str) -> Paragraph:
    """'Label: value' with the label bold, replacing placeholder blanks."""
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)
    if p.runs:
        p.runs[0].text = f"{label}: "
        p.runs[0].bold = True
    else:
        p.add_run(f"{label}: ").bold = True
    p.add_run(value).bold = False
    return p


def _new_paragraph_after(anchor) -> Paragraph:
    el = anchor._element if hasattr(anchor, "_element") else anchor
    new_p = OxmlElement("w:p")
    el.addnext(new_p)
    parent = anchor._parent if hasattr(anchor, "_parent") else None
    return Paragraph(new_p, parent)


def add_paragraph_after(anchor, text: str = "", style: Optional[str] = None, bold: bool = False,
                        italic: bool = False, size: Optional[float] = None,
                        align: Optional[str] = None, label: Optional[str] = None) -> Paragraph:
    """Insert a paragraph after a paragraph/table. label='X' renders 'X: text' with X bold."""
    p = _new_paragraph_after(anchor)
    if style:
        p.style = style
    if label:
        lr = p.add_run(f"{label}: ")
        lr.bold = True
        if size:
            lr.font.size = Pt(size)
    if text:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        if size:
            r.font.size = Pt(size)
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def add_paragraphs_after(anchor, items: Iterable, style: Optional[str] = None):
    """Insert several paragraphs in order; items are str or (label, text). Returns the last one."""
    last = anchor
    for it in items:
        if isinstance(it, tuple):
            last = add_paragraph_after(last, it[1], style=style, label=it[0])
        else:
            last = add_paragraph_after(last, it, style=style)
    return last


def remove(el_or_obj) -> None:
    el = el_or_obj._element if hasattr(el_or_obj, "_element") else el_or_obj
    el.getparent().remove(el)


# ----------------------------------------------------------------------------- tables

def _set_cell_shading(cell: _Cell, fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def set_cell(cell: _Cell, text: str, bold: bool = False, size: Optional[float] = None,
             align: Optional[str] = None) -> None:
    """Replace a cell's content with text; newlines become separate paragraphs."""
    lines = str(text).split("\n")
    paras = cell.paragraphs
    for extra in paras[1:]:
        remove(extra)
    p = paras[0]
    set_text(p, lines[0], bold=bold)
    if not p.runs:
        p.add_run(lines[0]).bold = bold
    for r in p.runs:
        if size:
            r.font.size = Pt(size)
    for line in lines[1:]:
        np_ = cell.add_paragraph()
        r = np_.add_run(line)
        r.bold = bold
        if size:
            r.font.size = Pt(size)
    if align == "center":
        for q in cell.paragraphs:
            q.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _borders(tbl_el) -> None:
    tblPr = tbl_el.find(qn("w:tblPr"))
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{edge}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "808080")
        borders.append(b)
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    tblPr.append(borders)


def add_table_after(doc: Document, anchor, rows: Sequence[Sequence[str]], widths_cm: Sequence[float],
                    header: bool = True, size: float = 9.0, first_col_bold: bool = False) -> Table:
    """Insert a bordered table after a paragraph/table. rows[0] is the header if header=True."""
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    _borders(t._tbl)
    t.autofit = False
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = t.rows[ri].cells[ci]
            cell.width = Cm(widths_cm[ci])
            is_head = header and ri == 0
            set_cell(cell, val, bold=is_head or (first_col_bold and ci == 0), size=size)
            if is_head:
                _set_cell_shading(cell, HEADER_FILL)
    # Column widths on the grid too, so Word respects them
    grid = t._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths_cm):
        gc.set(qn("w:w"), str(int(Cm(w).twips)))
    el = anchor._element if hasattr(anchor, "_element") else anchor
    el.addnext(t._tbl)
    return t


def fill_table(table: Table, rows: Sequence[Sequence[str]], start_row: int = 1, size: Optional[float] = None,
               bold_first_col: bool = False) -> None:
    """Fill a template table from start_row, cloning the last row when more rows are needed."""
    needed = start_row + len(rows)
    while len(table.rows) < needed:
        table._tbl.append(copy.deepcopy(table.rows[-1]._tr))
    while len(table.rows) > needed:
        table._tbl.remove(table.rows[-1]._tr)
    for i, row in enumerate(rows):
        cells = table.rows[start_row + i].cells
        for ci, val in enumerate(row):
            if val is None:
                continue
            set_cell(cells[ci], val, bold=(bold_first_col and ci == 0), size=size)


def fill_key_value_table(table: Table, values: Sequence[str], size: Optional[float] = None) -> None:
    """Fill column 2 of a 2-column 'label | value' template table, row by row."""
    for row, val in zip(table.rows, values):
        set_cell(row.cells[1], val, size=size)


def fill_students(table: Table) -> None:
    """Names in the 'Name of the students' column; Group/Roll/Div left blank for the students."""
    fill_table(table, [[None, None, None, n] for n in STUDENTS], start_row=1)


# ----------------------------------------------------------------------------- figures

def add_picture_after(anchor, path: str, width_cm: float, caption: Optional[str] = None) -> Paragraph:
    """Centred picture paragraph (and optional caption) after the anchor; returns the last paragraph."""
    p = _new_paragraph_after(anchor)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    last = p
    if caption:
        last = add_paragraph_after(p, caption, italic=True, size=9, align="center")
    return last


def clear_body_after(doc: Document, keep_until) -> None:
    """Delete every body element after keep_until, except the final section properties."""
    body = doc.element.body
    keep_el = keep_until._element if hasattr(keep_until, "_element") else keep_until
    found = False
    for el in list(body.iterchildren()):
        if found and el.tag != qn("w:sectPr"):
            body.remove(el)
        if el is keep_el:
            found = True


def append_heading(doc: Document, text: str) -> Paragraph:
    return doc.add_paragraph(text, style="Heading 1")


def append_para(doc: Document, text: str = "", label: Optional[str] = None, bold: bool = False,
                italic: bool = False, align: Optional[str] = None, size: Optional[float] = None) -> Paragraph:
    p = doc.add_paragraph()
    if label:
        r = p.add_run(f"{label}: ")
        r.bold = True
        if size:
            r.font.size = Pt(size)
    if text:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        if size:
            r.font.size = Pt(size)
    if align == "justify":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def append_table(doc: Document, rows: Sequence[Sequence[str]], widths_cm: Sequence[float], header: bool = True,
                 size: float = 9.0, first_col_bold: bool = False) -> Table:
    anchor = doc.add_paragraph()
    t = add_table_after(doc, anchor, rows, widths_cm, header=header, size=size, first_col_bold=first_col_bold)
    remove(anchor)
    doc.add_paragraph()  # spacing after the table
    return t


def append_picture(doc: Document, path: str, width_cm: float, caption: Optional[str] = None) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    if caption:
        append_para(doc, caption, italic=True, align="center", size=9)


def placeholder(text: str) -> str:
    """Visible marker for information only the students can supply."""
    return f"[{text}]"
