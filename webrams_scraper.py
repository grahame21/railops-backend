import os
import re
import json
import time
import traceback
from copy import deepcopy
from datetime import datetime, timezone

from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException


load_dotenv()

BASE_URL = os.getenv("WEBRAMS_BASE_URL", "https://webrams.artc.com.au").rstrip("/")
HEADLESS = os.getenv("HEADLESS", "false").strip().lower() == "true"
MAX_TRAINS = int(os.getenv("WEBRAMS_MAX_TRAINS", "25"))

DATA_DIR = "data"
OUT_FILE = os.path.join(DATA_DIR, "webrams_consists.json")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def clean_text(value: str) -> str:
    if value is None:
        return ""
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def norm_key(value: str) -> str:
    value = clean_text(value).lower()
    value = value.replace("/", "_")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def build_driver() -> webdriver.Chrome:
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,2200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-AU")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(90)
    return driver


def wait_for_page(driver, timeout=25):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def find_first(driver, xpaths, timeout=10, clickable=False):
    last_error = None
    for xp in xpaths:
        try:
            if clickable:
                return WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp))
            )
        except Exception as e:
            last_error = e
    if last_error:
        raise last_error
    raise TimeoutException("No matching element found.")


def find_all(driver, xpaths):
    for xp in xpaths:
        elems = driver.find_elements(By.XPATH, xp)
        if elems:
            return elems
    return []


def safe_click(driver, elem):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
        time.sleep(0.25)
        elem.click()
        return True
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", elem)
            return True
        except Exception:
            return False


def click_link_by_text(driver, text, timeout=10):
    xpaths = [
        f"//a[normalize-space()='{text}']",
        f"//button[normalize-space()='{text}']",
        f"//input[@type='submit' and @value='{text}']",
        f"//*[self::a or self::button][contains(normalize-space(), '{text}')]",
    ]
    elem = find_first(driver, xpaths, timeout=timeout, clickable=True)
    if not safe_click(driver, elem):
        raise RuntimeError(f"Could not click link/button with text: {text}")
    time.sleep(1)
    wait_for_page(driver, timeout=20)


def maybe_click_link_by_text(driver, text, timeout=3):
    try:
        click_link_by_text(driver, text, timeout=timeout)
        return True
    except Exception:
        return False


def set_input_near_label(driver, label_text, value):
    candidates = [
        f"//td[contains(normalize-space(), '{label_text}')]/following-sibling::td//input[1]",
        f"//label[contains(normalize-space(), '{label_text}')]/following::input[1]",
        f"//*[contains(normalize-space(), '{label_text}')]/following::input[1]",
    ]
    elem = find_first(driver, candidates, timeout=10)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
    elem.clear()
    elem.send_keys(value)


def try_set_input_near_label(driver, label_text, value):
    try:
        set_input_near_label(driver, label_text, value)
        return True
    except Exception:
        return False


def select_near_label_by_visible_text(driver, label_text, visible_text):
    candidates = [
        f"//td[contains(normalize-space(), '{label_text}')]/following-sibling::td//select[1]",
        f"//label[contains(normalize-space(), '{label_text}')]/following::select[1]",
        f"//*[contains(normalize-space(), '{label_text}')]/following::select[1]",
    ]
    elem = find_first(driver, candidates, timeout=10)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
    select = Select(elem)
    select.select_by_visible_text(visible_text)


def try_select_near_label_by_visible_text(driver, label_text, visible_text):
    try:
        select_near_label_by_visible_text(driver, label_text, visible_text)
        return True
    except Exception:
        return False


def click_search_button(driver):
    candidates = [
        "//input[@type='submit' and @value='Search']",
        "//button[normalize-space()='Search']",
        "//*[self::a or self::button or self::input][contains(normalize-space(), 'Search')]",
    ]
    btn = find_first(driver, candidates, timeout=10, clickable=True)
    if not safe_click(driver, btn):
        raise RuntimeError("Could not click Search button.")
    time.sleep(1.25)
    wait_for_page(driver, timeout=20)


