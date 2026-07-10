"""target_source.py — Hedef GPS koordinatını LoRa DIŞINDA bir kaynaktan oku.

Madde 1 (görev sadeleştirme, yarışma günü kararı): yer istasyonu GPS'i
arızalı ve yer istasyonu tamamen göstermelik hale getirildi (madde 2). Hedef
artık bilgisayardan/Jetson'ın kendisinden doğrudan verilir, LoRa üzerinden
DEĞİL. Öncelik sırası (ilk bulunan kazanır):

  1) CLI argümanları        --target-lat / --target-lon
  2) Ortam değişkenleri     KOKPIT_TARGET_LAT / KOKPIT_TARGET_LON
  3) onboard/configs/target.yaml dosyası

systemd servisi (kokpit-mc.service) `/etc/kokpit/target_gps` dosyasını
EnvironmentFile olarak yükler — uçuş öncesi hedefi değiştirmek için o
dosyayı düzenleyip servisi yeniden başlatmak yeterli (bkz.
docs/BAGLANTI_VE_DURUM.md).
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from typing import Optional

from packet_protocol import DeliveryRequest

TARGET_YAML_PATH = Path(__file__).parent / "configs" / "target.yaml"


def _parse_flat_yaml(text: str) -> dict:
    """Düz `key: value` satırları için minik parser (pyyaml gerektirmez,
    bkz. extrinsics.py'deki aynı desen)."""
    out: dict = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def _from_yaml(path: Optional[Path] = None) -> Optional[dict]:
    # Modül seviyesi TARGET_YAML_PATH'i çağrı anında oku (test monkeypatch
    # edebilsin diye default argüman olarak DEĞİL, gövdede çözülüyor).
    path = path if path is not None else TARGET_YAML_PATH
    if not path.exists():
        return None
    try:
        data = _parse_flat_yaml(path.read_text())
    except OSError:
        return None
    return data or None


def _from_env() -> Optional[dict]:
    lat = os.environ.get("KOKPIT_TARGET_LAT")
    lon = os.environ.get("KOKPIT_TARGET_LON")
    if lat is None or lon is None:
        return None
    return {
        "lat": lat, "lon": lon,
        "alt": os.environ.get("KOKPIT_TARGET_ALT", "0"),
        "recipient_id": os.environ.get("KOKPIT_TARGET_RECIPIENT", "0"),
    }


def build_arg_parser(
        parser: Optional[argparse.ArgumentParser] = None) -> argparse.ArgumentParser:
    parser = parser or argparse.ArgumentParser(
        description="Kokpit görev yazılımı — hedef GPS bilgisayardan verilir (madde 1)")
    parser.add_argument(
        "--target-lat", type=float, default=None,
        help="Hedef enlem (derece) — verilirse env/yaml'dan önceliklidir")
    parser.add_argument(
        "--target-lon", type=float, default=None,
        help="Hedef boylam (derece)")
    parser.add_argument(
        "--target-alt", type=float, default=0.0,
        help="Hedef irtifa (AMSL, m) — sadece kayıt amaçlı, uçuş irtifası "
             "config.flight'tan gelir")
    parser.add_argument(
        "--target-recipient", type=int, default=0,
        help="Alıcı ID — biyometrik doğrulama bypass'lı olduğu için (madde 4) "
             "davranışı etkilemez, sadece loglama/kayıt amaçlı")
    return parser


def resolve_target(args: Optional[argparse.Namespace] = None) -> DeliveryRequest:
    """Hedefi CLI > env > target.yaml sırasıyla çözer.

    Hiçbiri yoksa RuntimeError fırlatır — gerçek uçuşta (main()) bu bilinçli
    bir sert hata: hedefsiz kalkış YAPILMAMALI.
    """
    if args is not None and args.target_lat is not None and args.target_lon is not None:
        return DeliveryRequest(
            lat=args.target_lat, lon=args.target_lon, alt=args.target_alt,
            recipient_id=args.target_recipient, gps_fix=3, num_sats=12)

    env = _from_env()
    if env is not None:
        return DeliveryRequest(
            lat=float(env["lat"]), lon=float(env["lon"]), alt=float(env["alt"]),
            recipient_id=int(env["recipient_id"]), gps_fix=3, num_sats=12)

    y = _from_yaml()
    if y is not None and "lat" in y and "lon" in y:
        return DeliveryRequest(
            lat=float(y["lat"]), lon=float(y["lon"]),
            alt=float(y.get("alt", 0)),
            recipient_id=int(y.get("recipient_id", 0)),
            gps_fix=3, num_sats=12)

    raise RuntimeError(
        "Hedef GPS koordinatı bulunamadı — --target-lat/--target-lon, "
        "KOKPIT_TARGET_LAT/KOKPIT_TARGET_LON ortam değişkenleri veya "
        "onboard/configs/target.yaml sağlanmalı (madde 1 — yer istasyonu "
        "artık hedef göndermiyor)")
