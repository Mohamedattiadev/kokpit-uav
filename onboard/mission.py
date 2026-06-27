"""
mission.py — Kokpit otonom teslimat görevi: ana orkestratör

Tüm alt sistemleri (LoRa, MAVLink, ArUco, yüz tanıma, görsel servo, paket bırakma)
bir durum makinesinde birleştirir. Rapor 1.2.2 / 2.1.2 operasyonel akışını uygular:

  WAIT_PACKET -> TAKEOFF -> NAVIGATE -> SEARCH_MARKER -> PRECISION_APPROACH
  -> BIOMETRIC_VERIFY -> DROP_PACKAGE -> RETURN_HOME -> LANDING -> DISARM

Arka planda bir FAILSAFE izleyici batarya/geofence/link denetler; eşik aşılırsa
görevi güvenle sonlandırır (RTL/LAND). "Safety First" — drone düşmesin.

Çalıştırma:
  KOKPIT_SIM=1 python3 mission.py        # SITL (gerçek kamera/LoRa yoksa enjekte gerekir)
  KOKPIT_SIM=0 python3 mission.py        # gerçek donanım
SITL'de uçtan uca otomatik test için: simulation/test_mission_sitl.py
"""
from __future__ import annotations
import threading
import time
from typing import Optional

from config import CFG
from mavlink_interface import DroneController
from lora_receiver import open_lora, BaseLoRaReceiver
from aruco_detector import ArucoDetector, Detection
from face_verifier import FaceVerifier
from package_dropper import PackageDropper
from visual_servo import PrecisionApproach
from autonomous_takeoff import autonomous_takeoff
from state_machine import StateMachine, MissionState
from packet_protocol import DeliveryRequest


