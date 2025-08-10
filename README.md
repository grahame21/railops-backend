# Train Tracker 2.0 – Backend

## Configure
Create a `.env` (for local dev) with:

TRAINFINDER_VIEWPORT_URL=https://trainfinder.otenko.com/Home/GetViewPortData?...(exact URL from your browser Network tab)...
TRAINFINDER_ASPXAUTH=YOUR_COOKIE_VALUE
# Optional proxy:
# HTTP_PROXY_URL=http://username:password@au.proxymesh.com:31280
UPDATE_INTERVAL=30

## Run locally
pip install -r requirements.txt
uvicorn app.main:app --reload

Open http://localhost:8000/healthz  (should say ok after first fetch)
Open http://localhost:8000/trains.json  (live data)

## Deploy to Render
- Create new Web Service from this repo.
- Set env vars:
  - TRAINFINDER_VIEWPORT_URL
  - TRAINFINDER_ASPXAUTH
  - (optional) HTTP_PROXY_URL
  - UPDATE_INTERVAL (e.g., 30)
- Deploy. Use https://<your-service>.onrender.com/trains.json in your frontend.
