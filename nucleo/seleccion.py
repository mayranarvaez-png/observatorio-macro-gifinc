"""Selección de acciones compartida por las páginas «Comparador de acciones» y «Portafolio».

La elección (tickers, periodo, moneda y referencia) se recuerda al pasar de una página a otra.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from . import almacen, mercado, portafolio as pf, ui, yahoo

REFERENCIAS = {
    "COLCAP (ETF ICOLCAP)": "ICOLCAP.CL",
    "S&P 500 (SPY)": "SPY",
    "Mercados emergentes (EEM)": "EEM",
    "Latinoamérica (ILF)": "ILF",
    "Brasil (EWZ)": "EWZ",
    "México (EWW)": "EWW",
    "Chile (ECH)": "ECH",
    "Perú (EPU)": "EPU",
    "Argentina (ARGT)": "ARGT",
}
MONEDAS = {"COP": "Pesos colombianos (COP)", "USD": "Dólares (USD)",
           "LOCAL": "Moneda local de cada acción (no comparable entre países)"}
DEFECTO = ["ECOPETROL.CL", "ISA.CL", "GRUPOSURA.CL", "NUTRESA.CL", "CEMARGOS.CL"]


@dataclass
class Seleccion:
    tickers: list[str]
    anios: int
    base: str
    referencia: str
    nombre_ref: str
    rf: float


def _mem(clave: str, defecto):
    return st.session_state.setdefault(f"_mem_acc_{clave}", defecto)


def _limpiar(t: str) -> str:
    return str(t).strip().upper()


def etiquetas() -> dict[str, str]:
    """ticker → «ticker · empresa (país)» para las acciones del cuaderno de betas."""
    emp = almacen.leer_empresas_propias()
    if emp is None:
        return {}
    return {r.ticker: f"{r.ticker} · {r.empresa} ({r.pais_es})" for r in emp.itertuples()}


def rf_por_defecto(base: str) -> float:
    """Tasa libre de riesgo anual para el Sharpe: TES 10A en pesos, Tesoro 10A en dólares."""
    serie = "tes_10" if base == "COP" else "ust_10"
    _, v = ui.ultimo(serie)
    return (v or 4.0) / 100


def selector(clave: str, min_tickers: int = 1) -> Seleccion | None:
    etq = etiquetas()
    c1, c2 = st.columns([3, 1])
    elegidos = c1.multiselect(
        "Acciones (símbolos de Yahoo Finance)", options=list(dict.fromkeys(list(etq) + _mem("tickers", DEFECTO))),
        default=_mem("tickers", DEFECTO), accept_new_options=True, key=f"{clave}_tickers",
        format_func=lambda t: etq.get(t, t), max_selections=15,
        help="Busca por nombre o ticker entre las 585 acciones del cuaderno, o escribe cualquier símbolo de Yahoo "
             "(p. ej. AAPL, MSFT, PETR4.SA, WALMEX.MX, SQM-B.SN). Las colombianas terminan en .CL.")
    tickers = list(dict.fromkeys(_limpiar(t) for t in elegidos))
    anios = c2.selectbox("Historial", [3, 5, 10], index=[3, 5, 10].index(_mem("anios", 5)),
                         format_func=lambda a: f"{a} años", key=f"{clave}_anios")
    d1, d2, d3 = st.columns([2, 2, 1])
    base = d1.selectbox("Moneda de análisis", list(MONEDAS), format_func=MONEDAS.get,
                        index=list(MONEDAS).index(_mem("base", "COP")), key=f"{clave}_base",
                        help="Todas las series se convierten con el tipo de cambio semanal de Yahoo. "
                             "El retorno en pesos incluye el efecto cambiario de las acciones extranjeras.")
    nombre_ref = d2.selectbox("Índice de referencia", list(REFERENCIAS),
                              index=list(REFERENCIAS).index(_mem("ref", "COLCAP (ETF ICOLCAP)")), key=f"{clave}_ref",
                              help="Se usa para el beta, la correlación y el alfa. ICOLCAP es el ETF que replica el COLCAP.")
    rf = d3.number_input("Tasa libre (%)", value=round(rf_por_defecto(base) * 100, 2), step=0.1,
                         key=f"{clave}_rf_{base}", help="TES 10A para COP; Tesoro 10A para USD o moneda local.") / 100
    st.session_state.update({"_mem_acc_tickers": tickers, "_mem_acc_anios": anios, "_mem_acc_base": base,
                             "_mem_acc_ref": nombre_ref})
    if len(tickers) < min_tickers:
        st.info(f"Elige al menos {min_tickers} acción{'es' if min_tickers > 1 else ''} para continuar.")
        return None
    return Seleccion(tickers, anios, base, REFERENCIAS[nombre_ref], nombre_ref, rf)


def cargar(sel: Seleccion):
    """Descarga (con caché) y arma precios, retornos y referencia. Devuelve None si no hay datos suficientes."""
    with st.spinner("Descargando precios de Yahoo Finance…"):
        px, metas, fallos = yahoo.panel(sel.tickers, sel.base, sel.anios)
        ref = yahoo.serie_en(sel.referencia, sel.base, sel.anios)
    if fallos:
        st.warning("No se encontraron datos para: **" + ", ".join(fallos) + "**. Revisa el símbolo (las colombianas "
                   "terminan en `.CL`) o intenta de nuevo más tarde si Yahoo limitó las peticiones.", icon=":material/warning:")
    if px.empty:
        st.error("Ninguno de los símbolos devolvió datos.")
        return None
    ref_px = None if ref is None else ref[0]
    if ref is None:
        st.caption(f"No se pudo descargar el índice de referencia ({sel.nombre_ref}); se omiten beta y alfa.")
    ret = pf.retornos(px)
    ret_ref = None if ref_px is None else pf.retornos(ref_px)
    return px, ret, ref_px, ret_ref, metas
