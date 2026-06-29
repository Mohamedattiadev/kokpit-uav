"""Test/demo görev verisi üretici — 5 farklı senaryo.

happy / abort_battery / abort_face_mismatch / abort_link_lost / marker_lost
Replay dashboard'ı varied verilerle test etmek için. Gerçek görev sırasında
mission.py kendi runs/<ts>/ dizinini üretir; bu sadece UI/UX kontrolü.
"""
from __future__ import annotations
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


CSV_HEADER = ("ts_unix_us,lat,lon,alt_rel,vx,vy,vz,heading,roll,pitch,yaw,"
              "battery_v,battery_pct,satellites,hdop,mode,armed,lidar_alt_body,"
              "mission_state,failsafe_active")


def _csv_row(t_us, lat, lon, alt, batt_v, mode, state, failsafe=0):
    return (f"{t_us},{lat:.6f},{lon:.6f},{alt:.2f},0,0,0,0,0,0,0,"
            f"{batt_v:.2f},{batt_v*4:.0f},12,0.7,{mode},1,{alt:.2f},"
            f"{state},{failsafe}")


def _interp(start, end, n, jitter=0.0):
    out = []
    for i in range(n):
        f = i / max(1, n - 1)
        v = start + (end - start) * f
        if jitter:
            v += random.uniform(-jitter, jitter)
        out.append(v)
    return out


def write_run(name: str, events: list[tuple[int, str, dict]],
              telemetry: list[tuple[int, str, float, float, float, float, int]]):
    """events: list of (rel_sec, event_name, payload)
    telemetry: list of (rel_sec, mode, alt, lat, lon, battery_v, failsafe)
    """
    d = RUNS / name
    d.mkdir(parents=True, exist_ok=True)
    base_ts = time.time()
    # events.jsonl
    with (d / "events.jsonl").open("w") as f:
        for rel_s, ev, payload in events:
            rec = {"ts": base_ts + rel_s, "event": ev, **payload}
            f.write(json.dumps(rec) + "\n")
    # telemetry.csv
    lines = [CSV_HEADER]
    for rel_s, mode, alt, lat, lon, batt, fs in telemetry:
        ts_us = int((base_ts + rel_s) * 1e6)
        state = next((e[2].get("state", e[1].upper())
                      for e in events if e[0] <= rel_s
                      and e[1] in ("phase", "start")), "IDLE")
        # use better state via state map
        lines.append(_csv_row(ts_us, lat, lon, alt, batt, mode, mode_to_state(mode, rel_s, events), fs))
    (d / "telemetry.csv").write_text("\n".join(lines) + "\n")
    print(f"OK: {d}")


def mode_to_state(mode: str, rel_s: float, events: list) -> str:
    """En son phase event'inden state çıkar."""
    state = "IDLE"
    for e in events:
        if e[0] > rel_s:
            break
        if e[1] == "phase":
            state = e[2].get("state", state)
    return state


# Ankara civarı koordinatlar
BASE_LAT = 39.9208
BASE_LON = 32.8541


