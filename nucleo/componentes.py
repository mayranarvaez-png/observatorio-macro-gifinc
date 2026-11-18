"""Componentes interactivos compartidos por los módulos de análisis.

- `costo_de_capital_sector`: el estudiante elige el sector y el WACC se calcula solo
  con la beta de Damodaran, la prima de riesgo país y los datos de mercado del día.
- `escenario_macro`: trayectoria editable de PIB, inflación y TRM que alimenta las proyecciones.

Los valores elegidos se guardan en `st.session_state` para que el escenario y el sector
se conserven al pasar de una página a otra.
"""
from __future__ import annotations

import io
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import almacen, mercado, ui
from . import costo_capital as cc
from . import escenarios as esc

UNIVERSOS_DAMODARAN = {"emergentes": "Mercados emergentes", "global": "Global", "eeuu": "Estados Unidos"}
UNIVERSOS_PROPIOS = {"latam_propio": "LatAm propio (Yahoo Finance)",
                     "latam_combinado": "LatAm combinado (propio + Damodaran)"}
UNIVERSOS = {**UNIVERSOS_DAMODARAN, **UNIVERSOS_PROPIOS}


def universos_disponibles() -> dict[str, str]:
    """Los universos de Damodaran y, si ya se importó la corrida del cuaderno, los propios."""
    if almacen.leer_betas_propios() is None:
        return dict(UNIVERSOS_DAMODARAN)
    return dict(UNIVERSOS)


def betas_universo(universo: str):
    """Betas por industria del universo elegido (el combinado usa el τ fijado por el usuario)."""
    return almacen.leer_betas(universo, tau=_memoria("tau", None))


def etiqueta_fuente_beta(universo: str, sector: str, n: int) -> str:
    """Texto citable del origen de la beta."""
    if universo in UNIVERSOS_PROPIOS:
        meta = almacen.leer_meta_propia() or {}
        return (f"{UNIVERSOS[universo]}, corrida del {meta.get('fecha_corrida', '—')}: "
                f"{sector} ({n} empresas)")
    return f"Damodaran, {UNIVERSOS[universo]}: {sector} ({n} empresas)"


def _memoria(nombre: str, defecto):
    """Valor compartido entre páginas (sobrevive al cambio de página)."""
    return st.session_state.setdefault(f"_mem_{nombre}", defecto)


def _recordar(nombre: str, valor) -> None:
    st.session_state[f"_mem_{nombre}"] = valor


