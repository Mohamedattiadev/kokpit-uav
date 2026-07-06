#!/usr/bin/env bash
# İŞ-1 — Jetson'ı tam güce al + görev servisini otomatik başlat.
# Tek komutla çalışır, elle dosya düzenlemesi gerekmez (yollar otomatik bulunur).
#
# Kullanım:
#   bash scripts/is1_jetson_kurulum.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$REPO_DIR/.venv/bin/python3"
SERVICE_SRC="$REPO_DIR/systemd/kokpit-mc.service"
SERVICE_TMP="/tmp/kokpit-mc.service.generated"

echo "======================================================"
echo " İŞ-1 — Jetson TensorRT + Otomatik Başlatma Kurulumu"
echo "======================================================"
echo
echo "Bu script şunları otomatik yapacak:"
echo "  1) Jetson'ı tam güç moduna alacak (MAXN)"
echo "  2) Görev yazılımını 'her açılışta otomatik başlasın' olarak ayarlayacak"
echo "  3) Ayarların doğru olduğunu kontrol edecek"
echo
echo "Not: Bu işin FİZİKSEL bir tarafı yok — kablo bağlamana, bir şeyi"
echo "ölçmene ya da elle bir yere dokunmana gerek yok. Jetson'a klavye"
echo "monitörle veya SSH ile (uzaktan) bağlıysan bu script her ikisinde de"
echo "aynı şekilde çalışır."
echo
echo "Repo yolu otomatik bulundu: $REPO_DIR"
echo

if [[ ! -x "$VENV_PY" ]]; then
    echo "HATA: $VENV_PY bulunamadı."
    echo "Önce sanal ortamı (venv) kurman gerekiyor. Örnek:"
    echo "  cd $REPO_DIR && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

read -r -p "Devam etmek için Enter'a bas (iptal için Ctrl+C): " _

echo
echo "--- Adım 1/3: Jetson'ı tam güç moduna alıyorum (sudo şifresi isteyecek) ---"
sudo nvpmodel -m 0
sudo jetson_clocks
echo
echo "Kontrol: nvpmodel -q ->"
nvpmodel -q

echo
echo "--- Adım 2/3: Görev servisini kuruyorum (yollar otomatik dolduruluyor) ---"
sed \
    -e "s#^WorkingDirectory=.*#WorkingDirectory=$REPO_DIR#" \
    -e "s#^ExecStart=.*#ExecStart=$VENV_PY -m onboard.mission#" \
    "$SERVICE_SRC" > "$SERVICE_TMP"

echo "Oluşturulan servis dosyası (kontrol için):"
echo "  WorkingDirectory=$REPO_DIR"
echo "  ExecStart=$VENV_PY -m onboard.mission"
echo

sudo cp "$SERVICE_TMP" /etc/systemd/system/kokpit-mc.service
sudo systemctl daemon-reload
sudo systemctl enable --now kokpit-mc
rm -f "$SERVICE_TMP"

echo
echo "--- Adım 3/3: Çalıştığını kontrol ediyorum ---"
sleep 2
if systemctl is-active --quiet kokpit-mc; then
    echo "OK: kokpit-mc servisi ÇALIŞIYOR (active)."
else
    echo "UYARI: Servis aktif görünmüyor. Son loglar:"
    journalctl -u kokpit-mc -n 40 --no-pager || true
    echo
    echo "Sorun giderme için: docs/DONANIM_PLANI.md -> İŞ-1 -> 'Sorun Giderme' tablosu"
    exit 1
fi

echo
echo "Son 15 log satırı:"
journalctl -u kokpit-mc -n 15 --no-pager || true

echo
echo "======================================================"
echo " İŞ-1 TAMAM."
echo " Canlı logları izlemek istersen (durdurmak için Ctrl+C):"
echo "   journalctl -u kokpit-mc -f"
echo "======================================================"