def parse_simple_summary_pairs(driver):
    """
    Pulls top summary values like:
    Train ID, Operator, Train Date, Origin, Destination
    from the current page.
    """
    result = {}
    rows = driver.find_elements(By.XPATH, "//tr")
    for row in rows:
        tds = row.find_elements(By.XPATH, "./td")
        if len(tds) >= 2:
            texts = [clean_text(td.text) for td in tds]
            texts = [t for t in texts if t]
            if len(texts) >= 2:
                # Look for label/value pairs
                for i in range(0, len(texts) - 1, 2):
                    label = norm_key(texts[i].replace(":", ""))
                    value = texts[i + 1]
                    if label and value:
                        if label in {"train_id", "operator", "train_date", "origin", "destination", "status"}:
                            result[label] = value
    return result


def find_heading_container_table(driver, heading_text):
    """
    Finds the first table after a heading like 'Search Results', 'Consist', or 'Incidents'.
    """
    xpaths = [
        f"//h1[contains(normalize-space(), '{heading_text}')]/following::table[1]",
        f"//h2[contains(normalize-space(), '{heading_text}')]/following::table[1]",
        f"//h3[contains(normalize-space(), '{heading_text}')]/following::table[1]",
        f"//*[contains(normalize-space(), '{heading_text}')]/following::table[1]",
    ]
    return find_first(driver, xpaths, timeout=10)


def extract_table_headers(table_elem):
    headers = table_elem.find_elements(By.XPATH, ".//tr[1]//th")
    if headers:
        return [clean_text(h.text) for h in headers]

    first_row_tds = table_elem.find_elements(By.XPATH, ".//tr[1]//td")
    return [clean_text(td.text) for td in first_row_tds]


def extract_table_rows(table_elem):
    rows_out = []
    rows = table_elem.find_elements(By.XPATH, ".//tr")
    if not rows:
        return rows_out

    headers = extract_table_headers(table_elem)
    start_idx = 2 if table_elem.find_elements(By.XPATH, ".//tr[1]//th") else 2

    for row in rows[start_idx - 1:]:
        tds = row.find_elements(By.XPATH, "./td")
        if not tds:
            continue

        values = [clean_text(td.text) for td in tds]
        if not any(values):
            continue

        item = {}
        for i, header in enumerate(headers):
            key = norm_key(header or f"col_{i+1}")
            val = values[i] if i < len(values) else ""
            item[key] = val

        rows_out.append(item)

    return rows_out


def parse_train_list_rows(driver):
    table = find_heading_container_table(driver, "Search Results")
    rows = table.find_elements(By.XPATH, ".//tr[td]")
    results = []

    for row in rows:
        cells = row.find_elements(By.XPATH, "./td")
        if len(cells) < 6:
            continue

        cell_texts = [clean_text(c.text) for c in cells]
        if not cell_texts[0]:
            continue

        # Expected visible columns from your screenshot
        item = {
            "train_id": cell_texts[0] if len(cell_texts) > 0 else "",
            "train_date": cell_texts[1] if len(cell_texts) > 1 else "",
            "origin": cell_texts[2] if len(cell_texts) > 2 else "",
            "destination": cell_texts[3] if len(cell_texts) > 3 else "",
            "operator": cell_texts[4] if len(cell_texts) > 4 else "",
            "status": cell_texts[5] if len(cell_texts) > 5 else "",
        }
        if item["train_id"]:
            results.append(item)

    return results


def go_to_login_page(driver):
    driver.get(BASE_URL)
    wait_for_page(driver, timeout=30)


