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
    "file_text": _svg(
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/>'
        '<line x1="8" y1="13" x2="16" y2="13"/>'
        '<line x1="8" y1="17" x2="13" y2="17"/>'),
    "download": _svg(
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" y1="15" x2="12" y2="3"/>'),
    "compare": _svg(
        '<path d="m17 3 4 4-4 4"/><path d="M3 7h18"/>'
        '<path d="m7 21-4-4 4-4"/><path d="M21 17H3"/>'),
    "check_circle": _svg(
        '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
        '<polyline points="22 4 12 14.01 9 11.01"/>'),
    "alert_triangle": _svg(
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'),
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
.card-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.card-head .when {
  font-size: 11px; color: var(--text-soft);
}
.card h3 {
  margin: 0 0 12px;
  font-size: 13px; font-weight: 600; letter-spacing: -0.01em;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text);
  word-break: break-all;
}
.card-headline {
  font-size: 14px; font-weight: 500; color: var(--text);
  margin-bottom: 12px; line-height: 1.4;
}
.card-mini-stepper {
  display: flex; gap: 4px; margin-bottom: 14px;
}
.card-mini-stepper .ms {
  flex: 1; height: 3px; border-radius: 2px;
  background: var(--bg-3);
}
.card-mini-stepper .ms.done { background: var(--ok); }
.card-mini-stepper .ms.err { background: var(--err); }
.card-kpis {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 8px; margin-bottom: 12px;
}
.card-kpi {
  display: flex; flex-direction: column; gap: 2px;
}
.card-kpi-label {
  font-size: 10px; color: var(--text-soft);
  text-transform: uppercase; letter-spacing: .08em;
  font-weight: 600;
}
.card-kpi-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px; font-weight: 600; color: var(--text);
}
.card-foot {
  display: flex; justify-content: space-between; align-items: center;
  padding-top: 10px; border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-soft);
}
.card-foot .recipient {
  display: inline-flex; align-items: center; gap: 5px;
}
.card-foot svg { width: 12px; height: 12px; }

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
    <span class="nav-chip">""" + ICON["activity"] + """<span id="nav-count">{{ runs|length }}</span> {{ i18n.runs_word }}</span>
    <span class="nav-chip live"><span class="live-dot"></span>{{ i18n.live }}</span>
    <div class="lang-switch">
      <a href="?lang=tr" class="{{ 'active' if lang == 'tr' else '' }}">TR</a>
      <a href="?lang=en" class="{{ 'active' if lang == 'en' else '' }}">EN</a>
    </div>
    <span class="nav-brand-chip">Teknofest 2026</span>
  </div>
</div></nav>

<div class="wrap">
  <h1 class="page-title">{{ i18n.title }}</h1>
  <p class="page-sub">{{ i18n.sub }}</p>

  <!-- Hero stats (top) -->
  <div class="hero-stats">
    <div class="hero-stat">
      <div class="hero-num" id="s-total">—</div>
      <div class="hero-lbl">{{ i18n.total_runs }}</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num ok" id="s-deliv">—</div>
      <div class="hero-lbl">{{ i18n.delivered }}</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num err" id="s-abort">—</div>
      <div class="hero-lbl">{{ i18n.aborted }}</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num accent" id="s-rate">—</div>
      <div class="hero-lbl">{{ i18n.success_rate }}</div>
    </div>
    <div class="hero-stat">
      <div class="hero-num" id="s-fly">—</div>
      <div class="hero-lbl">{{ i18n.total_flight }}</div>
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
    <input id="search" type="search" placeholder="{{ i18n.search }}" autocomplete="off"
      style="background:var(--bg-1);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:8px;font-size:13px;min-width:240px;font-family:'JetBrains Mono',monospace"/>
    <div id="filters" style="display:flex;gap:6px">
      <button class="filter-btn active" data-f="all">{{ i18n.all }}</button>
      <button class="filter-btn" data-f="delivered">{{ i18n.f_deliv }}</button>
      <button class="filter-btn" data-f="abort">{{ i18n.f_abort }}</button>
      <button class="filter-btn" data-f="incomplete">{{ i18n.f_inc }}</button>
    </div>
    <div style="margin-left:auto;color:var(--text-soft);font-size:11px"><span id="run-count">{{ runs|length }}</span> {{ i18n.runs_word }}</div>
  </div>
  <style>
    .filter-btn { background:var(--bg-1);border:1px solid var(--border);color:var(--text-dim);padding:6px 12px;border-radius:6px;font-size:12px;cursor:pointer;font-weight:500;font-family:inherit }
    .filter-btn:hover { color:var(--text);border-color:var(--border-strong) }
    .filter-btn.active { background:var(--accent-soft);color:var(--accent);border-color:rgba(88,166,255,.3) }
  </style>

  <div id="runs-grid" class="grid"></div>
  <div id="empty-state" style="display:none" class="empty">
  """ + ICON["satellite"] + """
  <p>{{ i18n.empty }}</p>
  </div>

  {% if live_url %}
  <div class="section-label" style="margin-top:36px">{{ i18n.live_section }}</div>
  <div class="plot-card" style="padding:0;overflow:hidden">
    <iframe src="{{ live_url }}" style="width:100%;height:480px;border:0;background:var(--bg-2)"></iframe>
  </div>
  {% endif %}
</div>

