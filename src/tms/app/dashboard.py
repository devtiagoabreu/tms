"""Dashboard HTML simples (Fase 2) que consome `/api/monitor`."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

MONITOR_HTML = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TMS - Monitor</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; font-family: system-ui, "Segoe UI", sans-serif; background: #121417; color: #e8eaed; }
  header { padding: 12px 20px; background: #1b1f24; display: flex; gap: 24px; align-items: baseline; flex-wrap: wrap; }
  header h1 { font-size: 18px; margin: 0; font-weight: 600; }
  .kpi { font-size: 13px; color: #9aa0a6; }
  .kpi b { color: #e8eaed; font-size: 15px; }
  #grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; padding: 14px; }
  .card { border-radius: 8px; padding: 12px; background: #1b1f24; border-left: 6px solid #607D8B; }
  .card .top { display: flex; justify-content: space-between; align-items: baseline; }
  .card .mac { font-size: 20px; font-weight: 700; }
  .card .state { font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }
  .card .row { display: flex; justify-content: space-between; font-size: 12px; color: #bdc1c6; margin-top: 4px; }
  .card .stop { margin-top: 8px; font-size: 12px; color: #ff8a80; }
  .bar { height: 6px; border-radius: 3px; background: #303134; margin-top: 8px; overflow: hidden; }
  .bar > span { display: block; height: 100%; background: #4CAF50; }
  footer { padding: 8px 20px; font-size: 12px; color: #9aa0a6; }
</style>
</head>
<body>
<header>
  <h1>TMS - Monitor</h1>
  <span class="kpi">Em opera\u00e7\u00e3o <b id="k-run">-</b>/<span id="k-total">-</span></span>
  <span class="kpi">Paradas <b id="k-stop">-</b></span>
  <span class="kpi">Sem comunica\u00e7\u00e3o <b id="k-off">-</b></span>
  <span class="kpi">Efici\u00eancia m\u00e9dia <b id="k-eff">-</b>%</span>
</header>
<div id="grid"></div>
<footer>Atualizado <span id="ts">-</span> &middot; recarrega a cada 30s</footer>
<script>
const grid = document.getElementById('grid');
function card(m) {
  const eff = m.efficiency == null ? '-' : m.efficiency.toFixed(1);
  const prod = m.production == null ? '-' : m.production;
  const rpm = m.rpm == null ? '-' : m.rpm;
  const stop = m.stop ? `<div class="stop">${m.stop.cause} (${m.stop.duration_min ?? '?'} min)</div>` : '';
  const bar = m.efficiency == null ? '' : `<div class="bar"><span style="width:${Math.min(100, m.efficiency)}%"></span></div>`;
  const live = m.live ? `<div class="row"><span>${m.live.status}</span><span>24h ${m.live.efficiency_24h ?? '-'}%</span></div>` : '';
  return `<div class="card" style="border-left-color:${m.color}">
    <div class="top"><span class="mac">${m.mac_name}</span><span class="state" style="color:${m.color}">${m.state_label}</span></div>
    <div class="row"><span>${m.mac_type} ${m.style || ''}</span><span>visto h\u00e1 ${m.age_min ?? '?'} min</span></div>
    <div class="row"><span>Produ\u00e7\u00e3o ${prod}</span><span>RPM ${rpm}</span></div>
    <div class="row"><span>Efici\u00eancia ${eff}%</span><span>${m.shift_id || ''}</span></div>
    ${live}${bar}${stop}
  </div>`;
}
async function refresh() {
  const res = await fetch('/api/monitor');
  const data = await res.json();
  grid.innerHTML = data.map(card).join('');
  const run = data.filter(m => m.state === 'run').length;
  const off = data.filter(m => m.state === 'offline' || m.state === 'no_data').length;
  const stopped = data.filter(m => m.state === 'stopped').length;
  const effs = data.map(m => m.efficiency).filter(v => v != null);
  document.getElementById('k-run').textContent = run;
  document.getElementById('k-total').textContent = data.length;
  document.getElementById('k-stop').textContent = stopped;
  document.getElementById('k-off').textContent = off;
  document.getElementById('k-eff').textContent = effs.length ? (effs.reduce((a, b) => a + b, 0) / effs.length).toFixed(1) : '-';
  document.getElementById('ts').textContent = new Date().toLocaleTimeString();
}
refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""


@router.get("/monitor", response_class=HTMLResponse, include_in_schema=False)
def monitor_page() -> HTMLResponse:
    return HTMLResponse(MONITOR_HTML)