# =============================== COSTO DE CAPITAL ===================================
def costo_de_capital_sector(clave: str, sector_defecto: str = "Food Processing",
                            de_propio: float | None = None, kd_propio: float | None = None,
                            etiqueta_de: str = "", escenario: pd.DataFrame | None = None) -> dict | None:
    """Selector de sector → βU, βL, Ke, Kd y WACC automáticos (con ajuste opcional)."""
    pais = almacen.leer_parametros_pais()
    if pais is None:
        st.error("Faltan los datos de Damodaran. Usa **Actualizar datos ahora**.")
        return None

    c1, c2 = st.columns([1, 2])
    disponibles = universos_disponibles()
    memoria_u = _memoria("universo", "emergentes")
    universo = c1.selectbox("Universo de betas", list(disponibles), format_func=disponibles.get,
                            index=list(disponibles).index(memoria_u if memoria_u in disponibles else "emergentes"),
                            key=f"{clave}_universo",
                            help="La fuente por defecto se elige en la página «Beta propio vs Damodaran».")
    _recordar("universo", universo)
    betas = betas_universo(universo)
    industrias = betas["industria"].tolist()
    sector_mem = _memoria(f"sector_{clave}", sector_defecto)
    sector = c2.selectbox("Sector (clasificación Damodaran)", industrias,
                          index=industrias.index(sector_mem) if sector_mem in industrias else 0,
                          key=f"{clave}_sector",
                          help="Al cambiar el sector cambian automáticamente la beta y el WACC.")
    _recordar(f"sector_{clave}", sector)
    fila = betas[betas["industria"] == sector].iloc[0]

    opciones_rf = mercado.opciones_rf()
    rf = opciones_rf["Tesoro 10A – último dato"]
    infl_usa = mercado.opciones_infl_usa()["Breakeven 10A (mercado)"]
    kd_mercado = (mercado.opciones_kd_base()["TES 10A + spread"] or 0.12) + 0.02

    with st.expander("Ajustar supuestos del costo de capital", icon=":material/tune:"):
        a1, a2, a3 = st.columns(3)
        beta_u = a1.number_input("βU (desapalancada)", value=float(fila["beta_desapalancada_caja"]),
                                 step=0.05, format="%.3f", key=f"{clave}_bu_{sector}_{universo}")
        crp_opciones = {"Calificación": pais["crp_calificacion"], "CDS": pais["crp_cds"]}
        crp_nombre = a2.radio("Prima de riesgo país", list(crp_opciones), horizontal=True, key=f"{clave}_crp")
        crp = crp_opciones[crp_nombre]
        modo = a3.radio("Aplicación del CRP", ["aditivo", "beta"], horizontal=True, key=f"{clave}_modo",
                        format_func=lambda m: "λ = 1" if m == "aditivo" else "λ = βL")
        b1, b2, b3 = st.columns(3)
        if de_propio is None:
            de = b1.number_input("D/E (%)", value=float(fila["de"]) * 100, step=5.0,
                                 key=f"{clave}_de_{sector}_{universo}") / 100
            fuente_de = f"D/E del sector {sector}"
        else:
            de = de_propio
            b1.metric("D/E", ui.pct(de), help=etiqueta_de or "Definido por la estructura de financiación.")
            fuente_de = etiqueta_de or "Estructura propia"
        if kd_propio is None:
            kd = b2.number_input("Kd antes de impuestos (%)", value=round(kd_mercado * 100, 2), step=0.25,
                                 key=f"{clave}_kd", help="Por defecto: TES 10A + 2 p.p.") / 100
        else:
            kd = kd_propio
            b2.metric("Kd antes de impuestos", ui.pct(kd), help="Tasa del crédito definido en el modelo.")
        tes10 = mercado.opciones_kd_base()["TES 10A + spread"]
        opciones_pi = {}
        if escenario is not None:
            opciones_pi["Del escenario (coherente con los flujos)"] = (
                float(escenario["Inflación Colombia (%)"].mean()) / 100)
        if tes10:
            rf_cop = tes10 - pais["spread_default_calificacion"]
            opciones_pi["Implícita en los TES"] = (1 + rf_cop) / (1 + rf) * (1 + infl_usa) - 1
        opciones_pi["Meta del BanRep (3 %)"] = mercado.META_INFLACION_BANREP
        fuente_pi = b3.selectbox("Inflación COL para Fisher", list(opciones_pi), key=f"{clave}_pi",
                                 help="Del escenario: promedio de la inflación proyectada, la misma que mueve "
                                      "los flujos. Implícita en los TES: la que hace equivalentes el TES 10A "
                                      "(menos el spread de default) y el Tesoro de EE. UU.")
        infl_col = opciones_pi[fuente_pi]
        b3.caption(f"→ {ui.pct(infl_col)}")
        manual = st.toggle("Usar una tasa de descuento manual", key=f"{clave}_manual")
        wacc_manual = (st.number_input("WACC manual (%)", value=14.0, step=0.25, key=f"{clave}_wacc_man") / 100
                       if manual else None)

    s = cc.Supuestos(rf=rf, beta_u=beta_u, de=de, tasa_impuesto=pais["tasa_impositiva_marginal"],
                     erp=pais["erp_madura"], crp=crp, infl_col=infl_col, infl_usa=infl_usa, kd_cop=kd,
                     modo_crp=modo)
    r = cc.calcular(s)
    ku = cc.calcular(cc.Supuestos(**{**s.__dict__, "de": 0.0}))["ke_cop"]
    wacc = wacc_manual if wacc_manual is not None else r["wacc_cop"]

    tes = mercado.opciones_kd_base()["TES 10A + spread"]
    if tes and r["ke_cop"] < tes and wacc_manual is None:
        st.warning(f"El Ke en pesos ({ui.pct(r['ke_cop'])}) es menor que el rendimiento del TES 10A "
                   f"({ui.pct(tes)}): el patrimonio no puede costar menos que la deuda del Gobierno. "
                   "Suele indicar que la inflación usada en Fisher es menor que la que descuenta el mercado. "
                   "Revisa la inflación en **Ajustar supuestos**.", icon=":material/warning:")
    m = ui.tarjetas(5)
    m[0].metric("βU sector", ui.num(beta_u, 2), border=True,
                help=etiqueta_fuente_beta(universo, sector, int(fila["n_empresas"])))
    m[1].metric("βL", ui.num(r["beta_apalancada"], 2), border=True, help=f"Hamada con {fuente_de}")
    m[2].metric("Ke (COP)", ui.pct(r["ke_cop"]), border=True,
                help="rf + βL·ERP + λ·CRP, convertido a COP por Fisher")
    m[3].metric("Kd neto", ui.pct(r["kd_neto"]), border=True, help="Kd · (1 − t)")
    m[4].metric("WACC", ui.pct(wacc), border=True,
                help="Tasa manual del usuario" if wacc_manual else "E/V·Ke + D/V·Kd·(1−t)")
    return {"wacc": wacc, "ke": r["ke_cop"], "infl_fisher": infl_col, "fuente_infl": fuente_pi, "ku": ku, "kd": kd, "t": s.tasa_impuesto,
            "sector": sector, "universo": universo, "beta_u": beta_u, "beta_l": r["beta_apalancada"],
            "de": de, "supuestos": s, "resultado": r, "manual": wacc_manual is not None}


