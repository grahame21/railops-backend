# RailOps Auth Pack

This ZIP gives you a starter Flask app with:

- admin + guest login
- protected dashboard and admin pages
- guest token links using `/access?token=...`
- admin panel links for tracker/data files
- admin button to trigger a GitHub Actions fast scraper workflow
- modern glass-style pages with a train-themed background

## First run

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:5000/login
```

## Default login

Admin:

- username: `admin`
- password: `change-me-now`

Guest:

- username: `guest`
- password: `guest123`

Change these straight away in `data/users.json` after first run.

## GitHub fast scraper button setup

Set these environment variables before running Flask:

- `SECRET_KEY`
- `GITHUB_PAT`
- `GITHUB_REPO` → for example `grahame21/railops-backend`
- `GITHUB_WORKFLOW_ID` → for example `fast-scraper.yml` or the numeric workflow ID
- `GITHUB_WORKFLOW_REF` → usually `main`

Example on Windows PowerShell:

```powershell
$env:SECRET_KEY="replace-this"
$env:GITHUB_PAT="github_pat_xxx"
$env:GITHUB_REPO="grahame21/railops-backend"
$env:GITHUB_WORKFLOW_ID="fast-scraper.yml"
$env:GITHUB_WORKFLOW_REF="main"
python app.py
```

## Where to plug in your real site

- Replace the contents of `templates/dashboard.html` with your full live map page, or embed your existing map into that page.
- Replace `/flight-tracker` with your real flight tracker route/page.
- Replace `/loco-db` with your real locomotive DB viewer route/page.
- Put your real files in `static/data/`.

## Notes

- Passwords are stored plainly in this starter pack for speed while you get moving. For a production version, switch to password hashing.
- The included background is a bundled train-themed SVG, so the ZIP works immediately. You can later replace `static/img/train-bg.svg` with your own train photo file and update the CSS reference.
