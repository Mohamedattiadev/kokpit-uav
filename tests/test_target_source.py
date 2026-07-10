"""target_source.py — madde 1: hedef GPS artık LoRa yerine bilgisayardan.

Öncelik: CLI > env > target.yaml. Hiçbiri yoksa RuntimeError.
"""
from __future__ import annotations
import os

import pytest

import target_source
from packet_protocol import DeliveryRequest


def _clear_env(monkeypatch):
    for k in ("KOKPIT_TARGET_LAT", "KOKPIT_TARGET_LON",
              "KOKPIT_TARGET_ALT", "KOKPIT_TARGET_RECIPIENT"):
        monkeypatch.delenv(k, raising=False)


def test_cli_args_take_priority(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("KOKPIT_TARGET_LAT", "1.0")
    monkeypatch.setenv("KOKPIT_TARGET_LON", "2.0")
    args = target_source.build_arg_parser().parse_args(
        ["--target-lat", "39.9", "--target-lon", "32.8"])
    t = target_source.resolve_target(args)
    assert isinstance(t, DeliveryRequest)
    assert t.lat == pytest.approx(39.9)
    assert t.lon == pytest.approx(32.8)


def test_env_used_when_no_cli_args(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("KOKPIT_TARGET_LAT", "39.925533")
    monkeypatch.setenv("KOKPIT_TARGET_LON", "32.866287")
    args = target_source.build_arg_parser().parse_args([])
    t = target_source.resolve_target(args)
    assert t.lat == pytest.approx(39.925533)
    assert t.lon == pytest.approx(32.866287)
    assert t.is_valid_fix(), "resolve_target sonucu is_valid_fix() geçmeli"


def test_missing_target_raises(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setattr(target_source, "TARGET_YAML_PATH",
                        target_source.Path("/nonexistent/target.yaml"))
    args = target_source.build_arg_parser().parse_args([])
    with pytest.raises(RuntimeError):
        target_source.resolve_target(args)


def test_yaml_fallback(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    p = tmp_path / "target.yaml"
    p.write_text("lat: 40.1\nlon: 29.0\nrecipient_id: 3\n")
    monkeypatch.setattr(target_source, "TARGET_YAML_PATH", p)
    args = target_source.build_arg_parser().parse_args([])
    t = target_source.resolve_target(args)
    assert t.lat == pytest.approx(40.1)
    assert t.lon == pytest.approx(29.0)
    assert t.recipient_id == 3
