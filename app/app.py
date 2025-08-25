# --- BEGIN SUPER SIMPLE TEST UI --------------------------------------------
from flask import Response

@staticmethod
def _html_page():
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>RailOps Quick Tester</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, Arial, "Apple Color Emoji","Segoe UI Emoji"; }
  body { margin: 24px; }
  h1 { margin: 0 0 12px 0; font-size: 20px; }
  .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; max-width: 900px; margin-bottom: 16px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  input[type=text] { padding: 8px 10px; border: 1px solid #ccc; border-radius: 8px; min-width: 240px; }
  button { padding: 8px 12px; border: 1px solid #999; background: #f7f7f7; border-radius: 8px; cursor: pointer; }
  button.primary { background: #0b5cff; color: white; border-color: #0b5cff; }
  .help { color: #555; font-size: 13px; }
  pre { background: #0a0a0a; color: #d9d9d9; padding: 12px; border-radius: 10px; overflow:auto; max-height: 50vh;}
  .grid { display:grid; grid-template-columns: repeat(3,minmax(180px,1fr)); gap:8px; }
  .muted { color:#666; }
</style>
</head>
<body>
  <h1>RailOps Quick Tester</h1>

  <div class="card">
    <div class="row" style="margin-bottom:8px">
      <label for="token"><strong>.ASPXAUTH</strong></label>
      <input id="token" type="text" placeholder="paste your ASPXAUTH here">
      <button id="save">Save in this tab</button>
      <span class="help">Or leave blank to use server env <code>TF_AUTH_COOKIE</code>.</span>
    </div>
    <div class="row muted" id="status">No token set (will try server env)</div>
  </div>

  <div class="card">
    <div class="row" style="margin-bottom:8px">
      <strong>Viewport Params</strong>
    </div>
    <div class="grid" style="margin-bottom:8px">
      <input id="lat" type="text" value="-33.8688"  placeholder="lat">
      <input id="lng" type="text" value="151.2093"  placeholder="lng">
      <input id="zm"  type="text" value="12"        placeholder="zoom (int)">
    </div>
    <div class="row">
      <button class="primary" id="btn-auth">/authcheck</button>
      <button class="primary" id="btn-vp">/debug/viewport</button>
      <button class="primary" id="btn-scan">/scan</button>
      <button id="btn-clear">Clear output</button>
    </div>
  </div>

  <div class="card">
    <div class="row" style="margin-bottom:8px"><strong>Output</strong></div>
    <pre id="out"></pre>
  </div>

<script>
  const $ = sel => document.querySelector(sel);
  const out = $('#out'), status = $('#status');

  function getToken(){ return ($('#token').value||'').trim(); }
  function hdrs() {
    const t = getToken();
    return t ? { 'X-TF-ASPXAUTH': t } : {};
  }
  function log(obj){ out.textContent += (typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)) + "\\n"; }
  function setStatus(){ 
    const t = getToken();
    status.textContent = t ? "Token set in page (header X-TF-ASPXAUTH will be sent)" : "No token set (server env TF_AUTH_COOKIE will be used if configured)";
  }

  $('#save').onclick = () => { setStatus(); $('#token').blur(); };
  $('#btn-clear').onclick = () => { out.textContent = ""; };
  $('#btn-auth').onclick = async () => {
    log("GET /authcheck …");
    const r = await fetch('/authcheck', { headers: hdrs() });
    const j = await r.json();
    log(j);
  };
  $('#btn-vp').onclick = async () => {
    const lat = $('#lat').value.trim(), lng = $('#lng').value.trim(), zm = $('#zm').value.trim();
    const url = `/debug/viewport?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}&zm=${encodeURIComponent(zm)}`;
    log(`GET ${url} …`);
    const r = await fetch(url, { headers: hdrs() });
    const j = await r.json();
    log(j);
  };
  $('#btn-scan').onclick = async () => {
    log("GET /scan …");
    const r = await fetch('/scan', { headers: hdrs() });
    const j = await r.json();
    log(j);
  };
  setStatus();
</script>
</body>
</html>"""

@app.get("/try")
def try_ui():
    return Response(_html_page.__func__(), mimetype="text/html")
# --- END SUPER SIMPLE TEST UI ----------------------------------------------
