# faces/ — Kayıtlı Yüz Veri Seti (Biyometrik Doğrulama)

İHA, hedefte gördüğü kişiyi buradaki referans fotoğraflarla karşılaştırır.

## Dosya adlandırma

Her yetkili alıcı için bir referans fotoğraf koy:

```
faces/alici_<id>.jpg
```

`<id>`, yer istasyonunun (ESP32) gönderdiği `recipient_id` ile **aynı** olmalı.

Örnek:
```
faces/alici_7.jpg     # recipient_id = 7 olan kişi
faces/alici_3.jpg     # recipient_id = 3 olan kişi
```

## Fotoğraf önerileri

- Net, önden çekilmiş, iyi aydınlatılmış tek yüz.
- En az 300x300 px, yüz kareyi büyük ölçüde doldursun.
- Demo ışık koşullarına yakın çekilmiş olması doğruluğu artırır
  (rapor hedefi: farklı ışıkta +%90 doğruluk).

## Backend

- Üretim: `face_recognition` (dlib) — `pip install face_recognition`
- Kurulu değilse kod otomatik olarak hafif OpenCV yedeğine düşer (yalnızca
  geliştirme/test içindir, demo öncesi gerçek backend'i kur).

Eşik ve oylama ayarları: `onboard/config.py` → `FaceConfig`.
