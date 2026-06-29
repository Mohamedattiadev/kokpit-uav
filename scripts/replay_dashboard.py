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


BASE_CSS = """
<style>
:root {
  --bg: #0b0f17;
  --panel: #131a26;
  --panel-2: #1a2333;
  --border: #243049;
  --text: #e5edff;
  --muted: #8090b3;
  --accent: #38bdf8;
  --ok: #4ade80;
  --warn: #fbbf24;
  --err: #f87171;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: linear-gradient(180deg, #0b0f17 0%, #050810 100%);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  min-height: 100vh;
}
.header {
  background: rgba(19,26,38,.8);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 18px 32px;
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between;
}
.brand { font-size: 20px; font-weight: 700; letter-spacing: .3px; }
.brand .dot { color: var(--accent); margin-right: 8px; }
.subtitle { color: var(--muted); font-size: 13px; }
.container { max-width: 1100px; margin: 0 auto; padding: 32px; }
.runs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  transition: all .15s ease;
  text-decoration: none; color: inherit; display: block;
}
.card:hover {
  border-color: var(--accent);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(56,189,248,.08);
}
.card h3 { margin: 0 0 8px; font-size: 16px; font-weight: 600; }
.badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.badge {
  font-size: 11px; padding: 3px 9px; border-radius: 999px;
  background: var(--panel-2); border: 1px solid var(--border);
  color: var(--muted); font-weight: 500;
}
.badge.ok { background: rgba(74,222,128,.12); color: var(--ok); border-color: rgba(74,222,128,.3); }
.badge.warn { background: rgba(251,191,36,.12); color: var(--warn); border-color: rgba(251,191,36,.3); }
.badge.err { background: rgba(248,113,113,.12); color: var(--err); border-color: rgba(248,113,113,.3); }
.empty {
  text-align: center; padding: 60px 20px;
  color: var(--muted);
}
.empty .icon { font-size: 48px; margin-bottom: 16px; opacity: .4; }
.section { margin-top: 28px; }
.section h2 {
  font-size: 14px; text-transform: uppercase; letter-spacing: 2px;
  color: var(--muted); margin: 0 0 14px; font-weight: 600;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 24px;
}
.timeline { display: flex; flex-direction: column; gap: 4px; }
.event {
  display: grid; grid-template-columns: 70px 40px 1fr;
  gap: 12px; align-items: center;
  padding: 10px 14px; border-radius: 8px;
  background: var(--panel-2);
  border-left: 3px solid var(--border);
  font-size: 14px;
}
.event.ev-start    { border-left-color: var(--accent); }
.event.ev-takeoff  { border-left-color: var(--accent); }
.event.ev-marker   { border-left-color: #a78bfa; }
.event.ev-face     { border-left-color: #f472b6; }
.event.ev-deliver  { border-left-color: var(--ok); }
.event.ev-abort    { border-left-color: var(--err); }
.event.ev-rtl      { border-left-color: var(--warn); }
.event .ts { color: var(--muted); font-family: ui-monospace, monospace; font-size: 13px; }
.event .icon { font-size: 18px; text-align: center; }
.event .payload { color: var(--muted); font-family: ui-monospace, monospace; font-size: 12px; }
.event .payload b { color: var(--text); font-weight: 600; }
.kv { display: flex; gap: 24px; flex-wrap: wrap; margin: 16px 0; }
.kv .item { display: flex; flex-direction: column; gap: 4px; }
.kv .lbl { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 1px; }
.kv .val { font-size: 22px; font-weight: 600; }
.plot-wrap { margin-top: 20px; }
.plot-wrap img { width: 100%; border-radius: 8px; border: 1px solid var(--border); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.back { color: var(--muted); font-size: 13px; }
</style>
"""

INDEX_HTML = (BASE_CSS + """
<div class="header">
  <div>
    <div class="brand"><span class="dot">●</span>Kokpit Mission Replay</div>
    <div class="subtitle">Otonom teslimat görev kayıtları · {{ runs|length }} kayıt</div>
  </div>
  <div class="subtitle">Teknofest 2026</div>
</div>
<div class="container">
{% if runs %}
<div class="runs-grid">
  {% for r in runs %}
  <a class="card" href="/run/{{ r.name }}">
    <h3>{{ r.name }}</h3>
    <div class="subtitle">{{ r.duration_s }}s · {{ r.telemetry_rows }} telemetry</div>
    <div class="badges">
      {% if r.delivered %}<span class="badge ok">✓ delivered</span>{% endif %}
      {% if r.abort_reason %}<span class="badge err">⚠ {{ r.abort_reason }}</span>{% endif %}
      {% if not r.delivered and not r.abort_reason %}<span class="badge warn">incomplete</span>{% endif %}
    </div>
  </a>
  {% endfor %}
</div>
{% else %}
<div class="empty">
  <div class="icon">📡</div>
  <div>Henüz kayıt yok. Görev çalıştırınca <code>runs/&lt;ts&gt;/</code> burada görünür.</div>
</div>
{% endif %}
</div>
""")

