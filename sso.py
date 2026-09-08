"""Acceso unificado entre el portal y las apps de proyecto.

El portal es el único que guarda usuarios y contraseñas. Tras autenticar,
firma un token con HMAC-SHA256 y lo pasa en la URL de la app de destino
(`?t=...`). Cada app verifica la firma con el mismo `SSO_SECRET`, comprueba
la caducidad y que el proyecto esté entre los permitidos. Las apps no
almacenan contraseñas ni conocen la lista de usuarios.

Este fichero es idéntico en los cuatro repos (portal, accessibility,
vitoria-bilbao, enkarterri). Si lo cambias, cópialo a los cuatro.

Secrets que usa (App settings → Secrets en Streamlit Community Cloud):

    SSO_SECRET     = "<64 hex>"   # obligatorio, el mismo en las cuatro apps
    PORTAL_URL     = "https://teknei-movilidad.streamlit.app"
    SSO_TTL_HOURS  = 8            # solo lo usa el portal, al emitir
    SSO_CLEAN_URL  = false        # true: borra el token de la URL al validar
                                  # (más seguro, pero recargar echa al portal)
    SSO_DEV_OPEN   = true         # salta el login. Solo en el secrets.toml
                                  # local: se ignora si la app no se sirve
                                  # desde localhost.

Genera el secreto con:  python tools/hash_password.py --secret
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import streamlit as st

_STATE_KEY = "_sso_claims"
_DEFAULT_PORTAL = "https://teknei-movilidad.streamlit.app"


# ── Secrets ───────────────────────────────────────────────────────────────────

def _secret() -> str:
    """Shared HMAC key, or "" when this deployment has not been configured."""
    return str(st.secrets.get("SSO_SECRET", "") or "")


def portal_secret_ready() -> bool:
    """True when this deployment has a shared secret configured."""
    return bool(_secret())


def portal_url() -> str:
    return str(st.secrets.get("PORTAL_URL", _DEFAULT_PORTAL)).rstrip("/")


def _served_from_localhost() -> bool:
    """True solo cuando el navegador ha pedido la app a localhost.

    Es la guarda de `SSO_DEV_OPEN`: si alguien pega por error un secrets con el
    flag en Community Cloud, la cabecera Host será el dominio público y el flag
    no abrirá nada. Ante cualquier duda, responde False (falla cerrado).
    """
    try:
        headers = st.context.headers or {}
        host = headers.get("Host") or headers.get("host") or ""
    except Exception:
        return False
    host = host.strip().lower()
    # Una dirección IPv6 llega entre corchetes ("[::1]:8501"), así que el puerto
    # no se puede recortar por el primer ":".
    host = host.partition("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}


def dev_open() -> bool:
    """True cuando hay que saltarse el login por desarrollo local."""
    return bool(st.secrets.get("SSO_DEV_OPEN", False)) and _served_from_localhost()


def _dev_claims(project: str) -> dict:
    return {"u": "dev", "n": "Desarrollo local", "p": ["*"],
            "exp": int(time.time()) + 12 * 3600}


# ── Token ─────────────────────────────────────────────────────────────────────

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def issue(user: str, name: str, projects: list, ttl_seconds: int = 8 * 3600) -> str:
    """Mint a signed token. Only the portal calls this."""
    secret = _secret()
    if not secret:
        raise RuntimeError("SSO_SECRET no configurado en el portal.")
    body = json.dumps(
        {"u": user, "n": name, "p": list(projects), "exp": int(time.time()) + int(ttl_seconds)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return f"{_b64e(body)}.{_sign(body, secret)}"


def verify(token: str, project: str) -> dict | None:
    """Return the claims when `token` is a valid pass for `project`, else None."""
    secret = _secret()
    if not secret or not token or "." not in token:
        return None
    encoded, signature = token.split(".", 1)
    try:
        body = _b64d(encoded)
    except Exception:
        return None
    # compare_digest sobre la firma: evita distinguir fallos por tiempo.
    if not hmac.compare_digest(signature, _sign(body, secret)):
        return None
    try:
        claims = json.loads(body)
        allowed = claims["p"]
        expires = int(claims["exp"])
    except Exception:
        return None
    if expires <= time.time():
        return None
    if project not in allowed and "*" not in allowed:
        return None
    return claims


# ── Puerta de entrada de cada app ─────────────────────────────────────────────

def _deny(message: str) -> None:
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.error(message)
        st.link_button("Ir al portal", portal_url(), use_container_width=True)
    st.stop()


def require(
    project: str,
    *,
    fallback=None,
    auth_key: str | None = None,
    name_key: str | None = None,
) -> dict:
    """Gate the app on a valid portal token. Stops the script when there is none.

    `fallback` is the app's own legacy login, used only while `SSO_SECRET` is
    absent — that keeps local development and a not-yet-migrated deployment
    working. `auth_key`/`name_key` mirror the claims into the session keys the
    app already reads, so the rest of the code needs no changes.
    """
    if dev_open():
        claims = st.session_state.get(_STATE_KEY) or _dev_claims(project)
        st.session_state[_STATE_KEY] = claims
        if auth_key:
            st.session_state[auth_key] = True
        if name_key:
            st.session_state[name_key] = claims["n"]
        return claims

    claims = st.session_state.get(_STATE_KEY)
    if not (claims and claims["exp"] > time.time()):
        claims = None
        token = st.query_params.get("t", "")

        if not _secret():
            # Despliegue sin SSO configurado todavía.
            if fallback is not None:
                if not fallback():
                    st.stop()
                claims = {
                    "u": "local",
                    "n": st.session_state.get(name_key or "", "") or "Local",
                    "p": [project],
                    "exp": int(time.time()) + 8 * 3600,
                }
            else:
                _deny("Acceso no configurado. Contacta con el administrador.")
        elif token:
            claims = verify(token, project)
            if claims is None:
                _deny("Enlace no válido o caducado. Vuelve a entrar desde el portal.")
        else:
            _deny("Entra desde el portal para acceder a este proyecto.")

        st.session_state[_STATE_KEY] = claims
        if st.secrets.get("SSO_CLEAN_URL", False) and "t" in st.query_params:
            del st.query_params["t"]

    if auth_key:
        st.session_state[auth_key] = True
    if name_key:
        st.session_state[name_key] = claims.get("n", claims.get("u", ""))
    return claims


def current_user() -> dict | None:
    return st.session_state.get(_STATE_KEY)


def logout() -> None:
    """Drop the session and send the browser back to the portal."""
    st.session_state.pop(_STATE_KEY, None)
    for legacy in ("_pub_auth", "_pub_name", "_vb_auth", "_vb_name"):
        st.session_state.pop(legacy, None)
    st.query_params.clear()
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url={portal_url()}">',
        unsafe_allow_html=True,
    )
    st.stop()
