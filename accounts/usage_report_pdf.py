"""Branded usage report PDF with charts for customer sharing."""

from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

from accounts.templatetags.display_tz import DISPLAY_TZ

PDF_MIMETYPE = 'application/pdf'

_PAGE_W = 595.0
_PAGE_H = 842.0
_MARGIN_L = 42.0
_MARGIN_R = 42.0
_MARGIN_T = 42.0
_MARGIN_B = 48.0
_CONTENT_W = _PAGE_W - _MARGIN_L - _MARGIN_R

_NAVY = (0.008, 0.024, 0.149)
_ORANGE = (1.0, 0.4, 0.0)
_TEAL = (0.133, 0.827, 0.647)
_TEXT = (0.102, 0.153, 0.267)
_MUTED = (0.42, 0.44, 0.52)
_WHITE = (1.0, 1.0, 1.0)
_ROW_ALT = (0.97, 0.98, 0.99)
_HEADER_BG = (0.96, 0.97, 0.99)
_BORDER = (0.86, 0.88, 0.92)

_LOGO_PATH = Path(__file__).resolve().parent / 'static' / 'accounts' / 'img' / 'ig-logo-dark.png'
_CHART_PALETTE = ['#ff6600', '#22d3a5', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316']


def _header_logo_png() -> bytes | None:
    """White IG logo with transparent background, sized for the PDF header."""
    if not _LOGO_PATH.exists():
        return None

    img = Image.open(_LOGO_PATH).convert('RGBA')
    max_width = 320
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize(
            (max_width, max(1, int(img.height * ratio))),
            Image.Resampling.LANCZOS,
        )

    pixels = img.load()
    width, height = img.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if red < 40 and green < 40 and blue < 40:
                pixels[x, y] = (red, green, blue, 0)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _image_bytes(img: Image.Image, *, format: str = 'JPEG', quality: int = 88) -> bytes:
    buffer = io.BytesIO()
    if format.upper() == 'JPEG':
        rgb = img.convert('RGB')
        rgb.save(buffer, format='JPEG', quality=quality, optimize=True)
    else:
        img.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _format_period(report: dict) -> str:
    start = report['period_start_display']
    end = report['period_end_display']
    return f'{start.strftime("%b %d, %Y")} – {end.strftime("%b %d, %Y")}'


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = (
        ['Arial Bold.ttf', 'DejaVuSans-Bold.ttf', 'LiberationSans-Bold.ttf']
        if bold
        else ['Arial.ttf', 'DejaVuSans.ttf', 'LiberationSans-Regular.ttf']
    )
    roots = [
        Path('/System/Library/Fonts/Supplemental'),
        Path('/Library/Fonts'),
        Path('/usr/share/fonts/truetype/dejavu'),
        Path('/usr/share/fonts/truetype/liberation'),
        Path('C:/Windows/Fonts'),
    ]
    for root in roots:
        for name in names:
            path = root / name
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    continue
    return ImageFont.load_default()


def _daily_points(report: dict, *, customer_group: dict | None) -> list[dict]:
    if customer_group:
        return customer_group['daily']
    return report['daily_overall']


def _customer_groups(report: dict, *, customer_group: dict | None) -> list[dict]:
    if customer_group:
        return [customer_group]
    return [group for group in report['customer_groups'] if group['total'] > 0]


def _render_daily_chart(points: list[dict], *, title: str) -> bytes:
    width, height = 1000, 300
    img = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(img)
    font = _load_font(22)
    font_sm = _load_font(16)
    legend_font = _load_font(15)

    left, top, right, bottom = 72, 56, 36, 72
    plot_w = width - left - right
    plot_h = height - top - bottom

    draw.text((left, 18), title, fill='#020626', font=font)
    draw.rectangle((left, top, left + plot_w, top + plot_h), outline='#dde1ea', width=1)

    active = [point for point in points if point['total'] > 0]
    series = active if active else points[-14:]
    if not series:
        series = points[:1] if points else [{'date': '-', 'signing': 0, 'gst': 0, 'total': 0}]

    max_total = max(point['total'] for point in series) or 1
    count = len(series)
    gap = 4 if count > 20 else 8
    bar_w = max(6, (plot_w - gap * max(count - 1, 0)) // count)

    for index, point in enumerate(series):
        x0 = left + index * (bar_w + gap)
        signing_h = int(plot_h * point['signing'] / max_total)
        gst_h = int(plot_h * point['gst'] / max_total)
        y_base = top + plot_h
        if signing_h:
            draw.rectangle(
                (x0, y_base - signing_h, x0 + bar_w, y_base),
                fill='#ff6600',
            )
            y_base -= signing_h
        if gst_h:
            draw.rectangle(
                (x0, y_base - gst_h, x0 + bar_w, y_base),
                fill='#22d3a5',
            )
        if count <= 18:
            label = point['date'][5:].replace('-', '/')
            draw.text((x0, top + plot_h + 10), label, fill='#5c6078', font=font_sm)

    for tick in range(0, max_total + 1):
        if max_total <= 4 or tick % max(1, math.ceil(max_total / 4)) == 0 or tick == max_total:
            y = top + plot_h - int(plot_h * tick / max_total)
            draw.line((left - 6, y, left + plot_w, y), fill='#eef1f6', width=1)
            draw.text((18, y - 8), str(tick), fill='#5c6078', font=font_sm)

    draw.rectangle((left + plot_w + 48, 24, left + plot_w + 68, 44), fill='#ff6600')
    draw.text((left + plot_w + 76, 22), 'Signing / USB', fill='#020626', font=legend_font)
    draw.rectangle((left + plot_w + 48, 52, left + plot_w + 68, 72), fill='#22d3a5')
    draw.text((left + plot_w + 76, 50), 'GST', fill='#020626', font=legend_font)

    return _image_bytes(img)


def _render_share_chart(groups: list[dict], *, title: str) -> bytes:
    width, height = 640, 300
    img = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(img)
    font = _load_font(22)
    font_sm = _load_font(16)

    draw.text((24, 18), title, fill='#020626', font=font)
    total = sum(group['total'] for group in groups)
    cx, cy, outer, inner = 220, 230, 132, 78

    if total <= 0:
        draw.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), outline='#dde1ea', width=2)
        draw.text((cx - 28, cy - 10), 'No data', fill='#5c6078', font=font_sm)
    else:
        start = -90.0
        for index, group in enumerate(groups):
            sweep = 360.0 * group['total'] / total
            color = _CHART_PALETTE[index % len(_CHART_PALETTE)]
            draw.pieslice(
                (cx - outer, cy - outer, cx + outer, cy + outer),
                start=start,
                end=start + sweep,
                fill=color,
                outline='#ffffff',
                width=2,
            )
            start += sweep
        draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill='#ffffff')
        draw.text((cx - 14, cy - 18), str(total), fill='#020626', font=_load_font(28, bold=True))
        draw.text((cx - 22, cy + 10), 'total', fill='#5c6078', font=font_sm)

    legend_x = 390
    legend_y = 88
    for index, group in enumerate(groups):
        color = _CHART_PALETTE[index % len(_CHART_PALETTE)]
        draw.rectangle((legend_x, legend_y, legend_x + 18, legend_y + 18), fill=color)
        label = group['customer_label'][:28]
        pct = 0 if total == 0 else round(100 * group['total'] / total)
        draw.text((legend_x + 28, legend_y - 2), f'{label}  ({group["total"]} · {pct}%)', fill='#020626', font=font_sm)
        legend_y += 34

    return _image_bytes(img)