<script>
const LANG = {{ lang|tojson }};
const T = {
  delivered: LANG === 'en' ? 'Delivered' : 'Teslim edildi',
  incomplete: LANG === 'en' ? 'Incomplete' : 'Tamamlanmadı',
  mission: LANG === 'en' ? 'mission' : 'görev',
  duration: LANG === 'en' ? 'Duration' : 'Süre',
  max_alt: LANG === 'en' ? 'Max alt' : 'Max irtifa',
  battery: LANG === 'en' ? 'Battery' : 'Batarya',
  recipient: LANG === 'en' ? 'recipient' : 'alıcı',
  head_ok: LANG === 'en' ? 'Package delivered successfully' : 'Paket başarıyla teslim edildi',
  head_inc: LANG === 'en' ? 'Mission did not complete' : 'Görev tamamlanmadı',
  ago_now: LANG === 'en' ? 'just now' : 'az önce',
  ago_min: LANG === 'en' ? 'min ago' : 'dk önce',
  ago_hr: LANG === 'en' ? 'hr ago' : 'sa önce',
  ago_day: LANG === 'en' ? 'days ago' : 'gün önce',
};
const ABORT_TR = {
  BATTERY_LOW: LANG === 'en' ? 'Battery low' : 'Batarya zayıf',
  LINK_LOST: LANG === 'en' ? 'Link lost' : 'İletişim koptu',
  GPS_LOST: LANG === 'en' ? 'GPS lost' : 'GPS kayboldu',
  MARKER_LOST: LANG === 'en' ? 'Marker lost' : 'İşaret kayboldu',
  FACE_MISMATCH: LANG === 'en' ? 'Face mismatch' : 'Yüz eşleşmedi',
};
const ABORT_HEAD = {
  BATTERY_LOW: LANG === 'en' ? 'Aborted due to low battery' : 'Batarya zayıfladığı için iptal',
  LINK_LOST: LANG === 'en' ? 'Aborted due to lost link' : 'İletişim koptuğu için iptal',
  GPS_LOST: LANG === 'en' ? 'Aborted due to lost GPS' : 'GPS kaybolduğu için iptal',
  MARKER_LOST: LANG === 'en' ? 'Aborted: marker lost' : 'İşaret bulunamadığı için iptal',
  FACE_MISMATCH: LANG === 'en' ? 'Aborted: face did not match' : 'Yüz eşleşmediği için iptal',
};
function relTime(ts) {
  if (!ts) return '';
  const diff = (Date.now() / 1000) - ts;
  if (diff < 60) return T.ago_now;
  if (diff < 3600) return `${Math.floor(diff / 60)} ${T.ago_min}`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ${T.ago_hr}`;
  return `${Math.floor(diff / 86400)} ${T.ago_day}`;
}
function fmtDur(s) {
  const m = Math.floor(s / 60), sec = s % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}
let _filter = 'all', _query = '', _runs = [];
const FLOW = ['marker_locked', 'face_matched', 'delivered', 'rtl_done'];
const card = r => {
  const cls = r.delivered ? 'ok' : (r.abort_reason ? 'err' : 'warn');
  const chip = r.delivered
    ? `<span class="chip ok">""" + ICON["package"] + """ ${T.delivered}</span>`
    : r.abort_reason
    ? `<span class="chip err">""" + ICON["octagon_x"] + """ ${ABORT_TR[r.abort_reason] || r.abort_reason}</span>`
    : `<span class="chip warn">${T.incomplete}</span>`;
  const headline = r.delivered ? T.head_ok :
    (r.abort_reason ? (ABORT_HEAD[r.abort_reason] || r.abort_reason) : T.head_inc);
  // mini progress: 4 steps (marker / face / delivered / rtl)
  const steps = FLOW.map(k => {
    if (r[k]) return '<div class="ms done"></div>';
    if (r.abort_reason) return '<div class="ms err"></div>';
    return '<div class="ms"></div>';
  }).join('');
  // foot
  const footLeft = r.delivered && r.recipient_id != null
    ? `""" + ICON["user_check"] + """ ${T.recipient} #${r.recipient_id}`
    : (r.abort_reason ? `""" + ICON["alert"] + """ ${r.abort_reason}` : '');
  return `<a class="card ${cls}" href="/run/${r.name}?lang=${LANG}">
    <div class="card-head">${chip}<span class="when">${relTime(r.ts)}</span></div>
    <div class="card-headline">${headline}</div>
    <div class="card-mini-stepper">${steps}</div>
    <div class="card-kpis">
      <div class="card-kpi"><div class="card-kpi-label">${T.duration}</div><div class="card-kpi-value">${fmtDur(r.duration_s)}</div></div>
      <div class="card-kpi"><div class="card-kpi-label">${T.max_alt}</div><div class="card-kpi-value">${(r.max_alt||0).toFixed(0)}m</div></div>
      <div class="card-kpi"><div class="card-kpi-label">${T.battery}</div><div class="card-kpi-value">${(r.battery_drop||0).toFixed(1)}V</div></div>
    </div>
    <h3>${r.name}</h3>
    <div class="card-foot">
      <span class="recipient">${footLeft}</span>
    </div>
  </a>`;
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
    const nc = document.getElementById('nav-count'); if (nc) nc.textContent = s.total_runs;
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

/* Phase stepper (fit width, no scroll) */
.stepper {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 4px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 14px;
}
.step {
  display: flex; flex-direction: column;
  align-items: center; gap: 8px;
  position: relative; min-width: 0;
}
.step:not(:last-child)::after {
  content: ""; position: absolute;
  top: 16px; left: calc(50% + 18px);
  right: calc(-50% + 18px);
  height: 2px; background: var(--border);
}
.step.done:not(:last-child)::after { background: var(--ok); }
.step-circle {
  width: 32px; height: 32px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--bg-3); border: 1.5px solid var(--border);
  color: var(--text-soft); position: relative; z-index: 1;
  font-size: 14px; font-weight: 700;
}
.step.done .step-circle { background: var(--ok); border-color: var(--ok); color: #0d1117; }
.step.current .step-circle { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); animation: pulse 1.8s infinite; }
.step.err .step-circle { background: var(--err-soft); border-color: var(--err); color: var(--err); }
.step-label {
  font-size: 11px; font-weight: 500;
  color: var(--text-soft);
  text-align: center; line-height: 1.2;
  max-width: 100%;
  overflow: hidden; text-overflow: ellipsis;
}
.step.done .step-label, .step.current .step-label { color: var(--text); font-weight: 600; }
.step.err .step-label { color: var(--err); font-weight: 600; }
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(88,166,255,.4); }
  50%      { box-shadow: 0 0 0 8px rgba(88,166,255,0); }
}
@media (max-width: 700px) {
  .stepper { grid-template-columns: repeat(4, 1fr); row-gap: 16px; }
  .step:nth-child(4)::after { display: none; }
}

