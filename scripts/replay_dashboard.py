"""N3 — Mission Replay Dashboard.

Görev sonrası analiz: runs/<ts>/events.jsonl + telemetry.csv → web timeline.
Flask, port 5000, sadece 127.0.0.1 bind (güvenlik).
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template_string, abort

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"

app = Flask(__name__)


# Lucide-style inline SVG icons (MIT). 20x20 stroke 1.75
def _svg(d_paths: str, size: int = 18) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
            f'stroke-linejoin="round">{d_paths}</svg>')


ICON = {
    "play": _svg('<polygon points="6 3 20 12 6 21 6 3"/>'),
    "plane_up": _svg('<path d="M14.639 10.258 21 6"/><path d="m2 16 20-5"/>'
                     '<path d="M9 17.5 8 22l-2-2-2-2 4.5-1"/>'),
    "plane": _svg('<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>'),
    "crosshair": _svg('<circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/>'
                      '<line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/>'
                      '<line x1="12" y1="22" x2="12" y2="18"/>'),
    "alert": _svg('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
                  '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
    "user_check": _svg('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
                       '<circle cx="9" cy="7" r="4"/><polyline points="16 11 18 13 22 9"/>'),
    "user_x": _svg('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
                   '<circle cx="9" cy="7" r="4"/><line x1="17" y1="8" x2="22" y2="13"/>'
                   '<line x1="22" y1="8" x2="17" y2="13"/>'),
    "package": _svg('<path d="m7.5 4.27 9 5.15"/>'
                    '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
                    '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'),
    "home": _svg('<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
                 '<polyline points="9 22 9 12 15 12 15 22"/>'),
    "octagon_x": _svg('<polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/>'
                      '<line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'),
    "arrow_down": _svg('<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>'),
    "dot": _svg('<circle cx="12" cy="12" r="3" fill="currentColor"/>'),
    "arrow_left": _svg('<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>', size=14),
    "activity": _svg('<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>'),
    "satellite": _svg('<path d="M13 7 9 3 5 7l4 4"/><path d="m17 11 4 4-4 4-4-4"/>'
                      '<path d="m8 12 4 4"/><path d="m16 8-4 4"/>'
                      '<path d="m6 16 1.5 1.5"/><path d="M18 21a3 3 0 0 1-3-3"/>'),
    "clock": _svg('<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'),
}


BASE_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg-0: #07090e;
  --bg-1: #0d1117;
  --bg-2: #131922;
  --bg-3: #1a212d;
  --border: #1f2733;
  --border-strong: #2c3645;
  --text: #e6edf3;
  --text-dim: #9aa5b8;
  --text-soft: #6b7689;
  --accent: #58a6ff;
  --accent-soft: rgba(88,166,255,.10);
  --ok: #3fb950;
  --ok-soft: rgba(63,185,80,.12);
  --warn: #d29922;
  --warn-soft: rgba(210,153,34,.12);
  --err: #f85149;
  --err-soft: rgba(248,81,73,.12);
  --violet: #a371f7;
  --pink: #db61a2;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg-0); color: var(--text); }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  font-size: 14px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
  background:
    radial-gradient(800px 400px at 20% -10%, rgba(88,166,255,.05), transparent 60%),
    radial-gradient(600px 300px at 90% 0%, rgba(163,113,247,.04), transparent 60%),
    var(--bg-0);
}
.mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }

.nav {
  border-bottom: 1px solid var(--border);
  background: rgba(13,17,23,.72);
  backdrop-filter: blur(10px);
  position: sticky; top: 0; z-index: 50;
}
.nav-inner {
  max-width: 1180px; margin: 0 auto;
  padding: 14px 28px;
  display: flex; align-items: center; justify-content: space-between;
}
.brand {
  display: flex; align-items: center; gap: 10px;
  font-weight: 600; font-size: 15px; letter-spacing: -0.01em;
}
.brand-mark {
  width: 28px; height: 28px;
  background: linear-gradient(135deg, #58a6ff 0%, #a371f7 100%);
  border-radius: 7px;
  display: grid; place-items: center;
  color: white;
}
.brand-mark svg { stroke-width: 2.2; }
.brand-sub { color: var(--text-soft); font-size: 12px; font-weight: 400; margin-left: 10px; }
.nav-meta { color: var(--text-soft); font-size: 12px; display: flex; gap: 18px; align-items: center; }

.wrap { max-width: 1180px; margin: 0 auto; padding: 32px 28px 80px; }
.page-title { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 4px; }
.page-sub { color: var(--text-dim); font-size: 13px; margin: 0 0 28px; }

.grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}
.card {
  display: block; text-decoration: none; color: inherit;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  transition: border-color .15s ease, transform .15s ease, background .15s ease;
  position: relative;
  overflow: hidden;
}
.card::before {
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  background: var(--border-strong);
  transition: background .15s ease;
}
.card.ok::before { background: var(--ok); }
.card.err::before { background: var(--err); }
.card.warn::before { background: var(--warn); }
.card:hover {
  border-color: var(--border-strong);
  background: var(--bg-2);
}
.card h3 {
  margin: 0 0 6px;
  font-size: 14px; font-weight: 600; letter-spacing: -0.01em;
  font-family: 'JetBrains Mono', monospace;
}
.card-meta { color: var(--text-soft); font-size: 12px; }
.card-row { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; }
.card-stats { display: flex; gap: 14px; font-size: 12px; color: var(--text-dim); }
.card-stats span { display: inline-flex; align-items: center; gap: 5px; }
.card-stats svg { color: var(--text-soft); }

.chip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 500;
  padding: 3px 8px; border-radius: 5px;
  background: var(--bg-3); color: var(--text-dim);
  border: 1px solid var(--border);
}
.chip.ok { background: var(--ok-soft); color: var(--ok); border-color: rgba(63,185,80,.25); }
.chip.warn { background: var(--warn-soft); color: var(--warn); border-color: rgba(210,153,34,.25); }
.chip.err { background: var(--err-soft); color: var(--err); border-color: rgba(248,81,73,.25); }
.chip svg { width: 12px; height: 12px; }

.empty {
  text-align: center; padding: 80px 20px;
  color: var(--text-soft);
  border: 1px dashed var(--border);
  border-radius: 12px;
  background: var(--bg-1);
}
.empty svg { color: var(--text-soft); width: 32px; height: 32px; margin-bottom: 12px; }
.empty p { margin: 0; font-size: 13px; }
.empty code {
  font-family: 'JetBrains Mono', monospace;
  background: var(--bg-3); padding: 2px 6px; border-radius: 4px;
  font-size: 12px;
}

/* Run detail */
.back {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--text-dim); font-size: 13px; text-decoration: none;
  margin-bottom: 14px;
}
.back:hover { color: var(--text); }
.run-header {
  display: flex; justify-content: space-between; align-items: flex-end;
  margin-bottom: 28px; padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.run-title { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: 'JetBrains Mono', monospace; }
.run-sub { color: var(--text-soft); font-size: 12px; margin-top: 4px; }

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1px;
  background: var(--border);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 28px;
}
.stat { background: var(--bg-1); padding: 18px 20px; }
.stat-label {
  color: var(--text-soft); font-size: 11px;
  text-transform: uppercase; letter-spacing: .08em; font-weight: 500;
  display: inline-flex; align-items: center; gap: 6px;
  margin-bottom: 8px;
}
.stat-label svg { width: 13px; height: 13px; }
.stat-value { font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
.stat-value.mono { font-family: 'JetBrains Mono', monospace; font-weight: 500; }

.section-label {
  color: var(--text-soft); font-size: 11px;
  text-transform: uppercase; letter-spacing: .1em; font-weight: 600;
  margin: 28px 0 12px;
}

.timeline {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-1);
}
.event {
  display: grid; grid-template-columns: 70px 36px 1fr auto;
  align-items: center; gap: 14px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
}
.event:last-child { border-bottom: none; }
.event:hover { background: var(--bg-2); }
.event .t {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px; color: var(--text-soft);
}
.event .ic {
  width: 30px; height: 30px;
  display: grid; place-items: center;
  border-radius: 7px;
  background: var(--bg-3);
  color: var(--text-dim);
}
.event .ic.ok { background: var(--ok-soft); color: var(--ok); }
.event .ic.err { background: var(--err-soft); color: var(--err); }
.event .ic.warn { background: var(--warn-soft); color: var(--warn); }
.event .ic.violet { background: rgba(163,113,247,.12); color: var(--violet); }
.event .ic.pink { background: rgba(219,97,162,.12); color: var(--pink); }
.event .ic.accent { background: var(--accent-soft); color: var(--accent); }
.event .name {
  font-size: 13px; font-weight: 500;
  font-family: 'JetBrains Mono', monospace;
}
.event .detail {
  color: var(--text-soft); font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
}

.plot-card {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-1);
}
.plot-card img { width: 100%; display: block; }

a.link { color: var(--accent); text-decoration: none; }
a.link:hover { text-decoration: underline; }
</style>
"""