def login(driver, username, password):
    go_to_login_page(driver)

    # Find username
    user_elem = find_first(driver, [
        "//input[@type='email']",
        "//input[contains(translate(@name, 'USERNAME', 'username'), 'user')]",
        "//input[contains(translate(@id, 'USERNAME', 'username'), 'user')]",
        "//input[@type='text']",
    ], timeout=15)

    pass_elem = find_first(driver, [
        "//input[@type='password']",
        "//input[contains(translate(@name, 'PASSWORD', 'password'), 'pass')]",
        "//input[contains(translate(@id, 'PASSWORD', 'password'), 'pass')]",
    ], timeout=15)

    user_elem.clear()
    user_elem.send_keys(username)
    pass_elem.clear()
    pass_elem.send_keys(password)

    submit_elem = find_first(driver, [
        "//input[@type='submit']",
        "//button[@type='submit']",
        "//button[contains(normalize-space(), 'Login')]",
        "//button[contains(normalize-space(), 'Sign in')]",
        "//a[contains(normalize-space(), 'Login')]",
    ], timeout=15, clickable=True)

    if not safe_click(driver, submit_elem):
        raise RuntimeError("Could not click login submit button.")

    time.sleep(2)
    wait_for_page(driver, timeout=30)

    # Very loose success check
    page_text = clean_text(driver.find_element(By.TAG_NAME, "body").text).lower()
    if "rail access management system" not in page_text and "train progress" not in page_text and "menu" not in page_text:
        raise RuntimeError("Login may have failed. Could not detect expected page content.")


def go_to_train_progress_menu(driver):
    clicked = maybe_click_link_by_text(driver, "Train Progress", timeout=8)
    if clicked:
        return

    # fallback: hamburger menu then link
    maybe_click_link_by_text(driver, "Menu", timeout=3)
    click_link_by_text(driver, "Train Progress", timeout=8)


def run_running_train_search(driver):
    # We only set Status=Running for the first version
    try_select_near_label_by_visible_text(driver, "Status", "Running")
    click_search_button(driver)
    return parse_train_list_rows(driver)


def search_train_by_id(driver, train_id):
    go_to_train_progress_menu(driver)
    try_set_input_near_label(driver, "Train ID", train_id)
    try_select_near_label_by_visible_text(driver, "Status", "Running")
    click_search_button(driver)


def open_first_view_result(driver):
    view_elem = find_first(driver, [
        "(//input[@type='submit' and @value='View'])[1]",
        "(//button[normalize-space()='View'])[1]",
        "(//*[self::a or self::button or self::input][contains(normalize-space(), 'View')])[1]",
    ], timeout=10, clickable=True)

    if not safe_click(driver, view_elem):
        raise RuntimeError("Could not click View.")
    time.sleep(1.5)
    wait_for_page(driver, timeout=20)


def parse_progress_page(driver):
    summary = parse_simple_summary_pairs(driver)

    try:
        schedule_table = find_heading_container_table(driver, "Schedule")
        schedule_rows = extract_table_rows(schedule_table)
    except Exception:
        schedule_rows = []

    return {
        "summary": summary,
        "schedule": schedule_rows
    }


def parse_consist_page(driver):
    click_link_by_text(driver, "Consist History", timeout=10)
    summary = parse_simple_summary_pairs(driver)

    try:
        consist_table = find_heading_container_table(driver, "Consist")
        consist_rows = extract_table_rows(consist_table)
    except Exception:
        consist_rows = []

    return {
        "summary": summary,
        "consist": consist_rows
    }


def parse_incidents_page(driver):
    click_link_by_text(driver, "Incidents", timeout=10)
    summary = parse_simple_summary_pairs(driver)

    incidents_total = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        m = re.search(r"Total Delay:\s*([0-9]+)", body_text, re.IGNORECASE)
        if m:
            incidents_total = m.group(1)
    except Exception:
        pass

    try:
        incidents_table = find_heading_container_table(driver, "Incidents")
        incidents_rows = extract_table_rows(incidents_table)
    except Exception:
        incidents_rows = []

    return {
        "summary": summary,
        "total_delay": incidents_total,
        "incidents": incidents_rows
    }


