"""#15 — Mission PDF report (jüri'ye sunulabilir).

runs/<ts>/events.jsonl + telemetry.csv -> runs/<ts>/report.md (+ pdf pandoc varsa).
"""
from __future__ import annotations
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


EVENT_TR = {
    "start": ("Görev başladı", "Mission started"),
    "takeoff": ("Drone havalandı", "Drone took off"),
    "cruise": ("Drone hedefe yöneldi", "Drone cruising to target"),
    "marker_locked": ("Yer işareti bulundu", "Ground marker located"),
    "marker_lost": ("Yer işareti kaybedildi", "Marker lost"),
    "face_match": ("Alıcı yüzü tanındı", "Recipient face matched"),
    "face_mismatch": ("Yüz eşleşmedi", "Face mismatch"),
    "package_delivered": ("Paket teslim edildi", "Package delivered"),
    "rtl_complete": ("Drone üsse döndü", "Drone returned to base"),
    "abort": ("Görev iptal edildi", "Mission aborted"),
    "land": ("İniş yapıldı", "Landing"),
    "mission_end": ("Görev sona erdi", "Mission ended"),
    "phase": ("Aşama değişti", "Phase changed"),
}


def _event_detail_human(ev: dict, lang: str) -> str:
    tr = lang == "tr"
    name = ev.get("event", "")
    if name == "takeoff" and "alt" in ev:
        return f"{float(ev['alt']):.0f} metre" if tr else f"{float(ev['alt']):.0f} m"
    if name == "face_match" and "confidence" in ev:
        pct = float(ev["confidence"]) * 100
        return f"%{pct:.0f} güven" if tr else f"{pct:.0f}% confidence"
    if name == "marker_locked" and "id" in ev:
        return f"işaret no {ev['id']}" if tr else f"marker id {ev['id']}"
    if name == "abort" and "reason" in ev:
        return f"sebep: {ev['reason']}" if tr else f"reason: {ev['reason']}"
    if name == "package_delivered" and "recipient_id" in ev:
        return f"alıcı {ev['recipient_id']}" if tr else f"recipient {ev['recipient_id']}"
    if name == "phase" and "state" in ev:
        return ev["state"]
    return ""