LOGO_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 4 6v6c0 5 3.5 9.5 8 10 4.5-.5 8-5 8-10V6z"/></svg>'

INDEX_HTML = (BASE_CSS + """
<nav class="nav"><div class="nav-inner">
  <div class="brand">
    <div class="brand-mark">""" + LOGO_SVG + """</div>
    <span>Kokpit</span>
    <span class="brand-sub">Mission Replay</span>
  </div>
  <div class="nav-meta">
    <span>{{ runs|length }} run{{ '' if runs|length==1 else 's' }}</span>
    <span>·</span>
    <span>Teknofest 2026</span>
  </div>
</div></nav>

<div class="wrap">
  <h1 class="page-title">Mission archive</h1>
  <p class="page-sub">Otonom teslimat görev kayıtları — events, telemetry ve plot.</p>

{% if runs %}
<div class="grid">
  {% for r in runs %}
  <a class="card {{ 'ok' if r.delivered else ('err' if r.abort_reason else 'warn') }}"
     href="/run/{{ r.name }}">
    <h3>{{ r.name }}</h3>
    <div class="card-meta">{{ r.duration_s }}s mission</div>
    <div class="card-row">
      <div class="card-stats">
        <span>""" + ICON["clock"] + """ {{ r.duration_s }}s</span>
        <span>""" + ICON["activity"] + """ {{ r.telemetry_rows }}</span>
      </div>
      {% if r.delivered %}
        <span class="chip ok">""" + ICON["package"] + """ delivered</span>
      {% elif r.abort_reason %}
        <span class="chip err">""" + ICON["octagon_x"] + """ {{ r.abort_reason }}</span>
      {% else %}
        <span class="chip warn">incomplete</span>
      {% endif %}
    </div>
  </a>
  {% endfor %}
</div>
{% else %}
<div class="empty">
  """ + ICON["satellite"] + """
  <p>Henüz görev kaydı yok.</p>
  <p style="margin-top:6px;font-size:12px">Yeni run <code>runs/&lt;ts&gt;/</code> dizininde otomatik görünür.</p>
</div>
{% endif %}
</div>
""")

