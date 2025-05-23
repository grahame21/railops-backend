import os
from github import Github

GITHUB_TOKEN = os.getenv("GH_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")

with open("cookie.txt", "r") as f:
    cookie = f.read().strip()

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)
repo.create_secret("ASPXAUTH", cookie)
print("✅ Updated secret ASPXAUTH")
