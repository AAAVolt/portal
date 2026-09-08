"""Portal de acceso a las aplicaciones de movilidad.

Único punto con usuarios y contraseñas: autentica, muestra los proyectos que
el usuario tiene asignados y enlaza a cada app con un token firmado.

Configura usuarios y apps en `.streamlit/secrets.toml` (ver secrets.toml.example).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from pathlib import Path

import streamlit as st

import sso

ASSET_DIR = Path(__file__).resolve().parent / "assets"
LOGO_FILE = ASSET_DIR / "logo-teknei.png"
FAVICON_FILE = ASSET_DIR / "teknei.com-favicon.ico"

st.set_page_config(
    page_title="Portal de movilidad",
    page_icon=str(FAVICON_FILE) if FAVICON_FILE.exists() else "🚌",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      [data-testid="stSidebar"] { display: none; }
      .portal-logo { text-align: center; margin: 1.5rem 0 0.5rem; }
      .portal-logo img { width: 150px; }
      .portal-sub { text-align: center; color: #6B7280; margin-bottom: 2rem; }
      .project-card h4 { margin: 0 0 .35rem; }
      .project-card p { color: #6B7280; font-size: .88rem; min-height: 3.2em; margin: 0 0 .75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Contraseñas ───────────────────────────────────────────────────────────────

def _scrypt_hash(plain: str, salt: bytes) -> str:
    return hashlib.scrypt(plain.encode(), salt=salt, n=16384, r=8, p=1).hex()


def _check_pw(plain: str, stored: str) -> bool:
    stored = stored.strip()
    if stored.startswith("scrypt$"):
        try:
            _, salt_hex, hash_hex = stored.split("$", 2)
        except ValueError:
            return False
        try:
            salt = bytes.fromhex(salt_hex)
        except ValueError:
            return False
        return hmac.compare_digest(_scrypt_hash(plain, salt), hash_hex.lower())
    # sha256 sin sal, heredado de las apps antiguas. Sigue aceptándose para no
    # obligar a repartir contraseñas nuevas el día de la migración.
    return hmac.compare_digest(hashlib.sha256(plain.encode()).hexdigest(), stored.lower())


_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 30


# ── Configuración ─────────────────────────────────────────────────────────────

def _users() -> dict:
    return {key: dict(value) for key, value in st.secrets.get("users", {}).items()}


def _apps() -> dict:
    return {key: dict(value) for key, value in st.secrets.get("apps", {}).items()}


def _ttl_seconds() -> int:
    return int(float(st.secrets.get("SSO_TTL_HOURS", 8)) * 3600)


def _logo_html() -> str:
    if not LOGO_FILE.exists():
        return ""
    b64 = base64.b64encode(LOGO_FILE.read_bytes()).decode()
    return f'<div class="portal-logo"><img src="data:image/png;base64,{b64}" alt="Teknei"></div>'


# ── Login ─────────────────────────────────────────────────────────────────────

def _login() -> dict | None:
    """Render the login form. Returns the user record once authenticated."""
    if session := st.session_state.get("_portal_user"):
        return session

    if sso.dev_open():
        # Desarrollo local: sin formulario y con todos los proyectos a la vista.
        st.session_state["_portal_user"] = {
            "id": "dev", "name": "Desarrollo local", "projects": ["*"],
        }
        return st.session_state["_portal_user"]

    users = _users()
    st.markdown(_logo_html(), unsafe_allow_html=True)

    if not users:
        st.error("No hay usuarios configurados. Revisa los secrets del portal.")
        st.stop()
    if not sso.portal_secret_ready():
        st.error("Falta `SSO_SECRET` en los secrets del portal.")
        st.stop()

    _, col, _ = st.columns([0.6, 1.4, 0.6])
    with col:
        st.markdown("### Acceso")

        lock_until = st.session_state.get("_portal_lock_until", 0.0)
        remaining = int(lock_until - time.time())
        locked = remaining > 0

        with st.form("portal_login"):
            username = st.text_input("Usuario", disabled=locked)
            password = st.text_input("Contraseña", type="password", disabled=locked)
            submitted = st.form_submit_button("Entrar", use_container_width=True, disabled=locked)

        if locked:
            st.warning(f"Demasiados intentos. Espera {remaining}s e inténtalo de nuevo.")
        elif submitted:
            record = users.get(username)
            if record and _check_pw(password, record.get("password", "")):
                st.session_state["_portal_user"] = {
                    "id": username,
                    "name": record.get("name", username),
                    "projects": list(record.get("projects", [])),
                }
                st.session_state.pop("_portal_attempts", None)
                st.session_state.pop("_portal_lock_until", None)
                st.rerun()
            else:
                attempts = st.session_state.get("_portal_attempts", 0) + 1
                st.session_state["_portal_attempts"] = attempts
                if attempts >= _MAX_ATTEMPTS:
                    st.session_state["_portal_lock_until"] = time.time() + _LOCKOUT_SECS
                    st.session_state["_portal_attempts"] = 0
                    st.error(f"Demasiados intentos. Acceso bloqueado {_LOCKOUT_SECS}s.")
                else:
                    st.error(
                        "Usuario o contraseña incorrectos "
                        f"({_MAX_ATTEMPTS - attempts} intentos restantes)."
                    )
    return None


# ── Selector de proyecto ──────────────────────────────────────────────────────

def _visible_projects(user: dict) -> list:
    apps = _apps()
    granted = user["projects"]
    if "*" in granted:
        return list(apps)
    return [key for key in apps if key in granted]


def _render_projects(user: dict) -> None:
    apps = _apps()
    visible = _visible_projects(user)

    st.markdown(_logo_html(), unsafe_allow_html=True)
    st.markdown(
        f'<div class="portal-sub">Bienvenido, <strong>{user["name"]}</strong>. '
        "Elige el proyecto al que quieres entrar.</div>",
        unsafe_allow_html=True,
    )

    if sso.dev_open():
        st.info("Modo desarrollo local: el login está desactivado (`SSO_DEV_OPEN`).")

    if not visible:
        st.warning("Tu usuario no tiene ningún proyecto asignado. Contacta con el administrador.")
    else:
        # El token se emite al pintar la tarjeta: link_button necesita la URL completa.
        ttl = _ttl_seconds()
        for row_start in range(0, len(visible), 2):
            for column, key in zip(st.columns(2), visible[row_start:row_start + 2]):
                config = apps[key]
                token = sso.issue(user["id"], user["name"], [key], ttl)
                url = f"{str(config['url']).rstrip('/')}/?t={token}"
                with column, st.container(border=True):
                    st.markdown(
                        f'<div class="project-card"><h4>{config.get("label", key)}</h4>'
                        f'<p>{config.get("description", "")}</p></div>',
                        unsafe_allow_html=True,
                    )
                    st.link_button("Entrar", url, use_container_width=True, type="primary")

        hours = ttl // 3600
        st.caption(
            f"El enlace de acceso caduca a las {hours} h. No lo compartas: "
            "durante ese tiempo permite entrar sin contraseña."
        )

    st.divider()
    _, col, _ = st.columns([1, 1, 1])
    with col:
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.clear()
            st.rerun()


user = _login()
if user:
    _render_projects(user)
