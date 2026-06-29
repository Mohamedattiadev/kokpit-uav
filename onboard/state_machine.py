"""
state_machine.py — Görev durumları ve geçiş çatısı

Rapor 2.1.4 "Level 4 otonomi" karar ağacını somutlaştıran durum makinesi.
mission.py bu durumları sırayla işler; her durum bir sonraki durumu döndürür.
"""
from __future__ import annotations
import time
from enum import Enum, auto


class MissionState(Enum):
    IDLE = auto()              # bekleme
    WAIT_PACKET = auto()       # yer istasyonundan teslimat talebi bekle
    PREFLIGHT = auto()         # arm öncesi emniyet kontrolleri
    TAKEOFF = auto()           # otonom dikey kalkış
    NAVIGATE = auto()          # hedef GPS koordinatına git
    SEARCH_MARKER = auto()     # hedef üzeri ArUco ara (gerekirse sarmal)
    PRECISION_APPROACH = auto()# görsel servo ile merkezle + alçal (2-3 m)
    BIOMETRIC_VERIFY = auto()  # yüz doğrulama
    DROP_PACKAGE = auto()      # paket bırak
    RETURN_HOME = auto()       # RTL
    LANDING = auto()           # üsse iniş
    DISARM = auto()            # motorları kapat, görev bitti
    ABORT = auto()             # iptal: güvenli iniş / RTL
    MISSION_COMPLETE = auto()
    FAILED = auto()
    READ_ONLY = auto()         # mid-mission reboot: pilot/AP komutta, Jetson izler
    PILOT_OVERRIDE = auto()    # pilot kumandayı aldı (MANUAL/STABILIZE/ACRO)


# Geçerli geçişler (denetim/loglama için referans; mission.py uygular)
VALID_TRANSITIONS = {
    MissionState.IDLE: {MissionState.WAIT_PACKET, MissionState.ABORT,
                        MissionState.READ_ONLY, MissionState.PILOT_OVERRIDE},
    MissionState.WAIT_PACKET: {MissionState.PREFLIGHT, MissionState.TAKEOFF,
                               MissionState.FAILED, MissionState.ABORT},
    MissionState.PREFLIGHT: {MissionState.TAKEOFF, MissionState.FAILED, MissionState.ABORT},
    MissionState.TAKEOFF: {MissionState.NAVIGATE, MissionState.ABORT, MissionState.FAILED},
    MissionState.NAVIGATE: {MissionState.SEARCH_MARKER, MissionState.ABORT, MissionState.RETURN_HOME},
    MissionState.SEARCH_MARKER: {MissionState.PRECISION_APPROACH, MissionState.RETURN_HOME, MissionState.ABORT},
    MissionState.PRECISION_APPROACH: {MissionState.BIOMETRIC_VERIFY, MissionState.SEARCH_MARKER, MissionState.ABORT, MissionState.RETURN_HOME},
    MissionState.BIOMETRIC_VERIFY: {MissionState.DROP_PACKAGE, MissionState.RETURN_HOME, MissionState.ABORT},
    MissionState.DROP_PACKAGE: {MissionState.RETURN_HOME, MissionState.ABORT},
    MissionState.RETURN_HOME: {MissionState.LANDING, MissionState.ABORT},
    MissionState.LANDING: {MissionState.DISARM, MissionState.ABORT},
    MissionState.DISARM: {MissionState.MISSION_COMPLETE},
    MissionState.ABORT: {MissionState.RETURN_HOME, MissionState.LANDING, MissionState.FAILED, MissionState.DISARM},
    MissionState.MISSION_COMPLETE: set(),
    MissionState.FAILED: set(),
    MissionState.READ_ONLY: {MissionState.IDLE, MissionState.DISARM,
                             MissionState.ABORT, MissionState.MISSION_COMPLETE},
    MissionState.PILOT_OVERRIDE: {MissionState.IDLE, MissionState.READ_ONLY,
                                  MissionState.ABORT,
                                  MissionState.MISSION_COMPLETE},
}


class StateMachine:
    def __init__(self, initial: MissionState = MissionState.IDLE, logger=print):
        self.state = initial
        self.log = logger
        self.history: list[tuple[float, MissionState]] = [(time.time(), initial)]

    def transition(self, new_state: MissionState, force: bool = False) -> bool:
        """Geçerli geçişi uygula. Geçersiz + force=False ise REDDET (False döndür).

        Eski davranış sessizce force ediyordu — güvenlik açığı. Şimdi mission.py
        kasıtlı 'kestirme' geçişler için force=True geçmek zorunda.
        """
        if new_state == self.state:
            return True
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed and not force:
            self.log(f"[FSM] HATA: geçersiz geçiş {self.state.name} -> "
                     f"{new_state.name} REDDEDILDI (force kullanılmadı)")
            return False
        if new_state not in allowed and force:
            self.log(f"[FSM] UYARI: geçersiz geçiş {self.state.name} -> "
                     f"{new_state.name} (force ile yapıldı)")
        self.log(f"[FSM] {self.state.name} -> {new_state.name}")
        prev = self.state
        self.state = new_state
        self.history.append((time.time(), new_state))
        try:
            import event_logger as _evl
            _evl.emit("phase", state=new_state.name, prev=prev.name)
        except Exception:
            pass
        return True

    def is_terminal(self) -> bool:
        return self.state in (MissionState.MISSION_COMPLETE, MissionState.FAILED)
