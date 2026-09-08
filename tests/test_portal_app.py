"""El portal: login, filtrado de proyectos por usuario y bloqueo por intentos."""

import hashlib
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
SECRET = "d" * 64


def _hash(plain: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(plain.encode(), salt=salt, n=16384, r=8, p=1).hex()}"


def _app():
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.secrets["SSO_SECRET"] = SECRET
    app.secrets["PORTAL_URL"] = "https://portal.example"
    app.secrets["SSO_TTL_HOURS"] = 8
    app.secrets["users"] = {
        "demo": {"name": "Demo", "password": _hash("clave-demo"), "projects": ["enkarterri"]},
        "jefe": {"name": "Jefa", "password": _hash("clave-jefe"), "projects": ["*"]},
    }
    app.secrets["apps"] = {
        "accessibility": {"label": "Accesibilidad", "url": "https://a.example"},
        "vitoria": {"label": "Vitoria — Bilbao", "url": "https://v.example"},
        "enkarterri": {"label": "Enkarterri", "url": "https://e.example"},
    }
    return app


def _entrar(app, usuario, clave):
    app.text_input[0].set_value(usuario)
    app.text_input[1].set_value(clave)
    app.button[0].click().run()
    return app


def _texto(app) -> str:
    return " ".join(element.value for element in app.markdown)


def test_arranca_pidiendo_credenciales():
    app = _app().run()
    assert not app.exception
    assert len(app.text_input) == 2
    assert "Acceso" in _texto(app)


def test_credenciales_malas_no_entran():
    app = _entrar(_app().run(), "demo", "incorrecta")
    assert not app.exception
    assert any("incorrectos" in message.value for message in app.error)
    assert len(app.text_input) == 2


def test_usuario_restringido_solo_ve_su_proyecto():
    app = _entrar(_app().run(), "demo", "clave-demo")
    assert not app.exception
    texto = _texto(app)
    assert "Demo" in texto and "Enkarterri" in texto
    assert "Vitoria" not in texto and "Accesibilidad" not in texto


def test_comodin_ve_los_tres_proyectos():
    app = _entrar(_app().run(), "jefe", "clave-jefe")
    assert not app.exception
    texto = _texto(app)
    for etiqueta in ("Accesibilidad", "Vitoria — Bilbao", "Enkarterri"):
        assert etiqueta in texto


def test_bloqueo_tras_cinco_intentos():
    app = _app().run()
    for _ in range(5):
        _entrar(app, "demo", "incorrecta")
    assert any("bloqueado" in message.value.lower() for message in app.error)
    # Con el formulario bloqueado, la contraseña correcta tampoco pasa.
    _entrar(app, "demo", "clave-demo")
    assert len(app.text_input) == 2


def test_dev_open_en_local_salta_el_login(monkeypatch):
    from types import SimpleNamespace

    import streamlit

    monkeypatch.setattr(streamlit, "context", SimpleNamespace(headers={"Host": "localhost:8501"}))
    app = _app()
    app.secrets["SSO_DEV_OPEN"] = True
    app.run()
    assert not app.exception
    assert not app.text_input          # no hay formulario
    texto = _texto(app)
    assert "Desarrollo local" in texto
    for etiqueta in ("Accesibilidad", "Vitoria — Bilbao", "Enkarterri"):
        assert etiqueta in texto


def test_dev_open_desplegado_sigue_pidiendo_login(monkeypatch):
    from types import SimpleNamespace

    import streamlit

    monkeypatch.setattr(
        streamlit, "context", SimpleNamespace(headers={"Host": "teknei-movilidad.streamlit.app"})
    )
    app = _app()
    app.secrets["SSO_DEV_OPEN"] = True
    app.run()
    assert not app.exception
    assert len(app.text_input) == 2