# =============================== ESCENARIO MACRO ====================================
def escenario_macro(clave: str, n: int, mostrar_grafico: bool = True) -> pd.DataFrame:
    """Editor de la trayectoria macro; devuelve la tabla anual para n años."""
    defecto = esc.anclas_por_defecto()
    guardado = _memoria("anclas", None)
    a = esc.Anclas(**guardado) if guardado else defecto

    escenario = st.segmented_control(
        "Escenario", list(esc.ESCENARIOS), default=_memoria("escenario", "Base"), key=f"{clave}_esc",
        help="Pesimista: PIB −1,5 p.p., inflación +1 p.p., devaluación +3 %/año. "
             "Optimista: PIB +1 p.p., inflación −0,5 p.p., revaluación 2 %/año.") or "Base"
    _recordar("escenario", escenario)

    c = st.columns(4)
    pib_lp = c[0].slider("PIB real de largo plazo (%)", 0.0, 6.0, float(a.pib_largo_plazo), 0.1,
                         key=f"{clave}_pib_lp", help="Crecimiento potencial supuesto. Editable.")
    infl_lp = c[1].slider("Inflación de largo plazo (%)", 1.0, 8.0, float(a.inflacion_largo_plazo), 0.1,
                          key=f"{clave}_infl_lp", help="Por defecto, la meta del BanRep (3 %).")
    anios_conv = c[2].slider("Años para converger", 1, 8, int(a.anios_convergencia), key=f"{clave}_conv",
                             help="Años en que PIB e inflación pasan del último dato al nivel de largo plazo.")
    pib_ini = c[3].number_input("PIB real de partida (%)", value=round(float(a.pib_inicial), 2), step=0.1,
                                key=f"{clave}_pib_ini", help=f"Último dato observado: {ui.num(defecto.pib_inicial)} %")
    a = esc.Anclas(pib_inicial=pib_ini, pib_largo_plazo=pib_lp, inflacion_inicial=a.inflacion_inicial,
                   inflacion_largo_plazo=infl_lp, inflacion_usa=a.inflacion_usa, trm_inicial=a.trm_inicial,
                   anios_convergencia=anios_conv)
    _recordar("anclas", a.__dict__)

    tabla = esc.construir(a, max(n, 10), escenario)
    if mostrar_grafico:
        g1, g2 = st.columns(2)
        with g1:
            ui.mostrar(_grafico_hist_proy("pib_var_anual", tabla, "PIB real (%)", "PIB real: histórico y proyectado"))
        with g2:
            ui.mostrar(_grafico_hist_proy("ipc_anual", tabla, "Inflación Colombia (%)",
                                          "Inflación: histórica y proyectada", referencia=3.0))
    with st.expander("Ver y editar la tabla del escenario", icon=":material/table_chart:"):
        st.caption("Puedes sobrescribir cualquier celda; los modelos usan esta tabla tal como quede.")
        editable = st.data_editor(
            tabla.iloc[:n].drop(columns=["t"]), hide_index=True, width="stretch", key=f"{clave}_esc_editor",
            disabled=["Año", "Crecimiento nominal (%)"],
            column_config={c: st.column_config.NumberColumn(format="%.2f") for c in tabla.columns if "%" in c}
            | {"TRM fin de año": st.column_config.NumberColumn(format="%.0f")})
        editable["t"] = range(1, len(editable) + 1)
        editable["Crecimiento nominal (%)"] = ((1 + editable["PIB real (%)"] / 100)
                                               * (1 + editable["Inflación Colombia (%)"] / 100) - 1) * 100
    return esc.extender(editable, n)


