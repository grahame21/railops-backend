import os
import base64
import json
import requests

REPO = os.getenv("GITHUB_REPOSITORY")  # e.g. grahame21/railops-backend
TOKEN = os.getenv("GH_TOKEN")          # GitHub personal access token

# Read the cookie value
try:
    with open("cookie.txt", "r") as f:
        cookie_value = f.read().strip()
except FileNotFoundError:
    print("❌ cookie.txt not found.")
    exit(1)

# Prepare GitHub API request
headers = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28"
}

# Set the secret
url = f"https://api.github.com/repos/{REPO}/actions/secrets/TRAINFINDER_COOKIE"

# Get repo public key
key_resp = requests.get(
    f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
    headers=headers
)
if key_resp.status_code != 200:
    print("❌ Failed to get public key:", key_resp.text)
    exit(1)

key_id = key_resp.json()["key_id"]
public_key = key_resp.json()["key"]

# Encrypt the secret
from nacl import encoding, public

def encrypt(public_key: str, secret_value: str) -> str:
    public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

encrypted_value = encrypt(public_key, cookie_value)

# Update the secret
put_resp = requests.put(
    url,
    headers=headers,
    json={
        "encrypted_value": encrypted_value,
        "key_id": key_id
    }
)

if put_resp.status_code == 201 or put_resp.status_code == 204:
    print("✅ TRAINFINDER_COOKIE secret updated successfully.")
else:
    print("❌ Failed to update secret:", put_resp.text)
