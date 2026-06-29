"""N11 — runs_index + archive testleri."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from runs_index import build_index, archive_old, summarize_run  # noqa: E402


def _make_run(d: Path, mtime: float = None, delivered: bool = True):
    d.mkdir(parents=True, exist_ok=True)
    ev = d / "events.jsonl"
    lines = [
        json.dumps({"ts": 1000, "event": "start"}),
        json.dumps({"ts": 1100, "event": "package_delivered" if delivered
                    else "abort", "reason": "" if delivered else "TEST"}),
    ]
    ev.write_text("\n".join(lines))
    tel = d / "telemetry.csv"
    tel.write_text("h\n" + "x\n" * 5)
    if mtime is not None:
        os.utime(d, (mtime, mtime))
        os.utime(ev, (mtime, mtime))


def test_build_index_picks_up_runs(tmp_path):
    _make_run(tmp_path / "r1")
    _make_run(tmp_path / "r2", delivered=False)
    idx = build_index(tmp_path)
    assert len(idx["runs"]) == 2
    p = tmp_path / "index.json"
    assert p.exists()
    data = json.loads(p.read_text())
    names = {r["name"] for r in data["runs"]}
    assert names == {"r1", "r2"}
    delivered = [r for r in data["runs"] if r["package_delivered"]]
    assert len(delivered) == 1


def test_archive_old_compresses(tmp_path):
    old = tmp_path / "r_old"
    _make_run(old, mtime=time.time() - 60 * 86400)  # 60 gün önce
    new = tmp_path / "r_new"
    _make_run(new)
    moved = archive_old(tmp_path, age_days=30)
    assert len(moved) == 1
    assert moved[0].suffix == ".gz"
    assert not old.exists()  # taşındı
    assert new.exists()      # taze, kaldı


def test_old_run_preserved_under_age(tmp_path):
    _make_run(tmp_path / "r1", mtime=time.time() - 5 * 86400)
    moved = archive_old(tmp_path, age_days=30)
    assert moved == []
    assert (tmp_path / "r1").exists()
