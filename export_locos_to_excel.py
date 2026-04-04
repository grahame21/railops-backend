import os
import json
import re
from datetime import datetime
from math import ceil
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

LOCOS_FILE = "locos.json"
BLOCKED_FILE = "blocked_locos.txt"
BLOCKED_DESCRIPTIONS_FILE = "blocked_descriptions.txt"
DOWNLOAD_DIR = os.path.join("static", "downloads")
XLSX_FILE = os.path.join(DOWNLOAD_DIR, "loco_database.xlsx")
NUMBERS_ONLY_FILE = os.path.join(DOWNLOAD_DIR, "loco_numbers_only.xlsx")

CM_TO_INCH = 1 / 2.54
MARGIN_1_5CM = 1.5 * CM_TO_INCH
NUMBERS_ONLY_COLUMNS = 10
NUMBERS_ONLY_COL_WIDTH = 14


SKIP_PREFIXES = (
    "ARROWMARKERSSOURCE_",
    "MARKERSOURCE_",
    "REGTRAINSSOURCE_",
    "UNREGTRAINSSOURCE_",
    "TRAINSOURCE_",
)


def is_real_loco_id(value):
    loco = normalize_loco(value)
    if not loco:
        return False
    return not any(prefix in loco for prefix in SKIP_PREFIXES)


