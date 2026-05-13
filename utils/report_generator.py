from datetime import datetime
import logging
from pathlib import Path

from fpdf import FPDF

from utils.attendance_utils import (
    get_defaulters,
    get_summary_stats,
    get_top_attenders,
)


BASE_DIR = Path(__file__).resolve().parent.parent
logging.getLogger("fontTools").setLevel(logging.WARNING)
HEADER_BG = (13, 10, 18)
HEADER_TEXT = (241, 238, 255)
TABLE_HEADER_BG = (28, 23, 48)
TABLE_HEADER_FG = (192, 132, 252)
ROW_ALT_BG = (20, 16, 32)
GREEN_TEXT = (74, 222, 128)
RED_TEXT = (248, 113, 113)
GOLD_TEXT = (251, 191, 36)
BODY_TEXT = (200, 190, 230)


class AttendanceReportPDF(FPDF):
    """PDF document with a FRAS footer on every page."""

    def footer(self):
        """Render the footer on every page."""
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(*BODY_TEXT)
        self.cell(0, 8, "FRAS - AI Facial Recognition Attendance System  |  Confidential", align="C")


def register_fonts(pdf):
    """Register Unicode-capable fonts when available."""
    regular_candidates = [
        Path("C:/Windows/Fonts/dejavusans.ttf"),
        Path("C:/Windows/Fonts/seguisym.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/dejavusans-bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    regular_font = next((path for path in regular_candidates if path.exists()), None)
    bold_font = next((path for path in bold_candidates if path.exists()), regular_font)

    if regular_font:
        pdf.add_font("DejaVu", "", str(regular_font))
    if bold_font:
        pdf.add_font("DejaVu", "B", str(bold_font))


def add_header(pdf):
    """Add the report header bar."""
    pdf.set_fill_color(*HEADER_BG)
    pdf.rect(0, 0, 210, 42, "F")
    pdf.set_text_color(*HEADER_TEXT)
    pdf.set_font("DejaVu", "B", 18)
    pdf.set_xy(12, 9)
    pdf.cell(0, 10, "FRAS - AI Attendance Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(160, 154, 180)
    pdf.set_font("DejaVu", "", 11)
    pdf.set_x(12)
    pdf.cell(0, 8, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.ln(22)


def add_section_title(pdf, title):
    """Add a section heading."""
    pdf.ln(8)
    pdf.set_font("DejaVu", "B", 13)
    pdf.set_text_color(*TABLE_HEADER_FG)
    pdf.cell(0, 9, title, new_x="LMARGIN", new_y="NEXT")


def add_table_header(pdf, headers, widths):
    """Add a table header row."""
    pdf.set_fill_color(*TABLE_HEADER_BG)
    pdf.set_text_color(*TABLE_HEADER_FG)
    pdf.set_font("DejaVu", "B", 9)
    for header, width in zip(headers, widths):
        pdf.cell(width, 8, header, border=1, fill=True)
    pdf.ln()


def add_table_row(pdf, values, widths, fill=False, colors=None):
    """Add a table data row."""
    pdf.set_fill_color(*ROW_ALT_BG)
    pdf.set_font("DejaVu", "", 9)
    colors = colors or [BODY_TEXT for _ in values]
    for value, width, color in zip(values, widths, colors):
        pdf.set_text_color(*color)
        pdf.cell(width, 8, str(value), border=1, fill=fill)
    pdf.ln()


def generate_pdf_report(output_path: str) -> None:
    """Generate a PDF attendance report at the provided output path."""
    output_file = Path(output_path)
    if not output_file.is_absolute():
        output_file = BASE_DIR / output_file

    summary = get_summary_stats()
    top_attenders = get_top_attenders(top_n=5)
    defaulters = get_defaulters(threshold=75)

    pdf = AttendanceReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    register_fonts(pdf)
    pdf.add_page()
    add_header(pdf)

    add_section_title(pdf, "Summary")
    add_table_header(pdf, ["Metric", "Value"], [120, 60])
    summary_rows = [
        ("Total Students Registered", summary["total_students"]),
        ("Total Attendance Records", summary["total_attendance_records"]),
        ("Today's Attendance Count", summary["today_attendance_count"]),
        ("Overall Attendance %", f"{summary['overall_attendance_percentage']}%"),
        ("Students Below 75% (At Risk)", summary["defaulters_count"]),
    ]
    for index, row in enumerate(summary_rows):
        add_table_row(pdf, row, [120, 60], fill=index % 2 == 1)

    add_section_title(pdf, "Top Attenders")
    add_table_header(pdf, ["Rank", "Name", "Attendance %"], [24, 106, 50])
    if top_attenders:
        rank_labels = ["1st", "2nd", "3rd"]
        for index, row in enumerate(top_attenders):
            rank = rank_labels[index] if index < len(rank_labels) else str(index + 1)
            add_table_row(
                pdf,
                [rank, row["Name"], f"{row['Percentage']}%"],
                [24, 106, 50],
                fill=index % 2 == 1,
                colors=[GOLD_TEXT if index < 3 else BODY_TEXT, BODY_TEXT, GREEN_TEXT],
            )
    else:
        add_table_row(pdf, ["No attendance data available yet.", "", ""], [24, 106, 50])

    add_section_title(pdf, "Defaulters List (Below 75%)")
    add_table_header(pdf, ["Name", "Attendance %"], [130, 50])
    if defaulters:
        for index, row in enumerate(defaulters):
            percentage = float(row["Percentage"])
            color = RED_TEXT if percentage < 50 else GOLD_TEXT
            add_table_row(
                pdf,
                [row["Name"], f"{percentage:.1f}%"],
                [130, 50],
                fill=index % 2 == 1,
                colors=[BODY_TEXT, color],
            )
    else:
        add_table_row(pdf, ["All students meet the 75% attendance threshold.", ""], [130, 50])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_file))