def scrape_one_train(driver, train_stub, account_label):
    train_id = train_stub.get("train_id", "").strip()
    if not train_id:
        return None

    print(f"  -> Scraping train {train_id}")
    search_train_by_id(driver, train_id)
    open_first_view_result(driver)

    progress_data = parse_progress_page(driver)
    consist_data = parse_consist_page(driver)

    incidents_data = {"summary": {}, "total_delay": "", "incidents": []}
    try:
        incidents_data = parse_incidents_page(driver)
    except Exception:
        pass

    combined = {
        "account_label": account_label,
        "scraped_at": utc_now_iso(),
        "train_id": train_id,
        "train_date": (
            progress_data.get("summary", {}).get("train_date")
            or consist_data.get("summary", {}).get("train_date")
            or train_stub.get("train_date", "")
        ),
        "operator": (
            progress_data.get("summary", {}).get("operator")
            or consist_data.get("summary", {}).get("operator")
            or train_stub.get("operator", "")
        ),
        "origin": (
            progress_data.get("summary", {}).get("origin")
            or consist_data.get("summary", {}).get("origin")
            or train_stub.get("origin", "")
        ),
        "destination": (
            progress_data.get("summary", {}).get("destination")
            or consist_data.get("summary", {}).get("destination")
            or train_stub.get("destination", "")
        ),
        "status": train_stub.get("status", ""),
        "progress": progress_data.get("schedule", []),
        "consist": consist_data.get("consist", []),
        "incidents_total_delay": incidents_data.get("total_delay", ""),
        "incidents": incidents_data.get("incidents", []),
    }

    return combined


def dedupe_and_merge_train_records(records):
    """
    Deduplicate by train_id + train_date.
    If duplicates exist from multiple accounts, keep the one with the richer consist/incidents.
    """
    best = {}

    def score(rec):
        return (
            len(rec.get("consist", [])) * 10
            + len(rec.get("incidents", [])) * 3
            + len(rec.get("progress", []))
        )

    for rec in records:
        key = (
            clean_text(rec.get("train_id", "")).upper(),
            clean_text(rec.get("train_date", ""))
        )
        if key not in best or score(rec) > score(best[key]):
            best[key] = rec

    return list(best.values())


def scrape_account(username, password, account_label):
    driver = build_driver()
    account_result = {
        "account_label": account_label,
        "scraped_at": utc_now_iso(),
        "train_count": 0,
        "trains": [],
        "error": ""
    }

    try:
        print(f"[{account_label}] Logging in...")
        login(driver, username, password)

        print(f"[{account_label}] Opening Train Progress...")
        go_to_train_progress_menu(driver)

        print(f"[{account_label}] Searching running trains...")
        train_list = run_running_train_search(driver)
        if not train_list:
            account_result["error"] = "No running trains found or results table not parsed."
            return account_result

        selected = train_list[:MAX_TRAINS]
        print(f"[{account_label}] Found {len(train_list)} trains, scraping first {len(selected)}")

        trains_out = []
        for stub in selected:
            try:
                item = scrape_one_train(driver, stub, account_label)
                if item:
                    trains_out.append(item)
            except Exception as e:
                print(f"[{account_label}] Failed on train {stub.get('train_id')}: {e}")
                traceback.print_exc()
                continue

        account_result["train_count"] = len(trains_out)
        account_result["trains"] = trains_out
        return account_result

    except Exception as e:
        account_result["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
        return account_result

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def load_accounts():
    accounts = []
    for i in range(1, 4):
        username = os.getenv(f"WEBRAMS_USERNAME_{i}", "").strip()
        password = os.getenv(f"WEBRAMS_PASSWORD_{i}", "").strip()
        label = os.getenv(f"WEBRAMS_LABEL_{i}", f"account_{i}").strip()
        if username and password:
            accounts.append({
                "username": username,
                "password": password,
                "label": label,
            })
    return accounts


def main():
    ensure_data_dir()
    accounts = load_accounts()

    if not accounts:
        raise RuntimeError("No WebRAMS accounts found in .env")

    all_account_results = []
    all_train_records = []

    for account in accounts:
        result = scrape_account(
            account["username"],
            account["password"],
            account["label"]
        )
        all_account_results.append(result)
        all_train_records.extend(result.get("trains", []))

    merged_records = dedupe_and_merge_train_records(all_train_records)

    output = {
        "updated_at": utc_now_iso(),
        "base_url": BASE_URL,
        "max_trains_per_account": MAX_TRAINS,
        "accounts": all_account_results,
        "trains": merged_records
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Saved {OUT_FILE}")
    print(f"Merged trains: {len(merged_records)}")


if __name__ == "__main__":
    main()