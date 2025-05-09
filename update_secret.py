import requests
import os
from nacl import encoding, public
import base64

# Load the cookie
with open("cookie.txt", "r") as f:
    new_cookie = f.read().strip()

# GitHub API values
repo = os.getenv("GITHUB_REPOSITORY")  # e.g., 'grahame21/railops-backend'
token = os.getenv("GH_TOKEN")  # automatically injected GitHub Actions token

# Step 1: Get public key
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
}
res = requests.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key", headers=headers)
res.raise_for_status()
key_data = res.json()

# Step 2: Encrypt the cookie
def encrypt(public_key: str, secret_value: str) -> str:
    key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

encrypted_value = encrypt(key_data["key"], new_cookie)

# Step 3: Upload the new secret
put_url = f"https://api.github.com/repos/{repo}/actions/secrets/ASPXAUTH_COOKIE"
res = requests.put(
    put_url,
    headers=headers,
    json={
        "encrypted_value": encrypted_value,
        "key_id": key_data["key_id"],
    }
)
res.raise_for_status()
print("✅ Secret ASPXAUTH_COOKIE updated.")
