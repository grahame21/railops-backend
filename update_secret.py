import os
import requests
import base64

# Load the cookie from file
cookie_file = "cookie.txt"
if not os.path.exists(cookie_file):
    raise FileNotFoundError("cookie.txt not found")

with open(cookie_file, "r") as f:
    cookie_value = f.read().strip()

# Optional: Get location info if stored
location = "Unknown"
location_file = "location.txt"
if os.path.exists(location_file):
    with open(location_file, "r") as loc_file:
        location = loc_file.read().strip()

# Encode secrets for GitHub
repo = os.environ["GITHUB_REPOSITORY"]
token = os.environ["GH_TOKEN"]

api_url = f"https://api.github.com/repos/{repo}/actions/secrets"

def put_secret(name, value):
    # Get the public key
    headers = {"Authorization": f"Bearer {token}"}
    key_resp = requests.get(f"{api_url}/public-key", headers=headers)
    key_resp.raise_for_status()
    key_data = key_resp.json()

    from nacl import encoding, public
    key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(key)
    encrypted = sealed_box.encrypt(value.encode("utf-8"))

    payload = {
        "encrypted_value": base64.b64encode(encrypted).decode("utf-8"),
        "key_id": key_data["key_id"]
    }

    put_resp = requests.put(
        f"{api_url}/{name}",
        headers={**headers, "Content-Type": "application/json"},
        json=payload
    )
    put_resp.raise_for_status()
    print(f"✅ Secret {name} updated.")

# Save both secrets
put_secret("TRAINFINDER_COOKIE", cookie_value)
put_secret("TRAINFINDER_LOCATION", location)