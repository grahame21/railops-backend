#!/usr/bin/env python3
import json, os, random, time
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
OUT  = BASE / "trains.json"

LOGIN_URL = "https://trainfinder.otenko.com/Home/NextLevel"
VIEW_URL  = "https://trainfinder.otenko.com/Home/GetViewPortData"

SWEEP = [
    (144.9631, -37.8136, 12),
    (151.2093, -33.8688, 12),
    (153.0260, -27.4705, 11),
    (138.6007, -34.9285, 11),
    (115.8605, -31.9505, 11),
    (147.3240, -42.8821, 11),
    (149.1287, -35.2820, 12),
    (133.7751, -25.2744, 5),
]

def now_iso(): return datetime.now(timezone.utc).isoformat()
def pf(v): 
    try: return float(v)
    except: return None
def first(d,*k):
    for x in k:
        if isinstance(d,dict) and x in d: return d[x]
    return None

def extract(p):
    if not p: return []
    if isinstance(p,list): return p
    for k in ["trains","Trains","markers","Markers","items","Items","results","Results","features","data","payload"]:
        v=p.get(k) if isinstance(p,dict) else None
        if isinstance(v,list): return v
        if isinstance(v,dict):
            sub=extract(v)
            if sub: return sub
    if isinstance(p,dict):
        for v in p.values():
            if isinstance(v,list) and v and isinstance(v[0],dict): return v
    return []

def normalize(r,i):
    if isinstance(r,dict) and r.get("type")=="Feature":
        g=r.get("geometry",{}); p=r.get("properties",{})
        if g.get("type")=="Point" and isinstance(g.get("coordinates"),(list,tuple)):
            lo,la=g["coordinates"][:2]
            return {
                "id": first(p,"id","ID","Name","Unit","Service","ServiceNumber") or f"train_{i}",
                "lat":pf(la),"lon":pf(lo),
                "heading":pf(first(p,"heading","Heading","bearing","Bearing")) or 0,
                "speed":pf(first(p,"speed","Speed")),
                "label":first(p,"label","Label","loco","Loco","Service","Operator") or "",
                "operator":first(p,"operator","Operator","company","Company") or "",
                "updatedAt":first(p,"Timestamp","updated","Updated","LastSeen","lastSeen") or now_iso()
            }
    lat=pf(first(r,"lat","Lat","latitude","Latitude","y","Y"))
    lon=pf(first(r,"lon","Lon","longitude","Longitude","x","X"))
    if lat is None or lon is None: return None
    return {
        "id": first(r,"id","ID","Name","Service") or f"train_{i}",
        "lat":lat,"lon":lon,
        "heading":pf(first(r,"heading","Heading","bearing")) or 0,
        "speed":pf(first(r,"speed","Speed")),
        "label":first(r,"label","Label","loco","Loco","Service","Operator") or "",
        "operator":first(r,"operator","Operator","company") or "",
        "updatedAt":first(r,"Timestamp","updated","Updated","LastSeen","lastSeen") or now_iso()
    }

def main():
    user=os.getenv("TRAINFINDER_USERNAME")
    pwd=os.getenv("TRAINFINDER_PASSWORD")
    if not user or not pwd:
        raise SystemExit("❌ Missing credentials")

    with sync_playwright() as p:
        print("🌐 Logging in...")
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context()
        page=ctx.new_page()
        page.goto(LOGIN_URL,wait_until="load",timeout=60_000)
        page.wait_for_selector("input#UserName",timeout=30_000)
        page.fill("input#UserName",user)
        page.fill("input#Password",pwd)
        page.locator("button:has-text('Log In'), input[type='submit'][value='Log In']").first.click()
        ctx.wait_for_event("requestfinished",timeout=30_000)
        cookies={c["name"]:c["value"] for c in ctx.cookies()}
        if ".ASPXAUTH" not in cookies:
            raise RuntimeError("Login failed")
        print("✅ Login OK")

        collected,seen=[],set()
        print("🚉 Sweeping AU viewports…")
        for lo,la,zm in SWEEP:
            try:
                page.goto(f"{LOGIN_URL}?lat={la}&lng={lo}&zm={zm}",wait_until="load",timeout=45_000)
                time.sleep(1.2)
                js=f"""
                (async () => {{
                  const res = await fetch("{VIEW_URL}", {{
                    method: "POST",
                    headers: {{ "x-requested-with": "XMLHttpRequest" }}
                  }});
                  const text = await res.text();
                  return {{status: res.status, text}};
                }})();
                """
                resp=page.evaluate(js)
                s=resp["status"]; t=(resp["text"] or "").strip()
                if s!=200 or not t or t.startswith("<") or t=='["cookie"]':
                    print(f"⚠️ Bad data {lo},{la}"); continue
                data=json.loads(t)
                arr=extract(data); got=0
                for i,r in enumerate(arr):
                    n=normalize(r,i)
                    if not n or n["lat"] is None or n["lon"] is None: continue
                    k=(n["id"],round(n["lat"],5),round(n["lon"],5))
                    if k in seen: continue
                    seen.add(k); collected.append(n); got+=1
                print(f"🛰️ {got} trains from {lo},{la}")
                time.sleep(random.uniform(1.0,2.0))
            except Exception as e:
                print(f"❌ viewport {lo},{la}: {e}")
        OUT.write_text(json.dumps(collected,indent=2,ensure_ascii=False))
        print(f"✅ Wrote {OUT} with {len(collected)} trains")
        browser.close()

if __name__=="__main__":
    main()
