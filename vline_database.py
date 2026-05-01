import csv
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

TRAINS_FILE = BASE_DIR / "trains.json"

VLINE_JSON_FILE = BASE_DIR / "vline_services.json"
VLINE_CSV_FILE = BASE_DIR / "vline_services.csv"

DOWNLOADS_DIR = BASE_DIR / "static" / "downloads"
VLINE_HTML_FILE = DOWNLOADS_DIR / "vline_services.html"

VLINE_PREFIX_RE = re.compile(r"^VLINE", re.IGNORECASE)


def load_json(path: Path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def first_value(item, keys):
    for key in keys:
        value = item.get(key)
        if value not in [None, ""]:
            return clean_text(value)
    return ""


def normalise_train_id(value):
    value = clean_text(value).upper()
    value = value.replace(" ", "")
    value = value.replace("-", "")
    return value


def looks_like_vline(item):
    fields = [
        first_value(item, ["loco_number", "loco", "trKey", "train_name", "trainName", "name", "id", "ID"]),
        first_value(item, ["train_id", "trainId", "train_number", "trainNumber", "service", "service_number"]),
        first_value(item, ["vehicle_description", "description", "desc"]),
        first_value(item, ["route", "service_name", "serviceName"]),
        first_value(item, ["current_operator", "operator", "owner"]),
    ]

    joined = " ".join(fields).upper()

    if "VLINE" in joined or "V/LINE" in joined or "V-LINE" in joined:
        return True

    for value in fields:
        cleaned = normalise_train_id(value)
        if VLINE_PREFIX_RE.match(cleaned):
            return True

    return False


def parse_generated_time(item):
    value = first_value(
        item,
        [
            "date_time_added",
            "datetime_added",
            "time",
            "timestamp",
            "last_seen",
            "lastUpdated",
            "updated",
            "generated",
        ],
    )

    return value


def extract_vline_service(item):
    train_id = first_value(
        item,
        [
            "loco_number",
            "loco",
            "trKey",
            "train_name",
            "trainName",
            "name",
            "id",
            "ID",
        ],
    )

    train_id = normalise_train_id(train_id)

    service_number = first_value(
        item,
        [
            "train_id",
            "trainId",
            "train_number",
            "trainNumber",
            "service",
            "service_number",
        ],
    )

    if not service_number:
        match = re.search(r"VLINE\s*([0-9A-Z]+)", train_id, re.IGNORECASE)
        if match:
            service_number = match.group(1)

    route = first_value(
        item,
        [
            "route",
            "service_name",
            "serviceName",
            "destination",
            "dest",
            "location",
            "place",
        ],
    )

    origin = first_value(item, ["origin", "from"])
    destination = first_value(item, ["destination", "dest", "to"])

    operator = first_value(
        item,
        [
            "current_operator",
            "operator",
            "owner",
        ],
    )

    description = first_value(
        item,
        [
            "vehicle_description",
            "description",
            "desc",
        ],
    )

    lat = first_value(item, ["lat", "latitude", "y"])
    lon = first_value(item, ["lon", "lng", "longitude", "x"])

    date_time_added = parse_generated_time(item)

    return {
        "train_id": train_id,
        "service_number": clean_text(service_number),
        "route": clean_text(route),
        "origin": clean_text(origin),
        "destination": clean_text(destination),
        "current_operator": operator or "V/Line",
        "vehicle_description": description or "V/Line regional passenger service",
        "date_time_added": clean_text(date_time_added),
        "lat": clean_text(lat),
        "lon": clean_text(lon),
        "source": "TrainFinder",
    }


def service_sort_key(row):
    service_number = clean_text(row.get("service_number"))
    train_id = clean_text(row.get("train_id")).upper()

    number_part = service_number

    if not number_part:
        match = re.search(r"(\d+)", train_id)
        if match:
            number_part = match.group(1)

    if number_part.isdigit():
        return (0, int(number_part), train_id)

    return (1, train_id)


def generate_html(rows, generated_iso):
    escaped_rows = []

    for row in rows:
        escaped_rows.append(
            {
                key: html.escape(clean_text(value))
                for key, value in row.items()
            }
        )

    table_rows = ""

    if escaped_rows:
        for row in escaped_rows:
            table_rows += f"""
<tr>
  <td><strong>{row.get("train_id", "")}</strong></td>
  <td>{row.get("service_number", "")}</td>
  <td>{row.get("route", "")}</td>
  <td>{row.get("current_operator", "")}</td>
  <td>{row.get("vehicle_description", "")}</td>
  <td>
    <strong class="time-local" data-raw="{row.get("date_time_added", "")}">{row.get("date_time_added", "")}</strong>
    <div class="raw">Raw: {row.get("date_time_added", "")}</div>
  </td>
</tr>
"""
    else:
        table_rows = """
<tr>
  <td colspan="6">No V/Line services found yet.</td>
</tr>
"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RailOps V/Line Services</title>
<style>
:root {{
  --bg: #041326;
  --panel: #0b1f3a;
  --panel2: #102b4f;
  --line: #28517f;
  --text: #eaf3ff;
  --muted: #a9bfdc;
  --blue: #5ab6ff;
  --green: #35b46f;
}}

* {{
  box-sizing: border-box;
}}

html, body {{
  margin: 0;
  padding: 0;
  background: radial-gradient(circle at top, #0a2b54 0%, #041326 48%, #020b16 100%);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
}}

body {{
  padding: 18px;
}}

.wrap {{
  width: min(1180px, 100%);
  margin: 0 auto;
}}

.card {{
  background: rgba(11,31,58,.92);
  border: 1px solid rgba(90,182,255,.22);
  border-radius: 26px;
  padding: 22px;
  margin-bottom: 22px;
  box-shadow: 0 14px 34px rgba(0,0,0,.28);
}}

h1 {{
  margin: 0 0 10px;
  font-size: clamp(34px, 6vw, 62px);
  line-height: 1.05;
  letter-spacing: -.04em;
}}

p {{
  color: var(--muted);
  font-size: clamp(18px, 4vw, 28px);
  line-height: 1.35;
  margin: 0 0 18px;
}}

.pills {{
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}}

.pill {{
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  padding: 9px 14px;
  border-radius: 999px;
  background: rgba(90,182,255,.16);
  border: 1px solid rgba(90,182,255,.35);
  font-weight: 800;
  font-size: 16px;
}}

.pill.green {{
  background: rgba(53,180,111,.18);
  border-color: rgba(53,180,111,.42);
}}

.actions {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}}

button, a.btn {{
  display: inline-flex;
  justify-content: center;
  align-items: center;
  min-height: 52px;
  padding: 12px 18px;
  border-radius: 18px;
  border: 1px solid rgba(90,182,255,.32);
  background: rgba(0,0,0,.18);
  color: var(--text);
  font-size: 17px;
  font-weight: 800;
  cursor: pointer;
}}

button.active {{
  background: linear-gradient(180deg, #5ab6ff, #2f8fff);
  color: #06111f;
}}

.search {{
  width: 100%;
  min-height: 56px;
  border-radius: 18px;
  border: 1px solid rgba(90,182,255,.32);
  background: rgba(0,0,0,.20);
  color: var(--text);
  font-size: 19px;
  padding: 12px 16px;
  outline: none;
  margin-top: 16px;
}}

.table-wrap {{
  overflow: auto;
  border: 1px solid rgba(90,182,255,.22);
  border-radius: 24px;
  background: rgba(6,18,34,.60);
}}

table {{
  width: 100%;
  border-collapse: collapse;
  min-width: 980px;
}}

th, td {{
  text-align: left;
  vertical-align: top;
  padding: 16px;
  border-bottom: 1px solid rgba(90,182,255,.18);
  font-size: 18px;
}}

th {{
  background: rgba(90,182,255,.11);
  font-size: 19px;
  font-weight: 900;
  position: sticky;
  top: 0;
  z-index: 2;
}}

.raw {{
  color: var(--muted);
  font-size: 14px;
  margin-top: 6px;
}}

@media(max-width: 760px) {{
  body {{
    padding: 12px;
  }}

  .card {{
    padding: 18px;
  }}

  .actions {{
    display: grid;
  }}

  button, a.btn {{
    width: 100%;
  }}
}}
</style>
</head>
<body>
<div class="wrap">
  <section class="card">
    <h1>RailOps V/Line Services</h1>
    <p>V/Line regional passenger train IDs separated from the locomotive database.</p>

    <div class="pills">
      <span class="pill green">Visible V/Line services: {len(rows)}</span>
      <span class="pill">Generated: <span class="time-local" data-raw="{html.escape(generated_iso)}">{html.escape(generated_iso)}</span></span>
      <span class="pill">Times shown in your phone/browser timezone</span>
    </div>

    <input class="search" id="searchBox" placeholder="Search V/Line ID, route, service number..." autocomplete="off">

    <div class="actions">
      <button id="allBtn" class="active" type="button">All</button>
      <button id="bendigoBtn" type="button">Bendigo</button>
      <button id="ballaratBtn" type="button">Ballarat</button>
      <button id="geelongBtn" type="button">Geelong</button>
      <button id="gippslandBtn" type="button">Gippsland</button>
      <button id="clearBtn" type="button">Clear Filter</button>
    </div>
  </section>

  <section class="card">
    <div class="table-wrap">
      <table id="serviceTable">
        <thead>
          <tr>
            <th>V/Line Train ID</th>
            <th>Service No.</th>
            <th>Route / Service</th>
            <th>Operator</th>
            <th>Description</th>
            <th>Date/Time Added</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>
  </section>
</div>

<script>
function formatLocalTimes() {{
  document.querySelectorAll(".time-local").forEach(el => {{
    const raw = el.dataset.raw || el.textContent;
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return;

    el.textContent = new Intl.DateTimeFormat(navigator.language || "en-AU", {{
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZoneName: "short"
    }}).format(d);
  }});
}}

function setActive(button) {{
  document.querySelectorAll(".actions button").forEach(btn => btn.classList.remove("active"));
  button.classList.add("active");
}}

function filterTable(text) {{
  const needle = String(text || "").toLowerCase();

  document.querySelectorAll("#serviceTable tbody tr").forEach(row => {{
    const haystack = row.textContent.toLowerCase();
    row.style.display = haystack.includes(needle) ? "" : "none";
  }});
}}

document.getElementById("searchBox").addEventListener("input", e => {{
  filterTable(e.target.value);
}});

document.getElementById("allBtn").addEventListener("click", e => {{
  setActive(e.target);
  document.getElementById("searchBox").value = "";
  filterTable("");
}});

document.getElementById("bendigoBtn").addEventListener("click", e => {{
  setActive(e.target);
  document.getElementById("searchBox").value = "Bendigo";
  filterTable("Bendigo");
}});

document.getElementById("ballaratBtn").addEventListener("click", e => {{
  setActive(e.target);
  document.getElementById("searchBox").value = "Ballarat";
  filterTable("Ballarat");
}});

document.getElementById("geelongBtn").addEventListener("click", e => {{
  setActive(e.target);
  document.getElementById("searchBox").value = "Geelong";
  filterTable("Geelong");
}});

document.getElementById("gippslandBtn").addEventListener("click", e => {{
  setActive(e.target);
  document.getElementById("searchBox").value = "Gippsland";
  filterTable("Gippsland");
}});

document.getElementById("clearBtn").addEventListener("click", e => {{
  setActive(document.getElementById("allBtn"));
  document.getElementById("searchBox").value = "";
  filterTable("");
}});

formatLocalTimes();
</script>
</body>
</html>
"""


def write_csv(rows):
    VLINE_CSV_FILE.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "train_id",
        "service_number",
        "route",
        "origin",
        "destination",
        "current_operator",
        "vehicle_description",
        "date_time_added",
        "lat",
        "lon",
        "source",
    ]

    with VLINE_CSV_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main():
    print("=== RAILOPS VLINE DATABASE START ===", flush=True)

    payload = load_json(TRAINS_FILE, {})
    trains = payload.get("trains", payload if isinstance(payload, list) else [])

    if not isinstance(trains, list):
        trains = []

    found = {}

    for item in trains:
        if not isinstance(item, dict):
            continue

        if not looks_like_vline(item):
            continue

        service = extract_vline_service(item)
        key = service.get("train_id") or service.get("service_number")

        if not key:
            continue

        found[key] = service

    rows = sorted(found.values(), key=service_sort_key)

    generated_iso = datetime.now(timezone.utc).isoformat()

    output = {
        "generated": generated_iso,
        "count": len(rows),
        "source": "trains.json",
        "services": rows,
    }

    save_json(VLINE_JSON_FILE, output)
    write_csv(rows)

    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    VLINE_HTML_FILE.write_text(generate_html(rows, generated_iso), encoding="utf-8")

    print(f"V/Line services found: {len(rows)}", flush=True)
    print(f"Wrote: {VLINE_JSON_FILE}", flush=True)
    print(f"Wrote: {VLINE_CSV_FILE}", flush=True)
    print(f"Wrote: {VLINE_HTML_FILE}", flush=True)
    print("=== RAILOPS VLINE DATABASE DONE ===", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
