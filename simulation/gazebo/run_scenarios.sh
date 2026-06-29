#!/usr/bin/env bash
# N2 — Gazebo SITL senaryo runner. CI gz binary yoksa skip.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/scenarios"

if ! command -v gz >/dev/null 2>&1 && ! command -v gazebo >/dev/null 2>&1; then
  echo "[SCENARIO] gz binary yok — skip"
  exit 0
fi

for s in 01_happy_path 02_marker_lost 03_face_mismatch 04_link_lost 05_battery_low 06_gps_lost; do
  echo "=== $s ==="
  python3 "$s.py" || { echo "FAIL: $s"; exit 1; }
done
echo "Tüm senaryolar geçti."
