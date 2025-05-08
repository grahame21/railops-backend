import os
import time
import requests
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from nacl import encoding, public

# --- ENV VARS ---
username = os.getenv("TRAINFINDER_USERNAME")
password = os.getenv("TRAINFINDER_PASSWORD")
repo = os.getenv("GITHUB_REPOSITORY")
token = os.getenv("GH_TOKEN")
secret_name = "TRAINFINDER_COOKIE"

# --- START SELENIUM ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)

# --- LOGIN ---
driver.get("https://trainfinder.otenko.com/home/nextlevel")
try:
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name")))
    driver.find_element(By.ID, "useR_name").send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)
    driver.find_element(By.CLASS_NAME, "button-green").click()
    time.sleep(5)
except Exception as e:
    driver.quit()
    raise Exception(f"❌ Login error: {str(e)}")

# --- GET COOKIE ---
cookie_value = None
for cookie in driver.get_cookies():
    if cookie['name'] == '.ASPXAUTH':
        cookie_value = cookie['value']
        break

driver.quit()

if not cookie_value:
    raise Exception("❌ .ASPXAUTH cookie not found after login.")

# --- ENCRYPT COOKIE ---
def encrypt(public_key: str, secret_value: str) -> str:
    pk = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(pk)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

# --- GET GITHUB PUBLIC KEY ---
headers = {"Authorization": f"Bearer {token}"}
key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
res = requests.get(key_url, headers=headers)
res.raise_for_status()
key_data = res.json()
encrypted_value = encrypt(key_data['key'], cookie_value)

# --- UPLOAD TO GITHUB SECRET ---
put_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
payload = {"encrypted_value": encrypted_value, "key_id": key_data["key_id"]}
res = requests.put(put_url, headers=headers, json=payload)
res.raise_for_status()

print("✅ Cookie saved successfully as GitHub secret.")