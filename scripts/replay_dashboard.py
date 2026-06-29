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

/* Friendly summary card */
.summary-card {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 18px; align-items: center;
  background: linear-gradient(135deg, rgba(88,166,255,.06) 0%, rgba(163,113,247,.04) 100%);
  border: 1px solid rgba(88,166,255,.25);
  border-radius: 14px;
  padding: 22px 26px;
  margin-bottom: 24px;
}
.summary-icon {
  width: 56px; height: 56px;
  background: var(--bg-2);
  border-radius: 14px;
  display: grid; place-items: center;
  color: var(--accent);
}
.summary-icon svg { width: 28px; height: 28px; }
.summary-title {
  font-size: 11px; color: var(--text-soft);
  text-transform: uppercase; letter-spacing: .12em;
  font-weight: 600; margin-bottom: 6px;
}
.summary-text {
  font-size: 16px; line-height: 1.55;
  color: var(--text); font-weight: 400;
}

/* Two-column layout: main + sticky map sidebar */
.two-col {
  display: grid;
  grid-template-columns: 1fr 420px;
  gap: 24px;
  align-items: start;
}
@media (max-width: 1024px) {
  .two-col { grid-template-columns: 1fr; }
  .col-side .plot-card { position: static !important; }
}
.col-main { min-width: 0; }
.col-side { min-width: 0; }
</style>
"""

LOGO_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 4 6v6c0 5 3.5 9.5 8 10 4.5-.5 8-5 8-10V6z"/></svg>'

COMPARE_HTML = (BASE_CSS + """
<nav class="nav"><div class="nav-inner">
  <div class="brand"><div class="brand-mark">""" + LOGO_SVG + """</div>
    <span>Kokpit</span><span class="brand-sub">Run comparison</span></div>
  <div class="nav-meta"><a class="back" href="/">""" + ICON["arrow_left"] + """ All runs</a></div>
</div></nav>
<div class="wrap">
  <h1 class="page-title">Compare</h1>
  <p class="page-sub mono">{{ a.name }} <span style="color:var(--text-soft)">vs</span> {{ b.name }}</p>
  <div class="stats" style="grid-template-columns:repeat(4,1fr)">
    <div class="stat"><div class="stat-label">Duration A</div><div class="stat-value mono">{{ a.duration_s }}s</div></div>
    <div class="stat"><div class="stat-label">Duration B</div><div class="stat-value mono">{{ b.duration_s }}s</div></div>
    <div class="stat"><div class="stat-label">Telemetry A</div><div class="stat-value mono">{{ a.telemetry_rows }}</div></div>
    <div class="stat"><div class="stat-label">Telemetry B</div><div class="stat-value mono">{{ b.telemetry_rows }}</div></div>
    <div class="stat"><div class="stat-label">Status A</div><div class="stat-value">{% if a.delivered %}<span style="color:var(--ok)">✓ delivered</span>{% elif a.abort_reason %}<span style="color:var(--err)">⚠ {{ a.abort_reason }}</span>{% else %}<span style="color:var(--warn)">—</span>{% endif %}</div></div>
    <div class="stat"><div class="stat-label">Status B</div><div class="stat-value">{% if b.delivered %}<span style="color:var(--ok)">✓ delivered</span>{% elif b.abort_reason %}<span style="color:var(--err)">⚠ {{ b.abort_reason }}</span>{% else %}<span style="color:var(--warn)">—</span>{% endif %}</div></div>
    <div class="stat"><div class="stat-label">Δ Duration</div><div class="stat-value mono">{{ b.duration_s - a.duration_s }}s</div></div>
    <div class="stat"><div class="stat-label">Δ Telemetry</div><div class="stat-value mono">{{ b.telemetry_rows - a.telemetry_rows }}</div></div>
  </div>
  <div class="section-label">Plots</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
    <div class="plot-card"><img src="/run/{{ a.name }}/plot.png" alt="A"/></div>
    <div class="plot-card"><img src="/run/{{ b.name }}/plot.png" alt="B"/></div>
  </div>
  <div class="section-label" style="margin-top:24px">Quick links</div>
  <div style="display:flex;gap:12px">
    <a class="link" href="/run/{{ a.name }}">View {{ a.name }} →</a>
    <a class="link" href="/run/{{ b.name }}">View {{ b.name }} →</a>
  </div>
</div>
""")

INDEX_HTML = (BASE_CSS + """
<nav class="nav"><div class="nav-inner">
  <a href="/" class="brand" style="text-decoration:none;color:inherit">
    <div class="brand-mark">""" + LOGO_SVG + """</div>
    <span>Kokpit</span>
    <span class="brand-sub">Mission Replay</span>
  </a>
  <div class="nav-meta">
    <span>{{ runs|length }} run{{ '' if runs|length==1 else 's' }}</span>
    <span>·</span>
    <span>Teknofest 2026</span>
  </div>