RUN_HTML = (BASE_CSS + """
<nav class="nav"><div class="nav-inner">
  <div class="brand">
    <div class="brand-mark">""" + LOGO_SVG + """</div>
    <span>Kokpit</span>
    <span class="brand-sub">Mission Replay</span>
  </div>
  <div class="nav-meta"><span>Teknofest 2026</span></div>
</div></nav>

<div class="wrap">
  <a class="back" href="/">""" + ICON["arrow_left"] + """ All runs</a>
  <div class="run-header">
    <div>
      <h1 class="run-title">{{ name }}</h1>
      <div class="run-sub">{{ events|length }} events · {{ tel_rows }} telemetry rows</div>
    </div>
    <div>
      {% if delivered %}<span class="chip ok">""" + ICON["package"] + """ delivered</span>
      {% elif abort_reason %}<span class="chip err">""" + ICON["octagon_x"] + """ {{ abort_reason }}</span>
      {% else %}<span class="chip warn">incomplete</span>{% endif %}
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="stat-label">""" + ICON["clock"] + """ Duration</div>
      <div class="stat-value mono">{{ duration_s }}s</div>
    </div>
    <div class="stat">
      <div class="stat-label">""" + ICON["activity"] + """ Telemetry</div>
      <div class="stat-value mono">{{ tel_rows }}</div>
    </div>
    <div class="stat">
      <div class="stat-label">""" + ICON["satellite"] + """ Events</div>
      <div class="stat-value mono">{{ events|length }}</div>
    </div>
  </div>

  <div class="section-label">Timeline</div>
  <div class="timeline">
    {% for e in events %}
    <div class="event">
      <div class="t">t+{{ '%02d'|format(e.dt // 60) }}:{{ '%02d'|format(e.dt % 60) }}</div>
      <div class="ic {{ e.tone }}">{{ e.icon|safe }}</div>
      <div>
        <div class="name">{{ e.name }}</div>
        {% if e.detail %}<div class="detail">{{ e.detail }}</div>{% endif %}
      </div>
      <div class="t">+{{ e.dt }}s</div>
    </div>
    {% endfor %}
  </div>

  {% if tel_rows > 0 %}
  <div class="section-label">Flight path</div>
  <div class="plot-card" style="padding:0">
    <div id="map" style="height:380px;width:100%;background:var(--bg-2);border-radius:10px"></div>
  </div>

  <div class="section-label">Phase timeline</div>
  <div class="plot-card" style="padding:14px 18px">
    <div id="phases" style="font-family:'JetBrains Mono',monospace;font-size:12px"></div>
  </div>

  <div class="section-label">Telemetry · altitude + battery</div>
  <div class="plot-card"><img src="/run/{{ name }}/plot.png" alt="plot"/></div>

  <div class="section-label">Failsafe events</div>
  <div class="plot-card" id="failsafe-panel" style="padding:14px 18px;color:var(--text-soft);font-size:13px">Yükleniyor…</div>
  {% endif %}
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script>
(async function(){
  const name = {{ name|tojson }};
  // Track / map
  try {
    const r = await fetch(`/run/${name}/track.json`);
    const data = await r.json();
    if (data.points && data.points.length) {
      const pts = data.points.map(p => [p.lat, p.lon]);
      const map = L.map('map', { zoomControl: true, attributionControl: false });
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {
        maxZoom: 19, subdomains: 'abcd'
      }).addTo(map);
      const line = L.polyline(pts, { color: '#58a6ff', weight: 3, opacity: 0.85 }).addTo(map);
      L.circleMarker(pts[0], { radius: 6, color: '#3fb950', fillOpacity: 1 })
        .bindTooltip('start').addTo(map);
      L.circleMarker(pts[pts.length-1], { radius: 6, color: '#d29922', fillOpacity: 1 })
        .bindTooltip('end').addTo(map);
      map.fitBounds(line.getBounds(), { padding: [20, 20] });
    } else {
      document.getElementById('map').innerHTML =
        '<div style="padding:60px 20px;text-align:center;color:var(--text-soft);font-size:13px">Track verisi yok (GPS fix yokken kaydedilen run)</div>';
    }
  } catch(e) { console.error(e); }

  // Phase timeline
  try {
    const r = await fetch(`/run/${name}/phases.json`);
    const data = await r.json();
    const colors = {
      IDLE: '#6b7689', WAIT_PACKET: '#6b7689', PREFLIGHT: '#58a6ff',
      TAKEOFF: '#58a6ff', NAVIGATE: '#a371f7', SEARCH_MARKER: '#a371f7',
      PRECISION_APPROACH: '#db61a2', BIOMETRIC_VERIFY: '#db61a2',
      DROP_PACKAGE: '#3fb950', RETURN_HOME: '#d29922', LANDING: '#d29922',
      DISARM: '#6b7689', MISSION_COMPLETE: '#3fb950', ABORT: '#f85149',
      FAILED: '#f85149', READ_ONLY: '#d29922',
    };
    if (!data.phases.length) {
      document.getElementById('phases').innerHTML =
        '<span style="color:var(--text-soft)">Phase verisi yok</span>';
      return;
    }
    const total = Math.max(1, data.phases[data.phases.length-1].end);
    let html = '<div style="display:flex;height:34px;border-radius:6px;overflow:hidden;border:1px solid var(--border)">';
    data.phases.forEach(p => {
      const w = ((p.end - p.start) / total * 100).toFixed(2);
      const c = colors[p.state] || '#6b7689';
      html += `<div title="${p.state} (${(p.end-p.start).toFixed(0)}s)" style="flex:0 0 ${w}%;background:${c};display:grid;place-items:center;font-size:10px;color:#0d1117;font-weight:600;overflow:hidden;white-space:nowrap;padding:0 4px">${w >= 6 ? p.state : ''}</div>`;
    });
    html += '</div>';
    html += '<div style="display:flex;justify-content:space-between;margin-top:8px;color:var(--text-soft);font-size:11px"><span>0s</span><span>' + total.toFixed(0) + 's</span></div>';
    document.getElementById('phases').innerHTML = html;
  } catch(e) { console.error(e); }

  // Failsafe events
  try {
    const r = await fetch(`/run/${name}/failsafe.json`);
    const data = await r.json();
    const panel = document.getElementById('failsafe-panel');
    if (!data.events.length) {
      panel.innerHTML = '<span style="color:var(--ok)">✓ Bu görevde failsafe tetiklenmedi</span>';
    } else {
      let html = '<div style="display:flex;flex-direction:column;gap:6px">';
      data.events.forEach(e => {
        html += `<div style="display:flex;gap:14px;font-family:'JetBrains Mono',monospace;font-size:12px"><span style="color:var(--err);font-weight:600">⚠ FAILSAFE</span><span>t+${e.t.toFixed(1)}s</span><span style="color:var(--text-soft)">${e.state}</span></div>`;
      });
      html += '</div>';
      panel.innerHTML = html;
    }
  } catch(e) { console.error(e); }
})();
</script>
""")