/* Lang switcher (segmented control) */
.lang-switch {
  display: inline-flex; background: var(--bg-2);
  border: 1px solid var(--border); border-radius: 7px;
  padding: 2px; gap: 2px;
}
.lang-switch a, .lang-switch a:visited, .lang-switch a:hover, .lang-switch a:active {
  text-decoration: none !important;
}
.lang-switch a {
  padding: 4px 12px; font-size: 11px; font-weight: 700;
  letter-spacing: .05em;
  color: var(--text-soft);
  border-radius: 5px;
  transition: all .12s ease;
  font-family: 'Inter', sans-serif;
}
.lang-switch a.active {
  background: var(--accent);
  color: #0d1117;
  box-shadow: 0 1px 2px rgba(88,166,255,.3);
}
.lang-switch a:hover:not(.active) { color: var(--text); background: var(--bg-3); }

/* Nav meta chips */
.nav-meta {
  display: flex; gap: 10px; align-items: center;
  font-size: 12px;
}
.nav-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 7px;
  background: var(--bg-2); border: 1px solid var(--border);
  color: var(--text-dim); font-weight: 500;
}
.nav-chip svg { width: 12px; height: 12px; color: var(--text-soft); }
.nav-chip.live {
  background: rgba(63,185,80,.08);
  border-color: rgba(63,185,80,.25);
  color: var(--ok);
}
.nav-chip.live .live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--ok); position: relative;
}
.nav-chip.live .live-dot::after {
  content: ""; position: absolute; inset: -3px;
  border-radius: 50%; background: var(--ok);
  opacity: .35; animation: livepulse 1.8s infinite;
}
@keyframes livepulse {
  0%   { transform: scale(0.6); opacity: .5; }
  100% { transform: scale(2.2); opacity: 0; }
}
.nav-brand-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 7px;
  background: linear-gradient(135deg, rgba(88,166,255,.10), rgba(163,113,247,.10));
  border: 1px solid rgba(88,166,255,.20);
  color: var(--text); font-weight: 600;
  font-size: 11px; letter-spacing: .04em;
}

/* Map playback */
.map-controls {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg-2);
}
.play-btn {
  width: 32px; height: 32px;
  border-radius: 50%; border: 0;
  background: var(--accent); color: #0d1117;
  cursor: pointer; display: grid; place-items: center;
  transition: transform .12s;
}
.play-btn:hover { transform: scale(1.08); }
.play-btn svg { width: 14px; height: 14px; stroke-width: 2.5; }
.scrub {
  flex: 1; min-width: 0;
  -webkit-appearance: none; appearance: none;
  height: 4px; background: var(--bg-3);
  border-radius: 2px; outline: none;
}
.scrub::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); cursor: pointer;
}
.scrub::-moz-range-thumb {
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent); cursor: pointer; border: 0;
}
.scrub-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px; color: var(--text-soft);
  min-width: 64px; text-align: right;
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
  <div class="nav-meta">
    <div class="lang-switch">
      <a href="?lang=tr" class="{{ 'active' if lang == 'tr' else '' }}">TR</a>
      <a href="?lang=en" class="{{ 'active' if lang == 'en' else '' }}">EN</a>
    </div>
    <span class="nav-brand-chip">Teknofest 2026</span>
  </div>
</div></nav>

