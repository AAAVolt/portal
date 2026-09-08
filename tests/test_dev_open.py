"""El atajo de desarrollo local y su guarda.

`SSO_DEV_OPEN` salta el login, así que lo importante es que no pueda abrir una
app desplegada: solo vale si el navegador ha pedido la app a localhost.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sso


def _host(monkeypatch, value):
    if value is None:
        monkeypatch.setattr(sso.st, "context", SimpleNamespace(headers=None))
    else:
        monkeypatch.setattr(sso.st, "context", SimpleNamespace(headers={"Host": value}))


@pytest.mark.parametrize("host", ["localhost:8501", "127.0.0.1:8502", "LOCALHOST", "[::1]:8501"])
def test_abre_en_localhost(monkeypatch, host):
    monkeypatch.setattr(sso.st, "secrets", {"SSO_DEV_OPEN": True})
    _host(monkeypatch, host)
    assert sso.dev_open() is True


@pytest.mark.parametrize("host", [
    "enkarterri.streamlit.app",
    "bizkaibus-accessibility.streamlit.app",
    "localhost.evil.com",
])
def test_no_abre_en_un_dominio_publico(monkeypatch, host):
    monkeypatch.setattr(sso.st, "secrets", {"SSO_DEV_OPEN": True})
    _host(monkeypatch, host)
    assert sso.dev_open() is False


def test_sin_flag_no_abre_ni_en_local(monkeypatch):
    monkeypatch.setattr(sso.st, "secrets", {})
    _host(monkeypatch, "localhost:8501")
    assert sso.dev_open() is False


def test_sin_cabeceras_falla_cerrado(monkeypatch):
    monkeypatch.setattr(sso.st, "secrets", {"SSO_DEV_OPEN": True})
    _host(monkeypatch, None)
    assert sso.dev_open() is False

    class Explota:
        @property
        def headers(self):
            raise RuntimeError("sin sesión")

    monkeypatch.setattr(sso.st, "context", Explota())
    assert sso.dev_open() is False
