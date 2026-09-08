"""Sin token, las otras dos apps tampoco dejan entrar.

Solo se comprueba la vía de denegación: es la que corta antes de cargar datos
y la que no depende de que el repo tenga los ficheros de datos al día.
"""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[2]
APPS = {
    "accessibility": ROOT / "accessibility" / "public_app.py",
    "vitoria": ROOT / "vitoria-bilbao" / "app.py",
}


@pytest.mark.parametrize("nombre", sorted(APPS))
def test_sin_token_no_entra(nombre):
    ruta = APPS[nombre]
    if not ruta.exists():
        pytest.skip(f"repo {nombre} no disponible")
    # AppTest no replica el sys.path que `streamlit run` da al script.
    if str(ruta.parent) not in sys.path:
        sys.path.insert(0, str(ruta.parent))
    app = AppTest.from_file(str(ruta), default_timeout=240)
    app.secrets["SSO_SECRET"] = "e" * 64
    app.secrets["PORTAL_URL"] = "https://portal.example"
    app.run()
    assert not app.exception
    assert any("portal" in message.value.lower() for message in app.error)
