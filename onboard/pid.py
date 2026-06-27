"""
pid.py — Anti-windup ve çıkış limitli PID denetleyici

Görsel servo (marker merkezleme) için kullanılır. Çıkış birimi m/s'dir ve
güvenlik için kırpılır. Türev terimi ölçüm üzerinden (derivative-on-error) ve
düşük geçiren filtre ile gürültüye karşı yumuşatılır.
"""
from __future__ import annotations
import time


class PID:
    def __init__(self, kp: float, ki: float, kd: float,
                 output_limit: float, integral_limit: float = 1.0,
                 deriv_filter: float = 0.5):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.output_limit = output_limit
        self.integral_limit = integral_limit
        self.deriv_filter = deriv_filter   # 0..1, büyük = daha çok yumuşatma
        self.reset()

    def reset(self):
        self._integral = 0.0
        self._prev_error = None
        self._prev_deriv = 0.0
        self._last_t = None

    def update(self, error: float, dt: float | None = None) -> float:
        now = time.monotonic()
        if dt is None:
            dt = (now - self._last_t) if self._last_t is not None else 0.0
        self._last_t = now
        if dt <= 0:
            dt = 1e-3

        # İntegral (anti-windup: clamp)
        self._integral += error * dt
        self._integral = _clip(self._integral, self.integral_limit)

        # Türev (filtreli)
        if self._prev_error is None:
            deriv = 0.0
        else:
            raw = (error - self._prev_error) / dt
            deriv = (self.deriv_filter * self._prev_deriv +
                     (1 - self.deriv_filter) * raw)
        self._prev_error = error
        self._prev_deriv = deriv

        out = self.kp * error + self.ki * self._integral + self.kd * deriv
        return _clip(out, self.output_limit)


def _clip(v: float, limit: float) -> float:
    return max(-limit, min(limit, v))
