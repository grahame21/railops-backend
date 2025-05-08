import os
import requests

repo = os.getenv("GITHUB_REPOSITORY")
token = os.getenv("GH_TOKEN")
secret_name = "TRAINFINDER_COOKIE"

with open("cookie.txt", "r") as f:
    secret_value = f.read().strip()

url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
}

# Get the public key
key_resp = requests.get(
    f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
    headers=headers,
)
key_data = key_resp.json()

from base64 import b64encode
from nacl import encoding, public

def encrypt(public_key: str, secret_value: str) -> str:
    key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")

encrypted_value = encrypt(key_data["key"], secret_value)

# Upload the secret
resp = requests.put(url, headers=headers, json={
    "encrypted_value": encrypted_value,
    "key_id": key_data["key_id"]
})

if resp.status_code == 201 or resp.status_code == 204:
    print("✅ GitHub secret updated successfully.")
else:
    print(f"❌ Failed to update secret: {resp.status_code} {resp.text}")