</div></nav>

<div class="wrap">
  <h1 class="page-title">Mission archive</h1>
  <p class="page-sub">Otonom teslimat görev kayıtları — events, telemetry ve plot.</p>

  <!-- Hero stats (top) -->
  <div class="hero-stats">
    <div class="hero-stat">
      <div class="hero-num" id="s-total">—</div>
      <div class="hero-lbl">Toplam görev</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num ok" id="s-deliv">—</div>
      <div class="hero-lbl">Başarılı teslimat</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num err" id="s-abort">—</div>
      <div class="hero-lbl">İptal edilen</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num accent" id="s-rate">—</div>
      <div class="hero-lbl">Başarı oranı</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num" id="s-fly">—</div>
      <div class="hero-lbl">Toplam uçuş</div>
    </div>
  </div>
  <style>
    .hero-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-bottom: 28px;
    }
    .hero-stat {
      background: var(--bg-1);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px 22px;
      transition: border-color .15s ease;
    }
    .hero-stat:hover { border-color: var(--border-strong); }
    .hero-num {
      font-size: 32px; font-weight: 700; letter-spacing: -0.025em;
      font-family: 'JetBrains Mono', monospace;
      line-height: 1.1;
    }
    .hero-num.ok { color: var(--ok); }
    .hero-num.err { color: var(--err); }
    .hero-num.accent { color: var(--accent); }
    .hero-lbl {
      color: var(--text-soft); font-size: 12px;
      margin-top: 6px;
    }
  </style>

  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;align-items:center">
    <input id="search" type="search" placeholder="Search runs…" autocomplete="off"
      style="background:var(--bg-1);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:8px;font-size:13px;min-width:240px;font-family:'JetBrains Mono',monospace"/>
    <div id="filters" style="display:flex;gap:6px">
      <button class="filter-btn active" data-f="all">All</button>
      <button class="filter-btn" data-f="delivered">Delivered</button>
      <button class="filter-btn" data-f="abort">Aborted</button>
      <button class="filter-btn" data-f="incomplete">Incomplete</button>
    </div>
    <div style="margin-left:auto;color:var(--text-soft);font-size:11px"><span id="run-count">{{ runs|length }}</span> runs · live</div>
  </div>
  <style>
    .filter-btn { background:var(--bg-1);border:1px solid var(--border);color:var(--text-dim);padding:6px 12px;border-radius:6px;font-size:12px;cursor:pointer;font-weight:500;font-family:inherit }
    .filter-btn:hover { color:var(--text);border-color:var(--border-strong) }
    .filter-btn.active { background:var(--accent-soft);color:var(--accent);border-color:rgba(88,166,255,.3) }
  </style>

  <div id="runs-grid" class="grid"></div>
  <div id="empty-state" style="display:none" class="empty">
  """ + ICON["satellite"] + """
  <p>Eşleşen kayıt yok.</p>
  </div>

  {% if live_url %}
  <div class="section-label" style="margin-top:36px">Live mission feed</div>
  <div class="plot-card" style="padding:0;overflow:hidden">
    <iframe src="{{ live_url }}" style="width:100%;height:480px;border:0;background:var(--bg-2)"></iframe>
  </div>
  {% endif %}
</div>

<script>
let _filter = 'all', _query = '', _runs = [];
const card = r => {
  const cls = r.delivered ? 'ok' : (r.abort_reason ? 'err' : 'warn');
  const chip = r.delivered
    ? '<span class="chip ok">""" + ICON["package"] + """ delivered</span>'
    : r.abort_reason
    ? `<span class="chip err">""" + ICON["octagon_x"] + """ ${r.abort_reason}</span>`
    : '<span class="chip warn">incomplete</span>';
  return `<a class="card ${cls}" href="/run/${r.name}">
    <h3>${r.name}</h3>
    <div class="card-meta">${r.duration_s}s mission</div>
    <div class="card-row">
      <div class="card-stats">
        <span>""" + ICON["clock"] + """ ${r.duration_s}s</span>
        <span>""" + ICON["activity"] + """ ${r.telemetry_rows}</span>
      </div>${chip}</div></a>`;
};

const match = r => {
  if (_query && !r.name.toLowerCase().includes(_query)) return false;
  if (_filter === 'delivered') return r.delivered;
  if (_filter === 'abort') return !!r.abort_reason;
  if (_filter === 'incomplete') return !r.delivered && !r.abort_reason;
  return true;
};

