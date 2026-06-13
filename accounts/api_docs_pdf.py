"""Render API documentation markdown as a styled PDF file."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import fitz

PDF_MIMETYPE = 'application/pdf'

_PAGE_WIDTH = 595
_PAGE_HEIGHT = 842
_MARGIN_LEFT = 50
_MARGIN_RIGHT = 545
_MARGIN_TOP = 50
_MARGIN_BOTTOM = 792
_CONTENT_WIDTH = _MARGIN_RIGHT - _MARGIN_LEFT

_TEXT = (0.102, 0.153, 0.267)
_HEADING = (0.059, 0.090, 0.165)
_H2 = (0.118, 0.227, 0.541)
_H3 = (0.200, 0.255, 0.333)
_CODE_BG = (0.973, 0.980, 0.988)
_CODE_BORDER = (0.796, 0.835, 0.882)
_TABLE_HEAD_BG = (0.937, 0.965, 1.0)
_TABLE_ALT = (0.973, 0.980, 0.988)
_ACCENT = (0.145, 0.388, 0.922)

BlockKind = Literal['h1', 'h2', 'h3', 'p', 'code', 'table', 'hr']


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    content: str | list[list[str]]


def _parse_inline_runs(text: str) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    cursor = 0
    for match in re.finditer(r'(\*\*[^*]+\*\*|`[^`]+`)', text):
        if match.start() > cursor:
            runs.append(('normal', text[cursor:match.start()]))
        token = match.group(0)
        if token.startswith('**'):
            runs.append(('bold', token[2:-2]))
        else:
            runs.append(('code', token[1:-1]))
        cursor = match.end()
    if cursor < len(text):
        runs.append(('normal', text[cursor:]))
    return runs or [('normal', text)]


def _parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith('|') or stripped.count('|') < 2:
        return None
    cells = [cell.strip() for cell in stripped.strip('|').split('|')]
    if all(set(cell) <= {'-', ':', ' '} for cell in cells):
        return None
    return cells


def _is_table_separator_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith('|'):
        return False
    cells = [cell.strip() for cell in stripped.strip('|').split('|')]
    return bool(cells) and all(set(cell) <= {'-', ':', ' '} for cell in cells)


def parse_markdown_blocks(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    lines = markdown.replace('\r\n', '\n').split('\n')
    index = 0
    in_code = False
    code_lines: list[str] = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith('```'):
            if in_code:
                blocks.append(Block('code', '\n'.join(code_lines)))
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue

        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if not stripped:
            index += 1
            continue

        if stripped == '---':
            blocks.append(Block('hr', ''))
            index += 1
            continue

        if stripped.startswith('#'):
            level = min(len(stripped) - len(stripped.lstrip('#')), 3)
            text = stripped[level:].strip()
            blocks.append(Block(f'h{level}', text))
            index += 1
            continue

        if stripped.startswith('|'):
            table_rows: list[list[str]] = []
            while index < len(lines):
                if _is_table_separator_line(lines[index]):
                    index += 1
                    continue
                row = _parse_table_row(lines[index])
                if row is None:
                    break
                table_rows.append(row)
                index += 1
            if table_rows:
                blocks.append(Block('table', table_rows))
            else:
                index += 1
            continue

        paragraph_lines = [line.strip()]
        index += 1
        while index < len(lines):
            nxt = lines[index].strip()
            if (
                not nxt
                or nxt == '---'
                or nxt.startswith('#')
                or nxt.startswith('|')
                or nxt.startswith('```')
            ):
                break
            paragraph_lines.append(nxt)
            index += 1
        blocks.append(Block('p', ' '.join(paragraph_lines)))

    return blocks


class _PdfBuilder:
    def __init__(self) -> None:
        self.doc = fitz.open()
        self.page = self.doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
        self.y = _MARGIN_TOP
        self._font_body = fitz.Font('helv')
        self._font_bold = fitz.Font('helvetica-bold')
        self._font_code = fitz.Font('cour')

    def _font_for_style(self, style: str) -> fitz.Font:
        if style == 'bold':
            return self._font_bold
        if style == 'code':
            return self._font_code
        return self._font_body

    def _fontsize_for_style(self, style: str, base: float) -> float:
        return 8.5 if style == 'code' else base

    def _ensure_space(self, height: float) -> None:
        if self.y + height <= _MARGIN_BOTTOM:
            return
        self.page = self.doc.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
        self.y = _MARGIN_TOP

    def _wrap_runs(
        self,
        runs: list[tuple[str, str]],
        max_width: float,
        base_size: float,
    ) -> list[list[tuple[str, fitz.Font, float, str]]]:
        lines: list[list[tuple[str, fitz.Font, float, str]]] = []
        current: list[tuple[str, fitz.Font, float, str]] = []
        current_width = 0.0

        def flush_word(
            word: str,
            style: str,
            *,
            prefix_space: bool,
        ) -> None:
            nonlocal current_width, current
            font = self._font_for_style(style)
            size = self._fontsize_for_style(style, base_size)
            chunk = ('' if prefix_space else '') + word
            if prefix_space and current:
                chunk = ' ' + word
            chunk_width = font.text_length(chunk, fontsize=size)
            if current_width + chunk_width > max_width and current:
                lines.append(current)
                current = [(word, font, size, style)]
                current_width = font.text_length(word, fontsize=size)
                return
            if current and current[-1][3] == style:
                text, seg_font, seg_size, seg_style = current[-1]
                joined = f'{text} {word}'
                current[-1] = (joined, seg_font, seg_size, seg_style)
                current_width += chunk_width
            else:
                current.append((chunk, font, size, style))
                current_width += chunk_width

        for style, text in runs:
            words = text.split(' ')
            for word_index, word in enumerate(words):
                if not word:
                    continue
                flush_word(word, style, prefix_space=word_index > 0 or bool(current))

        if current:
            lines.append(current)
        return lines or [[('', self._font_body, base_size, 'normal')]]

    def _draw_text_line(
        self,
        segments: list[tuple[str, fitz.Font, float, str]],
        *,
        x: float,
        baseline: float,
        color: tuple[float, float, float],
    ) -> None:
        cursor = x
        for text, font, size, _style in segments:
            if not text:
                continue
            self.page.insert_text(
                (cursor, baseline),
                text,
                fontname=font.name,
                fontsize=size,
                color=color,
            )
            cursor += font.text_length(text, fontsize=size)

    def add_heading(self, level: int, text: str) -> None:
        if level == 1:
            size, color, before, after = 22, _HEADING, 0, 14
        elif level == 2:
            size, color, before, after = 14, _H2, 20, 10
        else:
            size, color, before, after = 11, _H3, 14, 8

        self.y += before
        self._ensure_space(size + after + 8)
        baseline = self.y + size
        self.page.insert_text(
            (_MARGIN_LEFT, baseline),
            text,
            fontname=self._font_bold.name,
            fontsize=size,
            color=color,
        )
        self.y = baseline + 4
        if level == 1:
            self.page.draw_line(
                fitz.Point(_MARGIN_LEFT, self.y),
                fitz.Point(_MARGIN_RIGHT, self.y),
                color=_ACCENT,
                width=1.5,
            )
            self.y += 6
        self.y += after

    def add_paragraph(self, text: str) -> None:
        runs = _parse_inline_runs(text)
        line_height = 15.0
        lines = self._wrap_runs(runs, _CONTENT_WIDTH, 10.0)
        block_height = len(lines) * line_height + 10
        self._ensure_space(block_height)

        for line in lines:
            self._draw_text_line(
                line,
                x=_MARGIN_LEFT,
                baseline=self.y + 10,
                color=_TEXT,
            )
            self.y += line_height
        self.y += 10

    def add_code(self, code: str) -> None:
        lines = code.split('\n')
        padding = 10.0
        line_height = 8 * 1.35
        block_height = padding * 2 + len(lines) * line_height + 10
        self._ensure_space(block_height)

        top = self.y
        bottom = top + padding * 2 + len(lines) * line_height
        rect = fitz.Rect(_MARGIN_LEFT, top, _MARGIN_RIGHT, bottom)
        self.page.draw_rect(rect, color=_CODE_BG, fill=_CODE_BG)
        self.page.draw_rect(rect, color=_CODE_BORDER, width=0.6)

        baseline = top + padding + 8
        for line in lines:
            self.page.insert_text(
                (_MARGIN_LEFT + padding, baseline),
                line,
                fontname=self._font_code.name,
                fontsize=8,
                color=_HEADING,
            )
            baseline += line_height
        self.y = bottom + 10

    def add_table(self, rows: list[list[str]]) -> None:
        if not rows:
            return

        col_count = max(len(row) for row in rows)
        col_width = _CONTENT_WIDTH / col_count
        cell_padding_x = 6.0
        cell_padding_y = 6.0
        font_size = 9.0
        line_height = 12.0

        wrapped_rows: list[list[list[tuple[str, fitz.Font, float, str]]]] = []
        row_heights: list[float] = []
        for row_index, row in enumerate(rows):
            padded = row + [''] * (col_count - len(row))
            wrapped_cells = []
            max_lines = 1
            for cell in padded:
                runs = _parse_inline_runs(cell)
                lines = self._wrap_runs(
                    runs,
                    col_width - cell_padding_x * 2,
                    font_size,
                )
                max_lines = max(max_lines, len(lines))
                wrapped_cells.append(lines)
            row_height = cell_padding_y * 2 + max_lines * line_height
            row_heights.append(row_height)
            wrapped_rows.append(wrapped_cells)

        total_height = sum(row_heights) + 12
        self._ensure_space(total_height)

        top = self.y
        cursor_y = top
        for row_index, wrapped_cells in enumerate(wrapped_rows):
            row_height = row_heights[row_index]
            for col_index in range(col_count):
                x0 = _MARGIN_LEFT + col_index * col_width
                x1 = x0 + col_width
                rect = fitz.Rect(x0, cursor_y, x1, cursor_y + row_height)
                fill = _TABLE_HEAD_BG if row_index == 0 else (
                    _TABLE_ALT if row_index % 2 == 0 else (1, 1, 1)
                )
                self.page.draw_rect(rect, color=fill, fill=fill)
                self.page.draw_rect(rect, color=_CODE_BORDER, width=0.5)

                lines = wrapped_cells[col_index]
                baseline = cursor_y + cell_padding_y + font_size
                for line in lines:
                    self._draw_text_line(
                        line,
                        x=x0 + cell_padding_x,
                        baseline=baseline,
                        color=_H2 if row_index == 0 else _TEXT,
                    )
                    baseline += line_height
            cursor_y += row_height

        self.y = cursor_y + 12

    def add_hr(self) -> None:
        self._ensure_space(16)
        self.page.draw_line(
            fitz.Point(_MARGIN_LEFT, self.y),
            fitz.Point(_MARGIN_RIGHT, self.y),
            color=_CODE_BORDER,
            width=0.6,
        )
        self.y += 16

    def tobytes(self) -> bytes:
        try:
            return self.doc.tobytes(deflate=True, garbage=3)
        finally:
            self.doc.close()


def markdown_to_pdf_bytes(markdown: str) -> bytes:
    builder = _PdfBuilder()
    for block in parse_markdown_blocks(markdown):
        if block.kind == 'h1':
            builder.add_heading(1, block.content)
        elif block.kind == 'h2':
            builder.add_heading(2, block.content)
        elif block.kind == 'h3':
            builder.add_heading(3, block.content)
        elif block.kind == 'p':
            builder.add_paragraph(block.content)
        elif block.kind == 'code':
            builder.add_code(block.content)
        elif block.kind == 'table':
            builder.add_table(block.content)
        elif block.kind == 'hr':
            builder.add_hr()
    return builder.tobytes()