<div class="wrap">
  <a class="back" href="/">""" + ICON["arrow_left"] + """ {{ i18n.back }}</a>

  <!-- HERO: status + name + headline + summary -->
  {% set tone = 'ok' if delivered else ('err' if abort_reason else 'warn') %}
  <div class="hero {{ tone }}">
    <div class="hero-row">
      <div class="hero-left">
        <div class="hero-status">
          {% if delivered %}""" + ICON["package"] + """ <span>{{ i18n.delivered }}</span>
          {% elif abort_reason %}""" + ICON["octagon_x"] + """ <span>{{ i18n.abort }} — {{ abort_reason }}</span>
          {% else %}""" + ICON["alert"] + """ <span>{{ i18n.incomplete }}</span>{% endif %}
        </div>
        <div class="hero-name">{{ name }}</div>
        <h1 class="hero-headline">
          {% if delivered %}{{ i18n.headline_ok }}
          {% elif abort_reason %}{{ i18n.headline_err }}
          {% else %}{{ i18n.headline_warn }}{% endif %}
        </h1>
        <p class="hero-desc">{{ human_summary }}</p>
      </div>
      <div class="hero-actions">
        <a href="/run/{{ name }}/download.zip" class="btn">""" + ICON["download"] + """ {{ i18n.download }}</a>
        <a href="/run/{{ name }}/report.html?lang={{ lang }}" class="btn" target="_blank">""" + ICON["file_text"] + """ {{ i18n.report }}</a>
        <div style="position:relative">
          <span style="position:absolute;left:10px;top:50%;transform:translateY(-50%);pointer-events:none;color:var(--text-soft)">""" + ICON["compare"] + """</span>
          <select id="compare-pick" class="btn" style="appearance:none;padding-left:34px;padding-right:24px">
            <option value="">{{ i18n.compare }}</option>
          </select>
        </div>
      </div>
    </div>
  </div>

  <!-- Phase stepper (fit, no scroll) -->
  <div class="stepper" id="stepper">…</div>
  <script>window.MISSION_FLOW = {{ i18n.stepper|tojson }};</script>

  <!-- KPI cards -->
  <div class="kpis">
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["clock"] + """</div>
      <div class="kpi-label">{{ i18n.duration }}</div>
      <div class="kpi-value">{{ '%d:%02d'|format(duration_s // 60, duration_s % 60) }}</div>
      <div class="kpi-sub">{{ i18n.duration_sub }}</div>
    </div>
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["plane_up"] + """</div>
      <div class="kpi-label">{{ i18n.max_alt }}</div>
      <div class="kpi-value">{{ '%.0f'|format(tel_stats.max_alt or 0) }} m</div>
      <div class="kpi-sub">{{ i18n.max_alt_sub }}</div>
    </div>
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["activity"] + """</div>
      <div class="kpi-label">{{ i18n.events_lbl }}</div>
      <div class="kpi-value">{{ events|length }}</div>
      <div class="kpi-sub">{{ i18n.events_sub }}</div>
    </div>
    <div class="kpi">
      <div class="kpi-icon">""" + ICON["satellite"] + """</div>
      <div class="kpi-label">{{ i18n.battery }}</div>
      <div class="kpi-value">{{ '%.1f'|format(tel_stats.battery_drop or 0) }} V</div>
      <div class="kpi-sub">{{ i18n.battery_sub }}</div>
    </div>
  </div>

  <!-- 2-column: timeline+plot | map -->
  <div class="two-col">
    <div>
      <div class="section-label">{{ i18n.phases_title }}</div>
      <div class="panel">
        <div class="panel-hint">{{ i18n.phases_hint }}</div>
        <div id="phases"></div>
        <div id="phase-legend" style="margin-top:14px;display:flex;flex-wrap:wrap;gap:10px;font-size:11px;color:var(--text-dim)"></div>
      </div>

      <div class="section-label">{{ i18n.events_title }}</div>
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
      <div class="section-label">{{ i18n.plot_title }}</div>
      <div class="panel" style="padding:0;overflow:hidden">
        <img src="/run/{{ name }}/plot.png?lang={{ lang }}" alt="plot" style="width:100%;display:block"/>
      </div>

      <div class="section-label">{{ i18n.safety_title }}</div>
      <div class="panel" id="failsafe-panel" data-clear="{{ i18n.safety_clear }}" style="font-size:13px">…</div>
      {% endif %}
    </div>

    {% if tel_rows > 0 %}
    <aside>
      <div class="section-label" style="margin-top:0">{{ i18n.route_title }}</div>
      <div class="map-card">
        <div id="map" style="height:520px;background:var(--bg-2)"></div>
        <div class="map-controls">
          <button class="play-btn" id="play-btn" title="{{ i18n.playback }}">""" + ICON["play"] + """</button>
          <input type="range" class="scrub" id="scrub" min="0" max="100" value="0"/>
          <span class="scrub-time" id="scrub-time">0:00 / 0:00</span>
        </div>
        <div class="map-legend">
          <span><span class="dot" style="background:#3fb950"></span>{{ i18n.legend_start }}</span>
          <span><span class="dot" style="background:#d29922"></span>{{ i18n.legend_end }}</span>
          <span><span class="dot" style="background:#58a6ff;width:14px;height:2px;border-radius:0"></span>{{ i18n.legend_path }}</span>
        </div>
      </div>
    </aside>
    {% endif %}
  </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin=""/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script>
const LANG = {{ lang|tojson }};
(async function(){
  const name = {{ name|tojson }};
  // Track / map with playback
  try {
    const r = await fetch(`/run/${name}/track.json`);
    const data = await r.json();
    const mapEl = document.getElementById('map');
    if (!data.points || !data.points.length) {
      mapEl.innerHTML = '<div style="padding:60px 20px;text-align:center;color:var(--text-soft);font-size:13px">' +
        (LANG === 'en' ? 'No GPS track for this mission.' : 'Konum verisi yok (GPS sinyali olmadan kaydedilmiş).') +
        '</div>';
    } else {
      const pts = data.points.map(p => [p.lat, p.lon]);
      const map = L.map('map', { zoomControl: true, attributionControl: false });
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {
        maxZoom: 19, subdomains: 'abcd'
      }).addTo(map);
      const line = L.polyline(pts, { color: '#58a6ff', weight: 3, opacity: 0.75 }).addTo(map);
      L.circleMarker(pts[0], { radius: 7, color: '#3fb950', fillColor: '#3fb950', fillOpacity: 1, weight: 0 })
        .bindTooltip(LANG === 'en' ? 'Start' : 'Başlangıç').addTo(map);
      L.circleMarker(pts[pts.length-1], { radius: 7, color: '#d29922', fillColor: '#d29922', fillOpacity: 1, weight: 0 })
        .bindTooltip(LANG === 'en' ? 'End' : 'Bitiş').addTo(map);
      map.fitBounds(line.getBounds(), { padding: [30, 30] });

      // Playback: animated drone marker along the track
      const droneIcon = L.divIcon({
        className: 'drone-marker',
        html: '<div style="width:14px;height:14px;background:#58a6ff;border:3px solid #fff;border-radius:50%;box-shadow:0 0 16px rgba(88,166,255,.8)"></div>',
        iconSize: [14, 14], iconAnchor: [7, 7],
      });
      const drone = L.marker(pts[0], { icon: droneIcon }).addTo(map);
      const trail = L.polyline([pts[0]], { color: '#58a6ff', weight: 4, opacity: 1 }).addTo(map);
      const scrub = document.getElementById('scrub');
      const scrubTime = document.getElementById('scrub-time');
      const playBtn = document.getElementById('play-btn');
      const PLAY_HTML = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
      const PAUSE_HTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
      let playing = false, idx = 0;
      const total = pts.length;
      const totalSec = data.points[total-1] && data.points[0] ?
        Math.max(1, (parseFloat(data.points[total-1].alt||0) + total)) : total;
      scrub.max = total - 1;
      function fmtT(i) {
        const t = Math.floor((i / Math.max(1, total - 1)) * (totalSec));
        return `${Math.floor(t/60)}:${String(t%60).padStart(2,'0')}`;
      }
      function totalT() {
        return `${Math.floor(totalSec/60)}:${String(Math.floor(totalSec)%60).padStart(2,'0')}`;
      }
      function update(i) {
        idx = Math.max(0, Math.min(total - 1, i));
        drone.setLatLng(pts[idx]);
        trail.setLatLngs(pts.slice(0, idx + 1));
        scrub.value = idx;
        scrubTime.textContent = `${fmtT(idx)} / ${totalT()}`;
      }
      scrub.addEventListener('input', e => { pause(); update(parseInt(e.target.value)); });
      function play() {
        if (idx >= total - 1) idx = 0;
        playing = true;
        playBtn.innerHTML = PAUSE_HTML;
        playBtn.title = LANG === 'en' ? 'Pause' : 'Duraklat';
        function tick() {
          if (!playing) return;
          update(idx + 1);
          if (idx >= total - 1) { pause(); return; }
          setTimeout(tick, Math.max(60, (totalSec * 1000) / total / 1.5));
        }
        tick();
      }
      function pause() {
        playing = false;
        playBtn.innerHTML = PLAY_HTML;
        playBtn.title = LANG === 'en' ? 'Play' : 'Oynat';
      }
      playBtn.addEventListener('click', () => playing ? pause() : play());
      update(0);
      playBtn.innerHTML = PLAY_HTML;
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
      CRUISE: 'Seyir', DELIVERY: 'Teslimat', DROP: 'Bırakma',
    };
    const labels_en = {
      IDLE: 'Idle', WAIT_PACKET: 'Waiting', PREFLIGHT: 'Preflight',
      TAKEOFF: 'Takeoff', NAVIGATE: 'Navigate', SEARCH_MARKER: 'Searching',
      PRECISION_APPROACH: 'Approach', BIOMETRIC_VERIFY: 'Face verify',
      DROP_PACKAGE: 'Drop', RETURN_HOME: 'Return home',
      LANDING: 'Landing', DISARM: 'Disarmed',
      MISSION_COMPLETE: 'Complete', ABORT: 'Abort',
      FAILED: 'Failed', READ_ONLY: 'Read-only',
      CRUISE: 'Cruise', DELIVERY: 'Delivery', DROP: 'Drop',
    };
    const labels = LANG === 'en' ? labels_en : labels_tr;
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
      const lbl = labels[p.state] || p.state;
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

  // Phase stepper (i18n labels from window.MISSION_FLOW)
  try {
    const step = document.getElementById('stepper');
    const FLOW = window.MISSION_FLOW;  // [[state, label], …]
    const r = await fetch(`/run/${name}/phases.json`);
    const data = await r.json();
    const visited = new Set(data.phases.map(p => p.state));
    const aborted = visited.has('ABORT') || visited.has('FAILED');
    const current = data.phases.length ? data.phases[data.phases.length - 1].state : null;
    step.innerHTML = '';
    FLOW.forEach(([st, lbl]) => {
      let cls = '';
      if (visited.has(st)) cls = 'done';
      if (st === current && !aborted) cls = 'current';
      if (aborted && current === st) cls = 'err';
      const mark = cls === 'done' ? '✓' : (cls === 'err' ? '✕' : '');
      step.insertAdjacentHTML('beforeend',
        `<div class="step ${cls}"><div class="step-circle">${mark}</div><div class="step-label">${lbl}</div></div>`);
    });
  } catch(e) {
    document.getElementById('stepper').textContent =
      LANG === 'en' ? 'Phase data unavailable' : 'Aşama verisi yüklenemedi';
  }

  // Failsafe events (TR)
  try {
    const r = await fetch(`/run/${name}/failsafe.json`);
    const data = await r.json();
    const panel = document.getElementById('failsafe-panel');
    if (!data.events.length) {
      const clearMsg = panel.dataset.clear;
      panel.innerHTML = `<div style="display:flex;align-items:center;gap:10px;color:var(--ok)"><span style="display:inline-block;width:8px;height:8px;background:var(--ok);border-radius:50%"></span>${clearMsg}</div>`;
    } else {
      let html = '<div style="display:flex;flex-direction:column;gap:8px">';
      data.events.forEach(e => {
        const t = `${Math.floor(e.t/60)}:${String(Math.floor(e.t%60)).padStart(2,'0')}`;
        const lblWarn = LANG === 'en' ? '⚠ ALERT' : '⚠ UYARI';
        const lblPhase = LANG === 'en' ? 'phase' : 'Aşama';
        html += `<div style="display:flex;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="color:var(--err);font-weight:600;font-size:12px">${lblWarn}</span><span style="font-family:'JetBrains Mono',monospace;color:var(--text-soft);font-size:12px">${t}</span><span style="color:var(--text);font-size:13px">${lblPhase}: ${e.state}</span></div>`;
      });
      html += '</div>';
      panel.innerHTML = html;
    }
  } catch(e) { console.error(e); }
})();
</script>
""")


