"""Petits outils pour écrire le rapport Word avec python-docx (titres, paragraphes, tableaux, figures)."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

INK = RGBColor(0x0B, 0x0B, 0x0B)
INK2 = RGBColor(0x52, 0x51, 0x4E)
ACCENT = RGBColor(0x25, 0x6A, 0xBF)
HEADER_FILL = "E8F0FB"


class Rapport:
    def __init__(self):
        self.doc = Document()
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)          # A4
        sec.left_margin = sec.right_margin = Cm(2.2)
        sec.top_margin = sec.bottom_margin = Cm(2.0)
        st = self.doc.styles["Normal"]
        st.font.name, st.font.size = "Calibri", Pt(10.5)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
        st.paragraph_format.space_after = Pt(5)
        st.paragraph_format.line_spacing = 1.12
        for lvl, size in [(1, 15), (2, 12.5), (3, 11)]:
            h = self.doc.styles[f"Heading {lvl}"]
            h.font.name, h.font.size, h.font.color.rgb, h.font.bold = "Calibri", Pt(size), ACCENT if lvl == 1 else INK, True
            h.paragraph_format.space_before = Pt(14 if lvl == 1 else 9)
            h.paragraph_format.space_after = Pt(4)
        self.n_fig = 0
        self.n_tab = 0
        self._footer_page_numbers()

    # ---- texte -----------------------------------------------------------------
    def h(self, text: str, level: int = 1):
        self.doc.add_heading(text, level=level)

    def p(self, text: str, style: str | None = None, align=None, size: float | None = None, italic=False):
        """Paragraphe ; **gras**, *italique* et `code` (police à chasse fixe) en ligne sont interprétés."""
        par = self.doc.add_paragraph(style=style)
        for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)", text):
            if not part:
                continue
            if part.startswith("**"):
                run = par.add_run(part[2:-2]); run.bold = True
            elif part.startswith("*"):
                run = par.add_run(part[1:-1]); run.italic = True
            elif part.startswith("`"):
                run = par.add_run(part[1:-1]); run.font.name = "Consolas"; run.font.size = Pt(9.5)
            else:
                run = par.add_run(part)
            if size:
                run.font.size = Pt(size)
            if italic:
                run.italic = True
        if align:
            par.alignment = align
        return par

    def bullets(self, items: list[str], numbered: bool = False):
        for it in items:
            self.p(it, style="List Number" if numbered else "List Bullet")

    def encadre(self, text: str):
        """Paragraphe mis en évidence (fond bleu clair)."""
        par = self.p(text)
        pPr = par._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), HEADER_FILL)
        pPr.append(shd)
        par.paragraph_format.left_indent = Cm(0.2)
        return par

    # ---- figures et tableaux ----------------------------------------------------------
    def figure(self, path: Path, caption: str, width_cm: float = 16.5):
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.add_run().add_picture(str(path), width=Cm(width_cm))
        par.paragraph_format.keep_with_next = True
        self.n_fig += 1
        self._caption(f"Figure {self.n_fig}. {caption}")
        return self.n_fig

    def table(self, df: pd.DataFrame, caption: str, col_widths_cm: list[float] | None = None,
              font_size: float = 8.5, bold_rows: list[int] | None = None):
        self.n_tab += 1
        cap = self._caption(f"Tableau {self.n_tab}. {caption}")
        cap.paragraph_format.keep_with_next = True
        t = self.doc.add_table(rows=1, cols=len(df.columns))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for j, c in enumerate(df.columns):
            cell = t.rows[0].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(c)); run.bold = True; run.font.size = Pt(font_size)
            self._shade(cell, HEADER_FILL)
        for i, row in enumerate(df.itertuples(index=False)):
            cells = t.add_row().cells
            for j, v in enumerate(row):
                cells[j].text = ""
                run = cells[j].paragraphs[0].add_run("" if pd.isna(v) else str(v))
                run.font.size = Pt(font_size)
                if bold_rows and i in bold_rows:
                    run.bold = True
        if col_widths_cm:
            for row in t.rows:
                for j, w in enumerate(col_widths_cm):
                    row.cells[j].width = Cm(w)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return self.n_tab

    def page_break(self):
        self.doc.add_page_break()

    def save(self, path: Path):
        self.doc.save(str(path))

    # ---- interne -------------------------------------------------------------------------
    def _caption(self, text: str):
        par = self.doc.add_paragraph()
        run = par.add_run(text); run.italic = True; run.font.size = Pt(9); run.font.color.rgb = INK2
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return par

    @staticmethod
    def _shade(cell, fill: str):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

    def _footer_page_numbers(self):
        par = self.doc.sections[0].footer.paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = par.add_run()
        for tag, text in [("begin", None), (None, "PAGE"), ("end", None)]:
            if tag:
                el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), tag); run._r.append(el)
            else:
                el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = text; run._r.append(el)
        run.font.size = Pt(9); run.font.color.rgb = INK2


def docx_to_pdf(docx_path: Path, pdf_path: Path) -> None:
    """Export PDF via Microsoft Word (automatisation COM, Windows)."""
    import win32com.client  # type: ignore
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        d = word.Documents.Open(str(docx_path.resolve()))
        d.Fields.Update()
        d.SaveAs(str(pdf_path.resolve()), FileFormat=17)   # 17 = PDF
        d.Close(False)
    finally:
        word.Quit()
