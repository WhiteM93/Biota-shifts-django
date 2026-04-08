"""Excel и PDF отчёты."""
import os
from io import BytesIO
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from biota_shifts.config import APP_DIR
from biota_shifts.constants import (
    HOURS_GRID_NO_PUNCH,
    HOURS_GRID_SUFFIX_OUTSIDE_GRAPH,
    MONTH_NAMES_RU,
    SCHEDULE_CODE_COLORS,
)

def build_pretty_excel(df: pd.DataFrame, sheet_name: str = "Смены") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        center = Alignment(horizontal="center", vertical="center")
        thin = Side(style="thin", color="D9D9D9")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # Сетка и центрирование для всех ячеек
        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                cell = ws.cell(row=r, column=c)
                cell.alignment = center
                cell.border = border

        for idx, col_name in enumerate(df.columns, start=1):
            max_len = max([len(str(col_name))] + [len(str(v)) for v in df[col_name].fillna("")])
            cap = 60 if str(col_name) == "Сотрудник" else 40
            ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = min(max_len + 2, cap)

    output.seek(0)
    return output.getvalue()


def build_schedule_excel(df: pd.DataFrame, sheet_name: str = "График", year: int | None = None, month: int | None = None) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]

        header_fill = PatternFill(start_color="CCCCCC", end_color="CCCCCC", fill_type="solid")
        header_font = Font(color="000000", bold=True)
        center = Alignment(horizontal="center", vertical="center")
        weekend_header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        thin = Side(style="thin", color="D9D9D9")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center

        # Подсветка выходных (сб/вс) в строке заголовка
        if year is not None and month is not None:
            # weekday: Пн=0 ... Вс=6
            for col_idx, col_name in enumerate(df.columns, start=1):
                if str(col_name).isdigit():
                    day_num = int(col_name)
                    if 1 <= day_num <= 31:
                        wd = date(year, month, day_num).weekday()
                        if wd in (5, 6):
                            cell = ws.cell(row=1, column=col_idx)
                            cell.fill = weekend_header_fill
                            cell.font = Font(color="000000", bold=True)

        ws.freeze_panes = "D2"
        ws.auto_filter.ref = ws.dimensions

        day_cols = [idx for idx, name in enumerate(df.columns, start=1) if str(name).isdigit()]
        for row in range(2, ws.max_row + 1):
            for col_idx in day_cols:
                cell = ws.cell(row=row, column=col_idx)
                value = str(cell.value).strip().lower() if cell.value is not None else ""
                if value in SCHEDULE_CODE_COLORS:
                    cell.fill = PatternFill(
                        start_color=SCHEDULE_CODE_COLORS[value],
                        end_color=SCHEDULE_CODE_COLORS[value],
                        fill_type="solid",
                    )
                cell.alignment = center

        # Сетка и центрирование для всех ячеек (включая «Сотрудник» и «Код»)
        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                cell = ws.cell(row=r, column=c)
                cell.alignment = center
                cell.border = border

        # Размеры под ваши требования
        # openpyxl: ширина в “Excel units”, высота в “points”
        # приблизительно: px ~= 0.75 * pt  => pt ~= px / 0.75
        day_width_px = 30
        day_width_units = int(round((day_width_px - 5) / 7))  # эмпирическая формула Excel width
        row_height_px = 30
        row_height_points = row_height_px / 0.75

        for r in range(1, ws.max_row + 1):
            ws.row_dimensions[r].height = row_height_points

        max_employee_len = 0
        if "Сотрудник" in df.columns:
            max_employee_len = max(
                [len("Сотрудник")] + [len(str(v)) for v in df["Сотрудник"].fillna("").astype(str)]
            )

        # openpyxl задаёт ширину в “Excel units” (не в пикселях).
        # Для стандартного Excel это примерно 1 unit ~= 7px при шрифте Calibri ~11.
        employee_width_units = int(round(180 / 7))

        for idx, col_name in enumerate(df.columns, start=1):
            if str(col_name).isdigit():
                width = day_width_units
            elif col_name == "Сотрудник":
                width = employee_width_units
            elif col_name == "Код":
                width = 8
            else:
                width = 10
            ws.column_dimensions[ws.cell(row=1, column=idx).column_letter].width = width

    output.seek(0)
    return output.getvalue()