const render = () => {
  const grid = document.getElementById('runs-grid');
  const filtered = _runs.filter(match);
  grid.innerHTML = filtered.map(card).join('');
  document.getElementById('run-count').textContent = filtered.length;
  document.getElementById('empty-state').style.display = filtered.length ? 'none' : '';
};

document.getElementById('search').addEventListener('input', e => {
  _query = e.target.value.toLowerCase().trim();
  render();
});

document.querySelectorAll('.filter-btn').forEach(b => b.addEventListener('click', e => {
  document.querySelectorAll('.filter-btn').forEach(x => x.classList.remove('active'));
  e.target.classList.add('active');
  _filter = e.target.dataset.f;
  render();
}));

async function refresh() {
  try {
    const r = await fetch('/api/runs');
    const data = await r.json();
    _runs = data.runs || [];
    render();
    const s = await (await fetch('/api/stats')).json();
    document.getElementById('s-total').textContent = s.total_runs;
    document.getElementById('s-deliv').textContent = s.delivered;
    document.getElementById('s-abort').textContent = s.aborted;
    document.getElementById('s-rate').textContent = s.success_rate_pct + '%';
    const m = Math.floor(s.total_flight_s / 60), sec = s.total_flight_s % 60;
    document.getElementById('s-fly').textContent = `${m}m ${sec}s`;
  } catch(e) {}
}
refresh();
setInterval(refresh, 5000);
</script>
""")

RUN_HTML = (BASE_CSS + """
<style>
/* Big status hero */
.hero {
  position: relative;
  border-radius: 16px;
  padding: 32px 36px;
  margin-bottom: 28px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.hero.ok { background: radial-gradient(circle at top right, rgba(63,185,80,.18), transparent 60%), var(--bg-1); border-color: rgba(63,185,80,.3); }
.hero.err { background: radial-gradient(circle at top right, rgba(248,81,73,.18), transparent 60%), var(--bg-1); border-color: rgba(248,81,73,.3); }
.hero.warn { background: radial-gradient(circle at top right, rgba(210,153,34,.18), transparent 60%), var(--bg-1); border-color: rgba(210,153,34,.3); }
.hero-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
.hero-left { flex: 1; min-width: 280px; }
.hero-status {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .14em;
  padding: 6px 12px; border-radius: 20px;
  margin-bottom: 14px;
}
.hero.ok .hero-status { background: rgba(63,185,80,.18); color: var(--ok); }
.hero.err .hero-status { background: rgba(248,81,73,.18); color: var(--err); }
.hero.warn .hero-status { background: rgba(210,153,34,.18); color: var(--warn); }
.hero-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px; color: var(--text-soft);
  margin-bottom: 8px;
}
.hero-headline {
  font-size: 28px; font-weight: 700; letter-spacing: -0.025em;
  line-height: 1.2; margin: 0 0 14px;
  max-width: 720px;
}
.hero-desc {
  font-size: 16px; color: var(--text-dim);
  line-height: 1.6; max-width: 720px;
}
.hero-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--bg-2); border: 1px solid var(--border);
  color: var(--text); text-decoration: none;
  padding: 8px 14px; border-radius: 8px;
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all .15s ease;
}
.btn:hover { border-color: var(--border-strong); background: var(--bg-3); }
.btn svg { width: 14px; height: 14px; }

/* KPI grid */
.kpis {
  display: grid; gap: 14px;
  grid-template-columns: repeat(4, 1fr);
  margin-bottom: 28px;
}
.kpi {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  position: relative;
}
.kpi-icon {
  position: absolute; top: 18px; right: 18px;
  color: var(--text-soft); opacity: .5;
}
.kpi-label {
  font-size: 11px; color: var(--text-soft);
  text-transform: uppercase; letter-spacing: .1em;
  font-weight: 600; margin-bottom: 6px;
}
.kpi-value {
  font-size: 26px; font-weight: 700; letter-spacing: -0.02em;
  font-family: 'JetBrains Mono', monospace;
  line-height: 1.1;
}
.kpi-sub { font-size: 11px; color: var(--text-soft); margin-top: 4px; }

