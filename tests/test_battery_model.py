"""LiPoDischargeModel — 6S deşarj eğrisi birim testleri.

Kaynak: Grepow/HobbyKing LiPo deşarj eğrisi rehberleri (plato + diz şekli,
düşük SoC'de artan iç direnç/sag) — bkz. NEXT_SESSION araştırma notları.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "simulation"))

from battery_model import LiPoDischargeModel, HOVER_CURRENT_A  # noqa: E402


def test_full_battery_reports_nominal_voltage():
    m = LiPoDischargeModel()
    v = m.open_circuit_voltage()
    assert 24.5 <= v <= 25.5, "6S dolu paket ~25.2V (4.2V/hücre) civarında olmalı"


def test_voltage_monotonically_decreases_with_discharge():
    m = LiPoDischargeModel()
    prev = m.open_circuit_voltage()
    for _ in range(20):
        m.step(dt_s=60.0, current_a=HOVER_CURRENT_A)
        v = m.open_circuit_voltage()
        assert v <= prev + 1e-9, "deşarj arttıkça gerilim artmamalı (monoton azalan)"
        prev = v


def test_load_sag_reduces_terminal_voltage_below_ocv():
    m = LiPoDischargeModel()
    m.step(dt_s=600.0, current_a=HOVER_CURRENT_A)   # biraz deşarj et
    ocv = m.open_circuit_voltage()
    loaded = m.terminal_voltage(current_a=30.0)
    assert loaded < ocv, "yük altında gerilim sag nedeniyle OCV'nin altında olmalı"


def test_sag_worse_at_low_state_of_charge():
    """Araştırma bulgusu: düşük SoC'de iç direnç artar -> aynı akımda sag büyür."""
    m = LiPoDischargeModel()
    sag_full = m.open_circuit_voltage() - m.terminal_voltage(current_a=25.0)

    m2 = LiPoDischargeModel()
    m2.step(dt_s=1.0, current_a=m2.capacity_ah * 3600 * 0.9)  # ~%90 deşarj
    sag_low = m2.open_circuit_voltage() - m2.terminal_voltage(current_a=25.0)

    assert sag_low > sag_full, "boşalmış pakette sag, dolu pakete göre daha büyük olmalı"


def test_reaches_battery_low_before_critical_threshold():
    """Gerçekçi eğride, sabit hover akımıyla deşarj ederken SafetyConfig'in
    battery_low_voltage (22.0V) eşiği, battery_critical_voltage (21.0V)
    eşiğinden ÖNCE (daha az deşarjda) geçilmeli — failsafe kademesinin
    LOW->RTL, CRITICAL->LAND sırasını koruduğunu doğrular."""
    m = LiPoDischargeModel()
    t_low = t_crit = None
    t = 0.0
    while t < 3600 * 2 and (t_low is None or t_crit is None):
        m.step(dt_s=5.0, current_a=HOVER_CURRENT_A)
        t += 5.0
        v = m.terminal_voltage(HOVER_CURRENT_A)
        if t_low is None and v < 22.0:
            t_low = t
        if t_crit is None and v < 21.0:
            t_crit = t
    assert t_low is not None and t_crit is not None
    assert t_low < t_crit, "LOW eşiği CRITICAL'dan önce (daha erken zamanda) tetiklenmeli"


def test_estimated_remaining_time_decreases_with_discharge():
    m = LiPoDischargeModel()
    t0 = m.estimated_remaining_time_s(HOVER_CURRENT_A)
    m.step(dt_s=600.0, current_a=HOVER_CURRENT_A)
    t1 = m.estimated_remaining_time_s(HOVER_CURRENT_A)
    assert t1 < t0