RUN_HTML = (BASE_CSS + """
<div class="header">
  <div>
    <div class="brand"><span class="dot">●</span>{{ name }}</div>
    <div class="subtitle"><a href="/" class="back">← Tüm kayıtlar</a></div>
  </div>
  <div class="subtitle">{{ events|length }} olay · {{ tel_rows }} telemetry row</div>
</div>
<div class="container">

<div class="kv">
  <div class="item"><div class="lbl">Süre</div><div class="val">{{ duration_s }}s</div></div>
  <div class="item"><div class="lbl">Telemetry</div><div class="val">{{ tel_rows }}</div></div>
  <div class="item"><div class="lbl">Durum</div><div class="val">
    {% if delivered %}<span style="color:var(--ok)">✓ Teslim</span>
    {% elif abort_reason %}<span style="color:var(--err)">⚠ Abort</span>
    {% else %}<span style="color:var(--warn)">—</span>{% endif %}
  </div></div>
  {% if abort_reason %}
  <div class="item"><div class="lbl">Abort sebebi</div><div class="val" style="font-size:16px">{{ abort_reason }}</div></div>
  {% endif %}
</div>

<div class="section">
  <h2>Timeline</h2>
  <div class="panel">
    <div class="timeline">
      {% for e in events %}
      <div class="event {{ e.css }}">
        <div class="ts">t+{{ e.dt }}s</div>
        <div class="icon">{{ e.icon }}</div>
        <div class="payload"><b>{{ e.name }}</b> {{ e.detail }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

{% if tel_rows > 0 %}
<div class="section">
  <h2>Altitude + Battery</h2>
  <div class="plot-wrap"><img src="/run/{{ name }}/plot.png" alt="plot"/></div>
</div>
{% endif %}

</div>
""")


EVENT_ICONS = {
    "start": ("🚀", "ev-start"),
    "takeoff": ("⬆️", "ev-takeoff"),
    "cruise": ("✈️", "ev-takeoff"),
    "marker_locked": ("🎯", "ev-marker"),
    "marker_lost": ("⚠️", "ev-abort"),
    "face_match": ("👤", "ev-face"),
    "face_mismatch": ("✗", "ev-abort"),
    "package_delivered": ("📦", "ev-deliver"),
    "rtl_complete": ("🏠", "ev-rtl"),
    "abort": ("⛔", "ev-abort"),
    "land": ("⬇️", "ev-rtl"),
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
            name_ev = j.get("event", "?")
            icon, css = EVENT_ICONS.get(name_ev, ("•", ""))
            extras = {k: v for k, v in j.items() if k not in ("ts", "timestamp", "event")}
            detail = " · ".join(f"{k}={v}" for k, v in extras.items())
            events.append({"dt": int(t - first_ts), "icon": icon, "css": css,
                           "name": name_ev, "detail": detail})
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
    # Dark theme matplotlib
    plt.style.use("dark_background")
    fig, ax1 = plt.subplots(figsize=(10, 4.2), facecolor="#0b0f17")
    ax1.set_facecolor("#131a26")
    ax1.plot(ts, alt, color="#38bdf8", linewidth=2.2, label="Altitude (m)")
    ax1.fill_between(ts, alt, alpha=0.15, color="#38bdf8")
    ax1.set_xlabel("time (s)", color="#8090b3", fontsize=10)
    ax1.set_ylabel("Altitude (m)", color="#38bdf8", fontsize=10, fontweight="bold")
    ax1.tick_params(colors="#8090b3")
    ax1.grid(True, alpha=0.15, linestyle="--")
    for sp in ax1.spines.values():
        sp.set_color("#243049")
    ax2 = ax1.twinx()
    ax2.plot(ts, bat, color="#fbbf24", linewidth=2.2, label="Battery (V)")
    ax2.set_ylabel("Battery (V)", color="#fbbf24", fontsize=10, fontweight="bold")
    ax2.tick_params(colors="#8090b3")
    for sp in ax2.spines.values():
        sp.set_color("#243049")
    fig.suptitle(f"Mission Telemetry — {safe}",
                 color="#e5edff", fontsize=13, fontweight="bold", y=0.98)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor="#0b0f17",
                bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype="image/png")


@app.route("/api/runs")
def api_runs():
    return jsonify({"runs": [r["name"] for r in _list_runs()]})


def main():
    app.run(host="127.0.0.1", port=int(os.environ.get("KOKPIT_REPLAY_PORT", 5000)))


if __name__ == "__main__":
    sys.exit(main())