/* Phase stepper */
.stepper {
  display: flex; align-items: center;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 14px;
  overflow-x: auto;
}
.step {
  display: flex; align-items: center;
  flex-shrink: 0; gap: 10px;
  padding-right: 20px; position: relative;
}
.step:not(:last-child)::after {
  content: ""; width: 28px; height: 2px;
  background: var(--border);
  margin-left: 10px;
  display: inline-block;
}
.step.done:not(:last-child)::after { background: var(--ok); }
.step-circle {
  width: 28px; height: 28px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--bg-3); border: 1.5px solid var(--border);
  color: var(--text-soft); flex-shrink: 0;
}
.step.done .step-circle { background: var(--ok); border-color: var(--ok); color: #0d1117; }
.step.current .step-circle { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); animation: pulse 1.8s infinite; }
.step.err .step-circle { background: var(--err-soft); border-color: var(--err); color: var(--err); }
.step-label {
  font-size: 12px; font-weight: 500;
  color: var(--text-soft); white-space: nowrap;
}
.step.done .step-label, .step.current .step-label { color: var(--text); }
.step.err .step-label { color: var(--err); }
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(88,166,255,.4); }
  50%      { box-shadow: 0 0 0 8px rgba(88,166,255,0); }
}

/* Timeline (cleaner cards) */
.tl-card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}
.tl-row {
  display: grid;
  grid-template-columns: 64px 44px 1fr;
  align-items: center; gap: 14px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  transition: background .12s ease;
}
.tl-row:last-child { border-bottom: none; }
.tl-row:hover { background: var(--bg-2); }
.tl-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px; color: var(--text-soft);
  font-weight: 500;
}
.tl-ic {
  width: 36px; height: 36px;
  display: grid; place-items: center;
  border-radius: 9px;
  background: var(--bg-3);
  color: var(--text-dim);
}
.tl-ic svg { width: 18px; height: 18px; }
.tl-ic.ok { background: var(--ok-soft); color: var(--ok); }
.tl-ic.err { background: var(--err-soft); color: var(--err); }
.tl-ic.warn { background: var(--warn-soft); color: var(--warn); }
.tl-ic.violet { background: rgba(163,113,247,.15); color: var(--violet); }
.tl-ic.pink { background: rgba(219,97,162,.15); color: var(--pink); }
.tl-ic.accent { background: var(--accent-soft); color: var(--accent); }
.tl-text { min-width: 0; }
.tl-name { font-size: 14px; font-weight: 500; color: var(--text); margin-bottom: 2px; }
.tl-detail {
  font-size: 12px; color: var(--text-soft);
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
}
.panel-title {
  font-size: 13px; font-weight: 600;
  color: var(--text); margin: 0 0 4px;
}
.panel-hint { font-size: 12px; color: var(--text-soft); margin-bottom: 14px; }

.map-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-1);
  position: sticky; top: 80px;
}
.map-legend {
  padding: 12px 14px; font-size: 12px;
  border-top: 1px solid var(--border);
  display: flex; gap: 16px; flex-wrap: wrap;
  color: var(--text-soft);
}
.map-legend .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }

.two-col { display: grid; grid-template-columns: 1fr 400px; gap: 22px; align-items: start; }
@media (max-width: 1024px) {
  .two-col { grid-template-columns: 1fr; }
  .map-card { position: static !important; }
  .kpis { grid-template-columns: repeat(2, 1fr); }
}
</style>

<nav class="nav"><div class="nav-inner">
  <a href="/" class="brand" style="text-decoration:none;color:inherit">
    <div class="brand-mark">""" + LOGO_SVG + """</div>
    <span>Kokpit</span>
    <span class="brand-sub">Mission Replay</span>
  </a>
  <div class="nav-meta"><span>Teknofest 2026</span></div>
</div></nav>

