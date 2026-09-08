"""La puerta de Enkarterri: sin token no se entra, con token válido sí.

Ejecuta la app real con AppTest, así que también detecta que `import sso`
está bien colocado y que la puerta va antes de cargar datos.
"""

import sys
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
ENKARTERRI = ROOT / "enkarterri" / "app.py"
SECRET = "c" * 64

sys.path.insert(0, str(ROOT / "portal"))
import sso


def _token(projects, ttl=3600):
    """Firma un token con SECRET sin depender de st.secrets."""
    import base64
    import hashlib
    import hmac
    import json

    body = json.dumps(
        {"u": "test", "n": "Test", "p": projects, "exp": int(time.time()) + ttl},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(body).decode().rstrip("=")
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _app():
    app = AppTest.from_file(str(ENKARTERRI), default_timeout=120)
    app.secrets["SSO_SECRET"] = SECRET
    app.secrets["PORTAL_URL"] = "https://portal.example"
    return app


@pytest.mark.skipif(not ENKARTERRI.exists(), reason="repo enkarterri no disponible")
def test_sin_token_no_entra():
    app = _app().run()
    assert not app.exception
    assert any("portal" in message.value.lower() for message in app.error)
    # La puerta corta antes del contenido: el título no llega a pintarse.
    assert not app.title


@pytest.mark.skipif(not ENKARTERRI.exists(), reason="repo enkarterri no disponible")
def test_token_de_otro_proyecto_no_entra():
    app = _app()
    app.query_params["t"] = _token(["vitoria"])
    app.run()
    assert not app.exception
    assert any("caducado" in message.value.lower() for message in app.error)
    assert not app.title


@pytest.mark.skipif(not ENKARTERRI.exists(), reason="repo enkarterri no disponible")
def test_token_caducado_no_entra():
    app = _app()
    app.query_params["t"] = _token(["enkarterri"], ttl=-10)
    app.run()
    assert not app.exception
    assert any("caducado" in message.value.lower() for message in app.error)


@pytest.mark.skipif(not ENKARTERRI.exists(), reason="repo enkarterri no disponible")
def test_token_valido_entra():
    app = _app()
    app.query_params["t"] = _token(["enkarterri"])
    app.run()
    assert not app.exception
    assert any("Enkarterri" in message.value for message in app.title)


@pytest.mark.skipif(not ENKARTERRI.exists(), reason="repo enkarterri no disponible")
def test_dev_open_en_local_entra_sin_token(monkeypatch):
    from types import SimpleNamespace

    import streamlit

    monkeypatch.setattr(streamlit, "context", SimpleNamespace(headers={"Host": "localhost:8504"}))
    app = _app()
    app.secrets["SSO_DEV_OPEN"] = True
    app.run()
    assert not app.exception
    assert any("Enkarterri" in message.value for message in app.title)


@pytest.mark.skipif(not ENKARTERRI.exists(), reason="repo enkarterri no disponible")
def test_dev_open_desplegado_no_entra(monkeypatch):
    from types import SimpleNamespace

    import streamlit

    monkeypatch.setattr(
        streamlit, "context", SimpleNamespace(headers={"Host": "enkarterri.streamlit.app"})
    )
    app = _app()
    app.secrets["SSO_DEV_OPEN"] = True
    app.run()
    assert not app.exception
    assert any("portal" in message.value.lower() for message in app.error)
    assert not app.title
