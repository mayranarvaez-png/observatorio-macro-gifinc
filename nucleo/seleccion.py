"""Selección de acciones compartida por las páginas «Comparador de acciones» y «Portafolio».

Incluye un explorador del catálogo (Colombia, Latinoamérica, EE. UU., Europa, Canadá y Hong Kong) con filtros por
país, índice, sector y tipo. La elección (acciones, periodo, moneda y referencia) se recuerda entre páginas.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from . import portafolio as pf, ui, universo, yahoo

REFERENCIAS = {
    "COLCAP (ETF ICOLCAP)": "ICOLCAP.CL",
    "S&P 500 (SPY)": "SPY",
    "Nasdaq-100 (QQQ)": "QQQ",
    "Mundo (ACWI)": "ACWI",
    "Mercados emergentes (EEM)": "EEM",
    "Europa (Euro Stoxx 50, FEZ)": "FEZ",
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
MAX_ACCIONES = 30
MAX_FILAS = 2000


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


@st.cache_data(show_spinner=False)
def catalogo() -> pd.DataFrame:
    """Catálogo unificado. Si no se ha generado con `actualizar_universo.py`, se arma con lo que haya en disco."""
    cat = universo.leer_catalogo()
    if cat is None:
        cat = universo.construir_catalogo(universo.leer(), None)
    cat = cat.fillna({"sector": "—", "mercado": "—", "listas": "", "tipo": "Acción", "pais": "Otro"})
    # Orden: primero las que pertenecen a un índice o a la BVC, luego el resto por nombre.
    prioridad = cat["listas"].str.contains("S&P 500|Nasdaq-100|BVC|ADR|FTSE|DAX|CAC|Stoxx|IBEX|MIB|AEX|SMI|TSX|Hang", regex=True)
    return cat.assign(_p=~prioridad).sort_values(["_p", "nombre"]).drop(columns="_p").reset_index(drop=True)


def etiquetas() -> dict[str, str]:
    cat = catalogo()
    return dict(zip(cat["ticker"], cat["ticker"] + " · " + cat["nombre"] + " (" + cat["pais"] + ")"))


def rf_por_defecto(base: str) -> float:
    """Tasa libre de riesgo anual para el Sharpe: TES 10A en pesos, Tesoro 10A en dólares."""
    serie = "tes_10" if base == "COP" else "ust_10"
    _, v = ui.ultimo(serie)
    return (v or 4.0) / 100


def _agregar(clave: str, nuevos: list[str]) -> None:
    llave = f"{clave}_tickers"
    actuales = st.session_state.get(llave, _mem("tickers", DEFECTO))
    juntos = list(dict.fromkeys(list(actuales) + nuevos))[:MAX_ACCIONES]
    st.session_state[llave] = juntos
    st.session_state["_mem_acc_tickers"] = juntos


def explorador(clave: str) -> list[str]:
    """Filtros y tabla del catálogo. Devuelve los tickers que cumplen los filtros (para el buscador)."""
    cat = catalogo()
    with st.expander("Explorar acciones por país, índice o sector", expanded=_mem("explorar_abierto", True),
                     icon=":material/travel_explore:"):
        conteo = cat["pais"].value_counts()
        conteo = conteo.reindex(["Colombia"] + [p for p in conteo.index if p != "Colombia"]).dropna().astype(int)
        f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
        paises = f1.multiselect("País", list(conteo.index), default=[p for p in _mem("paises", ["Colombia", "EE. UU."]) if p in conteo.index],
                                format_func=lambda p: f"{p} ({conteo[p]:,})".replace(",", "."), key=f"{clave}_paises",
                                help="Déjalo vacío para buscar en todos los países.")
        st.session_state["_mem_acc_paises"] = paises
        base = cat[cat["pais"].isin(paises)] if paises else cat
        listas_disp = sorted({l for v in base["listas"] for l in str(v).split("|") if l})
        listas = f2.multiselect("Índice o lista", listas_disp, key=f"{clave}_listas_f",
                                help="Por ejemplo S&P 500, Nasdaq-100, Bolsa de Colombia (BVC), FTSE 100, DAX…")
        if listas:
            base = base[base["listas"].apply(lambda v: any(l in str(v).split("|") for l in listas))]
        sectores = f3.multiselect("Sector", sorted(base["sector"].dropna().unique()), key=f"{clave}_sectores")
        if sectores:
            base = base[base["sector"].isin(sectores)]
        tipo = f4.selectbox("Tipo", ["Acciones", "ETF", "Todos"], key=f"{clave}_tipo")
        if tipo != "Todos":
            base = base[base["tipo"] == ("ETF" if tipo == "ETF" else "Acción")]
        texto = st.text_input("Buscar por nombre o ticker", key=f"{clave}_texto",
                              placeholder="p. ej. Meta, Amazon, Cibest, Ecopetrol, ASML, Nestlé")
        if texto.strip():
            q = texto.strip().lower()
            base = base[base["ticker"].str.lower().str.contains(q, regex=False) | base["nombre"].str.lower().str.contains(q, regex=False)]
        vista = base.head(MAX_FILAS)
        st.caption(f"{len(base):,} resultados".replace(",", ".")
                   + (f" (se muestran los primeros {MAX_FILAS:,}; afina los filtros)".replace(",", ".") if len(base) > MAX_FILAS else "")
                   + ". Marca las casillas de la izquierda y pulsa **Agregar**.")
        evento = st.dataframe(
            vista[["ticker", "nombre", "pais", "mercado", "sector", "listas", "tipo"]].rename(columns={
                "ticker": "Ticker", "nombre": "Empresa", "pais": "País", "mercado": "Mercado", "sector": "Sector",
                "listas": "Índice o lista", "tipo": "Tipo"}),
            hide_index=True, width="stretch", height=300, on_select="rerun", selection_mode="multi-row", key=f"{clave}_tabla")
        filas = list(getattr(getattr(evento, "selection", None), "rows", []) or [])
        nuevos = vista.iloc[filas]["ticker"].tolist() if filas else []
        st.button(f"Agregar {len(nuevos)} acción(es) seleccionada(s)" if nuevos else "Agregar las acciones seleccionadas",
                  disabled=not nuevos, type="primary", icon=":material/add:", on_click=_agregar, args=(clave, nuevos),
                  key=f"{clave}_agregar")
    return base["ticker"].head(MAX_FILAS).tolist()


def selector(clave: str, min_tickers: int = 1) -> Seleccion | None:
    filtrados = explorador(clave)
    etq = etiquetas()
    llave = f"{clave}_tickers"
    if llave not in st.session_state:
        st.session_state[llave] = list(_mem("tickers", DEFECTO))
    c1, c2 = st.columns([3, 1])
    elegidos = c1.multiselect(
        f"Acciones elegidas (hasta {MAX_ACCIONES})", options=list(dict.fromkeys(list(st.session_state[llave]) + filtrados)),
        accept_new_options=True, key=llave, format_func=lambda t: etq.get(t, t), max_selections=MAX_ACCIONES,
        help="Quita una acción con la X. También puedes escribir directamente cualquier símbolo de Yahoo Finance "
             "(p. ej. META, AMZN, PETR4.SA, ASML.AS, 7203.T) y pulsar Enter.")
    tickers = list(dict.fromkeys(_limpiar(t) for t in elegidos))
    anios = c2.selectbox("Historial", [3, 5, 10], index=[3, 5, 10].index(_mem("anios", 5)),
                         format_func=lambda a: f"{a} años", key=f"{clave}_anios")
    d1, d2, d3 = st.columns([2, 2, 1])
    base = d1.selectbox("Moneda de análisis", list(MONEDAS), format_func=MONEDAS.get,
                        index=list(MONEDAS).index(_mem("base", "COP")), key=f"{clave}_base",
                        help="Todas las series se convierten con el tipo de cambio semanal de Yahoo. "
                             "El retorno en pesos incluye el efecto cambiario de las acciones extranjeras.")
    ref_mem = _mem("ref", "COLCAP (ETF ICOLCAP)")
    nombre_ref = d2.selectbox("Índice de referencia", list(REFERENCIAS),
                              index=list(REFERENCIAS).index(ref_mem if ref_mem in REFERENCIAS else "COLCAP (ETF ICOLCAP)"),
                              key=f"{clave}_ref",
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
