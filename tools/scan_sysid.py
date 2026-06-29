"""N5 — MAVLink ağında aktif sysid'leri listele.

Yarışma sahasında 2+ takım yan yana uçarken sysid çakışması telemetri
karışmasına yol açar. Bu araç tek port üzerinde 10 sn boyunca tüm heartbeat
sysid'lerini toplar.
"""
from __future__ import annotations
import argparse
import sys
import time
from collections import Counter


def scan(conn_str: str, duration: float = 10.0) -> Counter:
    from pymavlink import mavutil
    master = mavutil.mavlink_connection(conn_str)
    seen: Counter = Counter()
    end = time.time() + duration
    while time.time() < end:
        msg = master.recv_match(type="HEARTBEAT", blocking=True, timeout=1.0)
        if msg is None:
            continue
        seen[msg.get_srcSystem()] += 1
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conn", default="udpin:0.0.0.0:14550")
    ap.add_argument("--duration", type=float, default=10.0)
    args = ap.parse_args()
    seen = scan(args.conn, args.duration)
    print(f"Süre: {args.duration}s, port: {args.conn}")
    print(f"Bulunan sysid sayısı: {len(seen)}")
    for sysid, count in seen.most_common():
        print(f"  sysid={sysid}  heartbeat={count}")
    return 0 if len(seen) <= 1 else 2  # çakışma varsa exit 2


if __name__ == "__main__":
    sys.exit(main())
