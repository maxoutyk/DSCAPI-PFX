"""Render API documentation markdown as an OpenDocument Text (.odt) file."""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

ODT_MIMETYPE = 'application/vnd.oasis.opendocument.text'

_STYLES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
  xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
  <office:styles>
    <style:style style:name="Standard" style:family="paragraph"/>
    <style:style style:name="Heading_20_1" style:family="paragraph">
      <style:text-properties fo:font-size="18pt" fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="Heading_20_2" style:family="paragraph">
      <style:text-properties fo:font-size="14pt" fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="Heading_20_3" style:family="paragraph">
      <style:text-properties fo:font-size="12pt" fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="Preformatted" style:family="paragraph">
      <style:text-properties fo:font-family="Courier New, monospace" fo:font-size="9pt"/>
    </style:style>
    <style:style style:name="Code" style:family="text">
      <style:text-properties fo:font-family="Courier New, monospace" fo:font-size="9pt"/>
    </style:style>
    <style:style style:name="Bold" style:family="text">
      <style:text-properties fo:font-weight="bold"/>
    </style:style>
  </office:styles>
</office:document-styles>"""

_META_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <office:meta>
    <dc:title>IG E-Sign API documentation</dc:title>
    <meta:generator>IG E-Sign</meta:generator>
  </office:meta>
</office:document-meta>"""

_MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.text" manifest:full-path="/"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="styles.xml"/>
  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="meta.xml"/>
</manifest:manifest>"""

_HEADING_STYLES = {
    1: 'Heading_20_1',
    2: 'Heading_20_2',
    3: 'Heading_20_3',
}


def _inline_markup(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r'(\*\*[^*]+\*\*|`[^`]+`)', text):
        if match.start() > cursor:
            parts.append(escape(text[cursor:match.start()]))
        token = match.group(0)
        if token.startswith('**'):
            inner = escape(token[2:-2])
            parts.append(f'<text:span text:style-name="Bold">{inner}</text:span>')
        else:
            inner = escape(token[1:-1])
            parts.append(f'<text:span text:style-name="Code">{inner}</text:span>')
        cursor = match.end()
    if cursor < len(text):
        parts.append(escape(text[cursor:]))
    return ''.join(parts) if parts else escape(text)


def _paragraph(text: str, *, style: str = 'Standard') -> str:
    return f'<text:p text:style-name="{style}">{_inline_markup(text)}</text:p>'


def _heading(text: str, level: int) -> str:
    style = _HEADING_STYLES.get(level, 'Heading_20_3')
    return (
        f'<text:h text:outline-level="{level}" text:style-name="{style}">'
        f'{_inline_markup(text)}</text:h>'
    )


def _code_block(lines: list[str]) -> str:
    body = escape('\n'.join(lines))
    return f'<text:p text:style-name="Preformatted">{body}</text:p>'


def _table_rows(rows: list[list[str]]) -> str:
    if not rows:
        return ''
    xml_rows = []
    for row in rows:
        cells = ''.join(
            f'<table:table-cell office:value-type="string">'
            f'<text:p text:style-name="Standard">{_inline_markup(cell)}</text:p>'
            f'</table:table-cell>'
            for cell in row
        )
        xml_rows.append(f'<table:table-row>{cells}</table:table-row>')
    return (
        '<table:table table:name="ApiDocTable" table:style-name="Standard">'
        + ''.join(xml_rows)
        + '</table:table>'
    )


def _parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith('|') or stripped.count('|') < 2:
        return None
    cells = [cell.strip() for cell in stripped.strip('|').split('|')]
    if all(set(cell) <= {'-', ':', ' '} for cell in cells):
        return None
    return cells


def markdown_to_odt_bytes(markdown: str) -> bytes:
    blocks: list[str] = []
    lines = markdown.replace('\r\n', '\n').split('\n')
    index = 0
    in_code = False
    code_lines: list[str] = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith('```'):
            if in_code:
                blocks.append(_code_block(code_lines))
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
            index += 1
            continue

        if stripped.startswith('#'):
            level = len(stripped) - len(stripped.lstrip('#'))
            text = stripped[level:].strip()
            blocks.append(_heading(text, min(level, 3)))
            index += 1
            continue

        if stripped.startswith('|'):
            table_rows: list[list[str]] = []
            while index < len(lines):
                row = _parse_table_row(lines[index])
                if row is None:
                    break
                table_rows.append(row)
                index += 1
            blocks.append(_table_rows(table_rows))
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
        blocks.append(_paragraph(' '.join(paragraph_lines)))

    content_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">'
        '<office:body><office:text>'
        + ''.join(blocks)
        + '</office:text></office:body></office:document-content>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(
            'mimetype',
            ODT_MIMETYPE,
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr('META-INF/manifest.xml', _MANIFEST_XML)
        archive.writestr('styles.xml', _STYLES_XML)
        archive.writestr('meta.xml', _META_XML)
        archive.writestr('content.xml', content_xml)
    return buffer.getvalue()
