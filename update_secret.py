import base64
import os
import requests
from nacl import encoding, public

# GitHub environment variables
repo = os.environ['GITHUB_REPOSITORY']
token = os.environ['GH_TOKEN']
api_url = f'https://api.github.com/repos/{repo}'

# Step 1: Read the new cookie
with open('cookie.txt', 'r') as f:
    cookie_value = f.read().strip()

# Step 2: Get the public key for the repository
res = requests.get(f'{api_url}/actions/secrets/public-key', headers={
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
})
res.raise_for_status()
key_data = res.json()
public_key = key_data['key']
key_id = key_data['key_id']

# Step 3: Encrypt the secret
def encrypt(public_key_str, secret_value):
    public_key = public.PublicKey(public_key_str.encode('utf-8'), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode('utf-8'))
    return base64.b64encode(encrypted).decode('utf-8')

encrypted_cookie = encrypt(public_key, cookie_value)

# Step 4: Update the secret
put_res = requests.put(
    f'{api_url}/actions/secrets/TRAINFINDER_COOKIE',
    headers={
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    },
    json={
        'encrypted_value': encrypted_cookie,
        'key_id': key_id
    }
)
put_res.raise_for_status()
print("✅ GitHub secret TRAINFINDER_COOKIE updated successfully.")
