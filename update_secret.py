import requests
from github import Github
import os

username = os.environ["TRAINFINDER_USERNAME"]
password = os.environ["TRAINFINDER_PASSWORD"]
gh_token = os.environ["GH_TOKEN"]
repo_name = os.environ["GITHUB_REPOSITORY"]

# Step 1: Login and get cookie
session = requests.Session()
resp = session.post("https://trainfinder.otenko.com/home/nextlevel", data={
    "useR_name": username,
    "pasS_word": password
})

cookie_value = None
for cookie in session.cookies:
    if cookie.name == ".ASPXAUTH":
        cookie_value = cookie.value
        break

if not cookie_value:
    raise Exception("❌ .ASPXAUTH cookie not found")

# Step 2: Update GitHub secret
gh = Github(gh_token)
repo = gh.get_repo(repo_name)

from nacl import encoding, public
def encrypt(public_key: str, secret_value: str) -> str:
    public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return encoding.Base64Encoder().encode(encrypted).decode("utf-8")

key = repo.get_actions_public_key()
encrypted = encrypt(key.key, cookie_value)
repo.create_or_update_secret("TF_COOKIE", encrypted, key.key_id)

print("✅ TF_COOKIE updated")