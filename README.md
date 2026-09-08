# Portal de movilidad

Punto único de acceso a las tres aplicaciones de Streamlit: **Accesibilidad**,
**Vitoria — Bilbao** y **Enkarterri**. El usuario entra una vez aquí, elige
proyecto y pasa a la app correspondiente.

## Cómo funciona

El portal es el único sitio donde viven los usuarios y las contraseñas. Tras
autenticar, firma un token con HMAC-SHA256 (`sso.issue`) y enlaza a la app de
destino con ese token en la URL:

```
https://vitoria-bilbao.streamlit.app/?t=<token>
```

Cada app llama a `sso.require("<proyecto>")` antes de pintar nada: verifica la
firma con el mismo `SSO_SECRET`, comprueba la caducidad y que el proyecto esté
entre los concedidos. Las apps no guardan contraseñas ni conocen la lista de
usuarios: **altas y bajas se hacen solo aquí**.

`sso.py` es idéntico en los cuatro repos. Si lo cambias, cópialo a los cuatro.

### Lo que este diseño no es

No es SSO real, y conviene tenerlo presente:

- **El token viaja en la URL.** Con `SSO_TTL_HOURS = 8` recargar la app funciona,
  pero quien copie la URL completa entra sin contraseña hasta que caduque. Baja
  el TTL o pon `SSO_CLEAN_URL = true` en las apps si prefieres lo contrario
  (entonces recargar devuelve al portal).
- **No hay revocación.** Un token emitido vale hasta caducar. La única palanca es
  rotar `SSO_SECRET`, que invalida todos a la vez.
- **Los marcadores directos a una app no funcionan.** Sin token remiten al
  portal. Avisa al cliente de que guarde el marcador del portal.

## Configuración

Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y rellénalo.

```powershell
py tools\hash_password.py --secret        # genera SSO_SECRET
py tools\hash_password.py "micontraseña"  # genera el hash de un usuario
```

Los permisos por proyecto son la clave `projects` de cada usuario: una lista de
identificadores de `[apps.*]`, o `["*"]` para todos.

## Ejecución local

Los cuatro `secrets.toml` locales llevan `SSO_DEV_OPEN = true`, así que **en local
no hay login**: ni el portal pide credenciales ni las apps piden token.

```powershell
cd <ruta-de-tus-repos>\portal
py -m pip install -r requirements.txt
py -m streamlit run app.py                     # portal → localhost:8501
```

Cada app se levanta por su cuenta, en el puerto que el portal espera:

```powershell
py -m streamlit run ..\accessibility\public_app.py --server.port 8502
py -m streamlit run ..\vitoria-bilbao\app.py       --server.port 8503
py -m streamlit run ..\enkarterri\app.py           --server.port 8504
```

El flag solo surte efecto si el navegador pide la app a `localhost`: se comprueba
la cabecera `Host` y ante cualquier duda falla cerrado. Por eso no abriría nada
aunque el fichero acabase pegado en Community Cloud por error — pero aun así no
lo pegues allí.

Para probar el flujo real (login + token) en local, quita `SSO_DEV_OPEN` de los
cuatro ficheros. El usuario de ejemplo del portal es **demo / demo**.

## Despliegue

Regla de oro: **primero los secrets, después el código.** Poner un secreto en una
app que todavía no lo usa es inofensivo; desplegar el código sin el secreto deja
Enkarterri sin poder entrar.

### 1. Preparar los valores

```powershell
py tools\hash_password.py --secret            # SSO_SECRET, uno solo para todo
py tools\hash_password.py "clave-de-ana"      # un hash por usuario
```

Decide el subdominio del portal en Community Cloud (p. ej. `teknei-movilidad`):
su URL será `PORTAL_URL`.

### 2. Publicar el repo del portal

`git init`, commit y push a un repo nuevo de GitHub. **No subas
`.streamlit/secrets.toml`** — el `.gitignore` ya lo excluye.

### 3. Desplegar el portal

En share.streamlit.io → *New app*: repo `portal`, rama `main`, fichero principal
`app.py`, y el subdominio elegido. En *Advanced settings → Secrets*, pega el
contenido de `.streamlit/secrets.toml.example` ya relleno: `SSO_SECRET`,
`PORTAL_URL`, `SSO_TTL_HOURS`, los `[users.*]` reales y los `[apps.*]` con las
URLs **de producción**. Sin `SSO_DEV_OPEN`.

### 4. Dar el secreto a las tres apps

En cada una (App settings → Secrets), añade al principio del cuadro, **antes de
cualquier cabecera `[tabla]` que ya hubiera**:

```toml
SSO_SECRET = "<el mismo de arriba>"
PORTAL_URL = "https://teknei-movilidad.streamlit.app"
```

Si lo pegas al final, debajo de un `[pub_users.x]`, TOML lo mete dentro de esa
tabla y el token no validará nunca.

### 5. Subir el código de las tres apps

En cada repo hay que subir `sso.py` (nuevo) y el `app.py` / `public_app.py`
modificado. Al guardar los secrets, Community Cloud reinicia la app sola.

### 6. Comprobar

Entra al portal, autentícate y prueba las tres tarjetas. Después abre una app por
su URL directa sin token: debe mandarte al portal. Enkarterri, que hasta ahora
estaba abierta, ya no debe dejar pasar.

### 7. Limpiar

Borra los bloques `[pub_users]` y `[auth_cookie]` de los secrets de Accesibilidad
y Vitoria. El `_login()` que queda en el código solo actúa si falta `SSO_SECRET`,
y sin `[pub_users]` falla cerrado.

### Si algo va mal

- *"Entra desde el portal"* en una app a la que has llegado desde el portal: los
  `SSO_SECRET` no coinciden, o el de la app quedó dentro de una tabla TOML.
- *"Enlace no válido o caducado"*: el token expiró (`SSO_TTL_HOURS`), o la clave
  de `[apps.x]` en el portal no es la que la app pasa a `sso.require()`.
- Marcha atrás inmediata: quita `SSO_SECRET` de los secrets de Accesibilidad y
  Vitoria y vuelven a su login propio, siempre que no hayas hecho el paso 7.

## Tests

```powershell
py -m pytest tests -q
```

`test_sso.py` cubre la firma y la caducidad; `test_portal_app.py` el login, el
filtrado por permisos y el bloqueo por intentos; `test_gate_*.py` ejecutan las
apps reales con AppTest y comprueban que sin token no se entra y con token sí.
