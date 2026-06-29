"""N6 — Hava durumu pre-check (Open-Meteo API, key gerekmez).

Rüzgar > 5 m/s, yağmur > 0.1 mm/h, görüş < 1000 m -> NO-GO.
Offline ise skip + uyarı. Preflight'tan çağrılabilir.
"""
from __future__ import annotations
import argparse
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class WeatherDecision:
    go: bool
    wind_ms: Optional[float]
    precip_mmh: Optional[float]
    visibility_m: Optional[float]
    reason: str = ""


WIND_LIMIT_MS = 5.0
PRECIP_LIMIT_MMH = 0.1
VISIBILITY_MIN_M = 1000.0


def evaluate(wind_ms: Optional[float], precip_mmh: Optional[float],
             visibility_m: Optional[float]) -> WeatherDecision:
    reasons = []
    if wind_ms is not None and wind_ms > WIND_LIMIT_MS:
        reasons.append(f"rüzgar {wind_ms:.1f} m/s > {WIND_LIMIT_MS}")
    if precip_mmh is not None and precip_mmh > PRECIP_LIMIT_MMH:
        reasons.append(f"yağmur {precip_mmh:.2f} mm/h > {PRECIP_LIMIT_MMH}")
    if visibility_m is not None and visibility_m < VISIBILITY_MIN_M:
        reasons.append(f"görüş {visibility_m:.0f} m < {VISIBILITY_MIN_M}")
    return WeatherDecision(
        go=len(reasons) == 0,
        wind_ms=wind_ms, precip_mmh=precip_mmh, visibility_m=visibility_m,
        reason="; ".join(reasons) if reasons else "tüm parametreler limit içinde",
    )


def fetch_open_meteo(lat: float, lon: float, timeout: float = 5.0) -> dict:
    """Open-Meteo current weather. Hata fırlatır."""
    import requests
    url = (f"https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           f"&current=wind_speed_10m,precipitation,visibility")
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def check(lat: float, lon: float, fetch_fn=fetch_open_meteo) -> WeatherDecision:
    try:
        data = fetch_fn(lat, lon)
        cur = data.get("current", {})
        return evaluate(
            wind_ms=cur.get("wind_speed_10m"),
            precip_mmh=cur.get("precipitation"),
            visibility_m=cur.get("visibility"),
        )
    except Exception as e:
        # Offline veya API hatası — skip + warn
        return WeatherDecision(
            go=True, wind_ms=None, precip_mmh=None, visibility_m=None,
            reason=f"API hata: {e} (skip)",
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    args = ap.parse_args()
    d = check(args.lat, args.lon)
    tag = "GO" if d.go else "NO-GO"
    print(f"{tag}: wind={d.wind_ms} precip={d.precip_mmh} vis={d.visibility_m}")
    print(f"reason: {d.reason}")
    return 0 if d.go else 1


if __name__ == "__main__":
    sys.exit(main())
