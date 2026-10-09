"""Generuje stronę główną (index.html) dla GitHub Pages z wyników pipeline'u."""
from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>running-air · Kraków running routes</title>
<style>
  :root { --bg:#0f1117; --panel:#1a1f2e; --line:#2a3045; --text:#e8eaf0; --muted:#8892a4; --accent:#4f9eff; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); line-height:1.6; }
  header { padding:2.5rem 1.5rem 2rem; text-align:center; border-bottom:1px solid var(--line);
           background:linear-gradient(135deg,#1a1f2e,#0f1117); }
  header h1 { font-size:2rem; letter-spacing:-.5px; }
  header h1 span { color:var(--accent); }
  header p { color:var(--muted); max-width:560px; margin:.6rem auto 0; }
  main { max-width:900px; margin:0 auto; padding:2rem 1.5rem; }
  h2 { font-size:.75rem; letter-spacing:1.5px; text-transform:uppercase; color:var(--accent); margin:2rem 0 .8rem; }
  .date { color:var(--muted); font-size:.85rem; margin-bottom:.8rem; }
  .cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:1rem; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:1.2rem; }
  .km { font-size:2rem; font-weight:700; color:var(--accent); line-height:1; }
  .pm { display:inline-block; margin:.6rem 0; padding:.15rem .6rem; border-radius:20px; font-size:.78rem; font-weight:600; }
  .pm-good { background:#0d3320; color:#4caf7d; }
  .pm-ok { background:#1a2e0d; color:#8bc34a; }
  .pm-who { background:#2e2600; color:#ffcc02; }
  .pm-bad { background:#2e1200; color:#ff9800; }
  .row { display:flex; justify-content:space-between; font-size:.82rem; border-top:1px solid var(--line); padding:.35rem 0; }
  .row span:first-child { color:var(--muted); }
  .actions { display:flex; gap:.5rem; margin-top:.8rem; }
  .btn { flex:1; text-align:center; padding:.45rem .5rem; border-radius:8px; font-size:.82rem;
         font-weight:500; text-decoration:none; }
  .btn-main { background:var(--accent); color:#0f1117; }
  .btn-alt { border:1px solid var(--line); color:var(--text); }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:1.2rem 1.4rem;
           color:#b0b8c8; font-size:.9rem; }
  code { background:var(--bg); border:1px solid var(--line); border-radius:4px; padding:.15rem .45rem;
         color:var(--accent); font-size:.82rem; }
  .tags { display:flex; flex-wrap:wrap; gap:.5rem; }
  .tag { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:.25rem .7rem;
         font-size:.8rem; color:var(--muted); }
  .links { display:flex; gap:.8rem; flex-wrap:wrap; }
  .links .btn { flex:none; padding:.5rem 1.1rem; }
  footer { text-align:center; padding:2rem; color:#4a5264; font-size:.8rem; }
</style>
</head>
<body>
<header>
  <h1>🏃 <span>running-air</span></h1>
  <p>Daily running route optimizer for Kraków, powered by Airly air quality sensors and OpenStreetMap.</p>
</header>
<main>
  <h2>Latest best routes</h2>
  <p class="date">Generated: __DATE__</p>
  <div class="cards">
__CARDS__
  </div>

  <h2>Method</h2>
  <div class="panel">
    PM2.5 readings from Airly sensors are interpolated onto every edge of the OSM walking graph with
    <b>Inverse Distance Weighting</b>. Loop candidates are built from sampled waypoints using shortest paths
    with a PM2.5-weighted edge cost, then scored:<br><br>
    <code>score = 0.60 × air_quality + 0.25 × green_cover + 0.15 × length_accuracy</code><br><br>
    Each distance exports a GPX file you can load into a watch or phone. IDW is an estimate, so street-level
    pollution can differ from the nearest sensor reading.
  </div>

  <h2>Tech stack</h2>
  <div class="tags">
    <span class="tag">Python</span><span class="tag">OSMnx</span><span class="tag">NetworkX</span>
    <span class="tag">SciPy (IDW)</span><span class="tag">Folium</span><span class="tag">Pandas</span>
    <span class="tag">GitHub Actions</span><span class="tag">Airly API v2</span>
  </div>

  <h2>Links</h2>
  <div class="links">
    <a class="btn btn-main" href="https://github.com/elphi97/running-air">GitHub repository</a>
    <a class="btn btn-alt" href="https://github.com/elphi97/running-air/tree/main/data/measurements">Raw data (CSV)</a>
  </div>
</main>
<footer>running-air · updated daily via GitHub Actions</footer>
</body>
</html>
"""


def _pm_class(pm: float) -> str:
    if pm < 10:
        return "pm-good"
    if pm < 20:
        return "pm-ok"
    if pm < 25:
        return "pm-who"
    return "pm-bad"


def _card(r: dict) -> str:
    return f"""    <div class="card">
      <div class="km">{r['km']:g} km</div>
      <span class="pm {_pm_class(r['avg_pm25'])}">PM2.5 {r['avg_pm25']} µg/m³</span>
      <div class="row"><span>Length</span><span>{r['length_m'] / 1000:.1f} km</span></div>
      <div class="row"><span>Green cover</span><span>{r['green_pct']}%</span></div>
      <div class="row"><span>Score</span><span>{r['score']}</span></div>
      <div class="actions">
        <a class="btn btn-main" href="{r['map']}">Map</a>
        <a class="btn btn-alt" href="{r['gpx']}" download>GPX</a>
      </div>
    </div>"""


def write_index(results: list[dict], date: str, out_dir: Path) -> Path:
    """Zapisuje out_dir/index.html (+ .nojekyll) na podstawie podsumowania tras."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(_card(r) for r in sorted(results, key=lambda x: x["km"]))
    html = TEMPLATE.replace("__CARDS__", cards).replace("__DATE__", date)
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").touch()
    return path


def prune_old(out_dir: Path, keep_date: str) -> int:
    """Usuwa mapy/GPX/summary z innych dat, żeby repo nie puchło."""
    pattern = re.compile(r"^(map_.*|best_.*|summary)_(\d{4}-\d{2}-\d{2})\.(html|gpx|json)$")
    removed = 0
    for f in out_dir.iterdir():
        m = pattern.match(f.name)
        if m and m.group(2) != keep_date:
            f.unlink()
            removed += 1
    return removed
