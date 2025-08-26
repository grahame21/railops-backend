from flask import Blueprint, Response

bp = Blueprint("try_ui", __name__, url_prefix="")

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>RailOps Tester</title>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <style>
    body{font:14px system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin:20px; line-height:1.35}
    input,button{font:inherit}
    label{display:block;margin:.5rem 0 .25rem}
    .row{display:flex;gap:12px;flex-wrap:wrap}
    .row>*{flex:1 1 180px}
    textarea{width:100%;height:320px}
    code,pre{background:#f6f6f6;padding:8px;border-radius:6px;display:block;overflow:auto}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
    .card{border:1px solid #ddd;border-radius:10px;padding:12px}
  </style>
</head>
<body>
  <h1>RailOps Tester</h1>

  <div class="grid">
    <div class="card">
      <h3>Session</h3>
      <label>.ASPXAUTH cookie value</label>
      <input id="cookie" placeholder="paste value here (no quotes, no .ASPXAUTH=)"/>
      <button onclick="run('authcheck')">/authcheck</button>
    </div>

    <div class="card">
      <h3>Viewport</h3>
      <div class="row">
        <div><label>lat</label><input id="lat" value="-33.8688"/></div>
        <div><label>lng</label><input id="lng" value="151.2093"/></div>
        <div><label>zm</label><input id="zm" value="12"/></div>
      </div>
      <button onclick="run('debug/viewport?lat='+g('lat')+'&lng='+g('lng')+'&zm='+g('zm'))">/debug/viewport</button>
      <button onclick="run('scan')">/scan</button>
    </div>
  </div>

  <h3>Result</h3>
  <pre id="out"></pre>

<script>
function g(id){return document.getElementById(id).value}
async function run(path){
  const headers = {};
  const c = g('cookie').trim();
  if (c) headers['X-TF-ASPXAUTH'] = c;
  const res = await fetch('/'+path, {headers});
  const txt = await res.text();
  document.getElementById('out').textContent =
    'GET /'+path+' …\\n'+(txt.startsWith('{')? JSON.stringify(JSON.parse(txt),null,2): txt);
}
</script>
</body>
</html>
"""

@bp.get("/try")
def try_ui() -> Response:
    return Response(HTML, mimetype="text/html")
