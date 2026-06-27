"""PID denetleyici testleri — yakınsama, çıkış limiti, anti-windup."""
from pid import PID


def test_output_limit_respected():
    pid = PID(kp=100, ki=0, kd=0, output_limit=1.5)
    assert pid.update(1000.0, 0.1) <= 1.5
    assert pid.update(-1000.0, 0.1) >= -1.5


def test_converges_to_zero():
    """1B konum kapatma: hata->hız->entegrasyon kararlı şekilde sıfıra gitmeli."""
    pid = PID(kp=0.6, ki=0.05, kd=0.20, output_limit=1.5, integral_limit=2.0)
    pos = 2.0
    dt = 1 / 15
    for _ in range(450):
        v = pid.update(-pos, dt)
        pos += v * dt
    assert abs(pos) < 0.15  # operasyonel tolerans (15 cm) içinde


def test_stable_no_oscillation():
    pid = PID(kp=0.6, ki=0.05, kd=0.20, output_limit=1.5, integral_limit=2.0)
    pos, dt, traj = 2.0, 1 / 15, []
    for _ in range(450):
        v = pid.update(-pos, dt)
        pos += v * dt
        traj.append(pos)
    last = traj[-75:]
    assert (max(last) - min(last)) < 0.05  # salınım yok


def test_integral_antiwindup():
    pid = PID(kp=0, ki=1.0, kd=0, output_limit=10.0, integral_limit=2.0)
    for _ in range(1000):
        out = pid.update(5.0, 0.1)
    assert abs(out) <= 2.0 + 1e-6  # integral clamp


def test_reset_clears_state():
    pid = PID(kp=1, ki=1, kd=1, output_limit=100)
    pid.update(5.0, 0.1)
    pid.reset()
    # reset sonrası ilk güncellemede türev sıfır kabul edilir
    out = pid.update(1.0, 0.1)
    assert out == 1.0 * pid.kp + pid.ki * (1.0 * 0.1)
