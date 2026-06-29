"""N11 — runs/ klasörü index + otomatik archive.

runs/index.json: her görev özet. 30+ gün log'lar runs/archive/<year>/<month>.tar.gz
sıkıştırılır. systemd timer örneği systemd/ altında.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import tarfile
import time
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS = ROOT / "runs"
ARCHIVE_AGE_DAYS = 30


def summarize_run(run_dir: Path) -> dict:
    info = {
        "name": run_dir.name,
        "ts": int(run_dir.stat().st_mtime),
        "duration_s": 0,
        "package_delivered": False,
        "abort_reason": "",
        "telemetry_rows": 0,
    }
    events = run_dir / "events.jsonl"
    if events.exists():
        first_ts = last_ts = None
        for line in events.read_text().splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("ts") or d.get("timestamp")
            if t:
                if first_ts is None:
                    first_ts = t
                last_ts = t
            if d.get("event") == "package_delivered":
                info["package_delivered"] = True
            if d.get("event") == "abort":
                info["abort_reason"] = d.get("reason", "")
        if first_ts and last_ts:
            info["duration_s"] = max(0, int(last_ts - first_ts))
    tel = run_dir / "telemetry.csv"
    if tel.exists():
        info["telemetry_rows"] = max(0, len(tel.read_text().splitlines()) - 1)
    return info


def build_index(runs_dir: Path = DEFAULT_RUNS) -> dict:
    runs = []
    if runs_dir.exists():
        for d in sorted(runs_dir.iterdir()):
            if d.is_dir() and d.name != "archive":
                runs.append(summarize_run(d))
    index = {"generated_at": int(time.time()), "runs": runs}
    if runs_dir.exists():
        (runs_dir / "index.json").write_text(json.dumps(index, indent=2))
    return index


def archive_old(runs_dir: Path = DEFAULT_RUNS,
                age_days: int = ARCHIVE_AGE_DAYS) -> list[Path]:
    """age_days üzerindeki run'ları aylık tar.gz'ye taşı."""
    if not runs_dir.exists():
        return []
    cutoff = time.time() - age_days * 86400
    archive_root = runs_dir / "archive"
    moved: list[Path] = []
    for d in sorted(runs_dir.iterdir()):
        if not d.is_dir() or d.name == "archive":
            continue
        if d.stat().st_mtime > cutoff:
            continue
        ts = time.localtime(d.stat().st_mtime)
        out_dir = archive_root / f"{ts.tm_year:04d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        tar_path = out_dir / f"{ts.tm_year:04d}-{ts.tm_mon:02d}.tar.gz"
        mode = "a" if tar_path.exists() else "w"
        # tarfile append mode tar.gz desteklemez -> her ay için tek shot
        if mode == "a":
            # Açık tar.gz append etmek için uncompress -> append -> recompress
            # Basit yaklaşım: aynı aya başka run varsa, yeni dosya adı ver
            tar_path = out_dir / f"{ts.tm_year:04d}-{ts.tm_mon:02d}-{d.name}.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(d, arcname=d.name)
        import shutil
        shutil.rmtree(d)
        moved.append(tar_path)
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", action="store_true", help="eski log'ları sıkıştır")
    ap.add_argument("--age-days", type=int, default=ARCHIVE_AGE_DAYS)
    ap.add_argument("--runs-dir", default=str(DEFAULT_RUNS))
    args = ap.parse_args()
    runs_dir = Path(args.runs_dir)
    if args.archive:
        moved = archive_old(runs_dir, args.age_days)
        for m in moved:
            print(f"archived: {m}")
    idx = build_index(runs_dir)
    print(f"runs indexed: {len(idx['runs'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