def happy_path(name: str):
    """Tam başarılı görev — 3 dakika, paket teslim."""
    duration = 180
    events = [
        (0, "start", {"msg": "mission started"}),
        (2, "phase", {"state": "PREFLIGHT"}),
        (5, "phase", {"state": "TAKEOFF"}),
        (10, "takeoff", {"alt": 8.0}),
        (18, "phase", {"state": "NAVIGATE"}),
        (20, "cruise", {}),
        (80, "phase", {"state": "SEARCH_MARKER"}),
        (88, "marker_locked", {"id": 0}),
        (95, "phase", {"state": "PRECISION_APPROACH"}),
        (110, "phase", {"state": "BIOMETRIC_VERIFY"}),
        (118, "face_match", {"confidence": 0.94, "recipient_id": 7}),
        (125, "phase", {"state": "DROP_PACKAGE"}),
        (135, "package_delivered", {"recipient_id": 7}),
        (140, "phase", {"state": "RETURN_HOME"}),
        (175, "phase", {"state": "LANDING"}),
        (178, "rtl_complete", {}),
        (180, "mission_end", {"delivered": True}),
    ]
    # Telemetry: 1 row per second
    tel = []
    lats = _interp(BASE_LAT, BASE_LAT + 0.0008, duration + 1, 0.00001)
    lons = _interp(BASE_LON, BASE_LON + 0.0006, duration + 1, 0.00001)
    bats = _interp(25.0, 23.9, duration + 1)
    for s in range(duration + 1):
        if s < 5: alt = 0
        elif s < 20: alt = (s - 5) * 0.6  # climb
        elif s < 80: alt = 9 + s * 0.06   # cruise climb
        elif s < 110: alt = 15 - (s - 80) * 0.3  # descent
        elif s < 135: alt = 6 - (s - 110) * 0.18  # final approach
        elif s < 145: alt = 2.5
        elif s < 175: alt = 2.5 + (s - 145) * 0.4
        else: alt = max(0, 15 - (s - 175) * 5)
        # return lat/lon
        lat = lats[s] if s < 140 else lats[max(0, 280 - s)]
        lon = lons[s] if s < 140 else lons[max(0, 280 - s)]
        tel.append((s, "GUIDED" if s < 140 else "RTL", alt, lat, lon, bats[s], 0))
    write_run(name, events, tel)


def battery_abort(name: str):
    duration = 95
    events = [
        (0, "start", {}),
        (2, "phase", {"state": "TAKEOFF"}),
        (10, "takeoff", {"alt": 8.0}),
        (20, "phase", {"state": "NAVIGATE"}),
        (60, "phase", {"state": "SEARCH_MARKER"}),
        (75, "abort", {"reason": "BATTERY_LOW"}),
        (76, "phase", {"state": "ABORT"}),
        (80, "phase", {"state": "RETURN_HOME"}),
        (92, "phase", {"state": "LANDING"}),
        (95, "mission_end", {"delivered": False, "reason": "BATTERY_LOW"}),
    ]
    tel = []
    bats = _interp(22.4, 21.3, duration + 1)
    for s in range(duration + 1):
        if s < 5: alt = 0
        elif s < 20: alt = (s - 5) * 0.6
        elif s < 75: alt = 9 + (s % 10) * 0.2
        elif s < 90: alt = max(0, 12 - (s - 75) * 0.8)
        else: alt = 0
        fs = 1 if s >= 75 and s <= 92 else 0
        lat = BASE_LAT + 0.0003 * (s / 75) if s < 75 else BASE_LAT + 0.0003 - (s - 75) * 0.00002
        lon = BASE_LON + 0.0002 * (s / 75) if s < 75 else BASE_LON + 0.0002 - (s - 75) * 0.000013
        tel.append((s, "GUIDED" if s < 75 else "RTL", alt, lat, lon, bats[s], fs))
    write_run(name, events, tel)


def face_mismatch(name: str):
    duration = 130
    events = [
        (0, "start", {}),
        (2, "phase", {"state": "TAKEOFF"}),
        (10, "takeoff", {"alt": 8.0}),
        (18, "phase", {"state": "NAVIGATE"}),
        (75, "phase", {"state": "SEARCH_MARKER"}),
        (82, "marker_locked", {"id": 0}),
        (90, "phase", {"state": "BIOMETRIC_VERIFY"}),
        (102, "face_mismatch", {"confidence": 0.41}),
        (104, "abort", {"reason": "FACE_MISMATCH"}),
        (105, "phase", {"state": "RETURN_HOME"}),
        (128, "phase", {"state": "LANDING"}),
        (130, "mission_end", {"delivered": False, "reason": "FACE_MISMATCH"}),
    ]
    tel = []
    bats = _interp(24.8, 24.0, duration + 1)
    for s in range(duration + 1):
        if s < 5: alt = 0
        elif s < 20: alt = (s - 5) * 0.6
        elif s < 90: alt = 9 + (s % 10) * 0.2
        elif s < 105: alt = max(2, 12 - (s - 90) * 0.5)
        elif s < 128: alt = 4 + (s - 105) * 0.3
        else: alt = 0
        fs = 1 if 104 <= s <= 128 else 0
        lat = BASE_LAT + 0.00045 * min(1, s/85)
        lon = BASE_LON + 0.0003 * min(1, s/85)
        tel.append((s, "GUIDED" if s < 105 else "RTL", alt, lat, lon, bats[s], fs))
    write_run(name, events, tel)


