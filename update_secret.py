import base64
import json
import os
import requests
from nacl import encoding, public

# Load values
repo = os.getenv("GITHUB_REPOSITORY")  # e.g., grahame21/railops-backend
token = os.getenv("GH_TOKEN")

# Load cookie
with open("cookie.txt", "r") as f:
    secret_value = f.read().strip()

# Step 1: Get public key for encrypting the secret
url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json"
}
response = requests.get(url, headers=headers)
response.raise_for_status()
public_key_data = response.json()

# Step 2: Encrypt the cookie using the public key
def encrypt(public_key: str, secret_value: str) -> str:
    public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

encrypted_value = encrypt(public_key_data["key"], secret_value)

# Step 3: Upload encrypted secret to GitHub
secret_name = "ASPXAUTH_COOKIE"
put_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
payload = {
    "encrypted_value": encrypted_value,
    "key_id": public_key_data["key_id"]
}

put_response = requests.put(put_url, headers=headers, json=payload)
put_response.raise_for_status()

print(f"✅ GitHub secret '{secret_name}' updated successfully.")