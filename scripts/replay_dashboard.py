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


INDEX_HTML = """<!doctype html>
<title>Kokpit Replay</title>
<h1>Mission Replay</h1>
<ul>
{% for r in runs %}
  <li><a href="/run/{{ r }}">{{ r }}</a></li>
{% endfor %}
</ul>
"""

RUN_HTML = """<!doctype html>
<title>Run {{ name }}</title>
<h1>{{ name }}</h1>
<h2>Events</h2>
<pre>{{ events_text }}</pre>
<h2>Telemetry</h2>
<p>Rows: {{ tel_rows }} | <a href="/run/{{ name }}/plot.png">plot</a></p>
"""


def _list_runs(runs_dir: Optional[Path] = None) -> list[str]:
    d = runs_dir or RUNS_DIR
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


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
    events_text = ""
    ev = d / "events.jsonl"
    if ev.exists():
        events_text = ev.read_text()[:8000]
    tel_rows = 0
    tc = d / "telemetry.csv"
    if tc.exists():
        tel_rows = len(tc.read_text().splitlines()) - 1
    return render_template_string(RUN_HTML, name=safe,
                                  events_text=events_text, tel_rows=tel_rows)


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
    fig, ax1 = plt.subplots(figsize=(8, 4))
    ax1.plot(ts, alt, "b-", label="alt_rel (m)")
    ax2 = ax1.twinx()
    ax2.plot(ts, bat, "r-", label="batt (V)")
    ax1.set_xlabel("t (s)"); ax1.set_ylabel("alt"); ax2.set_ylabel("batt")
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    from flask import Response
    return Response(buf.read(), mimetype="image/png")


@app.route("/api/runs")
def api_runs():
    return jsonify({"runs": _list_runs()})


def main():
    app.run(host="127.0.0.1", port=int(os.environ.get("KOKPIT_REPLAY_PORT", 5000)))


if __name__ == "__main__":
    sys.exit(main())