def link_lost(name: str):
    duration = 85
    events = [
        (0, "start", {}),
        (2, "phase", {"state": "TAKEOFF"}),
        (10, "takeoff", {"alt": 8.0}),
        (20, "phase", {"state": "NAVIGATE"}),
        (50, "abort", {"reason": "LINK_LOST"}),
        (51, "phase", {"state": "RETURN_HOME"}),
        (82, "phase", {"state": "LANDING"}),
        (85, "mission_end", {"delivered": False, "reason": "LINK_LOST"}),
    ]
    tel = []
    bats = _interp(24.5, 23.6, duration + 1)
    for s in range(duration + 1):
        if s < 5: alt = 0
        elif s < 20: alt = (s - 5) * 0.6
        elif s < 50: alt = 9 + (s % 5) * 0.3
        elif s < 80: alt = max(2, 11 - (s - 50) * 0.3)
        else: alt = 0
        fs = 1 if 50 <= s <= 80 else 0
        lat = BASE_LAT + 0.0003 * min(1, s/45)
        lon = BASE_LON + 0.00015 * min(1, s/45)
        tel.append((s, "GUIDED" if s < 50 else "RTL", alt, lat, lon, bats[s], fs))
    write_run(name, events, tel)


def marker_lost(name: str):
    duration = 110
    events = [
        (0, "start", {}),
        (2, "phase", {"state": "TAKEOFF"}),
        (10, "takeoff", {"alt": 8.0}),
        (18, "phase", {"state": "NAVIGATE"}),
        (75, "phase", {"state": "SEARCH_MARKER"}),
        (95, "marker_lost", {}),
        (96, "abort", {"reason": "MARKER_LOST"}),
        (97, "phase", {"state": "RETURN_HOME"}),
        (108, "phase", {"state": "LANDING"}),
        (110, "mission_end", {"delivered": False, "reason": "MARKER_LOST"}),
    ]
    tel = []
    bats = _interp(24.7, 23.8, duration + 1)
    for s in range(duration + 1):
        if s < 5: alt = 0
        elif s < 20: alt = (s - 5) * 0.6
        elif s < 96: alt = 10 + (s % 7) * 0.4
        elif s < 108: alt = max(2, 12 - (s - 96) * 0.8)
        else: alt = 0
        fs = 1 if 96 <= s <= 108 else 0
        lat = BASE_LAT + 0.0004 * min(1, s/80)
        lon = BASE_LON + 0.00025 * min(1, s/80)
        tel.append((s, "GUIDED" if s < 96 else "RTL", alt, lat, lon, bats[s], fs))
    write_run(name, events, tel)


def main():
    RUNS.mkdir(exist_ok=True)
    # Çakışan eski demo'ları temizle
    for old in RUNS.glob("demo_*"):
        if old.is_dir():
            import shutil
            shutil.rmtree(old)
    # 5 farklı senaryo, kronolojik ts (saatler arası)
    base = time.strftime("%Y%m%d")
    happy_path(f"demo_{base}_01_happy")
    battery_abort(f"demo_{base}_02_battery_abort")
    face_mismatch(f"demo_{base}_03_face_mismatch")
    link_lost(f"demo_{base}_04_link_lost")
    marker_lost(f"demo_{base}_05_marker_lost")
    print("5 demo run oluşturuldu.")


if __name__ == "__main__":
    sys.exit(main() or 0)