EVENT_MAP = {
    "start":             ("play", "accent"),
    "takeoff":           ("plane_up", "accent"),
    "cruise":            ("plane", "accent"),
    "marker_locked":     ("crosshair", "violet"),
    "marker_lost":       ("alert", "err"),
    "face_match":        ("user_check", "pink"),
    "face_mismatch":     ("user_x", "err"),
    "package_delivered": ("package", "ok"),
    "rtl_complete":      ("home", "warn"),
    "abort":             ("octagon_x", "err"),
    "land":              ("arrow_down", "warn"),
}


def _summarize_run(d: Path) -> dict:
    info = {"name": d.name, "duration_s": 0, "delivered": False,
            "abort_reason": "", "telemetry_rows": 0}
    ev = d / "events.jsonl"
    if ev.exists():
        first = last = None
        for ln in ev.read_text().splitlines():
            try:
                j = json.loads(ln)
            except Exception:
                continue
            t = j.get("ts") or j.get("timestamp")
            if t is not None:
                if first is None:
                    first = t
                last = t
            if j.get("event") == "package_delivered":
                info["delivered"] = True
            if j.get("event") == "abort":
                info["abort_reason"] = j.get("reason", "abort")
        if first is not None and last is not None:
            info["duration_s"] = max(0, int(last - first))
    tel = d / "telemetry.csv"
    if tel.exists():
        info["telemetry_rows"] = max(0, len(tel.read_text().splitlines()) - 1)
    return info


