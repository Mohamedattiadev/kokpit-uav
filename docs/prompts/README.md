# Kokpit IHA — Yazılım Geliştirme Promptları

Bu klasör, projenin yazılım faz'ı için modül-başına Claude Code prompt'larını içerir. Her prompt bağımsız bir Claude oturumunda çalıştırılabilir, ancak hepsi `00_system_overview.md`'deki ortak sözleşmeye uyar.

## Çalıştırma Sırası (önerilen)

1. **00** — `00_system_overview.md` (sadece referans, çalıştırılmaz)
2. **02** — LoRa paket sözleşmesi (önce bu — diğer haberleşme modülleri buna bağlı)
3. **03** — Jetson görev bilgisayarı iskeleti
4. **01** — ESP32 yer istasyonu (paralel olabilir, 02 sonrası)
5. **07** — MAVLink köprüsü
6. **04** — Yüz tanıma (paralel)
7. **05** — ArUco visual servoing (paralel)
8. **06** — Sensör füzyonu (paralel)
9. **09** — Servo bırakma
10. **08** — State machine (tüm modülleri orkestre eder)
11. **10** — GCS / telemetri
12. **11** — SITL simülasyon (test ortamı, paralel başlatılabilir)

```
        02 ─┐
            ├─► 03 ─► 07 ─┬─► 05 ─┐
        01 ─┘             ├─► 04 ─┼─► 09 ─► 08 ─► 10
                          └─► 06 ─┘
                                                     ╰─ 11 (paralel)
```

## Çalıştırma Şekli

Her prompt'u açıp:
1. İçeriği kopyala.
2. İlgili klasörde (`firmware/esp32_ground/`, `jetson/mission_computer/`, vb.) yeni bir Claude Code oturumu başlat.
3. Prompt'u yapıştır.
4. Claude `00_system_overview.md` (ve varsa `packet_spec.md`) okuyacak.
5. Sana **netleştirme soruları** soracak — cevapla.
6. Kod üretip test koşacak.

## Kritik Kural

- `shared/protocol/` değişiklikleri **önce** yapılır, **sonra** o sözleşmeyi kullanan modüller güncellenir.
- Her modül kendi `tests/`'ini yazar.
- Hiçbir modül başka modülün dahili dosyasını import etmez — sadece `shared/`'dan veya `EventBus` üzerinden.

## Sözleşmeyi Değiştirmek

Bir modül başka modülün davranışına ihtiyaç duyup mevcut sözleşme yetmezse:
1. `shared/protocol/packet_spec.md` veya `00_system_overview.md` güncelle (PR).
2. Etkilenen modül prompt'larında değişiklik notu bırak.
3. İlgili modüllerin test'lerini güncelle.

## Yardımcı Komutlar

## Tek-Atımlık Mod (Single-Shot)

Multi-agent paralel geliştirme yerine, **tek bir Claude oturumunda** tüm sistemi üretmek istersen:

1. `MASTER_SYSTEM_PROMPT.md` yapıştır
2. Claude tek soru bloğuna cevap ister
3. Otomatik üretim + self-test
4. `make sitl-happy` ile doğrulama

`MASTER_SYSTEM_PROMPT.md` tüm 01–11 modüllerini subsume eder ve `AUDIT_GUCLENDIRMELER.md`'deki düzeltmeleri **default'tan** uygular.

## Audit / Güçlendirme

`AUDIT_GUCLENDIRMELER.md` — robotik/güvenli-uçuş bakış açısıyla 20 zayıf nokta ve fix. Her modül prompt'una "GÜÇLENDİRMELER" bölümü olarak işlendi.

```bash
# Tüm modüllerin testlerini koş
make test-all

# SITL ile happy path
make sitl-happy

# ESP32 build + flash
cd firmware/esp32_ground && pio run -t upload && pio device monitor
```
