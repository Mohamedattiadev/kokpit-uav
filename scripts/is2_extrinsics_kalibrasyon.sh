#!/usr/bin/env bash
# İŞ-2 — Kamera/Lidar ölçümünü gir + otomatik doğrula. Tek komut.
#
# Kullanım:
#   bash scripts/is2_extrinsics_kalibrasyon.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$REPO_DIR/.venv/bin/python3"

echo "======================================================"
echo " İŞ-2 — Kamera + Lidar Ölçüm Kalibrasyonu"
echo "======================================================"
echo
echo "Önce şerit metreyle ölçtüğün değerleri kağıda yazdığından emin ol"
echo "(bkz. docs/DONANIM_DURUM.md -> İŞ-2 -> Adım 2 ve Adım 3 tabloları)."
echo
echo "Not: Ölçümü bu script YAPMAZ — şerit metreyle ölçmek hâlâ senin işin,"
echo "onu kimse otomatikleştiremez. Bu script sadece, elindeki ölçüleri"
echo "yazılıma girme + doğrulama kısmını (dosya yazma, test çalıştırma,"
echo "sonucu kontrol etme) senin yerine yapar."
echo

if [[ ! -x "$VENV_PY" ]]; then
    echo "HATA: $VENV_PY bulunamadı. Önce venv kurulmalı:"
    echo "  cd $REPO_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

read -r -p "Ölçümler hazırsa Enter'a bas, başlayalım: " _

echo
"$VENV_PY" "$REPO_DIR/tools/calibrate_extrinsics.py"

echo
echo "--- Otomatik doğrulama çalışıyor ---"
cd "$REPO_DIR"
if KOKPIT_SIM=1 "$VENV_PY" -m pytest tests/test_extrinsics.py -q; then
    echo
    echo "======================================================"
    echo " İŞ-2 TAMAM — tüm testler PASSED."
    echo " Girilen değerler:"
    cat onboard/configs/extrinsics.yaml
    echo "======================================================"
else
    echo
    echo "HATA: Doğrulama testleri geçmedi. onboard/configs/extrinsics.yaml"
    echo "içinde bozuk bir değer olabilir. Script'i tekrar çalıştırıp"
    echo "ölçümleri yeniden gir."
    exit 1
fi
