"""battery_model.py — Gerçekçi 6S LiPo deşarj eğrisi (yazılım simülasyonu).

Amaç: SITL'in kendi batarya fiziği SIM_BATT_VOLTAGE'ı onurlandırmadığından
(bkz. libraries/SITL/SIM_Aircraft.cpp update_battery yorumu — SITL MultiCopter
BATTERY_STATUS'u her zaman ~12.6V/3S sabit raporlar), gerçek 6S hücre
davranışını yazılım-içi fizik katmanında (sim_backend.FakeDrone) modelleyip
failsafe eşiklerini (battery_warn/low/critical_voltage) adım fonksiyonu
yerine zaman + akım çekişine bağlı gerçekçi bir eğriyle test edebiliyoruz.

Model iki parçadan oluşur (literatür: LiPo deşarj eğrisi "plato + diz"
şeklindedir — bkz. Grepow/HobbyKing LiPo deşarj eğrisi kaynakları):
  1) Açık devre gerilimi (OCV) vs. deşarj edilen kapasite yüzdesi (SoC) —
     hücre başına tipik LiPo eğrisi (4.2V dolu -> ~3.7V plato -> 3.0V diz).
  2) Yük altında gerilim çöküşü (sag) = I * R_iç. İç direnç SoC azaldıkça
     artar (araştırma: "düşük SoC'de sag daha belirgin" — bkz. rapor
     kaynakları/kaynak listesi).

Bu, gerçek donanımın yerini TUTMAZ — sadece failsafe zamanlama testlerini
step-function yerine gerçekçi bir eğriye karşı doğrulamak içindir."""
from __future__ import annotations
from dataclasses import dataclass

# Hücre başına OCV eğrisi: (deşarj edilen kapasite yüzdesi, OCV volt)
# Tipik 6S/1P LiPo (22.2V nominal, 4.20V dolu hücre) hücre-başı eğri noktaları.
_CELL_OCV_CURVE = [
    (0.00, 4.20), (0.05, 4.08), (0.10, 4.00), (0.20, 3.90),
    (0.30, 3.83), (0.40, 3.79), (0.50, 3.76), (0.60, 3.73),
    (0.70, 3.70), (0.80, 3.66), (0.85, 3.62), (0.90, 3.55),
    (0.93, 3.45), (0.96, 3.30), (0.98, 3.10), (1.00, 2.80),
]
CELLS = 6
NOMINAL_CAPACITY_AH = 7.0          # rapor: 7000 mAh
INTERNAL_RESISTANCE_OHM_FULL = 0.006 * CELLS   # ~6 mOhm/hücre dolu iken (6S paket)
INTERNAL_RESISTANCE_OHM_EMPTY = 0.018 * CELLS  # boşaldıkça iç direnç ~3x artar


def _interp(curve, x):
    if x <= curve[0][0]:
        return curve[0][1]
    if x >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return curve[-1][1]


@dataclass
class LiPoDischargeModel:
    """6S 7000mAh LiPo paket deşarj + yük-altı sag modeli."""
    capacity_ah: float = NOMINAL_CAPACITY_AH
    cells: int = CELLS
    discharged_ah: float = 0.0

    def step(self, dt_s: float, current_a: float) -> None:
        """current_a: paketten çekilen anlık akım (A, pozitif = deşarj)."""
        self.discharged_ah += max(0.0, current_a) * dt_s / 3600.0

    @property
    def state_of_charge(self) -> float:
        """0.0 (dolu) .. 1.0 (boş) — deşarj edilen kapasite oranı."""
        return min(1.0, self.discharged_ah / self.capacity_ah)

    def open_circuit_voltage(self) -> float:
        soc = self.state_of_charge
        return self.cells * _interp(_CELL_OCV_CURVE, soc)

    def internal_resistance_ohm(self) -> float:
        soc = self.state_of_charge
        return (INTERNAL_RESISTANCE_OHM_FULL +
                soc * (INTERNAL_RESISTANCE_OHM_EMPTY - INTERNAL_RESISTANCE_OHM_FULL))

    def terminal_voltage(self, current_a: float) -> float:
        """Yük altı klemens gerilimi = OCV - I * R_iç (sag)."""
        return max(0.0, self.open_circuit_voltage() - current_a * self.internal_resistance_ohm())

    def remaining_ah(self) -> float:
        return max(0.0, self.capacity_ah - self.discharged_ah)

    def estimated_remaining_time_s(self, current_a: float) -> float:
        """Mevcut akım çekişinde tahmini kalan uçuş süresi (s). current_a<=0 -> inf."""
        if current_a <= 1e-6:
            return float("inf")
        return (self.remaining_ah() / current_a) * 3600.0


# Tipik akım çekişi profilleri (rapor: 2:1 thrust/weight, 4x Sunnysky X4110S 400KV)
HOVER_CURRENT_A = 18.0      # sabit hover, 4 motor toplam tahmini
CRUISE_CURRENT_A = 22.0     # ileri uçuş (rapor cruise_speed_ms=5)
CLIMB_CURRENT_A = 32.0      # dikey tırmanma / VTOL kalkış tepe akımı
