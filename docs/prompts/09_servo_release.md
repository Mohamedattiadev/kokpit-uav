# 09 — PAKET BIRAKMA SERVO

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `Promptlar/07_mavlink_bridge.md` (`set_servo` API)
3. `Promptlar/08_mission_state_machine.md` (DELIVERING fazı)

## Görev
Servo motorlu paket bırakma mekanizmasını güvenli, doğrulanabilir şekilde tetikle. Yanlış tetiklenmeyi engelle, gerçekten serbest kaldığını doğrula (mümkünse).

## Açılışta Executor'a Sor (zorunlu)

1. **Servo bağlantı**: Pixhawk AUX OUT (tavsiye — failsafe ve PWM zaten autopilot kontrolünde) mı, Jetson GPIO PWM mi?
2. **AUX kanal numarası**: AUX1 (SERVO9) (tavsiye) mi, başka?
3. **PWM değerleri**: Kapalı=1000 µs, Açık=1900 µs (tavsiye, geniş aralık güvenli açılma garanti). Onay?
4. **Bekleme süresi**: Servo'ya komut → mekanik açılma 500 ms (tavsiye). Onay?
5. **Doğrulama sensörü**: Limit switch / hall sensor / yok mu? *(Yoksa: timer-based "released" varsay, ama state machine güvenli irtifada beklesin)*
6. **Idle güvenlik kilidi**: Boot'ta servo PWM zorla 1000 (kapalı). Onay?

## Mimari

```
jetson/mission_computer/src/kokpit/servo_release.py
```

```python
class ServoRelease:
    def __init__(self, mav: MAVBridge, state: MissionState, cfg):
        self.mav, self.state, self.cfg = mav, state, cfg
        self._released = False

    async def boot_safety(self):
        """Boot'ta servo'yu kilitle (kapalı poz)."""
        await self.mav.set_servo(self.cfg.servo.channel, self.cfg.servo.pwm_closed)
        log.info("servo locked to closed", pwm=self.cfg.servo.pwm_closed)

    async def release(self) -> bool:
        # 1. Ön-kontroller
        if self.state.phase != MissionPhase.DELIVERING:
            log.error("release called in wrong phase", phase=self.state.phase)
            return False
        if not self.state.face_verified:
            log.error("release blocked: face not verified")
            return False
        if not self.state.marker_locked:
            log.error("release blocked: marker not locked")
            return False
        alt = self.state.lidar_alt
        if alt is None or not (self.cfg.servo.min_alt_m <= alt <= self.cfg.servo.max_alt_m):
            log.error("release blocked: altitude out of safe band", alt=alt)
            return False

        # 2. Servo açık komut
        ok = await self.mav.set_servo(self.cfg.servo.channel, self.cfg.servo.pwm_open)
        if not ok:
            await event_bus.publish("failsafe", FailsafeKind.SERVO_FAIL)
            return False

        # 3. Mekanik açılma bekle
        await asyncio.sleep(self.cfg.servo.release_delay_s)

        # 4. (Opsiyonel) limit switch doğrulama — yoksa zaman tabanlı
        self._released = True
        await event_bus.publish("servo.released", None)

        # 5. 2 sn sonra servo'yu tekrar kapalı poz'a (mekanik aşınma)
        await asyncio.sleep(2.0)
        await self.mav.set_servo(self.cfg.servo.channel, self.cfg.servo.pwm_closed)
        return True
```

## Config (`configs/default.yaml` eki)
```yaml
servo:
  channel: 9              # AUX1 = SERVO9
  pwm_closed: 1000
  pwm_open: 1900
  release_delay_s: 0.5
  min_alt_m: 1.0          # Min güvenli teslimat irtifası
  max_alt_m: 2.5          # Üstte açma yasak (paket düşer)
```

## Güvenlik Katmanları
1. **Phase guard**: Sadece DELIVERING fazında
2. **Face guard**: `face_verified == True` zorunlu
3. **Marker guard**: `marker_locked == True` zorunlu
4. **Altitude guard**: 1.0–2.5 m bandı
5. **MAVLink ACK guard**: `set_servo` ACK alınmazsa SERVO_FAIL
6. **Boot lock**: Açılışta zorla kapalı

## Testler
- `test_servo_phase_guard.py`: yanlış fazda çağrı → False, servo komut gönderilmez
- `test_servo_altitude_guard.py`: alt=5m → blocked
- `test_servo_face_guard.py`: face_verified=False → blocked
- `test_servo_happy_path.py`: tüm guardlar OK → komut gönderilir, event publish edilir
- SITL: DELIVERING fazına geçildiğinde SERVO_OUTPUT_RAW.servo9_raw değişimini gözle

## Kabul Kriterleri
- Yanlış fazda kesinlikle tetiklenmez (10/10 test)
- DELIVERING'de güvenli koşullar varsa < 1 sn'de release
- ACK alınmadığı durumda SERVO_FAIL failsafe yayılır

## GÜÇLENDİRMELER (AUDIT)

### G1. Crash Pre-check (KRİTİK)
Release çağrıldığında ATTITUDE snapshot al:
```python
att = await mav.get_attitude()
if abs(degrees(att.roll)) > 15 or abs(degrees(att.pitch)) > 15:
    log.error("release blocked: drone tilted", roll=att.roll, pitch=att.pitch)
    return False
```
DELIVERING sırasında devrilme = paket düşmesi = hasar. Modül 08 G3 crash monitor zaten EMERGENCY_DISARM yapar; bu lokal check ek katman.

### G2. Servo ACK Zorunlu
`MAV_CMD_DO_SET_SERVO` sonrası `COMMAND_ACK` bekle (timeout 500 ms). ACK gelmezse SERVO_FAIL failsafe.

### G3. Mechanical Confirmation (mümkünse)
Limit switch / hall sensor varsa GPIO oku. Yoksa: `SERVO_OUTPUT_RAW.servo9_raw == pwm_open` MAVLink stream'den doğrula.

### G4. Boot Lock Idempotency
Boot'ta servo birden fazla kez 1000 µs'ye yazılır (mavlink_bridge ready olduktan sonra ek 2 kez 100 ms aralıkla).

## Verme
- Çalışan `servo_release.py`
- Config örnekleri
- README: servo kalibrasyonu, mekanik test prosedürü, ArduCopter SERVO9_* paramları
