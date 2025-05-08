import os
import time
import base64
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

username = os.environ['TRAINFINDER_USERNAME']
password = os.environ['TRAINFINDER_PASSWORD']
repo = os.environ['GITHUB_REPOSITORY']
gh_token = os.environ['GH_TOKEN']

# Configure headless Chrome
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=chrome_options)
driver.get("https://trainfinder.otenko.com/home/nextlevel")

try:
    # Fill in the login form
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "useR_name"))).send_keys(username)
    driver.find_element(By.ID, "pasS_word").send_keys(password)
    driver.find_element(By.CLASS_NAME, "button-green").click()

    # Wait for login to complete and page to load
    time.sleep(5)

    # Get .ASPXAUTH cookie
    cookie = driver.get_cookie('.ASPXAUTH')
    if cookie:
        cookie_value = cookie['value']
        print("✅ Login successful. Extracted cookie.")
    else:
        print("❌ Login failed. No .ASPXAUTH cookie found.")
        driver.quit()
        exit(1)

    driver.quit()

    # Update GitHub Actions secret
    secret_payload = {
        "encrypted_value": base64.b64encode(cookie_value.encode()).decode(),
        "key_id": "manual"  # Not actually used because we're using REST not GraphQL here
    }

    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json"
    }

    # Get public key for encrypting secret
    key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
    key_response = requests.get(key_url, headers=headers).json()
    key_id = key_response["key_id"]
    key = key_response["key"]

    # Encrypt using GitHub's public key
    from nacl import encoding, public
    def encrypt(public_key: str, secret_value: str) -> str:
        public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    encrypted_cookie = encrypt(key, cookie_value)

    secret_url = f"https://api.github.com/repos/{repo}/actions/secrets/TRAINFINDER_COOKIE"
    secret_payload = {
        "encrypted_value": encrypted_cookie,
        "key_id": key_id
    }

    response = requests.put(secret_url, headers=headers, json=secret_payload)
    if response.status_code == 201 or response.status_code == 204:
        print("✅ GitHub secret TRAINFINDER_COOKIE updated.")
    else:
        print(f"❌ Failed to update secret: {response.status_code} - {response.text}")

except Exception as e:
    print(f"❌ Login error: {e}")
    driver.quit()
    exit(1)