class Mission:
    def __init__(self, drone: Optional[DroneController] = None,
                 lora: Optional[BaseLoRaReceiver] = None,
                 camera=None, detector: Optional[ArucoDetector] = None,
                 verifier: Optional[FaceVerifier] = None,
                 dropper: Optional[PackageDropper] = None):
        self.drone = drone or DroneController()
        self.lora = lora
        self.camera = camera
        self.detector = detector or ArucoDetector()
        self.verifier = verifier or FaceVerifier()
        self.dropper = dropper
        self.fsm = StateMachine()
        self.target: Optional[DeliveryRequest] = None
        self.package_delivered = False   # görev boyunca kalıcı teslimat kaydı

        self._abort = False
        self._abort_reason = ""
        self._monitor_running = False
        self._monitor_thread: Optional[threading.Thread] = None

    # =====================================================================
    # Kurulum
    # =====================================================================
    def setup(self):
        errs = CFG.validate()
        if errs:
            print("[GÖREV] KONFIG HATALARI:", errs)
            raise RuntimeError("Konfigürasyon doğrulanamadı")

        self.drone.connect()
        if self.dropper is None:
            self.dropper = PackageDropper(self.drone)
        self.dropper.lock()                       # güvenli başlangıç
        if self.lora is None:
            self.lora = open_lora()
        n = self.verifier.load_dataset()
        if n == 0:
            print("[GÖREV] UYARI: kayıtlı yüz yok — biyometrik doğrulama başarısız olur")
        self._start_failsafe_monitor()

    def _ensure_camera(self):
        if self.camera is None:
            from camera import open_camera
            self.camera = open_camera()

    # =====================================================================
    # Failsafe izleyici (arka plan)
    # =====================================================================
    def _start_failsafe_monitor(self):
        self._monitor_running = True
        self._monitor_thread = threading.Thread(
            target=self._failsafe_loop, daemon=True)
        self._monitor_thread.start()

    def _failsafe_loop(self):
        s = CFG.safety
        while self._monitor_running:
            t = self.drone.telemetry()
            reason = None
            if not self.drone.link_alive() and t.last_heartbeat > 0:
                reason = "MAVLink link kaybı"
            elif t.battery_voltage > 0 and t.battery_voltage < s.battery_critical_voltage:
                reason = f"Kritik batarya {t.battery_voltage:.1f}V"
            elif (self.drone.home_lat is not None and t.lat != 0 and
                  self._dist_from_home(t) > s.geofence_radius_m):
                reason = "Geofence yarıçapı aşıldı"
            elif t.alt_rel > s.geofence_max_alt_m + 2:
                reason = f"Geofence irtifa aşıldı ({t.alt_rel:.0f}m)"
            if reason and not self._abort:
                self.request_abort(reason)
            time.sleep(0.5)

    def _dist_from_home(self, t) -> float:
        from mavlink_interface import haversine_m
        return haversine_m(t.lat, t.lon, self.drone.home_lat, self.drone.home_lon)

    def request_abort(self, reason: str):
        self._abort = True
        self._abort_reason = reason
        print(f"[FAILSAFE] !!! ABORT: {reason}")

    def abort_check(self) -> bool:
        # LoRa'dan gelen ABORT da dikkate alınır
        if self.lora and getattr(self.lora, "abort_requested", False):
            if not self._abort:
                self.request_abort("Yer istasyonu ABORT")
        return self._abort

    # =====================================================================
    # Ana döngü
    # =====================================================================
    def run(self) -> bool:
        self.fsm.transition(MissionState.WAIT_PACKET)
        mission_start = None
        try:
            while not self.fsm.is_terminal():
                st = self.fsm.state

                # Genel abort denetimi (terminal/iniş durumları hariç)
                if self.abort_check() and st not in (
                        MissionState.RETURN_HOME, MissionState.LANDING,
                        MissionState.DISARM, MissionState.ABORT):
                    self.fsm.transition(MissionState.ABORT, force=True)
                    continue

                if (mission_start and
                        time.time() - mission_start > CFG.safety.overall_mission_timeout_s
                        and st not in (MissionState.RETURN_HOME, MissionState.LANDING,
                                       MissionState.DISARM, MissionState.ABORT)):
                    self.request_abort("Genel görev zaman aşımı")
                    self.fsm.transition(MissionState.ABORT, force=True)
                    continue

                if st == MissionState.WAIT_PACKET:
                    self._do_wait_packet()
                    mission_start = time.time()
                elif st == MissionState.TAKEOFF:
                    self._do_takeoff()
                elif st == MissionState.NAVIGATE:
                    self._do_navigate()
                elif st == MissionState.SEARCH_MARKER:
                    self._do_search_marker()
                elif st == MissionState.PRECISION_APPROACH:
                    self._do_precision_approach()
                elif st == MissionState.BIOMETRIC_VERIFY:
                    self._do_biometric_verify()
                elif st == MissionState.DROP_PACKAGE:
                    self._do_drop()
                elif st == MissionState.RETURN_HOME:
                    self._do_return_home()
                elif st == MissionState.LANDING:
                    self._do_landing()
                elif st == MissionState.DISARM:
                    self._do_disarm()
                elif st == MissionState.ABORT:
                    self._do_abort()
                else:
                    break
            ok = self.fsm.state == MissionState.MISSION_COMPLETE
            print(f"[GÖREV] {'TAMAMLANDI' if ok else 'BAŞARISIZ'} "
                  f"(durum={self.fsm.state.name})")
            return ok
        finally:
            self._monitor_running = False

    # =====================================================================
    # Durum eylemleri
    # =====================================================================
    def _do_wait_packet(self):
        print("[GÖREV] Yer istasyonundan teslimat talebi bekleniyor...")
        req = self.lora.wait_for_delivery(timeout=None)
        if req is None:
            self.fsm.transition(MissionState.FAILED, force=True)
            return
        self.target = req
        self.fsm.transition(MissionState.TAKEOFF)

    def _do_takeoff(self):
        if not autonomous_takeoff(self.drone, CFG.flight.takeoff_altitude_m):
            self.request_abort("Kalkış başarısız")
            self.fsm.transition(MissionState.ABORT, force=True)
            return
        self.fsm.transition(MissionState.NAVIGATE)

    def _do_navigate(self):
        t = self.target
        print(f"[GÖREV] Hedefe gidiliyor: ({t.lat:.6f}, {t.lon:.6f}) "
              f"@ {CFG.flight.cruise_altitude_m} m")
        self.drone.goto_global(t.lat, t.lon, CFG.flight.cruise_altitude_m)
        start = time.time()
        while time.time() - start < CFG.safety.navigation_timeout_s:
            if self.abort_check():
                return
            d = self.drone.distance_to(t.lat, t.lon)
            if d <= CFG.flight.waypoint_accept_radius_m:
                print(f"[GÖREV] Hedefe varıldı (kalan {d:.1f} m)")
                self.fsm.transition(MissionState.SEARCH_MARKER)
                return
            time.sleep(0.5)
        print("[GÖREV] Navigasyon zaman aşımı")
        self.request_abort("Navigasyon zaman aşımı")
        self.fsm.transition(MissionState.ABORT, force=True)

    def _do_search_marker(self):
        self._ensure_camera()
        # Arama irtifasına alçal
        t = self.target
        print(f"[GÖREV] Arama irtifasına ({CFG.flight.search_altitude_m} m) iniliyor")
        self.drone.goto_global(t.lat, t.lon, CFG.flight.search_altitude_m)
        # Birkaç saniye marker tara
        scan_start = time.time()
        found = False
        while time.time() - scan_start < 6.0:
            if self.abort_check():
                return
            ok, frame = self.camera.read()
            det = self.detector.detect(frame) if ok else Detection(found=False)
            if det.found:
                found = True
                break
            time.sleep(0.05)
        if not found:
            # Sarmal arama
            pa = PrecisionApproach(self.drone, self.detector, self.camera,
                                   abort_check=self.abort_check)
            found = pa.spiral_search()
        if found:
            self.fsm.transition(MissionState.PRECISION_APPROACH)
        else:
            print("[GÖREV] Marker bulunamadı -> üsse dönüş")
            self.fsm.transition(MissionState.RETURN_HOME, force=True)

    def _do_precision_approach(self):
        self._ensure_camera()
        pa = PrecisionApproach(self.drone, self.detector, self.camera,
                               abort_check=self.abort_check)
        if pa.run(CFG.flight.drop_altitude_m):
            self.fsm.transition(MissionState.BIOMETRIC_VERIFY)
        else:
            if self.abort_check():
                return
            print("[GÖREV] Hassas yaklaşma başarısız -> üsse dönüş")
            self.fsm.transition(MissionState.RETURN_HOME, force=True)

    def _do_biometric_verify(self):
        self._ensure_camera()
        print(f"[GÖREV] Biyometrik doğrulama (alıcı {self.target.recipient_id})...")
        # Hover'da sabit kal
        self.drone.send_velocity_body(0, 0, 0)
        res = self.verifier.verify_with_voting(self.target.recipient_id, self.camera)
        if res.matched:
            print(f"[GÖREV] Kimlik DOĞRULANDI (güven {res.confidence:.2f})")
            self.fsm.transition(MissionState.DROP_PACKAGE)
        else:
            print("[GÖREV] Kimlik doğrulanamadı -> teslimat ASKIYA alındı, üsse dönüş")
            self.fsm.transition(MissionState.RETURN_HOME, force=True)

    def _do_drop(self):
        self.drone.send_velocity_body(0, 0, 0)
        self.dropper.drop()
        self.package_delivered = True
        # Bırakıştan sonra biraz yüksel (güvenli RTL için)
        print("[GÖREV] Bırakış sonrası yükseliyor")
        t = self.drone.telemetry()
        self.drone.goto_global(t.lat, t.lon,
                               CFG.flight.drop_altitude_m + CFG.flight.post_drop_climb_m)
        time.sleep(3.0)
        self.fsm.transition(MissionState.RETURN_HOME)

    def _do_return_home(self):
        print("[GÖREV] RTL — üsse dönüş")
        self.drone.set_mode("RTL")
        start = time.time()
        while time.time() - start < CFG.safety.navigation_timeout_s:
            t = self.drone.telemetry()
            if not t.armed:
                # RTL inişi tamamladı ve disarm oldu
                self.fsm.transition(MissionState.DISARM, force=True)
                return
            if t.alt_rel < 0.5:
                self.fsm.transition(MissionState.LANDING, force=True)
                return
            time.sleep(0.5)
        self.fsm.transition(MissionState.LANDING, force=True)

    def _do_landing(self):
        print("[GÖREV] İniş bekleniyor")
        if self.drone.telemetry().alt_rel > 0.5:
            self.drone.set_mode("LAND")
        start = time.time()
        while time.time() - start < 60:
            if not self.drone.telemetry().armed:
                break
            time.sleep(0.5)
        self.fsm.transition(MissionState.DISARM, force=True)

    def _do_disarm(self):
        self.drone.disarm()
        self.dropper.reset()
        self.fsm.transition(MissionState.MISSION_COMPLETE, force=True)

    def _do_abort(self):
        print(f"[GÖREV] ABORT işleniyor: {self._abort_reason}")
        # Kritik batarya/link ise RTL en güvenlisi (ArduPilot kendi failsafe'i de var)
        try:
            self.drone.set_mode("RTL")
        except Exception:
            self.drone.set_mode("LAND")
        # İniş/disarm bekle
        start = time.time()
        while time.time() - start < CFG.safety.navigation_timeout_s:
            if not self.drone.telemetry().armed:
                break
            time.sleep(0.5)
        self.fsm.transition(MissionState.DISARM, force=True)

    def close(self):
        self._monitor_running = False
        try:
            if self.camera:
                self.camera.release()
        except Exception:
            pass
        if self.lora:
            self.lora.close()
        self.drone.close()


def main():
    m = Mission()
    try:
        m.setup()
        m.run()
    finally:
        m.close()


if __name__ == "__main__":
    main()
