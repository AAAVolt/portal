"""Comprobaciones del token firmado, sin levantar Streamlit."""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sso


@pytest.fixture(autouse=True)
def fake_secrets(monkeypatch):
    monkeypatch.setattr(sso.st, "secrets", {"SSO_SECRET": "a" * 64})


def test_roundtrip():
    token = sso.issue("bizkaibus", "Bizkaibus", ["vitoria"])
    claims = sso.verify(token, "vitoria")
    assert claims["u"] == "bizkaibus"
    assert claims["n"] == "Bizkaibus"


def test_rejects_other_project():
    token = sso.issue("demo", "Demo", ["enkarterri"])
    assert sso.verify(token, "vitoria") is None


def test_wildcard_grants_every_project():
    token = sso.issue("admin", "Admin", ["*"])
    assert sso.verify(token, "vitoria") is not None
    assert sso.verify(token, "accessibility") is not None


def test_rejects_expired():
    token = sso.issue("demo", "Demo", ["vitoria"], ttl_seconds=-1)
    assert sso.verify(token, "vitoria") is None


def test_rejects_tampered_payload():
    token = sso.issue("demo", "Demo", ["enkarterri"])
    forged = sso.issue("demo", "Demo", ["vitoria"])
    mixed = f"{forged.split('.')[0]}.{token.split('.')[1]}"
    assert sso.verify(mixed, "vitoria") is None


def test_rejects_wrong_secret(monkeypatch):
    token = sso.issue("demo", "Demo", ["vitoria"])
    monkeypatch.setattr(sso.st, "secrets", {"SSO_SECRET": "b" * 64})
    assert sso.verify(token, "vitoria") is None


def test_rejects_garbage():
    for junk in ("", "sin-punto", "!!!.abc", "YWJj.deadbeef"):
        assert sso.verify(junk, "vitoria") is None


def test_verify_without_secret(monkeypatch):
    token = sso.issue("demo", "Demo", ["vitoria"])
    monkeypatch.setattr(sso.st, "secrets", {})
    assert sso.verify(token, "vitoria") is None
    assert sso.portal_secret_ready() is False


def test_ttl_is_honoured():
    token = sso.issue("demo", "Demo", ["vitoria"], ttl_seconds=120)
    claims = sso.verify(token, "vitoria")
    assert 110 < claims["exp"] - time.time() <= 120