def _grafico_hist_proy(id_serie: str, tabla: pd.DataFrame, columna: str, titulo: str,
                       referencia: float | None = None) -> go.Figure:
    hist = ui.recortar(ui.serie(id_serie), 4)
    fig = go.Figure()
    fig.add_scatter(x=hist["fecha"], y=hist["valor"], mode="lines", name="Histórico",
                    line=dict(color=ui.PALETA[0], width=2),
                    hovertemplate="%{y:,.2f} %<extra>Histórico</extra>")
    fechas_proy = pd.to_datetime(tabla["Año"].astype(int).astype(str) + "-07-01")
    x = [hist["fecha"].iloc[-1]] + list(fechas_proy) if not hist.empty else list(fechas_proy)
    y = [hist["valor"].iloc[-1]] + list(tabla[columna]) if not hist.empty else list(tabla[columna])
    fig.add_scatter(x=x, y=y, mode="lines+markers", name="Escenario",
                    line=dict(color=ui.PALETA[1], width=2, dash="dash"), marker=dict(size=8),
                    hovertemplate="%{y:,.2f} %<extra>Escenario</extra>")
    if referencia is not None:
        fig.add_hline(y=referencia, line=dict(color=ui.GRIS_REF, width=1, dash="dot"))
    fig.update_layout(title=dict(text=titulo, font=dict(size=14)), height=320,
                      margin=dict(l=8, r=8, t=40, b=40), separators=",.", hovermode="x unified",
                      legend=dict(orientation="h", y=-0.15, x=0), yaxis=dict(title="%"))
    return fig


# =============================== EXPORTAR / CASOS ===================================
def a_excel(hojas: dict[str, pd.DataFrame]) -> bytes:
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as w:
        for nombre, df in hojas.items():
            df.to_excel(w, sheet_name=nombre[:31])
    return salida.getvalue()


def guardar_y_cargar_caso(clave: str, datos: dict, nombre_archivo: str) -> dict | None:
    """Botones para descargar el caso actual (JSON) o cargar uno guardado."""
    c1, c2 = st.columns(2)
    c1.download_button("Guardar caso (JSON)", json.dumps(datos, ensure_ascii=False, indent=2, default=str),
                       file_name=nombre_archivo, mime="application/json", icon=":material/save:",
                       width="stretch", key=f"{clave}_guardar")
    archivo = c2.file_uploader("Cargar un caso guardado", type="json", key=f"{clave}_cargar",
                               label_visibility="collapsed")
    if archivo is not None:
        marca = f"{clave}_cargado_{archivo.file_id}"
        if not st.session_state.get(marca):
            st.session_state[marca] = True
            return json.loads(archivo.getvalue().decode("utf-8"))
    return None
