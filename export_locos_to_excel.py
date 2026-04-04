import os
import json
import re
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break

LOCOS_FILE = "locos.json"
BLOCKED_FILE = "blocked_locos.txt"
BLOCKED_DESCRIPTIONS_FILE = "blocked_descriptions.txt"
DOWNLOAD_DIR = os.path.join("static", "downloads")
XLSX_FILE = os.path.join(DOWNLOAD_DIR, "loco_database.xlsx")
NUMBERS_ONLY_FILE = os.path.join(DOWNLOAD_DIR, "loco_numbers_only.xlsx")

CM_TO_INCH = 1 / 2.54
MARGIN_1_5CM = 1.5 * CM_TO_INCH
NUMBERS_ONLY_COLUMNS = 10
NUMBERS_ONLY_COL_WIDTH = 12
NUMBERS_ONLY_ROWS_PER_PAGE = 56
NUMBERS_ONLY_PAGE_GAP = 1

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


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def load_blocked_loco_rules():
    exact = set()
    prefixes = []
    if not os.path.exists(BLOCKED_FILE):
        return exact, prefixes
    with open(BLOCKED_FILE, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            value = normalize_loco(line)
            if value.endswith('*'):
                prefix = value[:-1]
                if prefix:
                    prefixes.append(prefix)
            else:
                exact.add(value)
    prefixes.sort(key=len, reverse=True)
    return exact, prefixes


def loco_is_blocked(loco_id, blocked_exact, blocked_prefixes):
    loco = normalize_loco(loco_id)
    if not loco:
        return False
    if loco in blocked_exact:
        return True
    return any(loco.startswith(prefix) for prefix in blocked_prefixes)


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
    blocked_exact, blocked_prefixes = load_blocked_loco_rules()
    blocked_descriptions = load_blocked_descriptions()
    visible = []
    for loco_number, data in locos.items():
        if loco_is_blocked(loco_number, blocked_exact, blocked_prefixes):
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


def write_numbers_pages(ws, running_order, center, columns=NUMBERS_ONLY_COLUMNS, rows_per_page=NUMBERS_ONLY_ROWS_PER_PAGE):
    loco_numbers = [loco_number for loco_number, _data in running_order]

    for col in range(1, columns + 1):
        ws.column_dimensions[get_column_letter(col)].width = NUMBERS_ONLY_COL_WIDTH

    row_pointer = 1
    total_per_page = columns * rows_per_page

    for page_start in range(0, len(loco_numbers), total_per_page):
        page_items = loco_numbers[page_start:page_start + total_per_page]

        for index, loco in enumerate(page_items):
            column_offset = index // rows_per_page
            row_offset = index % rows_per_page
            cell = ws.cell(row=row_pointer + row_offset, column=1 + column_offset, value=loco)
            cell.alignment = center

        next_page_row = row_pointer + rows_per_page
        if page_start + total_per_page < len(loco_numbers):
            ws.row_breaks.append(Break(id=next_page_row - 1))
            row_pointer = next_page_row + NUMBERS_ONLY_PAGE_GAP

    apply_print_settings(ws, orientation='portrait', repeat_header=False)


def build_workbooks(locos):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    visible_locos = get_visible_locos(locos)
    blocked_exact, blocked_prefixes = load_blocked_loco_rules()
    blocked_descriptions = sorted(load_blocked_descriptions())

    blocked_exact_sorted = sorted(blocked_exact, key=natural_sort_key)
    blocked_prefix_sorted = sorted(blocked_prefixes, key=natural_sort_key)

    running_order = sorted(visible_locos, key=lambda x: natural_sort_key(x[0]))
    recently_added = sorted(
        visible_locos,
        key=lambda x: parse_datetime_sort(x[1].get('date_time_added') or x[1].get('first_seen')),
        reverse=True,
    )

    headers = ["Loco Number", "Current Operator", "Vehicle Description", "Date/Time Added"]
    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center")
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

    write_numbers_pages(ws_numbers, running_order, center)

    ws_blocked.append(["Blocked Loco Rule"])
    ws_blocked['A1'].font = bold
    ws_blocked['A1'].alignment = center
    ws_blocked.column_dimensions['A'].width = 24
    for loco in blocked_exact_sorted:
        ws_blocked.append([loco])
    for prefix in blocked_prefix_sorted:
        ws_blocked.append([f"{prefix}*"])
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
        "Numbers Only: loco numbers only, printed down each column first, then across the same page before moving to the next page.",
        "Blocked: add one loco rule per line in blocked_locos.txt.",
        "Use an exact rule like NR74 or a prefix rule like TNSW*.",
        "Blocked Descriptions: partial-match vehicle description filters from blocked_descriptions.txt.",
        "",
        "Print margins on the print sheets are set to about 1.5 cm.",
        f"Numbers Only layout uses {NUMBERS_ONLY_COLUMNS} columns and about {NUMBERS_ONLY_ROWS_PER_PAGE} rows per printed page.",
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
    write_numbers_pages(ws_only, running_order, center)
    wb_numbers.save(NUMBERS_ONLY_FILE)

    return {
        'visible_count': len(running_order),
        'blocked_exact_count': len(blocked_exact_sorted),
        'blocked_prefix_count': len(blocked_prefix_sorted),
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
    print(f"🚫 Blocked exact locos listed: {stats['blocked_exact_count']}")
    print(f"🚫 Blocked loco prefixes listed: {stats['blocked_prefix_count']}")
    print(f"🚫 Blocked descriptions listed: {stats['blocked_description_count']}")


if __name__ == '__main__':
    main()