def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_loco(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def load_blocked_locos():
    blocked = []
    if not os.path.exists(BLOCKED_FILE):
        return blocked
    with open(BLOCKED_FILE, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            blocked.append(normalize_loco(line))
    return blocked


def load_blocked_descriptions():
    blocked = []
    if not os.path.exists(BLOCKED_DESCRIPTIONS_FILE):
        return blocked
    with open(BLOCKED_DESCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip().lower()
            if not line or line.startswith('#'):
                continue
            blocked.append(line)
    return blocked


def description_is_blocked(description, blocked_descriptions):
    desc = safe_text(description).lower()
    if not desc or not blocked_descriptions:
        return False
    return any(term in desc for term in blocked_descriptions)


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def natural_sort_key(value):
    text = normalize_loco(value)
    return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', text)]


def parse_datetime_sort(value):
    text = safe_text(value)
    if not text:
        return datetime.min
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return datetime.min


def get_visible_locos(locos):
    blocked = set(load_blocked_locos())
    blocked_descriptions = load_blocked_descriptions()
    visible = []
    for loco_number, data in locos.items():
        if normalize_loco(loco_number) in blocked:
            continue
        if not isinstance(data, dict):
            continue
        if not is_real_loco_id(loco_number):
            continue
        description = data.get('vehicle_description') or data.get('last_description') or ''
        if description_is_blocked(description, blocked_descriptions):
            continue
        visible.append((normalize_loco(loco_number), data))
    return visible


def autosize_columns(ws, widths):
    for idx, width in widths.items():
        ws.column_dimensions[get_column_letter(idx)].width = width


def apply_print_settings(ws, orientation='portrait', repeat_header=True):
    ws.page_margins = PageMargins(
        left=MARGIN_1_5CM,
        right=MARGIN_1_5CM,
        top=MARGIN_1_5CM,
        bottom=MARGIN_1_5CM,
        header=0.3,
        footer=0.3,
    )
    ws.page_setup.orientation = orientation
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = False
    if repeat_header:
        ws.print_title_rows = '1:1'


def make_row(loco_number, data):
    return [
        loco_number,
        safe_text(data.get('current_operator')),
        safe_text(data.get('vehicle_description') or data.get('last_description')),
        safe_text(data.get('date_time_added') or data.get('first_seen')),
    ]


def write_header(ws, headers, bold, center):
    ws.append(headers)
    for cell in ws[1]:
        cell.font = bold
        cell.alignment = center


def write_numbers_grid(ws, running_order, bold, center, columns=NUMBERS_ONLY_COLUMNS):
    headers = [f"Loco Number {i}" for i in range(1, columns + 1)]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = bold
        cell.alignment = center

    loco_numbers = [loco_number for loco_number, _data in running_order]
    total = len(loco_numbers)
    rows_needed = ceil(total / columns) if total else 0

    for _ in range(rows_needed):
        ws.append([""] * columns)

    for idx, loco in enumerate(loco_numbers):
        col_index = idx // rows_needed if rows_needed else 0
        row_index = idx % rows_needed if rows_needed else 0
        ws.cell(row=row_index + 2, column=col_index + 1, value=loco)

    for col in range(1, columns + 1):
        ws.column_dimensions[get_column_letter(col)].width = NUMBERS_ONLY_COL_WIDTH
    ws.freeze_panes = 'A2'
    apply_print_settings(ws, orientation='portrait')



def build_workbooks(locos):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    visible_locos = get_visible_locos(locos)
    blocked = sorted(load_blocked_locos(), key=natural_sort_key)
    blocked_descriptions = sorted(load_blocked_descriptions())

    running_order = sorted(visible_locos, key=lambda x: natural_sort_key(x[0]))
    recently_added = sorted(
        visible_locos,
        key=lambda x: parse_datetime_sort(x[1].get('date_time_added') or x[1].get('first_seen')),
        reverse=True,
    )

    headers = ["Loco Number", "Current Operator", "Vehicle Description", "Date/Time Added"]
    bold = Font(bold=True)
    center = Alignment(horizontal="center")
    widths = {1: 18, 2: 24, 3: 40, 4: 22}

    wb = Workbook()
    wb.remove(wb.active)

    ws_locos = wb.create_sheet("Locos")
    ws_recent = wb.create_sheet("Recently Added")
    ws_numbers = wb.create_sheet("Numbers Only")
    ws_blocked = wb.create_sheet("Blocked")
    ws_blocked_desc = wb.create_sheet("Blocked Descriptions")
    ws_info = wb.create_sheet("Instructions")

    write_header(ws_locos, headers, bold, center)
    for loco_number, data in running_order:
        ws_locos.append(make_row(loco_number, data))
    autosize_columns(ws_locos, widths)
    ws_locos.freeze_panes = 'A2'
    apply_print_settings(ws_locos, orientation='landscape')

    write_header(ws_recent, headers, bold, center)
    for loco_number, data in recently_added:
        ws_recent.append(make_row(loco_number, data))
    autosize_columns(ws_recent, widths)
    ws_recent.freeze_panes = 'A2'
    apply_print_settings(ws_recent, orientation='landscape')

    write_numbers_grid(ws_numbers, running_order, bold, center)

    ws_blocked.append(["Blocked Loco Number"])
    ws_blocked['A1'].font = bold
    ws_blocked['A1'].alignment = center
    ws_blocked.column_dimensions['A'].width = 22
    for loco in blocked:
        ws_blocked.append([loco])
    apply_print_settings(ws_blocked, orientation='portrait')

    ws_blocked_desc.append(['Blocked Vehicle Description'])
    ws_blocked_desc['A1'].font = bold
    ws_blocked_desc['A1'].alignment = center
    ws_blocked_desc.column_dimensions['A'].width = 36
    for desc in blocked_descriptions:
        ws_blocked_desc.append([desc])
    apply_print_settings(ws_blocked_desc, orientation='portrait')

    lines = [
        "This workbook is rebuilt automatically by the loco updater.",
        "",
        "Locos: full loco list in running order.",
        "Recently Added: newest locos first, based on Date/Time Added.",
        "Numbers Only: loco numbers only, in running order, laid out down each column first to save print space.",
        "Blocked: one loco number per line in blocked_locos.txt.",
        "Blocked Descriptions: partial-match vehicle description filters from blocked_descriptions.txt.",
        "",
        "Print margins on the print sheets are set to about 1.5 cm.",
        f"Numbers Only layout uses {NUMBERS_ONLY_COLUMNS} columns across each page, filling down each column first before moving across/page.",
        "Download files:",
        "- /downloads/loco_database.xlsx",
        "- /downloads/loco_numbers_only.xlsx",
    ]
    for line in lines:
        ws_info.append([line])
    ws_info.column_dimensions['A'].width = 110
    apply_print_settings(ws_info, orientation='portrait', repeat_header=False)

    wb.save(XLSX_FILE)

    wb_numbers = Workbook()
    ws_only = wb_numbers.active
    ws_only.title = "Loco Numbers"
    write_numbers_grid(ws_only, running_order, bold, center)
    wb_numbers.save(NUMBERS_ONLY_FILE)

    return {
        'visible_count': len(running_order),
        'blocked_count': len(blocked),
        'blocked_description_count': len(blocked_descriptions),
        'recent_count': len(recently_added),
    }



def main():
    locos = load_json(LOCOS_FILE)
    if not isinstance(locos, dict):
        raise SystemExit("locos.json is missing or invalid")
    stats = build_workbooks(locos)
    print(f"✅ Workbook saved to {XLSX_FILE}")
    print(f"✅ Numbers-only workbook saved to {NUMBERS_ONLY_FILE}")
    print(f"🚂 Visible locos: {stats['visible_count']}")
    print(f"🆕 Recently added rows: {stats['recent_count']}")
    print(f"🚫 Blocked locos listed: {stats['blocked_count']}")


if __name__ == '__main__':
    main()
