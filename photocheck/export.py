"""Atomic XLSX export using the standard library; no Excel installation needed."""
import os
from pathlib import Path
import re
import uuid
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from .domain import Result, Status

HEADERS = ["파일명", "판정사유"]
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def excel_text(value):
    value = re.sub(r'_x[0-9a-fA-F]{4}_', lambda m: '_x005F_'+m.group()[1:], str(value))
    value = ''.join(c if c in '\t\n\r' or '\x20' <= c <= '\ud7ff' or
                    '\ue000' <= c <= '\ufffd' or '\U00010000' <= c <= '\U0010ffff'
                    else f'_x{ord(c):04X}_' for c in value)
    if len(value) > 32767:
        raise ValueError("엑셀 셀에 저장할 수 있는 글자 수를 초과했습니다.")
    return escape(value)


def write_workbook(handle, rows):
    with ZipFile(handle, 'w', compression=ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>''')
        archive.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets><sheet name="확인 대상" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="{REL}/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', f'''<styleSheet xmlns="{NS}">
<fonts count="2"><font><sz val="11"/><name val="맑은 고딕"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="맑은 고딕"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2563EB"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        with archive.open('xl/worksheets/sheet1.xml', 'w') as sheet:
            def write(value):
                sheet.write(value.encode('utf-8'))
            last = len(rows)+1
            write(f'<worksheet xmlns="{NS}"><dimension ref="A1:B{last}"/><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="36"/><cols>')
            for index, width in enumerate((22,72), 1):
                write(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>')
            write('</cols><sheetData>')
            def row(index, values, header=False):
                write(f'<row r="{index}"'+(' ht="26" customHeight="1"' if header else '')+'>')
                for column, value in enumerate(values):
                    # Inline strings never execute filenames/reasons as formulas.
                    write(f'<c r="{chr(65+column)}{index}" t="inlineStr" s="{int(header)}"><is><t xml:space="preserve">{excel_text(value)}</t></is></c>')
                write('</row>')
            row(1, HEADERS, True)
            for index, r in enumerate(rows,2):
                row(index, [r.path.name, ' | '.join(r.reasons)])
            write(f'</sheetData><autoFilter ref="A1:B{last}"/></worksheet>')


def export_excel(path: Path, results: list[Result]):
    path = Path(path)
    if any(path.resolve() == r.path.resolve() for r in results):
        raise ValueError("원본 사진 경로에는 결과를 저장할 수 없습니다.")
    if path.suffix.casefold() != '.xlsx':
        raise ValueError("결과 파일은 .xlsx 확장자로 저장하세요.")
    rows = [r for r in results if r.status != Status.NORMAL]
    temporary = path.parent/f'.photocheck-{uuid.uuid4().hex}.tmp'
    try:
        with temporary.open('xb') as handle:
            write_workbook(handle, rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(rows)
