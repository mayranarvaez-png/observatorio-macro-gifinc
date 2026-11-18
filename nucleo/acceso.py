"""Modo público del tablero.

Cuando el tablero se publica para estudiantes, cualquier visitante comparte el mismo servidor. Por eso
las acciones que **modifican los datos guardados** (descargar de nuevo todas las fuentes e importar la
corrida del cuaderno de betas) se ocultan, salvo para quien conozca la clave de administración.

Cómo activarlo (en Streamlit Community Cloud: Settings → Secrets):

    publico = true
    admin_clave = "una-clave-larga"        # opcional; sin ella nadie ve las acciones de administración

También funciona con las variables de entorno OBSERVATORIO_PUBLICO=1 y OBSERVATORIO_ADMIN_CLAVE.
En uso local (sin esas variables) todo está disponible, como antes.
"""
from __future__ import annotations

import hmac
import os

import streamlit as st

_VERDADERO = ("1", "true", "si", "sí", "yes")


def _secreto(nombre: str):
    try:
        return st.secrets.get(nombre)
    except Exception:          # no hay archivo de secretos
        return None


def modo_publico() -> bool:
    valor = os.environ.get("OBSERVATORIO_PUBLICO") or _secreto("publico")
    return str(valor).strip().lower() in _VERDADERO


def es_admin() -> bool:
    """True en uso local, o en modo público si se ingresó la clave correcta."""
    return (not modo_publico()) or bool(st.session_state.get("_admin_ok"))


def panel_admin() -> None:
    """Campo de clave en la barra lateral (solo en modo público y si hay clave configurada)."""
    clave = _secreto("admin_clave") or os.environ.get("OBSERVATORIO_ADMIN_CLAVE")
    if not modo_publico() or not clave:
        return
    with st.sidebar.expander("Administración", icon=":material/lock:"):
        entrada = st.text_input("Clave", type="password", key="_admin_entrada")
        ok = bool(entrada) and hmac.compare_digest(entrada.encode(), str(clave).encode())
        st.session_state["_admin_ok"] = ok
        if entrada and not ok:
            st.caption("Clave incorrecta.")