EVENT_MAP = {
    # event_name: (icon, tone, label_tr, label_en)
    "start":             ("play", "accent", "Görev başladı", "Mission started"),
    "takeoff":           ("plane_up", "accent", "Drone havalandı", "Drone took off"),
    "cruise":            ("plane", "accent", "Hedefe gidiyor", "Cruising to target"),
    "marker_locked":     ("crosshair", "violet", "Hedef işaret bulundu", "Marker located"),
    "marker_lost":       ("alert", "err", "Hedef işaret kaybedildi", "Marker lost"),
    "face_match":        ("user_check", "pink", "Alıcı yüzü tanındı", "Recipient face matched"),
    "face_mismatch":     ("user_x", "err", "Yüz eşleşmedi", "Face mismatch"),
    "package_delivered": ("package", "ok", "Paket teslim edildi", "Package delivered"),
    "rtl_complete":      ("home", "warn", "Eve döndü", "Returned home"),
    "abort":             ("octagon_x", "err", "Görev iptal edildi", "Mission aborted"),
    "land":              ("arrow_down", "warn", "İniş yapıyor", "Landing"),
    "phase":             ("dot", "", "Aşama değişti", "Phase change"),
    "mission_end":       ("home", "warn", "Görev tamamlandı", "Mission ended"),
}


# Friendly detail formatter (no raw key=value)
def _format_detail(event_name: str, extras: dict, lang: str) -> str:
    tr = lang == "tr"
    if event_name == "phase":
        return extras.get("state", "")
    if event_name == "takeoff":
        alt = extras.get("alt")
        if alt is not None:
            return f"{alt:.0f} m" if tr else f"{alt:.0f} m altitude"
    if event_name == "face_match":
        conf = extras.get("confidence")
        if conf is not None:
            pct = float(conf) * 100
            return f"%{pct:.0f} eşleşme" if tr else f"{pct:.0f}% match"
    if event_name == "marker_locked":
        mid = extras.get("id")
        if mid is not None:
            return f"id {mid}"
    if event_name == "abort":
        return extras.get("reason", "")
    if event_name == "package_delivered":
        rid = extras.get("recipient_id")
        if rid is not None:
            return f"alıcı {rid}" if tr else f"recipient {rid}"
    # fallback: ignore raw msg/internal kvs
    if "msg" in extras:
        return ""
    return ""


