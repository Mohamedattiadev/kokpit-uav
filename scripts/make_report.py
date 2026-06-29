"""#15 — Mission PDF report (jüri'ye sunulabilir).

runs/<ts>/events.jsonl + telemetry.csv -> runs/<ts>/report.md (+ pdf pandoc varsa).
"""
from __future__ import annotations
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def build_report_md(run_dir: Path) -> str:
    name = run_dir.name
    md = [f"# Mission Report — {name}", ""]
    # Summary
    events_path = run_dir / "events.jsonl"
    events = []
    first_ts = last_ts = None
    delivered = False
    abort_reason = ""
    if events_path.exists():
        for ln in events_path.read_text().splitlines():
            try:
                j = json.loads(ln)
            except Exception:
                continue
            events.append(j)
            t = j.get("ts")
            if t and first_ts is None:
                first_ts = t
            if t:
                last_ts = t
            if j.get("event") == "package_delivered":
                delivered = True
            if j.get("event") == "abort":
                abort_reason = j.get("reason", "abort")
    duration = int((last_ts - first_ts)) if (first_ts and last_ts) else 0
    tel_path = run_dir / "telemetry.csv"
    tel_rows = 0
    if tel_path.exists():
        tel_rows = max(0, len(tel_path.read_text().splitlines()) - 1)
    status = ("✓ Delivered" if delivered
              else (f"⚠ Abort — {abort_reason}" if abort_reason
                    else "Incomplete"))
    md += [
        "## Summary", "",
        f"- **Status:** {status}",
        f"- **Duration:** {duration} s",
        f"- **Events:** {len(events)}",
        f"- **Telemetry rows:** {tel_rows}",
        "",
    ]
    md += ["## Event timeline", "", "| t (s) | event | detail |", "|---|---|---|"]
    for e in events:
        t = e.get("ts", 0)
        dt = int(t - first_ts) if first_ts else 0
        ev = e.get("event", "?")
        detail = ", ".join(f"{k}={v}" for k, v in e.items()
                           if k not in ("ts", "event"))
        md.append(f"| {dt} | `{ev}` | {detail} |")
    md.append("")
    # Telemetry stats
    if tel_path.exists():
        alts = []
        bats = []
        with tel_path.open() as f:
            for row in csv.DictReader(f):
                try:
                    alts.append(float(row["alt_rel"]))
                    bats.append(float(row["battery_v"]))
                except Exception:
                    continue
        if alts:
            md += ["## Telemetry stats", "",
                   f"- **Max altitude:** {max(alts):.1f} m",
                   f"- **Min altitude:** {min(alts):.1f} m",
                   f"- **Battery start:** {bats[0]:.2f} V",
                   f"- **Battery end:** {bats[-1]:.2f} V",
                   f"- **Battery drop:** {bats[0] - bats[-1]:.2f} V",
                   ""]
    return "\n".join(md)


def write_report(run_dir: Path, want_pdf: bool = True) -> dict:
    out = {"md": None, "pdf": None}
    md_text = build_report_md(run_dir)
    md_path = run_dir / "report.md"
    md_path.write_text(md_text)
    out["md"] = str(md_path)
    if want_pdf:
        try:
            subprocess.run(
                ["pandoc", str(md_path), "-o", str(run_dir / "report.pdf"),
                 "-V", "geometry:margin=1.5cm"],
                check=True, capture_output=True, timeout=20,
            )
            out["pdf"] = str(run_dir / "report.pdf")
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            pass  # pandoc yok — md yeterli
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    if not args.run_dir.exists():
        print(f"yok: {args.run_dir}", file=sys.stderr)
        return 2
    out = write_report(args.run_dir, want_pdf=not args.no_pdf)
    for k, v in out.items():
        if v:
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
