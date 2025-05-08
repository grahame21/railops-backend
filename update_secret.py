import os
import requests
import base64

GITHUB_REPO = "grahame21/railops-backend"  # Replace with your actual repo
GITHUB_SECRET_NAME = "ASPXAUTH_COOKIE"

# Read your cookie
with open("cookie.txt", "r") as file:
    new_cookie = file.read().strip()

# Get token and repo info
token = os.environ["GH_PAT"]
headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github+json",
}

# Get public key for encryption
response = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/actions/secrets/public-key", headers=headers)
response.raise_for_status()
data = response.json()
public_key = data["key"]
key_id = data["key_id"]

# Encrypt the secret using the public key
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.backends import default_backend
from nacl import encoding, public

def encrypt_secret(public_key_str, secret_value):
    public_key = public.PublicKey(public_key_str.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

encrypted_value = encrypt_secret(public_key, new_cookie)

# PUT the new encrypted value
res = requests.put(
    f"https://api.github.com/repos/{GITHUB_REPO}/actions/secrets/{GITHUB_SECRET_NAME}",
    headers=headers,
    json={"encrypted_value": encrypted_value, "key_id": key_id},
)
res.raise_for_status()

print("✅ ASPXAUTH_COOKIE GitHub Secret updated.")
