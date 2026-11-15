"""Make an Excel copy of the network list, for sorting and filtering.

  python3 scripts/network_xlsx.py     reads lists/network.md, writes lists/network.xlsx

lists/network.md is the master. Never edit the .xlsx by hand: it is rebuilt every time.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "lists" / "network.md"
OUT = ROOT / "lists" / "network.xlsx"


def summary_rows(text):
    """Rows of the first markdown table in the file (the summary table)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue  # the |---|---| divider
        rows.append(cells)
    return rows


def main():
    rows = summary_rows(SRC.read_text())
    wb = Workbook()
    ws = wb.active
    ws.title = "Network"
    for row in rows:
        ws.append(row)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    widths = [22, 38, 24, 30, 13, 48, 13]
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(OUT)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(rows) - 1} people)")


if __name__ == "__main__":
    main()
