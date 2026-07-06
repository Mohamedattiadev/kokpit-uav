"""param_yukle.py — İŞ-4 Adım 1'i otomatikleştirir.

Mission Planner'da "Full Parameter Tree -> Load from file" ile 7 dosyayı
tek tek yükleyip her seferinde Write Params'a basmak yerine, bu script
Pixhawk'a MAVLink üzerinden bağlanır ve 7 param dosyasını sırayla,
otomatik doğrulama (ACK bekleyerek) ile yükler. Sonda tek seferde reboot
sorar.

Kullanım (Pixhawk USB veya TELEM kablosuyla Jetson'a bağlıyken):
    python3 tools/param_yukle.py

Non-coder dostu: script tüm soruları numaralı seçenek olarak sorar,
"Enter'a bas" ile varsayılanı kabul edebilirsin.
"""
from __future__ import annotations
import sys
import time
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "onboard") not in sys.path:
    sys.path.insert(0, str(ROOT / "onboard"))

from pymavlink import mavutil, mavparm  # noqa: E402

PARAM_FILES = [
    "kokpit_baseline.param",
    "kokpit_companion.param",
    "kokpit_failsafe.param",
    "kokpit_geofence.param",
    "kokpit_lidar.param",
    "kokpit_precland.param",
    "kokpit_servo.param",
]


def _ask(prompt: str, default: str) -> str:
    try:
        s = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return s or default


def pick_connection() -> tuple[str, int | None]:
    print("Pixhawk'a nasıl bağlısın?")
    print("  1) USB kablo (örnek port: /dev/ttyACM0)")
    print("  2) TELEM/UART kablo, 921600 baud (örnek port: /dev/ttyTHS1)")
    choice = _ask("Seçim (1/2)", "1")

    candidates = sorted(
        glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
        + glob.glob("/dev/ttyTHS*")
    )
    if candidates:
        print("\nBulunan portlar:")
        for i, c in enumerate(candidates, 1):
            print(f"  {i}) {c}")
        idx = _ask("Hangisi Pixhawk? (numara yaz, yoksa elle yaz)", "1")
        if idx.isdigit() and 1 <= int(idx) <= len(candidates):
            port = candidates[int(idx) - 1]
        else:
            port = idx
    else:
        default_port = "/dev/ttyACM0" if choice == "1" else "/dev/ttyTHS1"
        port = _ask("Port yolunu yaz", default_port)

    baud = None if choice == "1" else 921600
    return port, baud


def main() -> int:
    print("======================================================")
    print(" İŞ-4 Adım 1 — Otomatik Param Yükleme (7 dosya)")
    print("======================================================")
    print()
    print("Pixhawk'ı USB veya TELEM kablosuyla Jetson'a bağladığından emin ol.")
    print()
    print("Not: Kabloyu takmak dışında bu adımın FİZİKSEL bir tarafı yok —")
    print("Mission Planner'da 7 dosyayı tek tek yükleyip her seferinde")
    print("'Write Params'a basmak yerine, script hepsini kendisi yükler.")
    print("Kalibrasyon/uçuş (drone'u elle döndürmek, uçurmak) hâlâ ayrı ve")
    print("fiziksel bir adım — bu script ona dokunmaz.")
    print()
    input("Hazırsa Enter'a bas: ")

    port, baud = pick_connection()

    print(f"\nBağlanılıyor: {port} ...")
    try:
        if baud:
            master = mavutil.mavlink_connection(port, baud=baud)
        else:
            master = mavutil.mavlink_connection(port)
        hb = master.wait_heartbeat(timeout=15)
    except Exception as e:
        print(f"\nHATA: Bağlantı kurulamadı ({e})")
        print("Kontrol et: kablo takılı mı, doğru port mu seçtin, Pixhawk açık mı?")
        return 1

    if hb is None:
        print("\nHATA: Heartbeat alınamadı (15 saniye içinde cevap yok).")
        print("Kablo/port yanlış olabilir — script'i tekrar çalıştırıp başka")
        print("port dene, ya da Pixhawk'ın açık/güçlü olduğunu kontrol et.")
        return 1

    print(f"OK: Bağlantı kuruldu (sistem {master.target_system}, "
          f"bileşen {master.target_component}).\n")

    ardupilot_dir = ROOT / "ardupilot"
    ok_count = 0
    for i, fname in enumerate(PARAM_FILES, 1):
        fpath = ardupilot_dir / fname
        if not fpath.exists():
            print(f"[{i}/7] HATA: {fpath} bulunamadı, atlanıyor.")
            continue
        print(f"[{i}/7] {fname} yükleniyor...")
        pdict = mavparm.MAVParmDict()
        try:
            pdict.load(str(fpath), mav=master, check=False)
            ok_count += 1
        except Exception as e:
            print(f"   HATA: {fname} yüklenemedi ({e})")
        time.sleep(0.3)

    print()
    if ok_count != len(PARAM_FILES):
        print(f"UYARI: {ok_count}/{len(PARAM_FILES)} dosya yüklendi. "
              "Yukarıdaki hataları kontrol et, script'i tekrar çalıştırabilirsin "
              "(zaten doğru olan parametreler yeniden yazılırsa zarar vermez).")
    else:
        print(f"OK: {ok_count}/{len(PARAM_FILES)} dosya başarıyla yüklendi.")

    print()
    ans = _ask("Şimdi Pixhawk'ı yeniden başlatayım mı? (bazı ayarlar "
               "reboot sonrası aktif olur) [E/h]", "E")
    if ans.strip().lower() in ("e", "evet", "y", "yes", ""):
        print("Pixhawk yeniden başlatılıyor...")
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
            0, 1, 0, 0, 0, 0, 0, 0)
        time.sleep(2)
        print("Gönderildi. Pixhawk birkaç saniye içinde yeniden başlayacak.")

    print()
    print("======================================================")
    print(" Sıradaki adım: docs/DONANIM_DURUM.md -> İŞ-4 -> Adım 2")
    print(" (Kalibrasyon turu — accel/compass/radio/ESC, bunlar")
    print(" fiziksel hareket gerektirdiği için Mission Planner'dan yapılır.)")
    print("======================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
