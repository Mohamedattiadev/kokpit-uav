"""
plot_mission.py — dataflash.bin + jsonl olay log'u → matplotlib plot.

Çıktı: irtifa-zaman, batarya-zaman, marker olayları. matplotlib yoksa
text özet yazdırır.
"""
from __future__ import annotations
import argparse
import json
import os
import sys


def parse_jsonl_events(path: str):
    if not os.path.exists(path):
        return []
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def summarize(events) -> dict:
    if not events:
        return {"count": 0}
    out: dict = {"count": len(events), "phases": []}
    for ev in events:
        if "phase" in ev:
            out["phases"].append(ev["phase"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", help="events.jsonl")
    ap.add_argument("--bin", help="dataflash.bin")
    ap.add_argument("--out", default="mission_plot.png")
    args = ap.parse_args(argv)

    events = parse_jsonl_events(args.events) if args.events else []
    summary = summarize(events)
    print("Events:", summary)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib yok; metin özetiyle yetinildi.")
        return 0

    fig, ax = plt.subplots(2, 1, figsize=(10, 6))
    ts = [ev.get("ts", i) for i, ev in enumerate(events)]
    alt = [ev.get("alt", 0.0) for ev in events]
    batt = [ev.get("batt", 0.0) for ev in events]
    ax[0].plot(ts, alt, label="alt_rel"); ax[0].set_ylabel("m")
    ax[1].plot(ts, batt, label="battery"); ax[1].set_ylabel("V")
    ax[1].set_xlabel("ts")
    for a in ax:
        a.grid(True); a.legend()
    fig.tight_layout()
    fig.savefig(args.out)
    print(f"Plot yazıldı: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
