from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/experiments/flowstudio-participant-questionnaire-zh.md"
OUTPUT = ROOT / "docs/experiments/FlowStudio_参与者实验问卷_v0.9.pdf"
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"

INK = colors.HexColor("#172033")
BLUE = colors.HexColor("#2457C5")
MUTED = colors.HexColor("#677085")
LIGHT_BLUE = colors.HexColor("#EAF0FF")
LIGHT_GRAY = colors.HexColor("#F3F5F8")
LINE = colors.HexColor("#CBD2DC")


def clean(text):
    return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)


def expand_blocks(lines):
    b_start = next(i for i, line in enumerate(lines) if line.startswith("## B."))
    c_start = next(i for i, line in enumerate(lines) if line.startswith("## C."))
    d_start = next(i for i, line in enumerate(lines) if line.startswith("## D."))
    expanded = list(lines[:b_start])
    for trial in range(1, 5):
        block = list(lines[b_start:c_start])
        block[0] = f"## B{trial}. 第 {trial} 次任务后问卷"
        expanded.extend(line for line in block if "请将本页复制四份" not in line)
    for condition in range(1, 3):
        block = list(lines[c_start:d_start])
        block[0] = f"## C{condition}. 第 {condition} 个系统后问卷"
        expanded.extend(block)
    expanded.extend(lines[d_start:])
    return expanded


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("CJK", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(letter[0] - 0.72 * inch, letter[1] - 0.35 * inch, "FLOWSTUDIO  |  PARTICIPANT STUDY")
    canvas.drawCentredString(letter[0] / 2, 0.33 * inch, f"参与者编号：____________    第 {doc.page} 页")
    canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="CJK", fontSize=23, leading=28, textColor=INK, alignment=TA_LEFT, spaceAfter=8),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="CJK", fontSize=15, leading=19, textColor=BLUE, spaceBefore=4, spaceAfter=7),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="CJK", fontSize=11.5, leading=14, textColor=INK, spaceBefore=5, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="CJK", fontSize=9.2, leading=13, textColor=INK, spaceAfter=3),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName="CJK", fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=3),
        "table": ParagraphStyle("table", parent=base["BodyText"], fontName="CJK", fontSize=7.4, leading=9.5, textColor=INK),
    }


def make_table(rows, st):
    if len(rows[0]) == 3:
        widths = [0.85 * inch, 2.85 * inch, 3.25 * inch]
    else:
        widths = [6.95 * inch / len(rows[0])] * len(rows[0])
    data = [[Paragraph(clean(cell), st["table"]) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_BLUE),
        ("GRID", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def build():
    pdfmetrics.registerFont(TTFont("CJK", FONT, subfontIndex=0))
    lines = expand_blocks(SOURCE.read_text(encoding="utf-8").splitlines())
    st = styles()

    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=letter,
        leftMargin=0.72 * inch, rightMargin=0.72 * inch,
        topMargin=0.62 * inch, bottomMargin=0.55 * inch,
        title="FlowStudio 参与者实验问卷",
        author="FlowStudio Research Team",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate("study", [frame], onPage=add_page_number))

    story = []
    title = lines[0].removeprefix("# ")
    story.append(Paragraph(title, st["title"]))
    meta = [
        ["参与者编号：____________    顺序组：G1 / G2 / G3 / G4", "日期：____________"],
        ["研究员编号：____________", "开始：__________    结束：__________"],
    ]
    meta_table = Table([[Paragraph(x, st["small"]) for x in row] for row in meta], colWidths=[3.8 * inch, 3.15 * inch])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([meta_table, Spacer(1, 7), Paragraph("填写说明：本问卷只使用参与者编号。没有正确或错误答案，请按照刚才的真实体验作答。", st["small"])])

    i = 1
    first_section = True
    while i < len(lines):
        text = lines[i].strip()
        i += 1
        if not text or text.startswith("**参与者编号") or text.startswith("**研究员编号") or text.startswith("> 本问卷"):
            continue
        if text.startswith("| "):
            raw_rows = [text]
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw_rows.append(lines[i].strip())
                i += 1
            rows = []
            for raw in raw_rows:
                cells = [c.strip() for c in raw.strip("|").split("|")]
                if all(re.fullmatch(r":?-+:?", c.replace(" ", "")) for c in cells):
                    continue
                rows.append(cells)
            story.append(make_table(rows, st))
            story.append(Spacer(1, 4))
            continue
        if text.startswith("## "):
            heading = text[3:]
            if not first_section:
                story.append(PageBreak())
            first_section = False
            story.append(Paragraph(clean(heading), st["h1"]))
            continue
        if text.startswith("### "):
            story.append(Paragraph(clean(text[4:]), st["h2"]))
            continue
        if text.startswith("# "):
            continue
        if text.startswith("________________________________________________________________"):
            story.append(Paragraph("________________________________________________________________________________", st["small"]))
            continue
        style = st["body"]
        if text.startswith("研究记录："):
            style = st["small"]
        story.append(Paragraph(clean(text), style))

    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    build()