def _resolve_logo_path() -> Path | None:
    env_logo = (os.getenv("BIOTA_LOGO_PATH") or "").strip()
    if env_logo:
        p = Path(env_logo)
        if p.is_file():
            return p
    for p in (APP_DIR / "Logo.png", APP_DIR / "logo.png"):
        if p.is_file():
            return p
    return None


def _resolve_pdf_cyrillic_font() -> tuple[str, Path | None]:
    """(имя шрифта для ReportLab, путь к TTF или None)."""
    env_font = (os.getenv("BIOTA_REPORT_FONT_TTF") or "").strip()
    candidates: list[Path] = []
    if env_font:
        candidates.append(Path(env_font))
    windir = os.environ.get("WINDIR", "C:\\Windows")
    candidates.extend(
        [
            Path(windir) / "Fonts" / "arial.ttf",
            Path(windir) / "Fonts" / "arialuni.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
    )
    for p in candidates:
        try:
            if p.is_file():
                return ("ArialUnicode", p)
        except OSError:
            continue
    return ("Helvetica", None)


def build_stats_pdf(stats_df: pd.DataFrame, employee_name: str, month_start: date) -> bytes:
    """PDF-отчет для печати по статистике сотрудника за месяц."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from PIL import Image

    # Шрифт с поддержкой кириллицы (Windows / Linux или BIOTA_REPORT_FONT_TTF)
    font_name, ttf_path = _resolve_pdf_cyrillic_font()
    if ttf_path is not None:
        pdfmetrics.registerFont(TTFont("ArialUnicode", str(ttf_path)))
        font_name = "ArialUnicode"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    logo_path = _resolve_logo_path()
    if logo_path is not None:
        logo_buf = BytesIO()
        img = Image.open(logo_path)
        # Не переводить в grayscale — иначе теряется альфа и пропадает прозрачный фон PNG
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode == "CMYK":
            img = img.convert("RGBA")
        elif img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.save(logo_buf, format="PNG")
        logo_buf.seek(0)
        story.append(RLImage(logo_buf, width=24 * mm, height=24 * mm, mask="auto"))
        story.append(Spacer(1, 3 * mm))

    title = f"Статистика сотрудника: {employee_name}"
    subtitle = f"Период: {month_start.strftime('%m.%Y')}"
    title_style = styles["Title"]
    title_style.fontName = font_name
    title_style.fontSize = 14
    story.append(Paragraph(title, title_style))
    sub_style = styles["Normal"]
    sub_style.fontName = font_name
    story.append(Paragraph(subtitle, sub_style))
    story.append(Spacer(1, 4 * mm))

    def _stats_pdf_header_label(col: str) -> str:
        if col == "Пришел":
            return "Пришел (первая)"
        if col == "Ушел":
            return "Ушел (последняя)"
        return str(col)

    cols = list(stats_df.columns)
    table_data = [[_stats_pdf_header_label(c) for c in cols]]
    for _, r in stats_df.iterrows():
        row_out: list[str] = []
        for c in cols:
            v = r.get(c)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                row_out.append("")
            else:
                row_out.append(str(v))
        table_data.append(row_out)

    # Ширина контента ~190 мм при полях 10 мм — колонки под книжный A4
    _default_w = [22, 16, 38, 22, 22, 22, 18, 18]
    if len(cols) == len(_default_w):
        col_w_mm = _default_w
    else:
        w = 190.0 / max(len(cols), 1)
        col_w_mm = [w] * len(cols)
    table = Table(table_data, repeatRows=1, colWidths=[w * mm for w in col_w_mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def build_hours_grid_pdf(grid_df: pd.DataFrame, year: int, month: int) -> bytes:
    """PDF сетки «Часы по дням»: только сотрудник и дни (без Порядок/Код), альбом A4."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from PIL import Image

    font_name, ttf_path = _resolve_pdf_cyrillic_font()
    if ttf_path is not None:
        pdfmetrics.registerFont(TTFont("ArialUnicode", str(ttf_path)))
        font_name = "ArialUnicode"

    buffer = BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page,
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    logo_path = _resolve_logo_path()
    if logo_path is not None:
        logo_buf = BytesIO()
        img = Image.open(logo_path)
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode == "CMYK":
            img = img.convert("RGBA")
        elif img.mode not in ("RGBA", "RGB"):
            img = img.convert("RGBA")
        img.save(logo_buf, format="PNG")
        logo_buf.seek(0)
        story.append(RLImage(logo_buf, width=22 * mm, height=22 * mm, mask="auto"))
        story.append(Spacer(1, 2 * mm))

    title_style = styles["Title"]
    title_style.fontName = font_name
    title_style.fontSize = 13
    story.append(Paragraph("Часы по дням (Biota, факт)", title_style))
    sub_style = styles["Normal"]
    sub_style.fontName = font_name
    sub_style.fontSize = 10
    story.append(
        Paragraph(
            f"Период: {MONTH_NAMES_RU.get(month, str(month))} {year}",
            sub_style,
        )
    )
    story.append(
        Paragraph(
            f"Ячейки: время — Biota; «{HOURS_GRID_NO_PUNCH}» — смена д/н без пары отметок; пусто — в графике нет смены; "
            f"время{HOURS_GRID_SUFFIX_OUTSIDE_GRAPH} — факт из Biota, в графике не д/н (нужно отметить смену); от/б/п/кп — по графику.",
            sub_style,
        )
    )
    story.append(Spacer(1, 3 * mm))

    _exclude = frozenset({"Порядок", "Код"})
    _digit_cols = [c for c in grid_df.columns if str(c).isdigit()]
    _digit_sorted = sorted(_digit_cols, key=lambda x: int(str(x)))
    _non_digit = [c for c in grid_df.columns if str(c) not in _exclude and c not in _digit_cols]
    cols = _non_digit + _digit_sorted
    table_data: list[list[str]] = [list(cols)]
    for _, r in grid_df.iterrows():
        row_out: list[str] = []
        for c in cols:
            v = r.get(c, "")
            if v is None or (isinstance(v, float) and pd.isna(v)):
                row_out.append("")
            else:
                row_out.append(str(v))
        table_data.append(row_out)

    day_cols = [c for c in cols if str(c).isdigit()]
    n_day = len(day_cols)
    # Ширина полезной области, мм (A4 альбом 297 − поля)
    content_mm = 297.0 - 16.0
    used_lead_mm = 0.0
    for c in cols:
        if str(c).isdigit():
            continue
        cs = str(c)
        if cs == "Порядок":
            used_lead_mm += 9.0
        elif cs == "Код":
            used_lead_mm += 14.0
        elif cs == "Сотрудник":
            used_lead_mm += 46.0
        else:
            used_lead_mm += 16.0
    rest_mm = max(0.0, content_mm - used_lead_mm)
    day_mm = max(4.2, rest_mm / n_day) if n_day else 5.0
    col_widths_pt: list[float] = []
    for c in cols:
        if str(c).isdigit():
            col_widths_pt.append(day_mm * mm)
        else:
            cs = str(c)
            if cs == "Порядок":
                col_widths_pt.append(9 * mm)
            elif cs == "Код":
                col_widths_pt.append(14 * mm)
            elif cs == "Сотрудник":
                col_widths_pt.append(46 * mm)
            else:
                col_widths_pt.append(16 * mm)

    table = Table(table_data, repeatRows=1, colWidths=col_widths_pt, splitByRow=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTSIZE", (0, 1), (-1, -1), 6),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