def _list_runs(runs_dir: Optional[Path] = None) -> list[dict]:
    d = runs_dir or RUNS_DIR
    if not d.exists():
        return []
    return [_summarize_run(p) for p in sorted(d.iterdir())
            if p.is_dir() and p.name != "archive"]


@app.route("/")
def index():
    return render_template_string(INDEX_HTML, runs=_list_runs())


@app.route("/run/<name>")
def run_view(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    summary = _summarize_run(d)
    events = []
    ev_file = d / "events.jsonl"
    first_ts = None
    if ev_file.exists():
        for ln in ev_file.read_text().splitlines():
            try:
                j = json.loads(ln)
            except Exception:
                continue
            t = j.get("ts") or j.get("timestamp") or 0
            if first_ts is None:
                first_ts = t
            ev_name = j.get("event", "?")
            ic_key, tone = EVENT_MAP.get(ev_name, ("dot", ""))
            extras = {k: v for k, v in j.items()
                      if k not in ("ts", "timestamp", "event")}
            detail = " · ".join(f"{k}={v}" for k, v in extras.items())
            events.append({
                "dt": int(t - first_ts),
                "icon": ICON.get(ic_key, ICON["dot"]),
                "tone": tone,
                "name": ev_name,
                "detail": detail,
            })
    tel = d / "telemetry.csv"
    tel_rows = max(0, len(tel.read_text().splitlines()) - 1) if tel.exists() else 0
    return render_template_string(
        RUN_HTML, name=safe, events=events, tel_rows=tel_rows,
        duration_s=summary["duration_s"], delivered=summary["delivered"],
        abort_reason=summary["abort_reason"],
    )


@app.route("/run/<name>/plot.png")
def plot_png(name):
    import io
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    tc = RUNS_DIR / safe / "telemetry.csv"
    if not tc.exists():
        abort(404)
    ts, alt, bat = [], [], []
    with tc.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ts.append(float(row["ts_unix_us"]) / 1e6)
                alt.append(float(row["alt_rel"]))
                bat.append(float(row["battery_v"]))
            except Exception:
                continue
    plt.style.use("dark_background")
    fig, ax1 = plt.subplots(figsize=(11, 4.2), facecolor="#0d1117")
    ax1.set_facecolor("#0d1117")
    ax1.plot(ts, alt, color="#58a6ff", linewidth=2.0, label="altitude")
    ax1.fill_between(ts, alt, alpha=0.10, color="#58a6ff")
    ax1.set_xlabel("time (s)", color="#9aa5b8", fontsize=10)
    ax1.set_ylabel("altitude (m)", color="#58a6ff", fontsize=10)
    ax1.tick_params(colors="#9aa5b8", labelsize=9)
    ax1.grid(True, alpha=0.08, linestyle="-", linewidth=0.5)
    for sp in ax1.spines.values():
        sp.set_color("#1f2733")
    ax2 = ax1.twinx()
    ax2.plot(ts, bat, color="#d29922", linewidth=2.0, label="battery")
    ax2.set_ylabel("battery (V)", color="#d29922", fontsize=10)
    ax2.tick_params(colors="#9aa5b8", labelsize=9)
    for sp in ax2.spines.values():
        sp.set_color("#1f2733")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, facecolor="#0d1117",
                bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype="image/png")