def _human_summary(name: str, events: list, duration_s: int,
                   delivered: bool, abort_reason: str,
                   tel_stats: dict, lang: str = "tr") -> str:
    """Görev özeti — TR veya EN."""
    parts = []
    en = lang == "en"
    if duration_s > 0:
        m, s = divmod(duration_s, 60)
        if en:
            parts.append(f"Mission lasted {m}m {s}s." if m else f"Mission lasted {s}s.")
        else:
            parts.append(f"Görev {m} dakika {s} saniye sürdü." if m else f"Görev {s} saniye sürdü.")
    max_alt = tel_stats.get("max_alt")
    if max_alt and max_alt > 1:
        parts.append(f"Drone reached {max_alt:.0f} m altitude." if en
                     else f"Drone en fazla {max_alt:.0f} metre yüksekliğe çıktı.")
    if any(e.get("event") == "marker_locked" for e in events):
        parts.append("Ground marker located." if en else "Yer işaretini buldu.")
    face = next((e for e in events if e.get("event") == "face_match"), None)
    if face:
        conf = face.get("confidence")
        if conf is not None:
            pct = float(conf) * 100
            parts.append(f"Recipient face matched at {pct:.0f}% confidence." if en
                         else f"Alıcının yüzünü %{pct:.0f} eşleşme ile tanıdı.")
        else:
            parts.append("Recipient face recognised." if en else "Alıcının yüzünü tanıdı.")
    if delivered:
        parts.append("Package successfully delivered." if en
                     else "Paketi başarıyla teslim etti.")
    elif abort_reason:
        reasons = {
            "BATTERY_LOW": ("due to low battery", "batarya zayıf olduğu için"),
            "LINK_LOST": ("because the link was lost", "iletişim koptuğu için"),
            "GPS_LOST": ("because GPS signal was lost", "GPS sinyali kaybolduğu için"),
            "MARKER_LOST": ("because the marker was lost", "hedef işaretini bulamadığı için"),
            "FACE_MISMATCH": ("because face did not match", "yüz eşleşmediği için"),
            "Yer istasyonu ABORT": ("because ground station aborted", "yer istasyonu durdurduğu için"),
        }
        en_why, tr_why = reasons.get(abort_reason, (abort_reason, abort_reason))
        parts.append(f"Mission aborted {en_why}." if en
                     else f"Görev {tr_why} iptal edildi.")
    else:
        parts.append("Mission did not complete." if en else "Görev tamamlanamadı.")
    if any(e.get("event") in ("rtl_complete", "mission_end") for e in events):
        parts.append("Drone returned to base." if en else "Drone üsse geri döndü.")
    bat_drop = tel_stats.get("battery_drop")
    if bat_drop and bat_drop > 0.05:
        parts.append(f"Battery consumed: {bat_drop:.1f} V." if en
                     else f"Bataryanın {bat_drop:.1f} voltu harcandı.")
    if not parts:
        return "No summary available." if en else "Bu görev hakkında özet üretilemedi."
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
    import csv
    info = {
        "name": d.name, "duration_s": 0, "delivered": False,
        "abort_reason": "", "telemetry_rows": 0,
        "ts": None, "max_alt": 0.0, "battery_drop": 0.0,
        "recipient_id": None, "marker_locked": False,
        "face_matched": False, "rtl_done": False,
    }
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
            name = j.get("event")
            if name == "package_delivered":
                info["delivered"] = True
                if "recipient_id" in j:
                    info["recipient_id"] = j["recipient_id"]
            elif name == "abort":
                info["abort_reason"] = j.get("reason", "abort")
            elif name == "marker_locked":
                info["marker_locked"] = True
            elif name == "face_match":
                info["face_matched"] = True
            elif name in ("rtl_complete", "mission_end"):
                info["rtl_done"] = True
        if first is not None and last is not None:
            info["duration_s"] = max(0, int(last - first))
            info["ts"] = first
    tel = d / "telemetry.csv"
    if tel.exists():
        alts = []
        bats = []
        try:
            with tel.open() as f:
                for row in csv.DictReader(f):
                    try:
                        alts.append(float(row["alt_rel"]))
                        bats.append(float(row["battery_v"]))
                    except Exception:
                        continue
        except Exception:
            pass
        info["telemetry_rows"] = len(alts)
        if alts:
            info["max_alt"] = max(alts)
        if bats:
            info["battery_drop"] = bats[0] - bats[-1]
    if info["ts"] is None:
        try:
            info["ts"] = d.stat().st_mtime
        except Exception:
            info["ts"] = 0
    return info


def _list_runs(runs_dir: Optional[Path] = None) -> list[dict]:
    d = runs_dir or RUNS_DIR
    if not d.exists():
        return []
    return [_summarize_run(p) for p in sorted(d.iterdir())
            if p.is_dir() and p.name != "archive"]


@app.route("/")
def index():
    from flask import request as freq
    lang = freq.args.get("lang", "tr")
    if lang not in ("tr", "en"):
        lang = "tr"
    live_url = os.environ.get("KOKPIT_LIVE_URL", "")
    tr = lang == "tr"
    i18n = {
        "title": "Görev arşivi" if tr else "Mission archive",
        "sub": "Otonom teslimat görev kayıtları — olaylar, telemetri ve haritalar."
               if tr else "Autonomous delivery mission records — events, telemetry, maps.",
        "total_runs": "Toplam görev" if tr else "Total missions",
        "delivered": "Başarılı teslimat" if tr else "Delivered",
        "aborted": "İptal edilen" if tr else "Aborted",
        "success_rate": "Başarı oranı" if tr else "Success rate",
        "total_flight": "Toplam uçuş" if tr else "Total flight",
        "search": "Görev ara…" if tr else "Search missions…",
        "all": "Tümü" if tr else "All",
        "f_deliv": "Başarılı" if tr else "Delivered",
        "f_abort": "İptal" if tr else "Aborted",
        "f_inc": "Tamamlanmamış" if tr else "Incomplete",
        "live": "live" if tr else "live",
        "runs_word": "görev" if tr else "missions",
        "empty": "Eşleşen kayıt yok." if tr else "No matching missions.",
        "live_section": "Canlı görev görüntüsü" if tr else "Live mission feed",
    }
    return render_template_string(INDEX_HTML, runs=_list_runs(),
                                  live_url=live_url, lang=lang, i18n=i18n)


