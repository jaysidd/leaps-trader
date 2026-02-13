#!/usr/bin/env python3
"""
Generate a self-contained PDF guide explaining each prompt in the trading prompt library.

Design goals:
- No external dependencies (standard library only).
- Vector charts/diagrams and tables rendered directly into the PDF content streams.
- Educational content only (not financial advice).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import math
import os
import re
import textwrap
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple


Color = Tuple[float, float, float]

PAGE_W = 612.0  # Letter: 8.5in * 72
PAGE_H = 792.0  # Letter: 11in * 72
MARGIN = 54.0   # 0.75in


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _rgb(r: float, g: float, b: float) -> Color:
    return (_clamp01(r), _clamp01(g), _clamp01(b))


COLORS = {
    "text": _rgb(0.10, 0.12, 0.16),
    "muted": _rgb(0.45, 0.50, 0.58),
    "rule": _rgb(0.85, 0.88, 0.92),
    "bg_soft": _rgb(0.97, 0.98, 0.99),
    "accent": _rgb(0.12, 0.46, 0.80),
    "green": _rgb(0.12, 0.70, 0.32),
    "red": _rgb(0.86, 0.18, 0.17),
    "orange": _rgb(0.95, 0.55, 0.10),
    "purple": _rgb(0.55, 0.29, 0.78),
}


def sanitize_text(s: str) -> str:
    """
    Keep the PDF generator dependency-free by sticking to mostly-ASCII output.
    Replace common punctuation/symbols with ASCII equivalents and strip the rest.
    """
    replacements = {
        "≥": ">=",
        "≤": "<=",
        "→": "->",
        "←": "<-",
        "•": "-",
        "–": "-",
        "—": "-",
        "“": "\"",
        "”": "\"",
        "’": "'",
        "…": "...",
        "↔": "<->",
        "×": "x",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)

    # Strip emoji (like 1️⃣) and other non-ascii characters.
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")

    # Collapse weird whitespace.
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def escape_pdf_text(s: str) -> str:
    # PDF string literal escaping for () and backslashes.
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def approx_text_width(text: str, font_size: float, font: str) -> float:
    # Rough heuristic. Good enough for wrapping.
    base = 0.52
    if font in ("F2",):  # bold
        base = 0.56
    if font in ("F4",):  # Courier
        base = 0.60
    return len(text) * font_size * base


def wrap_text(text: str, max_width: float, font_size: float, font: str) -> List[str]:
    text = sanitize_text(text)
    if not text:
        return [""]

    words = text.split(" ")
    lines: List[str] = []
    current: List[str] = []
    for word in words:
        candidate = (" ".join(current + [word])).strip()
        if not candidate:
            continue
        if approx_text_width(candidate, font_size, font) <= max_width or not current:
            current.append(word)
            continue
        lines.append(" ".join(current))
        current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


class PdfBuilder:
    def __init__(self) -> None:
        self._pages: List[str] = []
        self._cur: List[str] = []

    def new_page(self) -> None:
        if self._cur:
            self._pages.append("".join(self._cur))
        self._cur = []

    def _add(self, cmd: str) -> None:
        self._cur.append(cmd + "\n")

    def set_stroke_color(self, c: Color) -> None:
        r, g, b = c
        self._add(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def set_fill_color(self, c: Color) -> None:
        r, g, b = c
        self._add(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def set_line_width(self, w: float) -> None:
        self._add(f"{w:.2f} w")

    def line(self, x1: float, y1: float, x2: float, y2: float, *, w: float = 1.0, color: Color = COLORS["rule"]) -> None:
        self.set_line_width(w)
        self.set_stroke_color(color)
        self._add(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x: float, y: float, w: float, h: float, *, fill: Optional[Color] = None, stroke: Optional[Color] = None, stroke_w: float = 1.0) -> None:
        if fill is not None and stroke is not None:
            self.set_fill_color(fill)
            self.set_stroke_color(stroke)
            self.set_line_width(stroke_w)
            self._add(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re B")
            return
        if fill is not None:
            self.set_fill_color(fill)
            self._add(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
            return
        if stroke is not None:
            self.set_stroke_color(stroke)
            self.set_line_width(stroke_w)
            self._add(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def polyline(self, pts: Sequence[Tuple[float, float]], *, w: float = 1.5, color: Color = COLORS["accent"], dash: Optional[Tuple[float, float]] = None) -> None:
        if len(pts) < 2:
            return
        self.set_line_width(w)
        self.set_stroke_color(color)
        if dash is not None:
            a, b = dash
            self._add(f"[{a:.2f} {b:.2f}] 0 d")
        else:
            self._add("[] 0 d")
        x0, y0 = pts[0]
        self._add(f"{x0:.2f} {y0:.2f} m")
        for x, y in pts[1:]:
            self._add(f"{x:.2f} {y:.2f} l")
        self._add("S")
        self._add("[] 0 d")

    def circle(self, cx: float, cy: float, r: float, *, fill: Optional[Color] = None, stroke: Optional[Color] = None, stroke_w: float = 1.0) -> None:
        # Approximate circle with 4 Bézier curves.
        k = 0.552284749831  # control point constant
        self.set_line_width(stroke_w)
        if fill is not None:
            self.set_fill_color(fill)
        if stroke is not None:
            self.set_stroke_color(stroke)
        x0 = cx + r
        y0 = cy
        c = k * r
        ops = []
        ops.append(f"{x0:.2f} {y0:.2f} m")
        ops.append(f"{(cx + r):.2f} {(cy + c):.2f} {(cx + c):.2f} {(cy + r):.2f} {cx:.2f} {(cy + r):.2f} c")
        ops.append(f"{(cx - c):.2f} {(cy + r):.2f} {(cx - r):.2f} {(cy + c):.2f} {(cx - r):.2f} {cy:.2f} c")
        ops.append(f"{(cx - r):.2f} {(cy - c):.2f} {(cx - c):.2f} {(cy - r):.2f} {cx:.2f} {(cy - r):.2f} c")
        ops.append(f"{(cx + c):.2f} {(cy - r):.2f} {(cx + r):.2f} {(cy - c):.2f} {(cx + r):.2f} {cy:.2f} c")
        self._add("\n".join(ops))
        if fill is not None and stroke is not None:
            self._add("B")
        elif fill is not None:
            self._add("f")
        else:
            self._add("S")

    def text(self, x: float, y: float, s: str, *, font: str = "F1", size: float = 11.0, color: Color = COLORS["text"]) -> None:
        s = escape_pdf_text(sanitize_text(s))
        r, g, b = color
        self._add("BT")
        self._add(f"/{font} {size:.2f} Tf")
        self._add(f"{r:.3f} {g:.3f} {b:.3f} rg")
        self._add(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        self._add(f"({s}) Tj")
        self._add("ET")

    def write(self, out_path: str) -> None:
        if self._cur:
            self._pages.append("".join(self._cur))
            self._cur = []

        pages = self._pages
        if not pages:
            raise RuntimeError("No pages to write.")

        # Object numbering:
        # 1 Catalog
        # 2 Pages
        # 3 Helvetica (F1)
        # 4 Helvetica-Bold (F2)
        # 5 Helvetica-Oblique (F3)
        # 6 Courier (F4)
        # 7.. page+content objects
        font_objs = [
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        ]

        def obj(n: int, body: bytes) -> bytes:
            return f"{n} 0 obj\n".encode("ascii") + body + b"\nendobj\n"

        out: List[bytes] = []
        out.append(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        page_obj_nums: List[int] = []
        content_obj_nums: List[int] = []
        first_page_obj = 7
        for i in range(len(pages)):
            page_obj_nums.append(first_page_obj + i * 2)
            content_obj_nums.append(first_page_obj + i * 2 + 1)

        kids = " ".join([f"{n} 0 R" for n in page_obj_nums]).encode("ascii")
        pages_obj_body = b"<< /Type /Pages /Kids [ " + kids + b" ] /Count " + str(len(pages)).encode("ascii") + b" >>"

        out.append(obj(1, b"<< /Type /Catalog /Pages 2 0 R >>"))
        out.append(obj(2, pages_obj_body))
        out.append(obj(3, font_objs[0]))
        out.append(obj(4, font_objs[1]))
        out.append(obj(5, font_objs[2]))
        out.append(obj(6, font_objs[3]))

        for i, content in enumerate(pages):
            content_bytes = content.encode("latin-1", errors="ignore")
            stream = b"<< /Length " + str(len(content_bytes)).encode("ascii") + b" >>\nstream\n" + content_bytes + b"\nendstream"
            content_obj_n = content_obj_nums[i]
            page_obj_n = page_obj_nums[i]

            resources = b"<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >>"
            page_body = (
                b"<< /Type /Page /Parent 2 0 R "
                b"/MediaBox [0 0 "
                + str(int(PAGE_W)).encode("ascii")
                + b" "
                + str(int(PAGE_H)).encode("ascii")
                + b"] "
                b"/Resources "
                + resources
                + b" /Contents "
                + f"{content_obj_n} 0 R".encode("ascii")
                + b" >>"
            )

            out.append(obj(page_obj_n, page_body))
            out.append(obj(content_obj_n, stream))

        # Build xref
        xref_offsets: List[int] = [0]
        pdf_bytes = b"".join(out)
        # Offsets are measured from start; we need offsets of each object.
        # Rebuild with tracking to keep it correct.
        out2: List[bytes] = []
        out2.append(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        def append_obj_with_offset(blob: bytes) -> None:
            xref_offsets.append(len(b"".join(out2)))
            out2.append(blob)

        append_obj_with_offset(obj(1, b"<< /Type /Catalog /Pages 2 0 R >>"))
        append_obj_with_offset(obj(2, pages_obj_body))
        append_obj_with_offset(obj(3, font_objs[0]))
        append_obj_with_offset(obj(4, font_objs[1]))
        append_obj_with_offset(obj(5, font_objs[2]))
        append_obj_with_offset(obj(6, font_objs[3]))
        for i, content in enumerate(pages):
            content_bytes = content.encode("latin-1", errors="ignore")
            stream = b"<< /Length " + str(len(content_bytes)).encode("ascii") + b" >>\nstream\n" + content_bytes + b"\nendstream"
            content_obj_n = content_obj_nums[i]
            page_obj_n = page_obj_nums[i]

            resources = b"<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >>"
            page_body = (
                b"<< /Type /Page /Parent 2 0 R "
                b"/MediaBox [0 0 "
                + str(int(PAGE_W)).encode("ascii")
                + b" "
                + str(int(PAGE_H)).encode("ascii")
                + b"] "
                b"/Resources "
                + resources
                + b" /Contents "
                + f"{content_obj_n} 0 R".encode("ascii")
                + b" >>"
            )

            append_obj_with_offset(obj(page_obj_n, page_body))
            append_obj_with_offset(obj(content_obj_n, stream))

        xref_start = len(b"".join(out2))
        total_objs = 6 + len(pages) * 2
        xref_lines = [b"xref\n", f"0 {total_objs + 1}\n".encode("ascii")]
        xref_lines.append(b"0000000000 65535 f \n")
        for off in xref_offsets[1:]:
            xref_lines.append(f"{off:010d} 00000 n \n".encode("ascii"))
        xref = b"".join(xref_lines)

        trailer = (
            b"trailer\n"
            + b"<< /Size "
            + str(total_objs + 1).encode("ascii")
            + b" /Root 1 0 R >>\n"
            + b"startxref\n"
            + str(xref_start).encode("ascii")
            + b"\n%%EOF\n"
        )

        final_pdf = b"".join(out2) + xref + trailer
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(final_pdf)


class Layout:
    def __init__(self, pdf: PdfBuilder) -> None:
        self.pdf = pdf
        self.x = MARGIN
        self.w = PAGE_W - 2 * MARGIN
        self.y = PAGE_H - MARGIN
        self._page_no = 0
        self._new_page()

    def _new_page(self) -> None:
        if self._page_no > 0:
            self.pdf.new_page()
        self._page_no += 1
        self.y = PAGE_H - MARGIN

        # Header rule (skip on title page by caller).
        # Draw faint page number footer.
        self.pdf.text(PAGE_W - MARGIN, MARGIN - 22, f"{self._page_no}", font="F3", size=9, color=COLORS["muted"])

    def ensure(self, needed_height: float) -> None:
        if self.y - needed_height < MARGIN:
            self._new_page()

    def spacer(self, h: float) -> None:
        self.ensure(h)
        self.y -= h

    def hr(self) -> None:
        self.ensure(12)
        self.pdf.line(self.x, self.y, self.x + self.w, self.y, w=1.0, color=COLORS["rule"])
        self.y -= 12

    def h1(self, text: str) -> None:
        self.ensure(44)
        self.pdf.text(self.x, self.y, text, font="F2", size=22, color=COLORS["text"])
        self.y -= 28
        self.hr()

    def h2(self, text: str) -> None:
        self.ensure(34)
        self.pdf.text(self.x, self.y, text, font="F2", size=16, color=COLORS["text"])
        self.y -= 22

    def h3(self, text: str) -> None:
        self.ensure(26)
        self.pdf.text(self.x, self.y, text, font="F2", size=13, color=COLORS["text"])
        self.y -= 18

    def label(self, key: str, value: str) -> None:
        self.ensure(18)
        self.pdf.text(self.x, self.y, f"{key}: ", font="F2", size=10.5, color=COLORS["text"])
        self.pdf.text(self.x + 60, self.y, value, font="F1", size=10.5, color=COLORS["text"])
        self.y -= 14

    def paragraph(self, text: str, *, font: str = "F1", size: float = 11.0, color: Color = COLORS["text"], leading: float = 14.0) -> None:
        lines = wrap_text(text, self.w, size, font)
        block_h = len(lines) * leading + 6
        self.ensure(block_h)
        for line in lines:
            self.pdf.text(self.x, self.y, line, font=font, size=size, color=color)
            self.y -= leading
        self.y -= 6

    def bullets(self, items: Sequence[str], *, size: float = 10.8, leading: float = 13.5) -> None:
        bullet_indent = 12.0
        text_x = self.x + bullet_indent
        max_w = self.w - bullet_indent

        for item in items:
            lines = wrap_text(item, max_w, size, "F1")
            block_h = len(lines) * leading + 2
            self.ensure(block_h)
            self.pdf.text(self.x, self.y, "-", font="F2", size=size, color=COLORS["text"])
            for i, line in enumerate(lines):
                self.pdf.text(text_x, self.y, line, font="F1", size=size, color=COLORS["text"])
                self.y -= leading
            self.y -= 2

        self.y -= 4

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[str]], col_widths: Sequence[float]) -> None:
        assert len(headers) == len(col_widths)
        for r in rows:
            assert len(r) == len(headers)

        pad_x = 6.0
        pad_y = 5.0
        font = "F1"
        size = 9.6
        leading = 12.0

        def row_height(cells: Sequence[str]) -> float:
            heights = []
            for i, cell in enumerate(cells):
                lines = wrap_text(cell, col_widths[i] - 2 * pad_x, size, font)
                heights.append(len(lines) * leading + 2 * pad_y)
            return max(heights) if heights else (leading + 2 * pad_y)

        header_h = row_height(headers)
        total_h = header_h + sum(row_height(r) for r in rows)
        self.ensure(total_h + 10)

        # Header background.
        self.pdf.rect(self.x, self.y - header_h + 2, sum(col_widths), header_h, fill=COLORS["bg_soft"], stroke=COLORS["rule"], stroke_w=1.0)

        # Draw header text.
        cx = self.x
        for i, htxt in enumerate(headers):
            lines = wrap_text(htxt, col_widths[i] - 2 * pad_x, size, "F2")
            ty = self.y - pad_y - size
            for line in lines:
                self.pdf.text(cx + pad_x, ty, line, font="F2", size=size, color=COLORS["text"])
                ty -= leading
            cx += col_widths[i]

        # Header grid lines.
        self.pdf.line(self.x, self.y + 2, self.x + sum(col_widths), self.y + 2, w=1.0, color=COLORS["rule"])
        self.pdf.line(self.x, self.y - header_h + 2, self.x + sum(col_widths), self.y - header_h + 2, w=1.0, color=COLORS["rule"])
        cx = self.x
        for w in col_widths:
            self.pdf.line(cx, self.y + 2, cx, self.y - header_h + 2, w=1.0, color=COLORS["rule"])
            cx += w
        self.pdf.line(self.x + sum(col_widths), self.y + 2, self.x + sum(col_widths), self.y - header_h + 2, w=1.0, color=COLORS["rule"])

        # Rows.
        y = self.y - header_h + 2
        for r in rows:
            rh = row_height(r)
            self.pdf.rect(self.x, y - rh, sum(col_widths), rh, fill=None, stroke=COLORS["rule"], stroke_w=1.0)
            cx = self.x
            for i, cell in enumerate(r):
                lines = wrap_text(cell, col_widths[i] - 2 * pad_x, size, font)
                ty = y - pad_y - size
                for line in lines:
                    self.pdf.text(cx + pad_x, ty, line, font=font, size=size, color=COLORS["text"])
                    ty -= leading
                cx += col_widths[i]
            # vertical lines
            cx = self.x
            for w in col_widths:
                self.pdf.line(cx, y, cx, y - rh, w=1.0, color=COLORS["rule"])
                cx += w
            self.pdf.line(self.x + sum(col_widths), y, self.x + sum(col_widths), y - rh, w=1.0, color=COLORS["rule"])
            y -= rh

        self.y = y - 10

    def figure(self, caption: str, draw_fn: Callable[[float, float, float, float], None], *, height: float = 190.0) -> None:
        caption_lines = wrap_text(caption, self.w, 9.5, "F3")
        needed = height + len(caption_lines) * 12 + 18
        self.ensure(needed)

        # Figure frame.
        fig_x = self.x
        fig_y = self.y - height
        self.pdf.rect(fig_x, fig_y, self.w, height, fill=COLORS["bg_soft"], stroke=COLORS["rule"], stroke_w=1.0)

        draw_fn(fig_x + 10, fig_y + 10, self.w - 20, height - 20)

        self.y = fig_y - 8
        for line in caption_lines:
            self.pdf.text(self.x, self.y, line, font="F3", size=9.5, color=COLORS["muted"])
            self.y -= 12
        self.y -= 6


def _scale_series_to_rect(values: Sequence[float], x: float, y: float, w: float, h: float) -> List[Tuple[float, float]]:
    if not values:
        return []
    vmin = min(values)
    vmax = max(values)
    pad = (vmax - vmin) * 0.12 if vmax != vmin else 1.0
    vmin -= pad
    vmax += pad
    pts: List[Tuple[float, float]] = []
    for i, v in enumerate(values):
        px = x + (w * i) / (len(values) - 1 if len(values) > 1 else 1)
        t = (v - vmin) / (vmax - vmin) if vmax != vmin else 0.5
        py = y + t * h
        pts.append((px, py))
    return pts


def _moving_avg(values: Sequence[float], window: int) -> List[float]:
    if window <= 1:
        return list(values)
    out: List[float] = []
    q: List[float] = []
    for v in values:
        q.append(v)
        if len(q) > window:
            q.pop(0)
        out.append(sum(q) / len(q))
    return out


def draw_price_chart(pdf: PdfBuilder, x: float, y: float, w: float, h: float, price: Sequence[float], *, vwap: Optional[Sequence[float]] = None, hlines: Sequence[Tuple[float, str, Color]] = (), bands: Sequence[Tuple[float, float, str, Color]] = (), markers: Sequence[Tuple[int, str, Color]] = ()) -> None:
    # Plot area
    pdf.rect(x, y, w, h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)
    pad = 28.0
    ax_x = x + pad
    ax_y = y + pad
    ax_w = w - 2 * pad
    ax_h = h - 2 * pad
    pdf.rect(ax_x, ax_y, ax_w, ax_h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)

    # Axes labels (minimal)
    pdf.text(ax_x, y + 8, "Time ->", font="F3", size=8.5, color=COLORS["muted"])
    pdf.text(x + 4, ax_y + ax_h - 6, "Price", font="F3", size=8.5, color=COLORS["muted"])

    price_pts = _scale_series_to_rect(price, ax_x, ax_y, ax_w, ax_h)
    pdf.polyline(price_pts, w=2.0, color=COLORS["accent"])

    if vwap is not None:
        vwap_pts = _scale_series_to_rect(vwap, ax_x, ax_y, ax_w, ax_h)
        pdf.polyline(vwap_pts, w=1.5, color=COLORS["purple"], dash=(3.0, 2.0))
        pdf.text(ax_x + 6, ax_y + 10, "VWAP", font="F3", size=8.5, color=COLORS["purple"])

    # Horizontal bands (normalized by using chart y-scale based on price series)
    # We map band y-values using the same scaling function by constructing helper.
    vmin = min(price)
    vmax = max(price)
    pad_v = (vmax - vmin) * 0.12 if vmax != vmin else 1.0
    vmin -= pad_v
    vmax += pad_v

    def y_from_val(v: float) -> float:
        t = (v - vmin) / (vmax - vmin) if vmax != vmin else 0.5
        return ax_y + t * ax_h

    for lo, hi, label, color in bands:
        y0 = y_from_val(lo)
        y1 = y_from_val(hi)
        by = min(y0, y1)
        bh = abs(y1 - y0)
        pdf.rect(ax_x, by, ax_w, bh, fill=(color[0], color[1], color[2]), stroke=None)
        pdf.text(ax_x + 6, by + bh - 10, label, font="F3", size=8.5, color=COLORS["muted"])

    for val, label, color in hlines:
        yy = y_from_val(val)
        pdf.line(ax_x, yy, ax_x + ax_w, yy, w=1.0, color=color)
        pdf.text(ax_x + ax_w - 120, yy + 3, label, font="F3", size=8.5, color=color)

    for idx, label, color in markers:
        if idx < 0 or idx >= len(price_pts):
            continue
        mx, my = price_pts[idx]
        pdf.circle(mx, my, 4.0, fill=_rgb(1, 1, 1), stroke=color, stroke_w=1.3)
        pdf.text(mx + 6, my + 6, label, font="F3", size=8.5, color=color)


def draw_payoff_chart(pdf: PdfBuilder, x: float, y: float, w: float, h: float, title: str, xs: Sequence[float], ys: Sequence[float], *, bands: Sequence[Tuple[float, float, str, Color]] = ()) -> None:
    pdf.rect(x, y, w, h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)
    pad = 28.0
    ax_x = x + pad
    ax_y = y + pad
    ax_w = w - 2 * pad
    ax_h = h - 2 * pad
    pdf.rect(ax_x, ax_y, ax_w, ax_h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)

    pdf.text(x + 6, y + h - 18, title, font="F2", size=10.5, color=COLORS["text"])
    pdf.text(ax_x, y + 8, "Underlying Price ->", font="F3", size=8.5, color=COLORS["muted"])
    pdf.text(x + 4, ax_y + ax_h - 6, "P/L", font="F3", size=8.5, color=COLORS["muted"])

    if not xs or not ys or len(xs) != len(ys):
        return

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad_y = (ymax - ymin) * 0.20 if ymax != ymin else 1.0
    ymin -= pad_y
    ymax += pad_y

    def px(v: float) -> float:
        t = (v - xmin) / (xmax - xmin) if xmax != xmin else 0.5
        return ax_x + t * ax_w

    def py(v: float) -> float:
        t = (v - ymin) / (ymax - ymin) if ymax != ymin else 0.5
        return ax_y + t * ax_h

    # 0 line
    pdf.line(ax_x, py(0.0), ax_x + ax_w, py(0.0), w=1.0, color=COLORS["muted"])
    pdf.text(ax_x + ax_w - 60, py(0.0) + 3, "P/L=0", font="F3", size=8.0, color=COLORS["muted"])

    for lo, hi, label, color in bands:
        bx0 = px(lo)
        bx1 = px(hi)
        pdf.rect(min(bx0, bx1), ax_y, abs(bx1 - bx0), ax_h, fill=(color[0], color[1], color[2]), stroke=None)
        pdf.text(min(bx0, bx1) + 4, ax_y + ax_h - 12, label, font="F3", size=8.0, color=COLORS["muted"])

    pts = [(px(xv), py(yv)) for xv, yv in zip(xs, ys)]
    pdf.polyline(pts, w=2.0, color=COLORS["accent"])


def make_doc(pdf: PdfBuilder) -> None:
    l = Layout(pdf)

    # Title page
    l.h1("Trading Prompt Library Guide (Stocks & Options)")
    l.paragraph("Educational reference only - not financial advice. Examples are synthetic and simplified.")
    l.paragraph("Goal: explain what each prompt is trying to capture, when it tends to work, how it fails, what data is required, and how to interpret the outputs.")
    l.paragraph(f"Generated: {_dt.date.today().isoformat()}")
    l.spacer(10)
    l.table(
        headers=["How to Use", "Key Rule"],
        rows=[
            ["Provide required data fields", "If data is missing, the assistant must respond with NEEDED DATA (no guessing)."],
            ["Trade selection", "Only accept setups with confluence score >= needed_score and confidence >= min_confidence."],
            ["Risk first", "Stops must be structural + volatility-aware (ATR). Define invalidation explicitly."],
        ],
        col_widths=[l.w * 0.40, l.w * 0.60],
    )
    l.paragraph("Disclaimer: Institutions combine signals with position sizing, execution, and risk controls. A prompt template is not an edge by itself.", font="F3", size=10.2, color=COLORS["muted"])

    l._new_page()

    # Quick index
    l.h1("Index")
    l.paragraph("This guide is organized by asset class, horizon, and style.")
    l.h2("Stocks")
    l.bullets([
        "Intraday - Trend: ORB+VWAP, VWAP Pullback Trend, HOD/LOD Break",
        "Intraday - Mean Reversion: VWAP Stretch MR, Band Re-entry MR, Gap Fill MR",
        "Swing - Trend: Base Breakout, Pullback-to-MA, VCP Breakout",
        "Swing - Mean Reversion: Oversold Bounce, Pairs/Ratio Z-Score",
    ])
    l.h2("Options")
    l.bullets([
        "Intraday - Trend: Defined-Risk Debit Spread, 0DTE/1DTE Defined Risk (index/ETF only)",
        "Intraday - Mean Reversion: Credit Spread Fade, Iron Condor (range only)",
        "Swing - Trend: Debit vs Diagonal, Protective Put/Collar",
        "Swing - Mean Reversion: High-IV Mean Reversion (defined risk), Earnings Volatility Crush (event-driven)",
    ])
    l.h2("Meta / Utilities")
    l.bullets([
        "Regime Selector (trend vs range vs mixed)",
        "Multi-Symbol Scanner (pick 1 best setup across a watchlist)",
    ])

    # Helper: consistent prompt section rendering
    def prompt_section(category: str, title: str, description: str, what: str, mechanics: Sequence[str], checklist: Sequence[Tuple[str, str]], figure_caption: str, figure_draw: Callable[[float, float, float, float], None]) -> None:
        l._new_page()
        l.h2(category)
        l.h3(title)
        l.paragraph(description, font="F3", size=10.5, color=COLORS["muted"])
        l.h3("What it is")
        l.paragraph(what)
        l.h3("Mechanics (high level)")
        l.bullets(mechanics)
        l.h3("Checklist")
        l.table(headers=["Item", "Rule of thumb / notes"], rows=list(checklist), col_widths=[l.w * 0.36, l.w * 0.64])
        l.h3("Example (synthetic)")
        l.figure(figure_caption, figure_draw, height=210.0)

    # --- Stocks: Intraday Trend ---
    intraday_base = [100.0, 100.2, 100.1, 100.25, 100.3, 100.35, 100.4, 100.9, 101.2, 101.0, 101.25, 101.6, 101.4, 101.9, 102.2, 102.0]
    intraday_vwap = _moving_avg(intraday_base, 5)

    def fig_orb(x: float, y: float, w: float, h: float) -> None:
        or_lo = min(intraday_base[0:3])
        or_hi = max(intraday_base[0:3])
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            intraday_base,
            vwap=intraday_vwap,
            bands=[(or_lo, or_hi, "Opening Range", _rgb(0.90, 0.95, 1.00))],
            markers=[(7, "Break+Close", COLORS["green"]), (9, "Pullback", COLORS["orange"]), (10, "Entry", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Intraday - Trend",
        "ORB + VWAP Trend Continuation",
        "Finds a trend-following intraday setup using an Opening Range Break (ORB) confirmed by VWAP + volume + market proxy alignment.",
        "A classic momentum template: price breaks the opening range in the direction of the higher-timeframe trend, then continues after a brief pullback. VWAP helps separate true continuation from chop.",
        mechanics=[
            "Define opening range from the first completed M15 candle after cash open.",
            "Trade only in the H1 trend direction (EMA stack + structure).",
            "Require break AND close beyond ORH/ORL (avoid wick-only breaks).",
            "Prefer a pullback/retest (OR level or VWAP) before entry.",
            "Stops: beyond pullback swing + ATR buffer; exits: partial + trail.",
        ],
        checklist=[
            ("Regime", "Trending day or post-open expansion; avoid midday chop unless volatility is expanding."),
            ("VWAP", "Longs generally above VWAP; shorts generally below VWAP. Reclaims/loses matter."),
            ("Volume", "Break candle volume > ~1.2x 20-bar avg (or RVOL elevated)."),
            ("Risk", "RR >= rr_min and stop invalidates the thesis (not random)."),
            ("Common failure", "False breakouts near major weekly levels or during low liquidity."),
        ],
        figure_caption="Price breaks the opening range, then pulls back before continuing. VWAP stays supportive in a bullish trend.",
        figure_draw=fig_orb,
    )

    def fig_vwap_pullback(x: float, y: float, w: float, h: float) -> None:
        series = [100.0, 100.4, 100.8, 101.1, 101.4, 101.2, 101.0, 101.15, 101.35, 101.55, 101.35, 101.25, 101.45, 101.7, 101.9, 102.0]
        vwap = _moving_avg(series, 6)
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=vwap,
            markers=[(4, "Impulse", COLORS["green"]), (10, "Pullback", COLORS["orange"]), (12, "Trigger Close", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Intraday - Trend",
        "VWAP Pullback Trend (Trend-Day Playbook)",
        "Enters on pullbacks to VWAP/short EMA in the direction of the H1 trend, using contraction-then-expansion volume behavior.",
        "A continuation setup: in strong intraday trends, price often mean-reverts to VWAP/20EMA, then resumes. The edge is not VWAP itself, but the combination of trend + pullback quality + volume confirmation + room to run.",
        mechanics=[
            "Confirm H1 trend (EMA 20/50 stack + HH/HL or LH/LL).",
            "Wait for pullback into VWAP or M15 20EMA with reduced volume/volatility.",
            "Enter on a clear trigger close back in trend direction (HL for longs / LH for shorts).",
            "Avoid entries directly into nearby resistance/support within ~0.25-0.5x ATR.",
            "Scale out and trail using structure (prior swing highs/lows).",
        ],
        checklist=[
            ("Trend", "Clear H1 trend; if mixed -> skip."),
            ("Pullback", "Shallow and controlled; no waterfall moves unless you have reversal evidence."),
            ("Trigger", "Close back above VWAP/20EMA (long) or below (short) with intent."),
            ("Liquidity", "Prefer liquid names; wide spreads distort VWAP and entries."),
            ("Failure mode", "Trend exhaustion: late-day parabolic moves that snap back through VWAP."),
        ],
        figure_caption="In a trend day, pullbacks to VWAP/20EMA can offer defined-risk continuation entries when the trigger candle confirms.",
        figure_draw=fig_vwap_pullback,
    )

    def fig_hod_break(x: float, y: float, w: float, h: float) -> None:
        series = [100.0, 100.3, 100.6, 100.9, 101.1, 101.3, 101.35, 101.32, 101.34, 101.33, 101.36, 101.38, 101.42, 101.85, 102.1, 102.0]
        hod = max(series[:13])
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=_moving_avg(series, 7),
            hlines=[(hod, "HOD", COLORS["muted"])],
            markers=[(11, "Compression", COLORS["orange"]), (13, "Break+Close", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Intraday - Trend",
        "HOD/LOD Break + Tight-Risk Momentum",
        "Momentum breakout template: consolidation under HOD (or above LOD) with volume contraction, then break with volume expansion in trend direction.",
        "This is a structure + liquidity setup. HOD/LOD levels are where many stops and breakout orders cluster; the goal is to trade only the breakouts that occur after tight consolidation and with strong participation.",
        mechanics=[
            "Identify HOD/LOD and the most recent tight consolidation near it.",
            "Trade only in the direction of the H1 trend and market proxy alignment.",
            "Require a close beyond the level; prefer increasing volume on the trigger candle.",
            "Stop outside the breakout range + ATR buffer; avoid oversized stops.",
            "If the breakout fails quickly and returns inside the range -> exit (failed breakout).",
        ],
        checklist=[
            ("Compression", "Range tightens into the level; wicks are controlled."),
            ("Volume", "Break candle volume expands vs recent consolidation candles."),
            ("VWAP", "Often supportive/confirming, but HOD/LOD is the primary level."),
            ("Room", "Enough distance to next major level for RR >= rr_min."),
            ("Failure mode", "False breaks in low volume or right into major weekly resistance."),
        ],
        figure_caption="Price compresses beneath HOD, then breaks and closes above with momentum.",
        figure_draw=fig_hod_break,
    )

    # --- Stocks: Intraday Mean Reversion ---
    def fig_vwap_stretch(x: float, y: float, w: float, h: float) -> None:
        series = [100.0, 99.6, 99.3, 99.1, 98.9, 98.8, 98.95, 99.2, 99.5, 99.7, 99.9, 100.0, 100.1, 100.05]
        vwap = _moving_avg(series, 5)
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=vwap,
            markers=[(5, "Stretch", COLORS["red"]), (6, "Rejection", COLORS["orange"]), (8, "Revert", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Intraday - Mean Reversion",
        "VWAP Stretch Reversion (Range Regime Only)",
        "Mean reversion template that fades extreme distance from VWAP only when the regime is range-like (not a strong trend day).",
        "VWAP acts as a gravity point in balanced markets. The idea is to wait for a true stretch (distance vs ATR), see rejection/exhaustion, and then target a controlled revert back toward VWAP.",
        mechanics=[
            "First confirm the day is not strongly trending (low ADX or choppy structure around VWAP/EMAs).",
            "Quantify stretch using ATR multiples (e.g., 1.5-2.5x ATR away from VWAP).",
            "Require rejection evidence: long wick, failed continuation, divergence, or volume climax then fade.",
            "Target VWAP as primary take-profit; scale out and manage time risk.",
            "If price keeps trending away from VWAP -> invalidation (do not average down).",
        ],
        checklist=[
            ("Regime gate", "If trend is strong, stretching can keep stretching (skip)."),
            ("Stretch", "Distance from VWAP is large vs ATR; small deviations are noise."),
            ("Confirmation", "Rejection candle + momentum divergence improves quality."),
            ("Exit", "Primary target is VWAP; consider time stop (e.g., 4 candles)."),
            ("Failure mode", "Trying to fade the first pullback of a new trend day."),
        ],
        figure_caption="Price stretches away from VWAP, prints rejection, and mean-reverts back toward VWAP in a range regime.",
        figure_draw=fig_vwap_stretch,
    )

    def fig_band_reentry(x: float, y: float, w: float, h: float) -> None:
        series = [100.0, 100.1, 100.0, 99.9, 99.8, 99.6, 99.4, 99.55, 99.7, 99.9, 100.05, 100.1]
        mid = _moving_avg(series, 4)
        # Synthetic "bands"
        upper = [m + 0.35 for m in mid]
        lower = [m - 0.35 for m in mid]
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=None,
            markers=[(6, "Close Outside", COLORS["red"]), (7, "Re-entry", COLORS["green"])],
        )
        # overlay band lines
        price_pts = _scale_series_to_rect(series, x + 38, y + 38, w - 76, h - 76)
        # compute mapping reuse by plotting separately using draw_price_chart scaling isn't directly accessible, so draw a simple band overlay using the same helper
        band_x = x + 38
        band_y = y + 38
        band_w = w - 76
        band_h = h - 76
        up_pts = _scale_series_to_rect(upper, band_x, band_y, band_w, band_h)
        lo_pts = _scale_series_to_rect(lower, band_x, band_y, band_w, band_h)
        pdf.polyline(up_pts, w=1.2, color=COLORS["muted"], dash=(2.0, 2.0))
        pdf.polyline(lo_pts, w=1.2, color=COLORS["muted"], dash=(2.0, 2.0))
        pdf.text(band_x + 6, band_y + band_h - 12, "Upper/Lower Band", font="F3", size=8.0, color=COLORS["muted"])

    prompt_section(
        "Stocks - Intraday - Mean Reversion",
        "Bollinger/Keltner Band Re-entry Fade",
        "Mean reversion entry: price closes outside a volatility band, then closes back inside (re-entry) near a key level; target mid-band/VWAP.",
        "Bands are a visualization of volatility. The re-entry condition (outside then back inside) is a simple way to avoid fading every touch and instead wait for exhaustion and re-acceptance.",
        mechanics=[
            "Use only when the higher timeframe is not strongly trending (range-like behavior).",
            "Trigger: close outside band followed by a close back inside (re-entry).",
            "Add confluence: prior day high/low, volume profile nodes, or obvious support/resistance.",
            "Target: mid-band and/or VWAP; stop beyond the extreme + ATR buffer.",
            "Avoid fading strong breakouts where bands expand and price rides the band.",
        ],
        checklist=[
            ("Regime gate", "Bands work best in ranges; in trends, price can walk the band."),
            ("Signal", "Outside close then inside close (not just a wick)."),
            ("Confluence", "Key level nearby improves odds and defines risk."),
            ("Target", "Mid-band/VWAP is a natural mean-reversion magnet."),
            ("Failure mode", "Selling the first breakout candle of a new impulse trend."),
        ],
        figure_caption="Price closes outside the lower band, then re-enters. In a range regime, the next move often reverts toward the mean.",
        figure_draw=fig_band_reentry,
    )

    def fig_gap_fill(x: float, y: float, w: float, h: float) -> None:
        # "gap up then fill" synthetic
        series = [100.0, 100.0, 100.0, 103.0, 102.4, 101.8, 101.2, 100.7, 100.2, 100.0, 100.1]
        vwap = _moving_avg(series[3:], 4)
        # extend vwap to same length
        vwap_full = [series[0], series[1], series[2]] + vwap
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=vwap_full,
            markers=[(3, "Gap", COLORS["orange"]), (4, "Fail", COLORS["red"]), (9, "Fill", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Intraday - Mean Reversion",
        "Gap Fill Mean Reversion (Conditional)",
        "Conditional gap-fill framework using premarket levels + VWAP + rejection so you do not blindly fade a real trend gap.",
        "Many gaps partially fill because early uncertainty resolves and liquidity returns, but not all gaps fill. This template tries to separate 'gap-and-go' from 'gap-and-fade' by demanding failure to hold key premarket/opening levels.",
        mechanics=[
            "Measure the gap: today open vs yesterday close; note premarket high/low (PMH/PML).",
            "If gapping up, look for failure to hold above PMH/ORH and a close back below VWAP.",
            "If gapping down, look for failure below PML/ORL and a close back above VWAP.",
            "Target: partial fill areas and/or full fill to yesterday close; scale out.",
            "High caution around news-driven gaps and earnings (gap behavior changes).",
        ],
        checklist=[
            ("Gap context", "Small gaps fill more often than large news gaps; ask for catalyst if unknown."),
            ("Trigger", "Reclaim/lose VWAP + rejection (not just drift)."),
            ("Level", "Premarket + opening range levels define invalidation."),
            ("Target", "Define partial-fill and full-fill objectives."),
            ("Failure mode", "Fading a gap-and-go trend that never looks back."),
        ],
        figure_caption="A gap up fails to hold above early levels and drifts back to fill the gap. VWAP helps confirm the fade.",
        figure_draw=fig_gap_fill,
    )

    # --- Stocks: Swing Trend ---
    def fig_base_breakout(x: float, y: float, w: float, h: float) -> None:
        series = [50, 52, 54, 55, 54, 53.5, 54.2, 54.8, 55.1, 54.7, 55.0, 55.2, 55.1, 55.3, 57.2, 58.0, 59.1]
        base_lo = min(series[5:14])
        base_hi = max(series[5:14])
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=None,
            bands=[(base_lo, base_hi, "Base Range", _rgb(0.92, 0.98, 0.94))],
            markers=[(14, "Breakout", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Swing - Trend",
        "Breakout From Base (Weekly/Daily Structure)",
        "Swing trend template: identify a multi-week base, then trade the breakout in the direction of the higher-timeframe trend with volume/RS confirmation.",
        "Base breakouts are common in systematic and discretionary trend approaches: a period of balance (base) resolves into expansion (breakout). The main risk is false breakouts when volume/participation is weak or when breaking into overhead supply.",
        mechanics=[
            "Use Weekly to define primary trend (HH/HL for longs; LH/LL for shorts).",
            "Find a multi-week base with tightening volatility on Daily.",
            "Trigger: Daily close beyond base boundary with volume expansion and/or strong RS vs SPY.",
            "Stop: below last contraction low (long) + ATR buffer; target: multiples of risk + trail.",
            "Avoid entering right before earnings unless it is explicitly an earnings play.",
        ],
        checklist=[
            ("Trend", "Weekly trend aligned; otherwise breakout is lower quality."),
            ("Base quality", "Tight range + volatility contraction; clean boundaries."),
            ("Volume/RS", "Breakout should show participation or RS improvement."),
            ("Event risk", "Earnings within a few days can invalidate backtests."),
            ("Failure mode", "Breakout into heavy supply; quick reversal back into base."),
        ],
        figure_caption="A multi-week base resolves upward; the breakout candle expands and leaves the base range.",
        figure_draw=fig_base_breakout,
    )

    def fig_ma_pullback_swing(x: float, y: float, w: float, h: float) -> None:
        series = [80, 82, 85, 88, 90, 92, 91, 89, 88, 89, 91, 94, 96, 95, 98]
        ema = _moving_avg(series, 4)
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=ema,
            markers=[(8, "Pullback", COLORS["orange"]), (10, "Reversal", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Swing - Trend",
        "Pullback-to-MA Trend Continuation",
        "Continuation entry on pullback to Daily 20/50 EMA area with volume contraction and a reversal/trigger close.",
        "In persistent trends, pullbacks to short/medium moving averages act as a structured location to re-enter. The goal is to avoid chasing breakouts and instead buy/sell when risk can be defined against structure.",
        mechanics=[
            "Confirm trend: price on correct side of 50EMA and structure supports continuation.",
            "Wait for pullback into 20/50EMA area with reduced volatility and/or volume.",
            "Trigger: reversal close + higher low (long) or lower high (short).",
            "Stop: beyond pullback swing + ATR buffer; partial at 2R; trail with swings.",
            "Avoid deep pullbacks that break structure (those are potential trend changes).",
        ],
        checklist=[
            ("Location", "Pullback lands into MA zone (not mid-air)."),
            ("Structure", "HL/LH forms; do not enter before stabilization."),
            ("Trend health", "Avoid late-stage parabolic trends without base support."),
            ("Targets", "Plan trail method (20EMA or swing points)."),
            ("Failure mode", "MA breaks and turns into resistance/support flip failure."),
        ],
        figure_caption="Price trends above the moving average, pulls back into the MA zone, then resumes after a reversal candle.",
        figure_draw=fig_ma_pullback_swing,
    )

    def fig_vcp(x: float, y: float, w: float, h: float) -> None:
        series = [100, 110, 105, 112, 107, 111, 108, 110, 109, 110.5, 109.5, 110.2, 109.9, 111.8, 114.0]
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=None,
            markers=[(11, "Contraction", COLORS["orange"]), (13, "Breakout", COLORS["green"])],
        )
        # draw contraction envelopes (simple)
        ax_x = x + 38
        ax_y = y + 38
        ax_w = w - 76
        ax_h = h - 76
        pdf.line(ax_x + ax_w * 0.40, ax_y + ax_h * 0.75, ax_x + ax_w * 0.75, ax_y + ax_h * 0.65, w=1.0, color=COLORS["muted"])
        pdf.line(ax_x + ax_w * 0.40, ax_y + ax_h * 0.35, ax_x + ax_w * 0.75, ax_y + ax_h * 0.45, w=1.0, color=COLORS["muted"])
        pdf.text(ax_x + ax_w * 0.42, ax_y + ax_h * 0.80, "Range narrows", font="F3", size=8.0, color=COLORS["muted"])

    prompt_section(
        "Stocks - Swing - Trend",
        "Volatility Contraction Pattern (VCP) Breakout",
        "Swing breakout template emphasizing volatility contraction and volume dry-up before a breakout and expansion.",
        "VCP-style setups attempt to capture the transition from compression to expansion. The pattern is useful as a checklist: does the stock repeatedly contract (smaller pullbacks) and then break out with participation?",
        mechanics=[
            "Look for multiple contractions: each pullback range is smaller than the prior.",
            "Volume should generally dry up during the base/handle portion.",
            "Trigger: breakout close above the final contraction high.",
            "Stop: below the final contraction low + ATR buffer.",
            "Manage: partial at 2R and trail using 20EMA or swing lows.",
        ],
        checklist=[
            ("Contractions", "Ranges visibly narrow; fewer shakeouts over time."),
            ("Volume", "Dry-up during consolidation, expansion on breakout."),
            ("Trend", "Usually best when the higher timeframe trend is up."),
            ("Entry timing", "Prefer close confirmation; avoid early entries before breakout."),
            ("Failure mode", "Breakout on weak volume that stalls and re-enters the base."),
        ],
        figure_caption="Contractions narrow, then price breaks out and expands upward.",
        figure_draw=fig_vcp,
    )

    # --- Stocks: Swing Mean Reversion ---
    def fig_oversold_bounce(x: float, y: float, w: float, h: float) -> None:
        series = [120, 118, 116, 113, 110, 108, 107, 108, 110, 112, 114, 113, 115]
        ema = _moving_avg(series, 5)
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            series,
            vwap=ema,
            markers=[(6, "Capitulation", COLORS["red"]), (7, "Reversal", COLORS["green"]), (9, "Revert-to-Mean", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Swing - Mean Reversion",
        "Oversold Bounce (Multi-factor Mean Reversion)",
        "Mean reversion bounce setup that requires extension + stabilization (no blind knife-catching). Targets a revert toward the mean (20EMA / breakdown level).",
        "Mean reversion works when a move is overextended relative to recent volatility and a stabilization signal appears. The goal is not to predict bottoms; it is to wait for evidence that downside momentum is weakening and risk can be defined.",
        mechanics=[
            "Quantify extension: distance below 20EMA/50EMA and/or large ATR multiples.",
            "Require stabilization: higher low, strong close, reclaim prior day high, or divergence.",
            "Avoid binary event risk (earnings) unless intentionally trading it.",
            "Target: mean reversion to 20EMA and/or key breakdown level.",
            "Time stop: if the bounce does not materialize within N days, exit.",
        ],
        checklist=[
            ("Extension", "Move is unusually large vs ATR; 'mild red' is not oversold."),
            ("Stabilization", "You need a reversal signal; otherwise you are averaging into a trend."),
            ("Market regime", "Broad-market selloffs can keep pushing (reduce size/skip)."),
            ("Targets", "Mean (20EMA) is primary; scale out into resistance."),
            ("Failure mode", "News-driven downtrends where mean reversion never happens."),
        ],
        figure_caption="Price extends far below the mean, stabilizes, then reverts upward toward the moving average.",
        figure_draw=fig_oversold_bounce,
    )

    def fig_pairs_ratio(x: float, y: float, w: float, h: float) -> None:
        ratio = [1.00, 0.99, 0.98, 0.97, 0.965, 0.97, 0.98, 0.99, 1.005, 1.01, 1.015, 1.005, 0.995]
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            ratio,
            vwap=_moving_avg(ratio, 4),
            markers=[(4, "z <= -Z", COLORS["red"]), (8, "Revert", COLORS["green"])],
        )

    prompt_section(
        "Stocks - Swing - Mean Reversion",
        "Pairs / Ratio Z-Score Mean Reversion",
        "Relative-value mean reversion: trade the ratio between two correlated assets when the ratio is statistically stretched (z-score extreme) and reverts.",
        "Pairs trading is about relative moves, not absolute direction. It is commonly used to reduce market beta and focus on idiosyncratic reversion. The main risk is correlation breakdown or a structural regime change.",
        mechanics=[
            "Pick a peer or benchmark with stable historical correlation.",
            "Compute ratio = A / B and its z-score over a chosen lookback.",
            "Enter when |z| is extreme and begins to turn (avoid 'catching the extreme').",
            "Size legs in a market-neutral way (dollar-neutral or beta-neutral).",
            "Exit when z-score mean reverts (near 0) or invalidates beyond stop threshold.",
        ],
        checklist=[
            ("Correlation", "If correlation is unstable, z-score signals degrade."),
            ("Data", "Use clean adjusted data (splits/dividends) for equities."),
            ("Stops", "Define stop on z-score and on fundamental breaks (earnings shocks)."),
            ("Crowding", "Highly crowded pairs can gap violently on news."),
            ("Failure mode", "A regime shift where the relationship permanently changes."),
        ],
        figure_caption="A ratio stretches (z-score extreme) and then mean-reverts back toward its average.",
        figure_draw=fig_pairs_ratio,
    )

    # --- Options: Intraday Trend ---
    def fig_debit_spread(x: float, y: float, w: float, h: float) -> None:
        # Example: call debit spread K1=100, K2=105, debit=2
        K1, K2, debit = 100.0, 105.0, 2.0
        xs = [90, 95, 100, 102, 105, 108, 112]
        ys = []
        for s in xs:
            intrinsic = max(0.0, min(s - K1, K2 - K1))
            ys.append(intrinsic - debit)
        draw_payoff_chart(
            pdf,
            x,
            y,
            w,
            h,
            "Call Debit Spread Payoff (example)",
            xs,
            ys,
            bands=[(K1, K2, "Between strikes", _rgb(0.92, 0.98, 0.94))],
        )
        pdf.text(x + 10, y + 14, f"K1={K1:.0f}, K2={K2:.0f}, debit={debit:.1f} (illustrative)", font="F3", size=8.5, color=COLORS["muted"])

    prompt_section(
        "Options - Intraday - Trend",
        "Defined-Risk Directional Debit Spread",
        "Defined-risk intraday options structure aligned to an underlying trend trigger (ORB/VWAP pullback/HOD break). Requires a chain snapshot to avoid hallucinated strikes.",
        "A debit spread reduces cost (and IV exposure) compared to a naked long call/put, while keeping max loss defined. It is often used when you want directional exposure but want to limit premium paid.",
        mechanics=[
            "First, confirm the underlying trigger (trend setup) - do not trade options without an underlying edge.",
            "Choose expiry (commonly ~7-21 DTE for non-0DTE) and a liquid strike region.",
            "Buy a call/put and sell a further OTM option to cap cost and risk.",
            "Max loss is the debit paid; manage via profit targets and time stops (intraday).",
            "Exit if underlying invalidates; options price alone can mislead.",
        ],
        checklist=[
            ("Chain required", "Without chain (bid/ask/OI/IV), do not output strikes."),
            ("Liquidity", "Tight bid/ask and sufficient OI/volume."),
            ("Delta", "Common long-leg delta ~0.45-0.65 (context dependent)."),
            ("Risk", "Max loss within risk_per_trade_pct; define exits."),
            ("Failure mode", "Chop: underlying never follows through; time decay hurts."),
        ],
        figure_caption="Debit spread payoff is capped on both sides: max loss is known (debit), max profit is limited (spread width - debit).",
        figure_draw=fig_debit_spread,
    )

    def fig_0dte_defined_risk(x: float, y: float, w: float, h: float) -> None:
        # Illustrate a tight-risk vertical spread around spot
        K1, K2, credit = 100.0, 102.0, 0.6
        xs = [96, 98, 100, 101, 102, 104]
        ys = []
        for s in xs:
            intrinsic = max(0.0, min(s - K1, K2 - K1))
            # short call spread profit: credit - intrinsic
            ys.append(credit - intrinsic)
        draw_payoff_chart(
            pdf,
            x,
            y,
            w,
            h,
            "Short Call Spread (defined risk) - example",
            xs,
            ys,
            bands=[(K1, K2, "Risk zone", _rgb(1.00, 0.96, 0.90))],
        )
        pdf.text(x + 10, y + 14, "0DTE/1DTE is highly path-dependent (gamma/theta). Use only with strict gates.", font="F3", size=8.5, color=COLORS["muted"])

    prompt_section(
        "Options - Intraday - Trend",
        "0DTE/1DTE Defined-Risk (Index/ETF Only, Strict)",
        "Ultra-short-dated defined-risk template for very liquid index/ETF products only. Strong gating on regime + liquidity; no naked options.",
        "0DTE/1DTE trades have extreme gamma and theta. They can work in clean, liquid trend moves, but they punish indecision. This is why the prompt is strict: if the environment is not ideal, the correct output is NO TRADE.",
        mechanics=[
            "Confirm symbol is highly liquid (index/ETF) and chain is tight.",
            "Require a clear underlying trigger (ORB/VWAP pullback) with strong trend evidence.",
            "Use defined-risk verticals (spreads) to cap max loss.",
            "Use smaller risk budgets and faster management (profit targets + time stops).",
            "Exit quickly if the underlying invalidates or VWAP flips against the trade.",
        ],
        checklist=[
            ("Liquidity", "Tight bid/ask; large volume; stable fills."),
            ("Regime", "Only clear trend days; range days are whipsaw traps."),
            ("Defined risk", "Spreads only; max loss <= risk_per_trade_pct."),
            ("Time stop", "If no follow-through quickly, exit (theta decay)."),
            ("Failure mode", "VWAP chop: repeated flips destroy premium."),
        ],
        figure_caption="Example of a defined-risk spread payoff. 0DTE/1DTE requires unusually strict regime and liquidity filters.",
        figure_draw=fig_0dte_defined_risk,
    )

    # --- Options: Intraday Mean Reversion ---
    def fig_credit_spread(x: float, y: float, w: float, h: float) -> None:
        # Example: short put spread K1=100 (sell), K2=98 (buy), credit=0.7
        K_short, K_long, credit = 100.0, 98.0, 0.7
        xs = [92, 95, 98, 99, 100, 102, 105]
        ys = []
        width = K_short - K_long
        for s in xs:
            intrinsic = max(0.0, min(K_short - s, width))
            ys.append(credit - intrinsic)
        draw_payoff_chart(
            pdf,
            x,
            y,
            w,
            h,
            "Short Put Spread Payoff (example)",
            xs,
            ys,
            bands=[(K_long, K_short, "Between strikes", _rgb(0.92, 0.98, 0.94))],
        )

    prompt_section(
        "Options - Intraday - Mean Reversion",
        "Credit Spread Fade at Extremes (Defined Risk)",
        "Defined-risk premium-selling setup after an exhaustion + rejection mean-reversion signal in the underlying. Requires IV and chain liquidity context.",
        "This is short-volatility expression of mean reversion: you sell premium after a stretched move when you expect price to revert and volatility to normalize. The key is strict gating: do not sell premium into a trend day.",
        mechanics=[
            "Confirm range-like regime and a clear exhaustion/rejection signal (VWAP stretch + reversal).",
            "Pick a credit spread (short put spread for bullish MR; short call spread for bearish MR).",
            "Use liquid strikes and define max loss; target a % of credit for profit (e.g., 40-70%).",
            "Have a hard stop (price level or spread value) and time stop.",
            "Avoid selling premium into binary events (earnings) unless it is an earnings strategy.",
        ],
        checklist=[
            ("Regime", "Must be range-like; avoid strong trends."),
            ("Signal", "Exhaustion + rejection, not just a small pullback."),
            ("IV context", "Premium selling is best when IV is elevated vs baseline."),
            ("Liquidity", "Tight bid/ask; avoid thin chains."),
            ("Failure mode", "A trend resumes and the spread goes ITM quickly."),
        ],
        figure_caption="Credit spread payoff: limited profit (credit) and limited loss (spread width - credit). Best used after exhaustion in a range regime.",
        figure_draw=fig_credit_spread,
    )

    def fig_iron_condor(x: float, y: float, w: float, h: float) -> None:
        # Simplified iron condor payoff shape
        xs = [90, 95, 98, 100, 102, 105, 110]
        ys = [-3, -1, 1, 1.2, 1, -1, -3]  # stylized
        draw_payoff_chart(
            pdf,
            x,
            y,
            w,
            h,
            "Iron Condor Payoff (stylized)",
            xs,
            ys,
            bands=[(98, 102, "Range thesis", _rgb(0.92, 0.98, 0.94))],
        )

    prompt_section(
        "Options - Intraday - Mean Reversion",
        "Iron Condor (Range Thesis Only)",
        "Range-only premium selling on both sides (defined risk). Requires clear range boundaries and strict breach/defense rules.",
        "An iron condor expresses a 'price stays inside a range' thesis. It benefits from time decay and volatility normalization, but it can be damaged quickly by breakout moves. This is why the prompt is range-only and requires explicit defense rules.",
        mechanics=[
            "Confirm range regime and define upper/lower range boundaries (levels or profile).",
            "Sell OTM call spread above resistance and sell OTM put spread below support.",
            "Define max loss, profit target, and breach defense (close, roll, or hedge).",
            "Avoid building condors into scheduled catalysts (earnings, Fed).",
            "Exit early if range breaks; do not 'hope' a breakout returns.",
        ],
        checklist=[
            ("Regime", "Range only; trend days are condor killers."),
            ("Range width", "Must be wide enough relative to expected move."),
            ("Liquidity", "All 4 legs need tight markets to avoid slippage."),
            ("Defense", "Predefined action if either side is threatened."),
            ("Failure mode", "Volatility expansion + breakout through short strike."),
        ],
        figure_caption="Iron condor payoff: profits if price stays inside the range; losses grow if price breaks beyond the wings.",
        figure_draw=fig_iron_condor,
    )

    # --- Options: Swing Trend ---
    def fig_diagonal_timeline(x: float, y: float, w: float, h: float) -> None:
        # A simple timeline diagram instead of a payoff curve (diagonals depend on time).
        pdf.rect(x, y, w, h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)
        pdf.text(x + 6, y + h - 18, "Diagonal / Calendar Concept (time-based)", font="F2", size=10.5, color=COLORS["text"])
        # timeline
        ty = y + h * 0.55
        pdf.line(x + 30, ty, x + w - 30, ty, w=2.0, color=COLORS["muted"])
        pdf.text(x + 30, ty + 10, "Now", font="F3", size=8.5, color=COLORS["muted"])
        pdf.text(x + w - 60, ty + 10, "Later", font="F3", size=8.5, color=COLORS["muted"])

        # blocks
        b1x = x + 70
        b1w = w * 0.35
        pdf.rect(b1x, ty + 20, b1w, 24, fill=_rgb(1.0, 0.96, 0.90), stroke=COLORS["rule"], stroke_w=1.0)
        pdf.text(b1x + 8, ty + 28, "Sell near-term option", font="F1", size=9.5, color=COLORS["text"])
        pdf.text(b1x + 8, ty + 16, "(collect theta)", font="F3", size=8.0, color=COLORS["muted"])

        b2x = x + 70
        b2w = w * 0.60
        pdf.rect(b2x, ty - 60, b2w, 24, fill=_rgb(0.92, 0.98, 0.94), stroke=COLORS["rule"], stroke_w=1.0)
        pdf.text(b2x + 8, ty - 52, "Buy longer-term option", font="F1", size=9.5, color=COLORS["text"])
        pdf.text(b2x + 8, ty - 64, "(keep exposure)", font="F3", size=8.0, color=COLORS["muted"])

        # arrows
        pdf.line(b1x + b1w, ty + 32, x + w - 40, ty + 32, w=1.2, color=COLORS["muted"])
        pdf.line(b2x + b2w, ty - 48, x + w - 40, ty - 48, w=1.2, color=COLORS["muted"])

    prompt_section(
        "Options - Swing - Trend",
        "Trend Rider: Debit Spread vs Diagonal (IV-aware)",
        "Swing trend options framework that selects a debit spread or diagonal based on IV context and the underlying trend trigger.",
        "Diagonals (or calendars) are time-structure trades: you sell shorter-dated premium against a longer-dated long option to reduce cost and partially hedge IV. Debit spreads are simpler and define payoff at expiry. The prompt chooses based on IV and objectives.",
        mechanics=[
            "Confirm the swing trend trigger (breakout or pullback-to-MA).",
            "If IV is high, prefer structures that reduce vega exposure (spreads/diagonals).",
            "Pick expiries across time (short near-term, long further out) for diagonals.",
            "Define max loss, roll rules (short leg), and profit plan.",
            "Respect event risk (earnings): diagonals can behave unexpectedly around IV shocks.",
        ],
        checklist=[
            ("IV context", "High IV -> spreads/diagonals; low IV -> long premium may be ok."),
            ("Chain required", "Need multi-expiry chain to construct diagonals."),
            ("Liquidity", "Both expiries must be liquid enough to roll/manage."),
            ("Roll plan", "Define when to roll the short leg (time/strike)."),
            ("Failure mode", "Underlying chops and time decay overwhelms the thesis."),
        ],
        figure_caption="Diagonals/calendars are time-based. You sell near-term premium and buy longer-term exposure; management (rolls) is part of the trade.",
        figure_draw=fig_diagonal_timeline,
    )

    def fig_protective_put(x: float, y: float, w: float, h: float) -> None:
        # Protective put: stock + long put
        xs = [80, 90, 100, 110, 120]
        entry = 100.0
        put_strike = 95.0
        put_cost = 2.0
        ys = []
        for s in xs:
            stock_pl = s - entry
            put_pl = max(0.0, put_strike - s) - put_cost
            ys.append(stock_pl + put_pl)
        draw_payoff_chart(
            pdf,
            x,
            y,
            w,
            h,
            "Protective Put (stock + long put) - example",
            xs,
            ys,
            bands=[(0, put_strike, "Downside floor", _rgb(1.0, 0.96, 0.90))],
        )
        pdf.text(x + 10, y + 14, "Illustrative numbers: entry=100, put strike=95, cost=2", font="F3", size=8.5, color=COLORS["muted"])

    prompt_section(
        "Options - Swing - Trend",
        "Protective Put / Collar (Risk-First)",
        "Hedging prompt for long stock exposure using protective puts or collars. Focuses on max loss, hedge cost, and roll/remove rules.",
        "Institutions often express 'I want to own the stock but cap risk' using puts or collars. The hedge is not free: you pay premium or give up upside (collar). This prompt forces explicit tradeoffs and risk math.",
        mechanics=[
            "Start with the stock thesis (entry, size, timeframe) and define worst-case acceptable drawdown.",
            "Protective put: buy puts to define a floor; cost reduces expected return.",
            "Collar: finance the put by selling a call (caps upside).",
            "Define when to roll: if stock moves, if time passes, or if volatility shifts.",
            "Avoid implementing/rolling collars into earnings without understanding IV effects.",
        ],
        checklist=[
            ("Max loss", "Explicitly compute stock risk + option hedge effect."),
            ("Cost", "Track hedge drag (premium) or upside cap (short call)."),
            ("Liquidity", "Choose strikes/expiries with tight markets."),
            ("Roll plan", "Predefine roll triggers (time, delta, price)."),
            ("Failure mode", "Overpaying for protection when IV is extremely high."),
        ],
        figure_caption="Protective put payoff: downside is floored by the put, while upside remains (minus hedge cost).",
        figure_draw=fig_protective_put,
    )

    # --- Options: Swing Mean Reversion ---
    def fig_high_iv_mr(x: float, y: float, w: float, h: float) -> None:
        # IV over time illustration
        iv = [0.28, 0.32, 0.40, 0.55, 0.48, 0.42, 0.36, 0.33, 0.30]
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            iv,
            vwap=_moving_avg(iv, 3),
            markers=[(3, "IV spike", COLORS["orange"]), (7, "Mean revert", COLORS["green"])],
        )

    prompt_section(
        "Options - Swing - Mean Reversion",
        "High IV Mean Reversion (Premium Selling, Defined Risk)",
        "Defined-risk premium selling when implied volatility is elevated; aims to benefit from IV normalization plus a range/mean-reversion price thesis.",
        "When IV is high, option prices are inflated. If price remains within a range and IV normalizes, premium sellers can profit. The key is to keep risk defined and avoid selling premium into unknown binary events unless that is the explicit strategy.",
        mechanics=[
            "Confirm IV is elevated (IV rank/percentile or IV vs historical baseline).",
            "Choose a defined-risk structure (credit spread or iron condor) aligned with a range/MR thesis.",
            "Set profit target (e.g., 40-70% of credit) and a hard stop/adjustment plan.",
            "Avoid earnings/Fed unless you are explicitly trading the event and understand crush risk.",
            "Position size conservatively; tail events can gap through strikes.",
        ],
        checklist=[
            ("IV context", "Premium selling makes most sense when IV is elevated."),
            ("Defined risk", "Use spreads/condors, not naked short options."),
            ("Thesis", "Range/MR thesis should have level support (not wishful)."),
            ("Event risk", "Know upcoming catalysts and decide: avoid vs trade."),
            ("Failure mode", "IV stays high and price trends through the short strike."),
        ],
        figure_caption="IV tends to spike during uncertainty and can mean-revert. Premium sellers benefit if price behaves and IV normalizes.",
        figure_draw=fig_high_iv_mr,
    )

    # Earnings Volatility Crush (expanded)
    l._new_page()
    l.h2("Options - Swing - Mean Reversion")
    l.h3("Earnings Volatility Crush (Event-Driven, Strict)")
    l.paragraph("Description: Earnings volatility crush is a commonly observed phenomenon where implied volatility (IV) collapses immediately after an earnings release, reducing option extrinsic value even if price moves.", font="F3", size=10.5, color=COLORS["muted"])
    l.h3("Why it is event-driven and strict")
    l.paragraph("This is not a general market condition. It is tied to a discrete catalyst: earnings resolve uncertainty, so the market typically reprices options with lower forward uncertainty. The only variable is magnitude: how much IV drops and how large the stock move is versus what was priced in.")
    l.h3("1) What happens (mechanically)")
    l.bullets([
        "Before earnings: uncertainty rises -> IV rises -> options get expensive (higher extrinsic value).",
        "After earnings: uncertainty is resolved -> IV often collapses -> extrinsic value compresses quickly.",
        "This can happen regardless of direction. A 'right direction' trade can still lose if the move is smaller than what IV had priced.",
    ])
    l.h3("2) Who gets hurt (and why)")
    l.bullets([
        "Long option holders (calls/puts/straddles) are long volatility (vega). If IV collapses, premium can drop fast.",
        "You can be correct on direction and still lose if the realized move is less than the expected move priced by options.",
    ])
    l.h3("3) Who benefits")
    l.bullets([
        "Short volatility traders (defined-risk credit spreads, iron condors) can benefit if IV collapses and price stays inside a range.",
        "They are effectively selling uncertainty before the event and buying it back cheaper after, but tail risk is real (surprise moves).",
    ])
    l.h3("4) Expected move vs actual move")
    l.paragraph("A simple mental model: options price in an expected move. If the actual move is smaller, long options often lose; if larger, they can win despite the crush.")
    l.table(
        headers=["Case", "Actual move vs expected move", "Typical outcome for long options"],
        rows=[
            ["Most common", "Actual < Expected", "Often loses (IV crush + insufficient move)."],
            ["Breakout surprise", "Actual > Expected", "Can win (move overcomes IV crush)."],
            ["In-line", "Actual ~= Expected", "May be near breakeven; depends on entry price and structure."],
        ],
        col_widths=[l.w * 0.18, l.w * 0.32, l.w * 0.50],
    )
    l.h3("Example visuals (synthetic)")

    def fig_iv_crush(x: float, y: float, w: float, h: float) -> None:
        iv = [0.35, 0.38, 0.42, 0.50, 0.62, 0.40, 0.34, 0.32]
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            iv,
            vwap=_moving_avg(iv, 3),
            markers=[(4, "Pre-earnings IV", COLORS["orange"]), (5, "Post IV crush", COLORS["green"])],
        )

    l.figure(
        "IV often rises into earnings and collapses after the release. The shape and magnitude vary by ticker and quarter.",
        fig_iv_crush,
        height=180.0,
    )

    def fig_extrinsic_drop(x: float, y: float, w: float, h: float) -> None:
        # Extrinsic value illustration
        extrinsic = [5.0, 5.4, 6.2, 7.0, 7.6, 3.8, 3.2, 3.0]
        draw_price_chart(
            pdf,
            x,
            y,
            w,
            h,
            extrinsic,
            vwap=_moving_avg(extrinsic, 3),
            markers=[(4, "Peak extrinsic", COLORS["orange"]), (5, "Extrinsic compresses", COLORS["green"])],
        )

    l.figure(
        "Extrinsic value (time + IV) can compress sharply after earnings. This is why long options can lose even if price moves.",
        fig_extrinsic_drop,
        height=180.0,
    )

    l.h3("How to trade it responsibly (guidance)")
    l.bullets([
        "Use defined-risk structures if you sell premium (credit spreads/condors). Avoid naked short options in prompts by default.",
        "Respect binary tail risk: surprises can gap through strikes; size small and predefine exits.",
        "If buying options, compare implied expected move vs your forecast; prefer structures that reduce vega risk (spreads).",
        "Treat earnings as a separate category in your prompt database (event-driven).",
    ])
    l.paragraph("Note: IV does not always drop 'normally' if guidance shocks, M&A rumors, or regulatory events change forward uncertainty. The prompt should explicitly ask for the earnings date/time and expected move/chain snapshot before proposing strikes.", font="F3", size=10.2, color=COLORS["muted"])

    # --- Meta ---
    def fig_regime_selector(x: float, y: float, w: float, h: float) -> None:
        pdf.rect(x, y, w, h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)
        pdf.text(x + 6, y + h - 18, "Regime Selector (flow)", font="F2", size=10.5, color=COLORS["text"])

        box_w = w * 0.42
        box_h = 34
        bx = x + 16
        by = y + h - 70

        def box(title: str, sub: str, yy: float) -> None:
            pdf.rect(bx, yy, box_w, box_h, fill=_rgb(0.92, 0.98, 0.94), stroke=COLORS["rule"], stroke_w=1.0)
            pdf.text(bx + 8, yy + 20, title, font="F2", size=9.8, color=COLORS["text"])
            pdf.text(bx + 8, yy + 8, sub, font="F3", size=8.2, color=COLORS["muted"])

        box("1) Determine regime", "Trend vs Range vs Mixed", by)
        box("2) Pick template", "Trend or Mean Reversion prompt", by - 55)
        box("3) Gate quality", "Score >= needed_score & confidence >= min_confidence", by - 110)
        box("4) Output", "1 setup or NO TRADE", by - 165)

        # arrows
        for i in range(3):
            xmid = bx + box_w / 2
            y0 = by - i * 55
            pdf.line(xmid, y0, xmid, y0 - 21, w=1.2, color=COLORS["muted"])
            pdf.line(xmid, y0 - 21, xmid - 4, y0 - 17, w=1.2, color=COLORS["muted"])
            pdf.line(xmid, y0 - 21, xmid + 4, y0 - 17, w=1.2, color=COLORS["muted"])

    l._new_page()
    l.h2("Meta / Utilities")
    l.h3("Regime Selector (Picks Trend vs Mean Reversion Prompt)")
    l.paragraph("Description: Classifies intraday and swing regime (trend/range/mixed), selects the best template, and outputs one setup only if thresholds pass.", font="F3", size=10.5, color=COLORS["muted"])
    l.paragraph("This is the safety layer: it prevents applying mean reversion tools to trend regimes and prevents forcing trades when quality gates are not met.")
    l.h3("Example (flow)")
    l.figure("A simple decision flow: regime -> template -> quality gate -> output.", fig_regime_selector, height=190.0)

    def fig_multi_symbol(x: float, y: float, w: float, h: float) -> None:
        pdf.rect(x, y, w, h, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)
        pdf.text(x + 6, y + h - 18, "Multi-Symbol Scanner (ranking) - example", font="F2", size=10.5, color=COLORS["text"])
        # Draw a small ranking table inside the figure.
        cols = [w * 0.30, w * 0.35, w * 0.18, w * 0.17]
        tx = x + 8
        ty = y + h - 40
        header = ["Symbol", "Template", "Score", "Confidence"]
        row_data = [
            ["AAPL", "VWAP Pullback", "9.0", "72%"],
            ["MSFT", "ORB+VWAP", "8.0", "67%"],
            ["TSLA", "NO TRADE (missing chain)", "-", "-"],
        ]
        # header background
        pdf.rect(tx, ty - 18, sum(cols) - 16, 18, fill=COLORS["bg_soft"], stroke=COLORS["rule"], stroke_w=1.0)
        cx = tx
        for i, t in enumerate(header):
            pdf.text(cx + 4, ty - 14, t, font="F2", size=8.8, color=COLORS["text"])
            cx += cols[i]
        yy = ty - 18
        for r in row_data:
            yy -= 18
            pdf.rect(tx, yy, sum(cols) - 16, 18, fill=_rgb(1, 1, 1), stroke=COLORS["rule"], stroke_w=1.0)
            cx = tx
            for i, t in enumerate(r):
                pdf.text(cx + 4, yy + 5, t, font="F1", size=8.6, color=COLORS["text"])
                cx += cols[i]

    l.h3("Multi-Symbol Scanner (1 Best Setup Across Watchlist)")
    l.paragraph("Description: From a provided watchlist, ranks candidates and returns the single best qualifying setup, excluding symbols with missing required inputs.", font="F3", size=10.5, color=COLORS["muted"])
    l.paragraph("The scanner prompt is useful when you do not want 20 mediocre setups. It forces a 'winner-takes-all' selection under strict quality constraints.")
    l.h3("Example (table)")
    l.figure("Example output ranks symbols and excludes those missing required data (e.g., options chain).", fig_multi_symbol, height=180.0)

    # Glossary (short)
    l._new_page()
    l.h1("Glossary (Quick)")
    l.bullets([
        "VWAP: Volume-Weighted Average Price; used as intraday fair value / execution reference.",
        "ORB: Opening Range Break; breakout of early-session range.",
        "HOD/LOD: High/Low of day levels used for momentum triggers.",
        "ATR: Average True Range; volatility proxy used for stops and sizing.",
        "ADX: Trend strength indicator; used as a regime filter (trend vs range).",
        "IV: Implied Volatility; market-implied future volatility in option prices.",
        "Expected Move: Rough move implied by options around an event (e.g., earnings).",
        "DTE: Days To Expiration; time remaining on an option contract.",
    ])
    l.paragraph("All examples are simplified. Real trading requires market data, slippage assumptions, commissions, and consistent risk management.", font="F3", size=10.2, color=COLORS["muted"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate TradingPromptLibrary guide PDF (no external deps).")
    parser.add_argument(
        "--out",
        default=os.path.join("docs", "trading-prompt-library", "TradingPromptLibraryGuide.pdf"),
        help="Output PDF path",
    )
    args = parser.parse_args()

    pdf = PdfBuilder()
    make_doc(pdf)
    pdf.write(args.out)
    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