class _PdfCanvas:
    def __init__(self):
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.y = _MARGIN_T

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.y = _MARGIN_T
        self._draw_footer()

    def _ensure(self, height: float) -> None:
        if self.y + height > _PAGE_H - _MARGIN_B:
            self._new_page()

    def _draw_footer(self) -> None:
        generated = datetime.now(DISPLAY_TZ).strftime('%b %d, %Y %H:%M %Z')
        self.page.draw_line(
            fitz.Point(_MARGIN_L, _PAGE_H - 34),
            fitz.Point(_PAGE_W - _MARGIN_R, _PAGE_H - 34),
            color=_BORDER,
            width=0.8,
        )
        self.page.insert_text(
            (_MARGIN_L, _PAGE_H - 18),
            'IG E-Sign · Incite Gravity',
            fontsize=8,
            fontname='helv',
            color=_MUTED,
        )
        self.page.insert_text(
            (_PAGE_W - _MARGIN_R - 150, _PAGE_H - 18),
            f'Generated {generated}',
            fontsize=8,
            fontname='helv',
            color=_MUTED,
        )

    def draw_header(
        self,
        *,
        title: str,
        tenant_name: str,
        period_label: str,
        subtitle: str | None = None,
    ) -> None:
        header_h = 96.0
        self.page.draw_rect(fitz.Rect(0, 0, _PAGE_W, header_h), color=_NAVY, fill=_NAVY)
        self.page.draw_rect(fitz.Rect(0, 0, 6, header_h), color=_ORANGE, fill=_ORANGE)

        if _LOGO_PATH.exists():
            logo_bytes = _header_logo_png()
            if logo_bytes:
                self.page.insert_image(
                    fitz.Rect(_MARGIN_L, 14, _MARGIN_L + 118, 46),
                    stream=logo_bytes,
                )

        self.page.insert_text(
            (_MARGIN_L, 72),
            title,
            fontsize=20,
            fontname='hebo',
            color=_WHITE,
        )
        self.page.insert_text(
            (_MARGIN_L, 88),
            f'{tenant_name}  ·  {period_label}',
            fontsize=9.5,
            fontname='helv',
            color=(0.78, 0.8, 0.88),
        )
        if subtitle:
            self.page.insert_text(
                (_PAGE_W - _MARGIN_R - 180, 72),
                subtitle,
                fontsize=10,
                fontname='helv',
                color=_WHITE,
            )

        self.y = header_h + 22
        self._draw_footer()

    def draw_section_title(self, text: str) -> None:
        self._ensure(28)
        self.page.insert_text((_MARGIN_L, self.y + 14), text, fontsize=12, fontname='hebo', color=_TEXT)
        self.y += 20
        self.page.draw_line(
            fitz.Point(_MARGIN_L, self.y),
            fitz.Point(_PAGE_W - _MARGIN_R, self.y),
            color=_BORDER,
            width=0.8,
        )
        self.y += 12

    def draw_kpi_row(self, items: list[tuple[str, str, str]]) -> None:
        self._ensure(74)
        gap = 10.0
        count = len(items)
        card_w = (_CONTENT_W - gap * (count - 1)) / count
        card_h = 64.0
        x = _MARGIN_L

        for label, value, meta in items:
            rect = fitz.Rect(x, self.y, x + card_w, self.y + card_h)
            self.page.draw_rect(rect, color=_BORDER, fill=(0.99, 0.99, 1.0), width=0.8)
            self.page.draw_rect(
                fitz.Rect(x, self.y, x + 4, self.y + card_h),
                color=_ORANGE,
                fill=_ORANGE,
            )
            self.page.insert_text((x + 14, self.y + 22), value, fontsize=18, fontname='hebo', color=_NAVY)
            self.page.insert_text((x + 14, self.y + 40), label, fontsize=9, fontname='helv', color=_MUTED)
            if meta:
                self.page.insert_text((x + 14, self.y + 54), meta, fontsize=8, fontname='helv', color=_MUTED)
            x += card_w + gap

        self.y += card_h + 18

    def draw_image(self, png_bytes: bytes, *, height: float) -> None:
        self._ensure(height + 8)
        rect = fitz.Rect(_MARGIN_L, self.y, _PAGE_W - _MARGIN_R, self.y + height)
        self.page.insert_image(rect, stream=png_bytes)
        self.y += height + 16

    def draw_table(self, headers: list[str], rows: list[list[str]], col_widths: list[float]) -> None:
        row_h = 22.0
        header_h = 26.0
        table_w = sum(col_widths)

        def draw_header() -> None:
            header_rect = fitz.Rect(_MARGIN_L, self.y, _MARGIN_L + table_w, self.y + header_h)
            self.page.draw_rect(header_rect, color=_BORDER, fill=_HEADER_BG, width=0.8)
            x = _MARGIN_L + 8
            for header, width in zip(headers, col_widths):
                self.page.insert_text((x, self.y + 17), header, fontsize=8.5, fontname='hebo', color=_TEXT)
                x += width
            self.y += header_h

        if not rows:
            return

        self._ensure(header_h + row_h)
        draw_header()
        for row_index, row in enumerate(rows):
            if self.y + row_h > _PAGE_H - _MARGIN_B:
                self._new_page()
                draw_header()

            if row_index % 2 == 1:
                self.page.draw_rect(
                    fitz.Rect(_MARGIN_L, self.y, _MARGIN_L + table_w, self.y + row_h),
                    color=None,
                    fill=_ROW_ALT,
                )
            x = _MARGIN_L + 8
            for cell, width in zip(row, col_widths):
                self.page.insert_text((x, self.y + 15), str(cell)[:42], fontsize=8.5, fontname='helv', color=_TEXT)
                x += width
            self.y += row_h

        self.y += 10

    def bytes(self) -> bytes:
        return self.doc.tobytes(deflate=True, garbage=4)