@app.route("/run/<name>")
def run_view(name):
    from flask import request as freq
    lang = freq.args.get("lang", freq.cookies.get("lang", "tr"))
    if lang not in ("tr", "en"):
        lang = "tr"
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
            mapped = EVENT_MAP.get(ev_name, ("dot", "", ev_name, ev_name))
            ic_key, tone = mapped[0], mapped[1]
            label = mapped[3] if lang == "en" else mapped[2]
            extras = {k: v for k, v in j.items()
                      if k not in ("ts", "timestamp", "event")}
            if ev_name == "phase":
                state = extras.get("state", "")
                label = (f"Phase: {state}" if lang == "en"
                         else f"Aşama: {state}")
            detail = _format_detail(ev_name, extras, lang)
            events.append({
                "dt": int(t - first_ts),
                "icon": ICON.get(ic_key, ICON["dot"]),
                "tone": tone,
                "label": label,
                "name": ev_name,
                "detail": detail,
            })
    tel = d / "telemetry.csv"
    tel_rows = max(0, len(tel.read_text().splitlines()) - 1) if tel.exists() else 0
    tel_stats = _telemetry_stats(d)
    human = _human_summary(safe, raw_events, summary["duration_s"],
                           summary["delivered"], summary["abort_reason"],
                           tel_stats, lang=lang)
    # I18n labels
    tr = lang == "tr"
    i18n = {
        "back": "Tüm görevler" if tr else "All missions",
        "delivered": "Başarılı teslimat" if tr else "Delivered",
        "abort": "Görev iptal" if tr else "Mission aborted",
        "incomplete": "Tamamlanamadı" if tr else "Incomplete",
        "headline_ok": "Paket başarıyla teslim edildi." if tr else "Package delivered successfully.",
        "headline_err": "Görev güvenlik nedeniyle iptal edildi." if tr else "Mission aborted for safety.",
        "headline_warn": "Görev tamamlanamadı." if tr else "Mission did not complete.",
        "download": "Verileri indir" if tr else "Download data",
        "report": "Rapor" if tr else "Report",
        "compare": "Karşılaştır…" if tr else "Compare…",
        "duration": "Süre" if tr else "Duration",
        "duration_sub": "dakika:saniye" if tr else "min:sec",
        "max_alt": "En yüksek irtifa" if tr else "Max altitude",
        "max_alt_sub": "yerden uzaklık" if tr else "above ground",
        "events_lbl": "Olay" if tr else "Events",
        "events_sub": "kaydedilen aşama" if tr else "logged stages",
        "battery": "Batarya harcaması" if tr else "Battery used",
        "battery_sub": "başlangıçtan sona" if tr else "start to end",
        "phases_title": "Görev aşamaları" if tr else "Mission phases",
        "phases_hint": "Görev her aşamada ne kadar zaman geçirdi:" if tr else "Time spent in each phase:",
        "events_title": "Olaylar" if tr else "Events",
        "plot_title": "İrtifa ve batarya" if tr else "Altitude & battery",
        "safety_title": "Güvenlik uyarıları" if tr else "Safety alerts",
        "safety_clear": "Bu görevde güvenlik uyarısı tetiklenmedi — her şey yolundaydı." if tr else "No safety alerts in this mission — all clear.",
        "route_title": "Uçuş rotası" if tr else "Flight path",
        "legend_start": "Başlangıç" if tr else "Start",
        "legend_end": "Bitiş" if tr else "End",
        "legend_path": "Uçuş yolu" if tr else "Flight path",
        "playback": "Oynat" if tr else "Play",
        "playback_pause": "Duraklat" if tr else "Pause",
        "stepper": ([
            ('WAIT_PACKET', 'Bekleme' if tr else 'Standby'),
            ('TAKEOFF', 'Kalkış' if tr else 'Takeoff'),
            ('NAVIGATE', 'Hedefe gidiş' if tr else 'Navigate'),
            ('SEARCH_MARKER', 'İşaret' if tr else 'Search'),
            ('PRECISION_APPROACH', 'Yaklaşım' if tr else 'Approach'),
            ('BIOMETRIC_VERIFY', 'Yüz' if tr else 'Face'),
            ('DROP_PACKAGE', 'Teslim' if tr else 'Deliver'),
            ('RETURN_HOME', 'Dönüş' if tr else 'Return'),
        ]),
    }
    return render_template_string(
        RUN_HTML, name=safe, events=events, tel_rows=tel_rows,
        duration_s=summary["duration_s"], delivered=summary["delivered"],
        abort_reason=summary["abort_reason"],
        human_summary=human, tel_stats=tel_stats,
        lang=lang, i18n=i18n,
    )


@app.route("/run/<name>/plot.png")
def plot_png(name):
    import io
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from flask import request as freq
    lang = freq.args.get("lang", "tr")
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
    if ts:
        t0 = ts[0]
        ts = [t - t0 for t in ts]
    plt.style.use("dark_background")
    fig, ax1 = plt.subplots(figsize=(11, 4.2), facecolor="#0d1117")
    ax1.set_facecolor("#0d1117")
    ax1.plot(ts, alt, color="#58a6ff", linewidth=2.2)
    ax1.fill_between(ts, alt, alpha=0.12, color="#58a6ff")
    en = lang == "en"
    ax1.set_xlabel("Zaman (saniye)" if not en else "Time (s)",
                   color="#9aa5b8", fontsize=11)
    ax1.set_ylabel("İrtifa (metre)" if not en else "Altitude (m)",
                   color="#58a6ff", fontsize=11, fontweight="bold")
    ax1.tick_params(colors="#9aa5b8", labelsize=10)
    ax1.grid(True, alpha=0.10, linestyle="-", linewidth=0.5)
    for sp in ax1.spines.values():
        sp.set_color("#1f2733")
    ax2 = ax1.twinx()
    ax2.plot(ts, bat, color="#d29922", linewidth=2.2)
    ax2.set_ylabel("Batarya (volt)" if not en else "Battery (V)",
                   color="#d29922", fontsize=11, fontweight="bold")
    ax2.tick_params(colors="#9aa5b8", labelsize=10)
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
    from flask import request as freq
    lang = freq.args.get("lang", "tr")
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_report import build_report_md
    from flask import Response
    return Response(build_report_md(d, lang=lang), mimetype="text/markdown")


