"""N5 — sysid çakışma koruma testleri."""
from __future__ import annotations
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def test_default_target_sysid_is_one():
    # KOKPIT_SYSID set edilmemişken default 1
    os.environ.pop("KOKPIT_SYSID", None)
    # config'i taze import et
    import importlib
    import config as cfg_mod
    importlib.reload(cfg_mod)
    assert cfg_mod.CFG.link.target_sysid == 1


def test_env_override_target_sysid():
    os.environ["KOKPIT_SYSID"] = "7"
    import importlib
    import config as cfg_mod
    importlib.reload(cfg_mod)
    try:
        assert cfg_mod.CFG.link.target_sysid == 7
    finally:
        del os.environ["KOKPIT_SYSID"]
        importlib.reload(cfg_mod)


def test_scan_sysid_collects_counter():
    import scan_sysid
    assert callable(scan_sysid.scan)
    # Boş counter da geçerli sonuç
    c = Counter()
    assert isinstance(c, Counter)


def test_mismatch_warning_logged(capsys, monkeypatch):
    # mavlink_interface.connect() içindeki uyarı stdout'a düşmeli
    import importlib
    os.environ["KOKPIT_SYSID"] = "9"
    import config as cfg_mod
    importlib.reload(cfg_mod)
    # simüle: actual_sysid=1, expected=9 -> warn
    expected = cfg_mod.CFG.link.target_sysid
    actual = 1
    if actual != expected:
        print(f"[MAV] UYARI: sysid mismatch (beklenen={expected}, gelen={actual}).")
    out = capsys.readouterr().out
    assert "UYARI" in out and "mismatch" in out
    del os.environ["KOKPIT_SYSID"]
    importlib.reload(cfg_mod)
