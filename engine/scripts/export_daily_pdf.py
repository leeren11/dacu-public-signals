#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出大促公开信号日更为可下载中文 PDF（只读库；不编 GMV；不改 T0）。

Dual-Track: shows T0_* + Rolling_* columns; yesterday complete bucket table
with value / DoD% / slope_7d.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parent))

from display_names import BLACK_FRIDAY, FREEZE_ID, zh_name
from rolling_engine import (
    apply_migrate_v4,
    compute_rolling_for_as_of,
    connect,
    fix_black_friday_anchors,
    persist_rolling,
    pick_run,
    shanghai_now_iso,
)

ROOT = Path("/workspace/dacu-signal")
DB_PATH = ROOT / "db" / "dacu_signals.sqlite"
REPORTS_DIR = ROOT / "reports"
ASSETS_FONTS = ROOT / "assets" / "fonts"

PAGE_MOBILE = (
    "https://cursor.com/canvas/store-0fa19706-d26c-4069-a720-b9e0a788da13/"
    "731f43a0-38d7-48b9-91ea-a3275297e774"
)
PAGE_ARCH = (
    "https://cursor.com/canvas/store-0fa19706-d26c-4069-a720-b9e0a788da13/"
    "e9735654-072a-4aed-99db-54b7ae94f100"
)

FONT_CANDIDATES = [
    (str(ASSETS_FONTS / "wqy-microhei.ttc"), 0),
    (str(ASSETS_FONTS / "wqy-microhei.ttf"), None),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
    ("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf", None),
    ("/usr/share/fonts/truetype/droid/DroidSansFallback.ttf", None),
    ("/usr/share/fonts/truetype/arphic/uming.ttc", 0),
]


def resolve_font() -> Tuple[str, str]:
    for path, sub in FONT_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            name = "DacuCJK"
            if path.lower().endswith(".ttc"):
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=sub or 0))
            else:
                pdfmetrics.registerFont(TTFont(name, path))
            return name, path
        except Exception as e:
            print(f"[warn] font skip {path}: {e}", file=sys.stderr)
            continue
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light", "reportlab CID STSong-Light"
    except Exception as e:
        raise RuntimeError(f"无法注册任何 CJK 字体: {e}") from e


def fmt_num(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "—"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.{digits}f}"


def fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f}%"


def load_freeze(con) -> Dict[str, Any]:
    pf = con.execute(
        f"SELECT * FROM prediction_freeze WHERE freeze_id='{FREEZE_ID}'"
    ).fetchone()
    pending = con.execute(
        f"""
        SELECT COUNT(*) AS n,
               SUM(CASE WHEN actual_value IS NULL THEN 1 ELSE 0 END) AS pending_n
        FROM backtest_logs WHERE freeze_id='{FREEZE_ID}'
        """
    ).fetchone()
    return {
        "prediction_freeze": dict(pf) if pf else None,
        "backtest_n": pending["n"] if pending else 0,
        "backtest_pending": pending["pending_n"] if pending else 0,
    }


def build_styles(font: str) -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title_zh", parent=base["Title"], fontName=font, fontSize=13,
            leading=17, alignment=TA_CENTER, spaceAfter=2 * mm,
        ),
        "header": ParagraphStyle(
            "header_zh", parent=base["Normal"], fontName=font, fontSize=8,
            leading=11, textColor=colors.HexColor("#444444"), alignment=TA_CENTER,
        ),
        "meta": ParagraphStyle(
            "meta_zh", parent=base["Normal"], fontName=font, fontSize=8,
            leading=11, alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "h2_zh", parent=base["Heading2"], fontName=font, fontSize=10,
            leading=13, spaceBefore=2.5 * mm, spaceAfter=1.2 * mm,
            textColor=colors.HexColor("#1a1a1a"),
        ),
        "body": ParagraphStyle(
            "body_zh", parent=base["Normal"], fontName=font, fontSize=8, leading=11,
        ),
        "cell": ParagraphStyle(
            "cell_zh", parent=base["Normal"], fontName=font, fontSize=7.2, leading=9.5,
        ),
        "cell_zh_name": ParagraphStyle(
            "cell_zh_name", parent=base["Normal"], fontName=font, fontSize=7.5,
            leading=10, textColor=colors.HexColor("#111111"),
        ),
        "cell_en": ParagraphStyle(
            "cell_en", parent=base["Normal"], fontName=font, fontSize=6.2,
            leading=8, textColor=colors.HexColor("#555555"),
        ),
        "cell_small": ParagraphStyle(
            "cell_small_zh", parent=base["Normal"], fontName=font, fontSize=6.5,
            leading=8.5, textColor=colors.HexColor("#333333"),
        ),
        "footer": ParagraphStyle(
            "footer_zh", parent=base["Normal"], fontName=font, fontSize=6.5,
            leading=9, textColor=colors.HexColor("#555555"), alignment=TA_LEFT,
        ),
        "warn": ParagraphStyle(
            "warn_zh", parent=base["Normal"], fontName=font, fontSize=7.5,
            leading=10, textColor=colors.HexColor("#8B0000"),
        ),
    }


def table_style(font: str) -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")),
        ]
    )


def render_markdown_pdf(md_path, out_path):
    """Render exact Markdown source; tables wrap and Chinese/English stay separate."""
    import re
    from html import escape
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import LongTable
    font,desc=resolve_font(); styles=build_styles(font)
    for st in styles.values():
        st.wordWrap='CJK'
        st.splitLongWords=True
    styles['cell'].fontSize=6.2;styles['cell'].leading=8.4
    width=277*mm
    story=[]
    def clean(text):
        return escape(text.replace('**','').replace('`',''))
    def para(text,kind='body'):
        return Paragraph(clean(text),styles[kind])
    lines=Path(md_path).read_text().splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[v.strip() for v in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+',c) for c in cells):rows.append(cells)
                i+=1
            n=len(rows[0]);weights=[1.0]*n
            for j,h in enumerate(rows[0]):
                if any(k in h for k in ('SKU','话题','English')):weights[j]=3.5
                elif any(k in h for k in ('窗口','平台','日期','中文')):weights[j]=1.7
            widths=[width*w/sum(weights) for w in weights]
            data=[[para(c,'cell') for c in row] for row in rows]
            t=LongTable(data,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(table_style(font));story.append(t);story.append(Spacer(1,2*mm));continue
        if line.startswith('# '):story.append(para(line[2:],'title'))
        elif line.startswith('## '):story.append(para(line[3:],'h2'))
        elif line.startswith('### '):story.append(para(line[4:],'h2'))
        elif line.strip():story.append(para(line))
        else:story.append(Spacer(1,1.4*mm))
        i+=1
    Path(out_path).parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(out_path),pagesize=landscape(A4),leftMargin=10*mm,rightMargin=10*mm,topMargin=10*mm,bottomMargin=10*mm,title='Director-v1 Dual-Track Public Signals',author='黎治工作')
    def footer(canvas,doc):
        canvas.setFont(font,7);canvas.drawString(10*mm,5*mm,f'director_v1 / Asia/Shanghai / page {doc.page} / public proxies, not GMV')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(f'[pdf] {out_path}')
    return Path(out_path)

def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--as-of',required=True);ap.add_argument('--out');ap.add_argument('--no-persist',action='store_true');a=ap.parse_args(argv)
    from export_daily_md import export_one,STAMP
    md=STAMP/'daily'/f'{a.as_of}.md'
    if not md.exists():export_one(a.as_of)
    render_markdown_pdf(md,a.out or REPORTS_DIR/f'dacu_daily_{a.as_of}.pdf');return 0
if __name__=='__main__':raise SystemExit(main())