def _md_to_html(md: str) -> str:
    """Hafif MD -> HTML çevirici (markdown paketi gerektirmez)."""
    import html as html_mod
    out = []
    in_table = False
    for line in md.splitlines():
        s = line
        if s.startswith("# "):
            out.append(f"<h1>{html_mod.escape(s[2:])}</h1>")
        elif s.startswith("## "):
            out.append(f"<h2>{html_mod.escape(s[3:])}</h2>")
        elif s.startswith("- "):
            content = s[2:]
            content = content.replace("**", "<b>", 1).replace("**", "</b>", 1)
            content = content.replace("`", "<code>", 1).replace("`", "</code>", 1)
            out.append(f"<li>{content}</li>")
        elif "|" in s and s.strip().startswith("|"):
            cells = [c.strip() for c in s.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator
            tag = "th" if not in_table else "td"
            row = "".join(f"<{tag}>{html_mod.escape(c)}</{tag}>" for c in cells)
            if not in_table:
                out.append('<table><thead><tr>' + row + '</tr></thead><tbody>')
                in_table = True
            else:
                out.append(f"<tr>{row}</tr>")
        elif not s.strip() and in_table:
            out.append("</tbody></table>")
            in_table = False
        elif s.strip():
            out.append(f"<p>{html_mod.escape(s)}</p>")
    if in_table:
        out.append("</tbody></table>")
    return "\n".join(out)


REPORT_HTML_CSS = """
<style>
:root { color-scheme: light; }
body {
  background: #f7f8fa; color: #1a212d;
  font: 15px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  margin: 0; padding: 0; -webkit-font-smoothing: antialiased;
}
.page {
  max-width: 780px; margin: 32px auto; padding: 48px 56px;
  background: white;
  border: 1px solid #e3e7ec;
  border-radius: 12px;
  box-shadow: 0 2px 24px rgba(0,0,0,.06);
}
.title-bar {
  border-bottom: 3px solid #2563eb;
  padding-bottom: 18px; margin-bottom: 28px;
  display: flex; justify-content: space-between; align-items: flex-end;
}
.brand-tag {
  display: inline-flex; align-items: center; gap: 8px;
  font: 600 13px ui-monospace, monospace;
  color: #2563eb;
}
.brand-tag::before {
  content: ""; display: inline-block;
  width: 14px; height: 14px; border-radius: 4px;
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
}
.report-date { font-size: 12px; color: #6b7280; }
h1 { font-size: 26px; margin: 0 0 16px; letter-spacing: -0.02em; font-weight: 700; }
h2 {
  font-size: 13px; margin: 32px 0 14px;
  text-transform: uppercase; letter-spacing: .1em;
  color: #2563eb; font-weight: 700;
}
h2::after {
  content: ""; display: block; height: 1px;
  background: linear-gradient(to right, #cdd5e0, transparent);
  margin-top: 6px;
}
li { margin: 6px 0; }
b { color: #1a212d; font-weight: 600; }
code { background: #eef2f7; padding: 2px 6px; border-radius: 4px;
       font: 13px ui-monospace, monospace; color: #1a212d; }
p { margin: 8px 0; }
table {
  width: 100%; border-collapse: collapse;
  margin: 14px 0; border: 1px solid #e3e7ec; border-radius: 8px;
  overflow: hidden; font-size: 13px;
}
th, td { padding: 10px 14px; text-align: left; vertical-align: top; }
th { background: #f3f5f8; font-size: 11px; text-transform: uppercase;
     letter-spacing: .08em; color: #6b7280; font-weight: 600; }
td { border-top: 1px solid #eef2f7; }
tbody tr:hover { background: #fafbfc; }
.lang-bar {
  position: fixed; top: 20px; right: 24px; display: flex; gap: 8px;
}
.lang-bar a, .lang-bar button {
  background: #2563eb; color: white; border: 0;
  padding: 8px 14px; border-radius: 8px;
  font: 600 13px inherit; cursor: pointer;
  text-decoration: none; box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
.lang-bar a.alt { background: white; color: #2563eb; border: 1px solid #cdd5e0; }
.footer {
  margin-top: 40px; padding-top: 18px;
  border-top: 1px solid #eef2f7;
  font-size: 11px; color: #9aa5b8; display: flex; justify-content: space-between;
}
@media print {
  body { background: white; }
  .page { box-shadow: none; border: 0; margin: 0 auto; padding: 24mm 18mm; max-width: none; }
  .lang-bar { display: none; }
  /* Keep colors */
  h2 { color: #2563eb !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .title-bar { border-bottom-color: #2563eb !important; }
  table { border-color: #cdd5e0 !important; }
  th { background: #f3f5f8 !important; -webkit-print-color-adjust: exact; }
}
</style>
"""


@app.route("/run/<name>/report.html")
def run_report_html(name):
    from flask import request as freq
    import time as _time
    lang = freq.args.get("lang", "tr")
    if lang not in ("tr", "en"):
        lang = "tr"
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    if safe != name:
        abort(400)
    d = RUNS_DIR / safe
    if not d.exists():
        abort(404)
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_report import build_report_md
    md = build_report_md(d, lang=lang)
    body = _md_to_html(md)
    tr = lang == "tr"
    title = "Kokpit Görev Raporu" if tr else "Kokpit Mission Report"
    print_btn = "PDF olarak yazdır" if tr else "Print as PDF"
    other_lang = "EN" if tr else "TR"
    other_url = f"?lang={'en' if tr else 'tr'}"
    date_str = _time.strftime("%d.%m.%Y %H:%M") if tr else _time.strftime("%Y-%m-%d %H:%M")
    footer = (f"Kokpit · Teknofest 2026 · "
              f"{'Otomatik üretildi' if tr else 'Auto-generated'} {date_str}")
    return (f"<!doctype html><html lang='{lang}'><head><meta charset=utf-8>"
            f"<title>{title} — {safe}</title>{REPORT_HTML_CSS}</head><body>"
            f'<div class="lang-bar">'
            f'  <a href="{other_url}" class="alt">{other_lang}</a>'
            f'  <button onclick="window.print()">{print_btn}</button>'
            f'</div>'
            f'<div class="page">'
            f'<div class="title-bar">'
            f'  <span class="brand-tag">KOKPIT</span>'
            f'  <span class="report-date">{date_str}</span>'
            f'</div>'
            f'{body}'
            f'<div class="footer"><span>{footer}</span><span>{safe}</span></div>'
            f'</div></body></html>')


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