def _read_telemetry(d: Path) -> list[dict]:
    import csv
    tc = d / "telemetry.csv"
    if not tc.exists():
        return []
    rows = []
    with tc.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


@app.route("/run/<name>/track.json")
def run_track(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    pts = []
    for row in _read_telemetry(d):
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
            if abs(lat) < 0.001 and abs(lon) < 0.001:
                continue  # zero-fill row
            pts.append({"lat": lat, "lon": lon,
                        "alt": float(row.get("alt_rel", 0)),
                        "mode": row.get("mode", "")})
        except Exception:
            continue
    return jsonify({"points": pts})


@app.route("/run/<name>/phases.json")
def run_phases(name):
    """mission_state sütununu zaman-aralık dilimlerine indirge."""
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    phases = []
    cur_state = None
    cur_start = None
    first_ts = None
    for row in _read_telemetry(d):
        try:
            ts = float(row["ts_unix_us"]) / 1e6
        except Exception:
            continue
        if first_ts is None:
            first_ts = ts
        st = row.get("mission_state", "") or "?"
        if st != cur_state:
            if cur_state is not None:
                phases.append({"state": cur_state,
                               "start": cur_start - first_ts,
                               "end": ts - first_ts})
            cur_state = st
            cur_start = ts
    if cur_state is not None and cur_start is not None and first_ts is not None:
        # son dilim — telemetry son satır zamanına kadar
        last_ts = float(_read_telemetry(d)[-1]["ts_unix_us"]) / 1e6
        phases.append({"state": cur_state,
                       "start": cur_start - first_ts,
                       "end": last_ts - first_ts})
    return jsonify({"phases": phases})


@app.route("/run/<name>/failsafe.json")
def run_failsafe(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    events = []
    first_ts = None
    prev_active = False
    for row in _read_telemetry(d):
        try:
            ts = float(row["ts_unix_us"]) / 1e6
            active = row.get("failsafe_active", "0") == "1"
        except Exception:
            continue
        if first_ts is None:
            first_ts = ts
        if active and not prev_active:
            events.append({"t": ts - first_ts, "state": row.get("mission_state", "")})
        prev_active = active
    return jsonify({"events": events})


@app.route("/api/runs")
def api_runs():
    return jsonify({"runs": [r["name"] for r in _list_runs()]})


def main():
    app.run(host="127.0.0.1",
            port=int(os.environ.get("KOKPIT_REPLAY_PORT", 5000)))


if __name__ == "__main__":
    sys.exit(main())