def build_usage_report_pdf(report: dict, tenant, *, customer_group: dict | None = None) -> bytes:
    period_label = _format_period(report)
    is_customer = customer_group is not None
    title = 'Customer Usage Report' if is_customer else 'Usage Report'
    subtitle = customer_group['customer_label'] if is_customer else 'Overall summary'

    canvas = _PdfCanvas()
    canvas.draw_header(
        title=title,
        tenant_name=tenant.name,
        period_label=period_label,
        subtitle=subtitle,
    )

    if is_customer:
        kpis = [
            ('Total usage', str(customer_group['total']), 'successful calls'),
            ('Signing / USB', str(customer_group['signing_count']), 'signing events'),
            ('GST', str(customer_group['gst_count']), 'GST API calls'),
        ]
        if customer_group.get('key_names'):
            kpis.append(('API keys', str(len(customer_group['key_names'])), ', '.join(customer_group['key_names'])[:28]))
        canvas.draw_kpi_row(kpis)
    else:
        kpis = [
            ('Total usage', str(report['total_usage']), 'signing, USB & GST'),
            ('Signing / USB', str(report['total_signing']), 'this period'),
            ('GST', str(report['total_gst']), 'this period'),
        ]
        if report.get('show_quota'):
            kpis.append(
                (
                    'Quota used',
                    f'{report["quota_used"]}/{report["monthly_quota"]}',
                    'current month',
                )
            )
        canvas.draw_kpi_row(kpis)

    daily = _daily_points(report, customer_group=customer_group)
    groups = _customer_groups(report, customer_group=customer_group)

    canvas.draw_section_title('Daily usage trend')
    canvas.draw_image(
        _render_daily_chart(daily, title='Daily usage (Signing / USB + GST)'),
        height=168,
    )

    if groups:
        canvas.draw_section_title('Usage share by customer' if not is_customer else 'Customer share')
        canvas.draw_image(
            _render_share_chart(groups, title='Distribution of usage'),
            height=168,
        )

    daily_rows = [
        [point['date'], str(point['signing']), str(point['gst']), str(point['total'])]
        for point in daily
        if point['total'] > 0
    ]
    if daily_rows:
        canvas.draw_section_title('Daily breakdown')
        canvas.draw_table(
            ['Date', 'Signing / USB', 'GST', 'Total'],
            daily_rows,
            [150, 110, 80, 80],
        )

    if is_customer:
        if customer_group.get('key_names'):
            canvas.draw_section_title('API keys')
            canvas.draw_table(
                ['Key name'],
                [[name] for name in customer_group['key_names']],
                [_CONTENT_W - 20],
            )
    else:
        customer_rows = [
            [
                group['customer_label'],
                ', '.join(group.get('key_names') or []) or 'Portal',
                str(group['signing_count']),
                str(group['gst_count']),
                str(group['total']),
            ]
            for group in report['customer_groups']
            if group['total'] > 0
        ]
        if customer_rows:
            canvas.draw_section_title('Usage by customer')
            canvas.draw_table(
                ['Customer', 'API keys', 'Signing / USB', 'GST', 'Total'],
                customer_rows,
                [120, 130, 80, 50, 50],
            )

        key_rows = [
            [
                row['customer_label'],
                row['key_name'] if not row['is_portal'] else 'Portal',
                str(row['signing_count']),
                str(row['gst_count']),
                str(row['total']),
            ]
            for row in report['rows']
            if row['total'] > 0 or not row['is_portal']
        ]
        if key_rows:
            canvas.draw_section_title('Usage by API key')
            canvas.draw_table(
                ['Customer', 'API key', 'Signing / USB', 'GST', 'Total'],
                key_rows,
                [110, 120, 80, 50, 50],
            )

    return canvas.bytes()