<div class="wrap">
  <a class="back" href="/">""" + ICON["arrow_left"] + """ Tüm görevler</a>

  <!-- HERO: status + name + headline + summary -->
  {% set tone = 'ok' if delivered else ('err' if abort_reason else 'warn') %}
  <div class="hero {{ tone }}">
    <div class="hero-row">
      <div class="hero-left">
        <div class="hero-status">
          {% if delivered %}""" + ICON["package"] + """ <span>Başarılı teslimat</span>
          {% elif abort_reason %}""" + ICON["octagon_x"] + """ <span>Görev iptal — {{ abort_reason }}</span>
          {% else %}""" + ICON["alert"] + """ <span>Tamamlanamadı</span>{% endif %}
        </div>
        <div class="hero-name">{{ name }}</div>
        <h1 class="hero-headline">
          {% if delivered %}Paket başarıyla teslim edildi.
          {% elif abort_reason %}Görev güvenlik nedeniyle iptal edildi.
          {% else %}Görev tamamlanamadı.{% endif %}
        </h1>
        <p class="hero-desc">{{ human_summary }}</p>
      </div>
      <div class="hero-actions">
        <a href="/run/{{ name }}/download.zip" class="btn">⬇ Verileri indir</a>
        <a href="/run/{{ name }}/report.md" class="btn" target="_blank">📄 Rapor</a>
        <select id="compare-pick" class="btn" style="appearance:none;padding-right:24px">
          <option value="">⇄ Karşılaştır…</option>
        </select>
      </div>
    </div>
  </div>

  <!-- Phase stepper -->
  <div class="stepper" id="stepper">Yükleniyor…</div>

  <!-- KPI cards -->
  <div class="kpis">
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["clock"] + """</div>
      <div class="kpi-label">Süre</div>
      <div class="kpi-value">{{ '%d:%02d'|format(duration_s // 60, duration_s % 60) }}</div>
      <div class="kpi-sub">dakika:saniye</div>
    </div>
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["plane_up"] + """</div>
      <div class="kpi-label">En yüksek irtifa</div>
      <div class="kpi-value">{{ '%.0f'|format(tel_stats.max_alt or 0) }} m</div>
      <div class="kpi-sub">yerden uzaklık</div>
    </div>
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["activity"] + """</div>
      <div class="kpi-label">Olay</div>
      <div class="kpi-value">{{ events|length }}</div>
      <div class="kpi-sub">kaydedilen aşama</div>
    </div>
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["satellite"] + """</div>
      <div class="kpi-label">Batarya harcaması</div>
      <div class="kpi-value">{{ '%.1f'|format(tel_stats.battery_drop or 0) }} V</div>
      <div class="kpi-sub">başlangıçtan sona</div>
    </div>
  </div>

  <!-- 2-column: timeline+plot | map -->
  <div class="two-col">
    <div>
      <div class="section-label">Görev aşamaları</div>
      <div class="panel">
        <div class="panel-hint">Görev her aşamada ne kadar zaman geçirdi:</div>
        <div id="phases"></div>
        <div id="phase-legend" style="margin-top:14px;display:flex;flex-wrap:wrap;gap:10px;font-size:11px;color:var(--text-dim)"></div>
      </div>

      <div class="section-label">Olaylar</div>
      <div class="tl-card">
        {% for e in events %}
        <div class="tl-row">
          <div class="tl-time">{{ '%d:%02d'|format(e.dt // 60, e.dt % 60) }}</div>
          <div class="tl-ic {{ e.tone }}">{{ e.icon|safe }}</div>
          <div class="tl-text">
            <div class="tl-name">{{ e.label }}</div>
            {% if e.detail %}<div class="tl-detail">{{ e.detail }}</div>{% endif %}
          </div>
        </div>
        {% endfor %}
      </div>

      {% if tel_rows > 0 %}
      <div class="section-label">İrtifa ve batarya</div>
      <div class="panel" style="padding:0;overflow:hidden">
        <img src="/run/{{ name }}/plot.png" alt="plot" style="width:100%;display:block"/>
      </div>

      <div class="section-label">Güvenlik uyarıları</div>
      <div class="panel" id="failsafe-panel" style="font-size:13px">Yükleniyor…</div>
      {% endif %}
    </div>

    {% if tel_rows > 0 %}
    <aside>
      <div class="section-label" style="margin-top:0">Uçuş rotası</div>
      <div class="map-card">
        <div id="map" style="height:560px;background:var(--bg-2)"></div>
        <div class="map-legend">
          <span><span class="dot" style="background:#3fb950"></span>Başlangıç</span>
          <span><span class="dot" style="background:#d29922"></span>Bitiş</span>
          <span><span class="dot" style="background:#58a6ff;width:14px;height:2px;border-radius:0"></span>Uçuş yolu</span>
        </div>
      </div>
    </aside>
    {% endif %}
  </div>
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
        '<div style="padding:60px 20px;text-align:center;color:var(--text-soft);font-size:13px">Konum verisi yok (GPS sinyali olmadan kaydedilmiş)</div>';
    }
  } catch(e) { console.error(e); }

  // Phase timeline (friendly Turkish labels)
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
    const labels_tr = {
      IDLE: 'Beklemede', WAIT_PACKET: 'Paket bekleniyor', PREFLIGHT: 'Hazırlık',
      TAKEOFF: 'Kalkış', NAVIGATE: 'Hedefe gidiş', SEARCH_MARKER: 'İşaret aranıyor',
      PRECISION_APPROACH: 'Hassas yaklaşım', BIOMETRIC_VERIFY: 'Yüz doğrulama',
      DROP_PACKAGE: 'Paket bırakma', RETURN_HOME: 'Eve dönüş',
      LANDING: 'İniş', DISARM: 'Motor kapalı',
      MISSION_COMPLETE: 'Tamamlandı', ABORT: 'İptal',
      FAILED: 'Başarısız', READ_ONLY: 'Salt-okunur',
    };
    if (!data.phases.length) {
      document.getElementById('phases').innerHTML =
        '<span style="color:var(--text-soft)">Aşama verisi yok</span>';
      return;
    }
    const total = Math.max(1, data.phases[data.phases.length-1].end);
    let html = '<div style="display:flex;height:36px;border-radius:8px;overflow:hidden;border:1px solid var(--border)">';
    const seen = new Set();
    data.phases.forEach(p => {
      const w = ((p.end - p.start) / total * 100).toFixed(2);
      const c = colors[p.state] || '#6b7689';
      const lbl = labels_tr[p.state] || p.state;
      const dur = (p.end-p.start).toFixed(0);
      seen.add(p.state);
      html += `<div title="${lbl} — ${dur} saniye" style="flex:0 0 ${w}%;background:${c};display:grid;place-items:center;font-size:11px;color:#0d1117;font-weight:600;overflow:hidden;white-space:nowrap;padding:0 6px;cursor:default">${w >= 10 ? lbl : ''}</div>`;
    });
    html += '</div>';
    html += '<div style="display:flex;justify-content:space-between;margin-top:8px;color:var(--text-soft);font-size:11px"><span>0:00</span><span>' + Math.floor(total/60) + ':' + String(Math.floor(total%60)).padStart(2,'0') + '</span></div>';
    document.getElementById('phases').innerHTML = html;
    // Legend
    let legend = '';
    seen.forEach(st => {
      const c = colors[st] || '#6b7689';
      legend += `<span style="display:inline-flex;align-items:center;gap:5px"><span style="display:inline-block;width:10px;height:10px;background:${c};border-radius:2px"></span>${labels_tr[st] || st}</span>`;
    });
    document.getElementById('phase-legend').innerHTML = legend;
  } catch(e) { console.error(e); }

  // Compare picker wiring
  try {
    const r = await fetch('/api/runs');
    const data = await r.json();
    const sel = document.getElementById('compare-pick');
    if (sel) {
      data.runs.filter(x => x.name !== name).forEach(x => {
        const o = document.createElement('option');
        o.value = x.name; o.textContent = x.name;
        sel.appendChild(o);
      });
      sel.addEventListener('change', e => {
        if (e.target.value) location.href = `/compare?a=${name}&b=${encodeURIComponent(e.target.value)}`;
      });
    }
  } catch(e) {}

  // Phase stepper (canonical mission flow)
  try {
    const FLOW = [
      ['WAIT_PACKET', 'Bekleme', '""" + "play" + """'],
      ['TAKEOFF', 'Kalkış', 'plane_up'],
      ['NAVIGATE', 'Hedefe gidiş', 'plane'],
      ['SEARCH_MARKER', 'İşaret', 'crosshair'],
      ['PRECISION_APPROACH', 'Yaklaşım', 'arrow_down'],
      ['BIOMETRIC_VERIFY', 'Yüz', 'user_check'],
      ['DROP_PACKAGE', 'Teslim', 'package'],
      ['RETURN_HOME', 'Dönüş', 'home'],
    ];
    const r = await fetch(`/run/${name}/phases.json`);
    const data = await r.json();
    const visited = new Set(data.phases.map(p => p.state));
    const aborted = visited.has('ABORT') || visited.has('FAILED');
    const current = data.phases.length ? data.phases[data.phases.length - 1].state : null;
    const step = document.getElementById('stepper');
    step.innerHTML = '';
    FLOW.forEach(([st, lbl, ic]) => {
      let cls = '';
      if (visited.has(st)) cls = 'done';
      if (st === current && !aborted) cls = 'current';
      if (aborted && current === st) cls = 'err';
      const html = `<div class="step ${cls}">
        <div class="step-circle">${cls==='done' ? '✓' : (cls==='err' ? '✕' : '·')}</div>
        <div class="step-label">${lbl}</div>
      </div>`;
      step.insertAdjacentHTML('beforeend', html);
    });
  } catch(e) { document.getElementById('stepper').textContent = 'Aşama verisi yüklenemedi'; }

  // Failsafe events (TR)
  try {
    const r = await fetch(`/run/${name}/failsafe.json`);
    const data = await r.json();
    const panel = document.getElementById('failsafe-panel');
    if (!data.events.length) {
      panel.innerHTML = '<div style="display:flex;align-items:center;gap:10px;color:var(--ok)"><span style="display:inline-block;width:8px;height:8px;background:var(--ok);border-radius:50%"></span>Bu görevde güvenlik uyarısı tetiklenmedi — her şey yolundaydı.</div>';
    } else {
      let html = '<div style="display:flex;flex-direction:column;gap:8px">';
      data.events.forEach(e => {
        const t = `${Math.floor(e.t/60)}:${String(Math.floor(e.t%60)).padStart(2,'0')}`;
        html += `<div style="display:flex;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="color:var(--err);font-weight:600;font-size:12px">⚠ UYARI</span><span style="font-family:'JetBrains Mono',monospace;color:var(--text-soft);font-size:12px">${t}</span><span style="color:var(--text);font-size:13px">Aşama: ${e.state}</span></div>`;
      });
      html += '</div>';
      panel.innerHTML = html;
    }
  } catch(e) { console.error(e); }
})();
</script>
""")


EVENT_MAP = {
    "start":             ("play", "accent", "Görev başladı"),
    "takeoff":           ("plane_up", "accent", "Drone havalandı"),
    "cruise":            ("plane", "accent", "Hedefe gidiyor"),
    "marker_locked":     ("crosshair", "violet", "Hedef işaret bulundu"),
    "marker_lost":       ("alert", "err", "Hedef işaret kaybedildi"),
    "face_match":        ("user_check", "pink", "Alıcı yüzü tanındı"),
    "face_mismatch":     ("user_x", "err", "Yüz eşleşmedi"),
    "package_delivered": ("package", "ok", "Paket teslim edildi"),
    "rtl_complete":      ("home", "warn", "Eve döndü"),
    "abort":             ("octagon_x", "err", "Görev iptal edildi"),
    "land":              ("arrow_down", "warn", "İniş yapıyor"),
    "phase":             ("dot", "", "Aşama değişti"),
    "mission_end":       ("home", "warn", "Görev tamamlandı"),
}


def _human_summary(name: str, events: list, duration_s: int,
                   delivered: bool, abort_reason: str,
                   tel_stats: dict) -> str:
    """Kısa, çocuk-anlayışlı Türkçe görev özeti üret."""
    parts = []
    if duration_s > 0:
        m, s = divmod(duration_s, 60)
        if m > 0:
            parts.append(f"Görev {m} dakika {s} saniye sürdü.")
        else:
            parts.append(f"Görev {s} saniye sürdü.")
    max_alt = tel_stats.get("max_alt")
    if max_alt and max_alt > 1:
        parts.append(f"Drone en fazla {max_alt:.0f} metre yüksekliğe çıktı.")
    if any(e.get("event") == "marker_locked" for e in events):
        parts.append("Yer işaretini buldu.")
    face = next((e for e in events if e.get("event") == "face_match"), None)
    if face:
        conf = face.get("confidence")
        if conf is not None:
            parts.append(f"Alıcının yüzünü %{float(conf)*100:.0f} eşleşme ile tanıdı.")
        else:
            parts.append("Alıcının yüzünü tanıdı.")
    if delivered:
        parts.append("Paketi başarıyla teslim etti.")
    elif abort_reason:
        reasons_tr = {
            "BATTERY_LOW": "batarya zayıf olduğu için",
            "LINK_LOST": "iletişim koptuğu için",
            "GPS_LOST": "GPS sinyali kaybolduğu için",
            "MARKER_LOST": "hedef işaretini bulamadığı için",
            "FACE_MISMATCH": "yüz eşleşmediği için",
            "Yer istasyonu ABORT": "yer istasyonu durdurduğu için",
        }
        why = reasons_tr.get(abort_reason, abort_reason)
        parts.append(f"Görev {why} iptal edildi.")
    else:
        parts.append("Görev tamamlanamadı.")
    if any(e.get("event") == "rtl_complete" for e in events) or \
       any(e.get("event") == "mission_end" for e in events):
        parts.append("Drone üsse geri döndü.")
    bat_drop = tel_stats.get("battery_drop")
    if bat_drop and bat_drop > 0.05:
        parts.append(f"Bataryanın {bat_drop:.1f} voltu harcandı.")
    if not parts:
        return "Bu görev hakkında özet üretilemedi."
    return " ".join(parts)


def _telemetry_stats(d: Path) -> dict:
    """Min/max altitude + battery harcaması özeti."""
    import csv
    tel = d / "telemetry.csv"
    if not tel.exists():
        return {}
    alts, bats = [], []
    with tel.open() as f:
        for row in csv.DictReader(f):
            try:
                alts.append(float(row["alt_rel"]))
                bats.append(float(row["battery_v"]))
            except Exception:
                continue
    out = {}
    if alts:
        out["max_alt"] = max(alts)
        out["min_alt"] = min(alts)
    if bats:
        out["battery_start"] = bats[0]
        out["battery_end"] = bats[-1]
        out["battery_drop"] = bats[0] - bats[-1]
    return out


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
    live_url = os.environ.get("KOKPIT_LIVE_URL", "")
    return render_template_string(INDEX_HTML, runs=_list_runs(), live_url=live_url)


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
    raw_events = []
    ev_file = d / "events.jsonl"
    first_ts = None
    if ev_file.exists():
        for ln in ev_file.read_text().splitlines():
            try:
                j = json.loads(ln)
            except Exception:
                continue
            raw_events.append(j)
            t = j.get("ts") or j.get("timestamp") or 0
            if first_ts is None:
                first_ts = t
            ev_name = j.get("event", "?")
            ic_key, tone, label_tr = EVENT_MAP.get(
                ev_name, ("dot", "", ev_name))
            extras = {k: v for k, v in j.items()
                      if k not in ("ts", "timestamp", "event")}
            # phase event: state field önemli
            if ev_name == "phase":
                detail = extras.get("state", "")
                label_tr = f"Aşama: {extras.get('state', '')}"
            else:
                detail = " · ".join(f"{k}={v}" for k, v in extras.items())
            events.append({
                "dt": int(t - first_ts),
                "icon": ICON.get(ic_key, ICON["dot"]),
                "tone": tone,
                "label": label_tr,
                "name": ev_name,
                "detail": detail,
            })
    tel = d / "telemetry.csv"
    tel_rows = max(0, len(tel.read_text().splitlines()) - 1) if tel.exists() else 0
    tel_stats = _telemetry_stats(d)
    human = _human_summary(safe, raw_events, summary["duration_s"],
                           summary["delivered"], summary["abort_reason"],
                           tel_stats)
    return render_template_string(
        RUN_HTML, name=safe, events=events, tel_rows=tel_rows,
        duration_s=summary["duration_s"], delivered=summary["delivered"],
        abort_reason=summary["abort_reason"],
        human_summary=human, tel_stats=tel_stats,
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
    return jsonify({"runs": _list_runs()})


@app.route("/api/stats")
def api_stats():
    runs = _list_runs()
    delivered = sum(1 for r in runs if r["delivered"])
    aborted = sum(1 for r in runs if r["abort_reason"])
    total_s = sum(r["duration_s"] for r in runs)
    rate = (100.0 * delivered / len(runs)) if runs else 0.0
    return jsonify({
        "total_runs": len(runs),
        "delivered": delivered,
        "aborted": aborted,
        "total_flight_s": total_s,
        "success_rate_pct": round(rate, 1),
    })


@app.route("/run/<name>/report.md")
def run_report_md(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_report import build_report_md
    from flask import Response
    return Response(build_report_md(d), mimetype="text/markdown")


@app.route("/run/<name>/track.tlog")
def run_tlog(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    tel = d / "telemetry.csv"
    if not tel.exists():
        abort(404)
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from csv_to_tlog import csv_to_tlog
        out = d / "track.tlog"
        csv_to_tlog(tel, out)
        from flask import send_file
        return send_file(out, mimetype="application/octet-stream",
                         as_attachment=True, download_name=f"{safe}.tlog")
    except ImportError:
        abort(503)


@app.route("/run/<name>/download.zip")
def run_download(name):
    import io
    import zipfile
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fname in ("events.jsonl", "telemetry.csv"):
            p = d / fname
            if p.exists():
                z.writestr(f"{safe}/{fname}", p.read_bytes())
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype="application/zip", headers={
        "Content-Disposition": f"attachment; filename={safe}.zip",
    })


@app.route("/compare")
def compare():
    from flask import request as freq
    a = freq.args.get("a", "")
    b = freq.args.get("b", "")
    sa = "".join(c for c in a if c.isalnum() or c in "-_.")
    sb = "".join(c for c in b if c.isalnum() or c in "-_.")
    if not sa or not sb or sa != a or sb != b:
        abort(400)
    da = RUNS_DIR / sa
    db = RUNS_DIR / sb
    if not da.exists() or not db.exists():
        abort(404)
    summary_a = _summarize_run(da)
    summary_b = _summarize_run(db)
    return render_template_string(COMPARE_HTML, a=summary_a, b=summary_b)


@app.route("/run/<name>/events.json")
def run_events_json(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    ev = RUNS_DIR / safe / "events.jsonl"
    if not ev.exists():
        return jsonify({"events": []})
    out = []
    for ln in ev.read_text().splitlines():
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return jsonify({"events": out})


def main():
    app.run(host="127.0.0.1",
            port=int(os.environ.get("KOKPIT_REPLAY_PORT", 5000)))


if __name__ == "__main__":
    sys.exit(main())