def build_report_md(run_dir: Path, lang: str = "tr") -> str:
    name = run_dir.name
    tr = lang == "tr"
    title = "Görev Raporu" if tr else "Mission Report"
    md = [f"# {title} — {name}", ""]
    events_path = run_dir / "events.jsonl"
    events = []
    first_ts = last_ts = None
    delivered = False
    abort_reason = ""
    if events_path.exists():
        for ln in events_path.read_text().splitlines():
            try:
                j = json.loads(ln)
            except Exception:
                continue
            events.append(j)
            t = j.get("ts")
            if t and first_ts is None:
                first_ts = t
            if t:
                last_ts = t
            if j.get("event") == "package_delivered":
                delivered = True
            if j.get("event") == "abort":
                abort_reason = j.get("reason", "abort")
    duration = int((last_ts - first_ts)) if (first_ts and last_ts) else 0
    tel_path = run_dir / "telemetry.csv"
    tel_rows = 0
    alts = []
    bats = []
    if tel_path.exists():
        with tel_path.open() as f:
            for row in csv.DictReader(f):
                try:
                    alts.append(float(row["alt_rel"]))
                    bats.append(float(row["battery_v"]))
                except Exception:
                    continue
        tel_rows = len(alts)

    # ---- Plain language summary ----
    parts = []
    m, s = divmod(duration, 60)
    if tr:
        parts.append(f"Görev {m} dakika {s} saniye sürdü." if m else f"Görev {s} saniye sürdü.")
    else:
        parts.append(f"Mission lasted {m} min {s} sec." if m else f"Mission lasted {s} sec.")
    if alts:
        parts.append(
            f"Drone en fazla {max(alts):.0f} metre yüksekliğe çıktı."
            if tr else f"Drone reached {max(alts):.0f} m altitude.")
    if any(e.get("event") == "marker_locked" for e in events):
        parts.append("Yer işareti tespit edildi." if tr else "Ground marker located.")
    face = next((e for e in events if e.get("event") == "face_match"), None)
    if face and "confidence" in face:
        c = float(face["confidence"]) * 100
        parts.append(
            f"Alıcının yüzü %{c:.0f} güvenle doğrulandı."
            if tr else f"Recipient face verified at {c:.0f}% confidence.")
    if delivered:
        parts.append("Paket başarıyla teslim edildi." if tr else "Package delivered successfully.")
    elif abort_reason:
        parts.append(
            f"Görev '{abort_reason}' nedeniyle iptal edildi."
            if tr else f"Mission was aborted due to '{abort_reason}'.")
    else:
        parts.append("Görev tamamlanmadı." if tr else "Mission did not complete.")
    if any(e.get("event") in ("rtl_complete", "mission_end") for e in events):
        parts.append("Drone başlangıç noktasına geri döndü." if tr else "Drone returned to base.")
    if bats:
        drop = bats[0] - bats[-1]
        if drop > 0.05:
            parts.append(
                f"Bataryanın {drop:.1f} voltu harcandı (başlangıç {bats[0]:.1f}V, sonuç {bats[-1]:.1f}V)."
                if tr else f"Battery consumed {drop:.1f}V (start {bats[0]:.1f}V, end {bats[-1]:.1f}V).")

    status_tr = "Başarılı teslimat" if delivered else (f"İptal — {abort_reason}" if abort_reason else "Tamamlanmadı")
    status_en = "Delivered" if delivered else (f"Aborted — {abort_reason}" if abort_reason else "Incomplete")
    md += [
        "## " + ("Özet" if tr else "Summary"), "",
        ("**Durum:** " if tr else "**Status:** ") + (status_tr if tr else status_en),
        "",
        " ".join(parts),
        "",
        "## " + ("Önemli rakamlar" if tr else "Key numbers"), "",
        f"- **{'Süre' if tr else 'Duration'}:** {m} dk {s} sn" if tr else f"- **Duration:** {m}m {s}s",
        f"- **{'En yüksek irtifa' if tr else 'Max altitude'}:** {max(alts):.1f} m" if alts else
        ("- **En yüksek irtifa:** —" if tr else "- **Max altitude:** —"),
        f"- **{'Olay sayısı' if tr else 'Event count'}:** {len(events)}",
        f"- **{'Telemetri satırı' if tr else 'Telemetry rows'}:** {tel_rows}",
    ]
    if bats:
        md.append(f"- **{'Batarya' if tr else 'Battery'}:** "
                  f"{bats[0]:.2f} V → {bats[-1]:.2f} V "
                  f"({'harcanan' if tr else 'used'} {bats[0]-bats[-1]:.2f} V)")
    md.append("")

    # ---- Event timeline (human friendly) ----
    md += ["## " + ("Olay zaman çizelgesi" if tr else "Event timeline"), "",
           "| " + ("Zaman" if tr else "Time") + " | " +
           ("Olay" if tr else "Event") + " | " +
           ("Detay" if tr else "Detail") + " |",
           "|---|---|---|"]
    for e in events:
        t = e.get("ts", 0)
        dt = int(t - first_ts) if first_ts else 0
        ev_name = e.get("event", "?")
        labels = EVENT_TR.get(ev_name, (ev_name, ev_name))
        label = labels[0] if tr else labels[1]
        if ev_name == "phase" and "state" in e:
            label = f"{'Aşama' if tr else 'Phase'}: {e['state']}"
        time_str = f"{dt // 60}:{dt % 60:02d}"
        detail = _event_detail_human(e, lang)
        md.append(f"| {time_str} | {label} | {detail} |")
    md.append("")

    return "\n".join(md)


def write_report(run_dir: Path, want_pdf: bool = True) -> dict:
    out = {"md": None, "pdf": None}
    md_text = build_report_md(run_dir)
    md_path = run_dir / "report.md"
    md_path.write_text(md_text)
    out["md"] = str(md_path)
    if want_pdf:
        try:
            subprocess.run(
                ["pandoc", str(md_path), "-o", str(run_dir / "report.pdf"),
                 "-V", "geometry:margin=1.5cm"],
                check=True, capture_output=True, timeout=20,
            )
            out["pdf"] = str(run_dir / "report.pdf")
        except (FileNotFoundError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired):
            pass  # pandoc yok — md yeterli
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    if not args.run_dir.exists():
        print(f"yok: {args.run_dir}", file=sys.stderr)
        return 2
    out = write_report(args.run_dir, want_pdf=not args.no_pdf)
    for k, v in out.items():
        if v:
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
