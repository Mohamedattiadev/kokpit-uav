#!/usr/bin/env bash
# run_sitl.sh — ArduCopter SITL'i görev yazılımı için başlatır.
#
# Bu script, gerçek Pixhawk OLMADAN, bilgisayarında ArduCopter simülasyonunu
# çalıştırır. Görev yazılımı SITL'e udp:127.0.0.1:14551 üzerinden bağlanır
# (config.LinkConfig.mavlink_sim ile aynı).
#
# ÖN KOŞUL (bir kez): ArduPilot kaynağını kur
#   git clone --recurse-submodules https://github.com/ArduPilot/ardupilot
#   cd ardupilot && Tools/environment_install/install-prereqs-ubuntu.sh -y
#   . ~/.profile
# Belge: https://ardupilot.org/dev/docs/sitl-simulator-software-in-the-loop.html
#
# Kullanım:
#   ./run_sitl.sh                 # varsayılan konum (Ankara YBÜ civarı)
#   ./run_sitl.sh -L KSQL         # başka konum

set -e

# Ankara YBÜ yakını bir başlangıç konumu (lat,lon,alt,heading)
LOC="${KOKPIT_HOME:-39.942000,32.847000,900,0}"

# sim_vehicle.py PATH'te mi?
if ! command -v sim_vehicle.py >/dev/null 2>&1; then
  echo "HATA: sim_vehicle.py bulunamadı."
  echo "ArduPilot'u kurup PATH'e ekleyin (bkz. script başı)."
  echo "Örn: export PATH=\$PATH:\$HOME/ardupilot/Tools/autotest"
  exit 1
fi

echo "ArduCopter SITL başlatılıyor (konum: $LOC)"
echo "Görev yazılımı bağlantısı: udp:127.0.0.1:14551"
echo "Durdurmak için Ctrl-C."

# --out: companion (görev yazılımı) için ek MAVLink çıkışı
exec sim_vehicle.py -v ArduCopter \
  --custom-location="$LOC" \
  --out=udp:127.0.0.1:14551 \
  --map --console \
  "$@"
