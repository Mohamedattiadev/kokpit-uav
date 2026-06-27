# 08 — GÖREV STATE MACHINE (Orchestrator)

## Bağlam (önce oku)
1. `Promptlar/00_system_overview.md`
2. `Promptlar/03_jetson_mission_computer.md` (MissionState + EventBus)
3. `Promptlar/04`, `05`, `06`, `07`, `09` (tüm alt modüllerin event'leri)

## Görev
Tüm sistemin "beyni". Event'leri dinler, state geçişlerini yapar, alt modüllere komut verir. Karar ağacı (decision tree) raporda tanımlandığı gibi:
- Marker tespiti başarısızsa → sarmal tarama
- Yüz eşleşmesi < %90 → teslimatı askıya al
- Pil kritik / link kayıp → RTL

## Açılışta Executor'a Sor (zorunlu)

1. **State machine kütüphanesi**: `transitions` (tavsiye — async destekli, basit) mi, `python-statemachine` mi, el yazımı (`match`/`case`) mi?
2. **Persistence**: State'i diske yazıp crash recovery yapsın mı (tavsiye: yarışma için gereksiz, skip), yoksa stateless restart mı?
3. **Abort davranışı**: Her abort RTL mi, kritik abort'larda LAND_HERE mi? *(Tavsiye: link/gps/battery → RTL; face_fail → LAND_HERE_SAFE; servo_fail → LAND_HERE)*
4. **Sarmal arama timeout**: 30 sn (tavsiye) sonra ABORT/RTL mi?
5. **Verification timeout**: VERIFYING fazında 20 sn'de yüz onaylanmazsa ABORT mi?

## State Diyagramı

```
       ┌──────┐
       │ IDLE │ ←──────────────────────┐
       └──┬───┘                        │
          │ lora.trigger               │
          ▼                            │
       ┌──────┐                        │
       │ ARMED│                        │
       └──┬───┘ arm OK                 │
          ▼                            │
       ┌────────┐                      │
       │TAKEOFF │                      │
       └──┬─────┘ alt_reached          │
          ▼                            │
       ┌──────────┐                    │
       │ EN_ROUTE │                    │
       └──┬───────┘ near_target        │
          ▼                            │
       ┌────────────┐                  │
       │ SEARCHING  │←──┐              │
       └──┬─────────┘   │              │
          │ marker_lock │ marker_lost  │
          ▼             │              │
       ┌──────────────┐ │              │
       │ APPROACHING  ├─┘              │
       └──┬───────────┘ alt < 1.5m     │
          ▼                            │
       ┌────────────┐                  │
       │ VERIFYING  │                  │
       └──┬─────────┘ face_verified    │
          ▼                            │
       ┌────────────┐                  │
       │ DELIVERING │ servo trigger    │
       └──┬─────────┘ servo_released   │
          ▼                            │
       ┌──────┐                        │
       │ RTL  │ at_home                │
       └──┬───┘                        │
          ▼                            │
       ┌────────┐                      │
       │LANDING │ landed_disarmed      │
       └──┬─────┘                      │
          ▼                            │
       ┌──────┐                        │
       │ DONE ├────────────────────────┘
       └──────┘

       Her state → ABORTED (failsafe trigger)
                      │
                      ▼
                   ┌─────┐
                   │ RTL │ (veya LAND_HERE)
                   └─────┘
```

## Implementasyon

```
jetson/mission_computer/src/kokpit/state_machine.py
```

```python
class MissionPhase(Enum):
    IDLE = auto()
    ARMED = auto()
    TAKEOFF = auto()
    EN_ROUTE = auto()
    SEARCHING = auto()
    APPROACHING = auto()
    VERIFYING = auto()
    DELIVERING = auto()
    RTL = auto()
    LANDING = auto()
    DONE = auto()
    ABORTED = auto()


class MissionOrchestrator:
    def __init__(self, state, bus, mav, servo, cfg):
        self.state, self.bus, self.mav = state, bus, mav
        self.servo = servo; self.cfg = cfg

    async def run(self):
        async for event in self.bus.subscribe_all():
            try:
                await self._handle(event)
            except Exception as e:
                log.exception("orchestrator error")
                await self._abort(f"exception:{e}")

    async def _handle(self, evt: Event):
        match (self.state.phase, evt.topic):
            case (MissionPhase.IDLE, "lora.trigger"):
                await self._begin_mission(evt.payload)
            case (MissionPhase.TAKEOFF, "mavlink.altitude_reached"):
                self.state.phase = MissionPhase.EN_ROUTE
                await self.mav.goto(self.state.target_lat,
                                    self.state.target_lon,
                                    self.cfg.approach_alt_m)
            case (MissionPhase.EN_ROUTE, "mavlink.waypoint_reached"):
                self.state.phase = MissionPhase.SEARCHING
            case (MissionPhase.SEARCHING, "aruco.detected"):
                self.state.phase = MissionPhase.APPROACHING
            case (MissionPhase.APPROACHING, "aruco.altitude_reached"):
                self.state.phase = MissionPhase.VERIFYING
            case (MissionPhase.VERIFYING, "face.verified"):
                self.state.phase = MissionPhase.DELIVERING
                await self.servo.release()
            case (MissionPhase.DELIVERING, "servo.released"):
                self.state.phase = MissionPhase.RTL
                await self.mav.rtl()
            case (MissionPhase.RTL, "mavlink.at_home"):
                self.state.phase = MissionPhase.LANDING
                await self.mav.land()
            case (MissionPhase.LANDING, "mavlink.disarmed"):
                self.state.phase = MissionPhase.DONE
            case (_, "failsafe"):
                await self._failsafe(evt.payload)

    async def _begin_mission(self, payload):
        self.state.target_lat = payload.lat
        self.state.target_lon = payload.lon
        self.state.ref_face_jpeg = payload.jpeg
        # face reference embedding hazır olana kadar bekle
        await self.bus.wait("face.ref_ready", timeout=3.0)
        await self.mav.set_mode("GUIDED")
        await self.mav.arm()
        self.state.phase = MissionPhase.TAKEOFF
        await self.mav.takeoff(self.cfg.takeoff_alt_m)
```

## Failsafe Karar Tablosu

| Failsafe | Mevcut Faz | Aksiyon |
|---|---|---|
| LINK_LOST | her | RTL |
| BATTERY < %25 | EN_ROUTE / SEARCHING / APPROACHING | RTL |
| BATTERY < %15 | her | LAND_HERE |
| GPS_LOST > 5sn | EN_ROUTE | LOITER + bekle, sonra RTL |
| MARKER_NOT_FOUND > 30sn | SEARCHING | RTL |
| FACE_NOT_VERIFIED > 20sn | VERIFYING | RTL (paket teslim ETME) |
| USER_ABORT | her | RTL |
| GEOFENCE | her | RTL |
| SERVO_FAIL | DELIVERING | LAND_HERE, manuel müdahale |

## Telemetri & Loglama
- Her state transition `MISSION_STATUS` LoRa paketi olarak yer istasyonuna gönderilir (modül 10)
- Tüm transitions JSON line log (`logs/mission_YYYYMMDD_HHMMSS.jsonl`)

## Testler
- `test_state_transitions.py`: her valid transition test edilir
- `test_invalid_transition.py`: VERIFYING'den IDLE'a doğrudan geçiş engellenir
- `test_failsafe_priority.py`: BATTERY_LOW vs USER_ABORT aynı anda → USER_ABORT öncelikli
- SITL: tam happy path simülasyon
- SITL: marker hiç bulunmuyor → sarmal → 30sn timeout → RTL
- SITL: yüz match etmiyor → RTL paket geri ile

## Kabul Kriterleri
- SITL'de happy path 10/10 başarı
- Her failsafe senaryosu için RTL/LAND tetiklenir
- State transition gecikme < 50 ms (event → action)

## GÜÇLENDİRMELER (AUDIT)

### G1. Task Cancellation (KRİTİK)
Her phase için `asyncio.TaskGroup`. Transition'da otomatik cancel:
```python
async def _enter_phase(self, new_phase):
    if self._phase_tg:
        self._phase_tg._aexit_called = True
        for t in self._phase_tg._tasks:
            t.cancel()
        await asyncio.gather(*self._phase_tg._tasks, return_exceptions=True)
    self.state.phase = new_phase
    self._phase_tg = asyncio.TaskGroup()
    async with self._phase_tg as tg:
        for coro in PHASE_TASKS[new_phase]:
            tg.create_task(coro(self.state, self.bus, self.mav))
```

### G2. Failsafe Priority Queue
Aynı anda birden fazla failsafe → tek priority winner:
```python
FAILSAFE_PRIORITY = {
    FailsafeKind.USER_ABORT:    100,
    FailsafeKind.CRASH:          95,
    FailsafeKind.BATTERY_CRT:    90,
    FailsafeKind.LINK_LOST:      80,
    FailsafeKind.BATTERY_LOW:    70,
    FailsafeKind.GPS_LOST:       60,
    FailsafeKind.MARKER_LOST:    50,
    FailsafeKind.FACE_TIMEOUT:   40,
    FailsafeKind.GEOFENCE:       30,
}
# pending_failsafes: heap; en yüksek priority her tick'te aksiyon
```

### G3. Crash Detection (KRİTİK)
RAW_IMU + ATTITUDE stream dinle:
```python
async def crash_monitor(state, mav, bus):
    async for att in mav.attitude_stream():
        if abs(degrees(att.roll)) > 45 or abs(degrees(att.pitch)) > 45:
            await bus.publish("failsafe", FailsafeKind.CRASH)
            await mav.force_disarm()
            return
    # IMU spike: |az| > 3g (g'siz koordinatta)
```

### G4. Reboot Recovery
```python
async def boot_recovery(state, mav):
    await mav.wait_heartbeat()
    current_mode = await mav.get_mode()
    if current_mode in ("AUTO", "GUIDED", "RTL", "LAND"):
        log.warning("Pixhawk mission active at boot; entering READ_ONLY")
        state.phase = MissionPhase.READ_ONLY
    else:
        state.phase = MissionPhase.IDLE
```

### G5. PILOT_OVERRIDE Faz
Yeni faz: pilot Manual/Stabilize'a alırsa state machine kendini kapatır, sadece telemetri okur. Pilot tekrar GUIDED'a alırsa IDLE'a döner.

### G6. Phase Timer Telemetri
Her faz için süre logla. 1 Hz `MISSION_STATUS` LoRa paketinde `phase_elapsed_s`.

## Verme
- Çalışan `state_machine.py`
- State diyagramı `docs/state_diagram.png` (Mermaid veya Graphviz)
- README: tüm transition'ların ve event'lerin matrisi
