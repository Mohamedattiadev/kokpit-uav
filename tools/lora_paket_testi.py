"""lora_paket_testi.py — İŞ-3 Adım 2'yi otomatikleştirir.

Yer istasyonundaki butona kaç kere basıldığını ve kaç paketin Jetson'a
ULAŞTIĞINI elle saymak yerine, bu script gerçek LoRa alıcısını dinler ve
otomatik sayar (aynı `onboard/lora_receiver.py` kodu üzerinden — görev
yazılımının kullandığı gerçek alıcı).

Kullanım (LoRa E32 alıcısı Jetson'a USB/UART ile bağlıyken):
    python3 tools/lora_paket_testi.py
"""
from __future__ import annotations
import sys
import time
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "onboard") not in sys.path:
    sys.path.insert(0, str(ROOT / "onboard"))


def _ask(prompt: str, default: str) -> str:
    try:
        s = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return s or default


def pick_port() -> str:
    candidates = sorted(
        glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    )
    if candidates:
        print("Bulunan portlar:")
        for i, c in enumerate(candidates, 1):
            print(f"  {i}) {c}")
        idx = _ask("Hangisi LoRa alıcısı? (numara yaz, yoksa elle yaz)", "1")
        if idx.isdigit() and 1 <= int(idx) <= len(candidates):
            return candidates[int(idx) - 1]
        return idx
    return _ask("Port yolunu yaz (örnek: /dev/ttyUSB0)", "/dev/ttyUSB0")


def main() -> int:
    print("======================================================")
    print(" İŞ-3 Adım 2 — Otomatik LoRa Paket Sayacı")
    print("======================================================")
    print()
    print("LoRa alıcısının (E32 modülü) Jetson'a USB/UART ile bağlı")
    print("olduğundan emin ol.")
    print()
    print("Not: Kabloyu takmak ve yer istasyonundaki butona basmak hâlâ")
    print("senin işin — bunlar fiziksel, script onları yapamaz. Script")
    print("sadece, kaç paketin ulaştığını elle saymak yerine senin için")
    print("otomatik sayar.")
    print()
    input("Hazırsa Enter'a bas: ")

    port = pick_port()
    baud = int(_ask("Baud hızı (E32 varsayılanı 9600, değiştirmediysen "
                     "Enter'a bas)", "9600"))

    from lora_receiver import SerialLoRaReceiver  # noqa: E402

    try:
        recv = SerialLoRaReceiver(port, baud)
    except Exception as e:
        print(f"\nHATA: Port açılamadı ({e})")
        print("Kontrol et: kablo takılı mı, port doğru mu, başka bir "
              "program aynı portu kullanıyor olabilir mi (örn. Arduino IDE "
              "Serial Monitor açık kalmış olabilir, onu kapat).")
        return 1

    print(f"\nOK: {port} dinleniyor (baud={baud}).")
    print()
    print("Şimdi yer istasyonundaki BUTONA istediğin kadar bas")
    print("(doküman önerisi: 100 kere). Bitirince buraya dön ve Enter'a bas.")
    print("(İstersen basarken gelen paketleri canlı görebilirsin.)")
    print()
    input("Basmayı bitirince Enter'a bas: ")

    time.sleep(1.0)  # son paketlerin de ulaşmasına izin ver
    stats = recv.link_stats()
    recv.close()

    print()
    print("======================================================")
    print(" SONUÇ")
    print("======================================================")
    print(f"  Ulaşan paket sayısı : {stats['received']}")
    print(f"  Kayıp (tahmini)     : {stats['missed']}")
    print(f"  Kayıp oranı         : %{stats['packet_loss_pct']:.1f}")
    print()
    if stats['packet_loss_pct'] > 30:
        print("UYARI: Kayıp oranı %30'un üzerinde.")
        print("Kontrol et: anten bağlantısı, mesafe, aradaki engeller "
              "(metal/duvar). Bkz. docs/DONANIM_DURUM.md -> İŞ-3.")
    elif stats['received'] == 0:
        print("UYARI: Hiç paket ulaşmadı. Kontrol et:")
        print("  - ESP32 firmware yüklü ve çalışıyor mu?")
        print("  - LoRa modüllerinin kanal/adres/hava-hızı ayarları AYNI mı?")
        print("  - GPS fix yoksa ESP32 paket GÖNDERMEZ (bu normal, GPS "
              "fix bekle).")
    else:
        print("OK: Paketler ulaşıyor. Kayıp oranı kabul edilebilir seviyede.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
