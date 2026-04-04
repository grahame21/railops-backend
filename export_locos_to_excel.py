import os
import json
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

LOCOS_FILE = "locos.json"
BLOCKED_FILE = "blocked_locos.txt"
DOWNLOAD_DIR = os.path.join("static", "downloads")
XLSX_FILE = os.path.join(DOWNLOAD_DIR, "loco_database.xlsx")


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


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def get_visible_locos(locos):
    blocked = set(load_blocked_locos())
    visible = []
    for loco_number, data in sorted(locos.items(), key=lambda x: normalize_loco(x[0])):
        if normalize_loco(loco_number) in blocked:
            continue
        if not isinstance(data, dict):
            continue
        visible.append((normalize_loco(loco_number), data))
    return visible


def autosize_columns(ws, widths):
    for idx, width in widths.items():
        ws.column_dimensions[get_column_letter(idx)].width = width


def build_workbook(locos):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    visible_locos = get_visible_locos(locos)
    blocked = sorted(load_blocked_locos())

    wb = Workbook()
    default_ws = wb.active
    wb.remove(default_ws)

    ws_locos = wb.create_sheet("Locos")
    ws_blocked = wb.create_sheet("Blocked")
    ws_print = wb.create_sheet("Print View")
    ws_info = wb.create_sheet("Instructions")

    headers = ["Loco Number", "Current Operator", "Vehicle Description", "Date/Time Added"]
    bold = Font(bold=True)
    center = Alignment(horizontal="center")

    # Locos
    ws_locos.append(headers)
    for cell in ws_locos[1]:
        cell.font = bold
        cell.alignment = center
    for loco_number, data in visible_locos:
        ws_locos.append([
            loco_number,
            safe_text(data.get('current_operator')),
            safe_text(data.get('vehicle_description') or data.get('last_description')),
            safe_text(data.get('date_time_added') or data.get('first_seen')),
        ])
    autosize_columns(ws_locos, {1: 18, 2: 24, 3: 40, 4: 22})
    ws_locos.freeze_panes = 'A2'

    # Blocked
    ws_blocked.append(["Blocked Loco Number"])
    ws_blocked['A1'].font = bold
    ws_blocked.column_dimensions['A'].width = 22
    for loco in blocked:
        ws_blocked.append([loco])

    # Print View
    ws_print.append(headers)
    for cell in ws_print[1]:
        cell.font = bold
        cell.alignment = center
    for loco_number, data in visible_locos:
        ws_print.append([
            loco_number,
            safe_text(data.get('current_operator')),
            safe_text(data.get('vehicle_description') or data.get('last_description')),
            safe_text(data.get('date_time_added') or data.get('first_seen')),
        ])
    autosize_columns(ws_print, {1: 18, 2: 24, 3: 40, 4: 22})
    ws_print.freeze_panes = 'A2'
    ws_print.page_setup.orientation = 'landscape'
    ws_print.page_setup.fitToWidth = 1
    ws_print.page_setup.fitToHeight = False
    ws_print.print_title_rows = '1:1'

    # Instructions
    lines = [
        "This workbook is rebuilt automatically by the loco updater.",
        "",
        "Locos: current visible loco list.",
        "Blocked: one loco number per line in blocked_locos.txt.",
        "Print View: print-friendly layout.",
        "",
        "If a blocked loco still appears, make sure:",
        "1. blocked_locos.txt is in the backend root",
        "2. one loco per line",
        "3. the updater has run again",
        "4. you download a fresh workbook",
    ]
    for line in lines:
        ws_info.append([line])
    ws_info.column_dimensions['A'].width = 90

    wb.save(XLSX_FILE)
    return len(visible_locos), len(blocked)


def main():
    locos = load_json(LOCOS_FILE)
    if not isinstance(locos, dict):
        raise SystemExit("locos.json is missing or invalid")
    visible_count, blocked_count = build_workbook(locos)
    print(f"✅ Workbook saved to {XLSX_FILE}")
    print(f"🚂 Visible locos: {visible_count}")
    print(f"🚫 Blocked locos listed: {blocked_count}")


if __name__ == '__main__':
    main()
