"""Calculadora de costo de capital: CAPM global + prima de riesgo país y WACC."""
import json
from dataclasses import asdict
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import almacen, componentes, lecturas, mercado, tema, ui
from nucleo import costo_capital as cc

tema.encabezado("Costo de capital · Colombia",
                "**CAPM global con prima de riesgo país** (Damodaran), conversión a pesos por paridad de Fisher y WACC. "
                "Cada supuesto muestra su fuente para que el resultado sea citable.",
                seccion="Análisis financiero", chips=["Ke · WACC", "Beta por industria", "Sensibilidad"])

pais = almacen.leer_parametros_pais()
if pais is None:
    st.error("No hay parámetros de Damodaran descargados. Usa **Actualizar datos ahora**.")
    st.stop()

MANUAL = "Manual"


def elegir(etiqueta: str, opciones: dict, clave: str, ayuda: str = "") -> tuple[float, str]:
    """Selector de fuente + campo numérico en %. Devuelve (fracción, descripción de la fuente)."""
    opciones = {k: v for k, v in opciones.items() if v is not None}
    nombre = st.selectbox(etiqueta, list(opciones) + [MANUAL], key=f"sel_{clave}", help=ayuda)
    if nombre == MANUAL:
        valor = st.number_input(f"{etiqueta} (%)", value=5.0, step=0.05, format="%.2f",
                                key=f"man_{clave}") / 100
    else:
        valor = opciones[nombre]
        st.caption(f"→ **{ui.pct(valor)}**")
    return valor, nombre


fecha_dam = pais["fecha_archivo"]
izq, der = st.columns([1, 2], gap="large")

# =============================== SUPUESTOS ==========================================
with izq:
    st.subheader("Supuestos")

    with st.expander("1. Tasa libre de riesgo (USD)", expanded=True):
        rf, f_rf = elegir("Fuente de rf", mercado.opciones_rf(), "rf",
                          "Bono del Tesoro de EE. UU. a 10 años (FRED: DGS10).")

    with st.expander("2. Primas de riesgo", expanded=True):
        erp, f_erp = elegir("Prima de mercado madura (ERP)",
                            {f"Damodaran – ERP implícita ({fecha_dam})": pais["erp_madura"]},
                            "erp", "ERP implícita del S&P 500 neta del spread de default de EE. UU.")
        crp, f_crp = elegir(
            "Prima de riesgo país (CRP)",
            {f"Damodaran – calificación {pais['calificacion_moodys']} ({fecha_dam})": pais["crp_calificacion"],
             f"Damodaran – CDS soberano ({fecha_dam})": pais["crp_cds"],
             f"Spread de default sin ajuste de volatilidad": pais["spread_default_calificacion"]},
            "crp",
            "CRP = spread de default × (σ acciones / σ bonos). Damodaran usa un multiplicador de "
            f"{ui.num(pais['multiplicador_volatilidad'])}.")
        modo_crp = st.radio("¿Cómo se aplica el CRP?", list(cc.MODOS_CRP),
                            format_func=lambda m: cc.MODOS_CRP[m], key="modo_crp")

    with st.expander("3. Empresa o industria", expanded=True):
        universos = componentes.universos_disponibles()
        memoria_u = st.session_state.get("_mem_universo", "emergentes")
        universo = st.selectbox("Universo de betas", list(universos),
                                index=list(universos).index(memoria_u if memoria_u in universos else "emergentes"),
                                format_func=universos.get, key="universo",
                                help="Para empresas colombianas se suele usar emergentes o global. "
                                     "«LatAm propio» y «combinado» salen del cuaderno de Yahoo Finance.")
        betas = componentes.betas_universo(universo)
        industrias = [MANUAL] + betas["industria"].tolist()
        industria = st.selectbox("Industria", industrias,
                                 index=industrias.index("Utility (General)") if "Utility (General)" in industrias else 0,
                                 key="industria")
        corregir_caja = st.toggle("Beta corregida por caja", value=True,
                                  help="Damodaran ajusta la beta desapalancada por la caja que tienen las empresas.")
        col_beta = "beta_desapalancada_caja" if corregir_caja else "beta_desapalancada"
        if industria == MANUAL:
            beta_u = st.number_input("Beta desapalancada (βU)", value=1.0, step=0.05, key="bu_man")
            de_ind = 0.5
            f_beta = "Manual"
        else:
            fila = betas[betas["industria"] == industria].iloc[0]
            beta_u = float(fila[col_beta])
            de_ind = float(fila["de"])
            f_beta = componentes.etiqueta_fuente_beta(universo, industria, int(fila["n_empresas"]))
            st.caption(f"→ βU = **{ui.num(beta_u, 3)}** · D/E de la industria = **{ui.pct(de_ind)}**")
        estructura = st.radio("Estructura de capital", ["D/E de la industria", "D/E objetivo propio"],
                              horizontal=True, key="estructura", disabled=industria == MANUAL)
        if estructura == "D/E objetivo propio" or industria == MANUAL:
            de = st.number_input("Deuda / Patrimonio (%)", value=round(de_ind * 100, 1), step=5.0,
                                 key=f"de_{industria}") / 100
            f_de = "Supuesto del usuario"
        else:
            de = de_ind
            f_de = f"Damodaran – D/E de la industria {industria}"
        t = st.number_input("Tasa impositiva marginal (%)",
                            value=float(pais.get("tasa_impositiva_marginal", 0.35)) * 100,
                            step=1.0, key="tasa") / 100
        f_t = "Tasa general de renta Colombia (Art. 240 E.T.; Damodaran Country Tax Rates)"

    with st.expander("4. Costo de la deuda (COP)", expanded=True):
        base_kd, f_base_kd = elegir("Tasa base", mercado.opciones_kd_base(), "kd",
                                    "Tasa de mercado a la que se suma el spread crediticio de la empresa.")
        if f_base_kd == MANUAL:
            kd, f_kd = base_kd, "Supuesto del usuario"
        else:
            spread = st.number_input("Spread crediticio (%)", value=2.0, step=0.25, key="spread_kd",
                                     help="Depende de la calificación de la empresa (p. ej., rating sintético "
                                          "por cobertura de intereses de Damodaran).") / 100
            kd = base_kd + spread
            f_kd = f"{f_base_kd.replace(' + spread', '')} ({ui.pct(base_kd)}) + spread {ui.pct(spread)}"
        st.caption(f"→ Kd antes de impuestos = **{ui.pct(kd)}**")

    with st.expander("5. Inflación esperada (paridad de Fisher)", expanded=True):
        infl_col, f_icol = elegir("Colombia", mercado.opciones_infl_col(), "icol",
                                  "Para horizontes largos se recomienda la meta de largo plazo.")
        infl_usa, f_iusa = elegir("Estados Unidos", mercado.opciones_infl_usa(), "iusa",
                                  "Breakeven 10A = bono nominal − TIPS (FRED: T10YIE).")

s = cc.Supuestos(rf=rf, beta_u=beta_u, de=de, tasa_impuesto=t, erp=erp, crp=crp,
                 infl_col=infl_col, infl_usa=infl_usa, kd_cop=kd, modo_crp=modo_crp)
r = cc.calcular(s)
fuentes = {"rf": f_rf, "beta_u": f_beta, "de": f_de, "t": f_t, "erp": f_erp, "crp": f_crp,
           "infl_col": f_icol, "infl_usa": f_iusa, "kd": f_kd}

# =============================== RESULTADOS =========================================
with der:
    st.subheader("Resultados")
    m = st.columns(2)
    m[0].metric("Ke (COP)", ui.pct(r["ke_cop"]), border=True)
    m[1].metric("WACC (COP)", ui.pct(r["wacc_cop"]), border=True)
    m = st.columns(2)
    m[0].metric("Ke (USD)", ui.pct(r["ke_usd"]), border=True)
    m[1].metric("WACC (USD)", ui.pct(r["wacc_usd"]), border=True)
    st.caption(f"βL = {ui.num(r['beta_apalancada'], 3)} · E/V = {ui.pct(r['peso_patrimonio'], 1)} · "
               f"D/V = {ui.pct(r['peso_deuda'], 1)} · Kd después de impuestos = {ui.pct(r['kd_neto'])}")

    pts_ke, tono_ke = lecturas.ke(r, s, f_beta, mercado.opciones_kd_base()["TES 10A + spread"])
    tema.lectura(pts_ke, titulo="Análisis del costo de capital", tono=tono_ke)

    # Construcción del Ke (cascada)
    ajuste_fisher = r["ke_cop"] - r["ke_usd"]
    fig = go.Figure(go.Waterfall(
        orientation="v",
        x=["Tasa libre<br>de riesgo", "βL × ERP", "λ × CRP", "Ke USD", "Ajuste<br>inflación", "Ke COP"],
        measure=["relative", "relative", "relative", "total", "relative", "total"],
        y=[rf * 100, r["prima_mercado"] * 100, r["prima_pais"] * 100, 0, ajuste_fisher * 100, 0],
        text=[ui.pct(v) for v in [rf, r["prima_mercado"], r["prima_pais"], r["ke_usd"],
                                   ajuste_fisher, r["ke_cop"]]],
        textposition="outside",
        increasing=dict(marker=dict(color=ui.GRIS)),
        decreasing=dict(marker=dict(color=ui.AZUL)),
        totals=dict(marker=dict(color=ui.ROJO)),
        connector=dict(line=dict(color=ui.GRIS_REF, width=1, dash="dot")),
        hovertemplate="%{x}: %{text}<extra></extra>",
    ))
    fig.update_layout(height=360, margin=dict(l=8, r=8, t=28, b=8), separators=",.",
                      yaxis=dict(title="%", range=[0, max(r["ke_cop"], r["ke_usd"]) * 100 * 1.18]),
                      showlegend=False)
    st.markdown("**Cómo se construye el costo del patrimonio**")
    ui.mostrar(fig)

    pas, sen, ind, hist = st.tabs(["Paso a paso", "Sensibilidad", "Por industria", "Historial de supuestos"])

    # --- Paso a paso (citable) -----------------------------------------------------
    with pas:
        tabla = cc.tabla_paso_a_paso(s, r, fuentes)
        sin_pct = {"Beta desapalancada (βU)", "Beta apalancada (βL)"}
        tabla["Valor mostrado"] = [ui.num(v, 3) if c in sin_pct else ui.pct(v)
                                   for c, v in zip(tabla["Concepto"], tabla["Valor"])]
        st.dataframe(tabla[["Tipo", "Concepto", "Valor mostrado", "Fórmula", "Fuente / nota"]],
                     hide_index=True, width="stretch", height=600)
        cita = (f"Costo de capital estimado el {date.today().isoformat()} con el Observatorio "
                f"Macro-Financiero de Colombia: Ke(COP) = {ui.pct(r['ke_cop'])}, WACC(COP) = "
                f"{ui.pct(r['wacc_cop'])}. CAPM global + CRP (Damodaran, archivo {fecha_dam}); "
                f"rf: {f_rf}; βU: {f_beta}; CRP aplicado de forma {modo_crp}; conversión por paridad "
                f"de Fisher (πCOL {ui.pct(infl_col)}, πUSA {ui.pct(infl_usa)}).")
        st.markdown("**Texto sugerido para citar el cálculo**")
        st.code(cita, language=None, wrap_lines=True)
        c1, c2 = st.columns(2)
        with c1:
            ui.boton_descarga(tabla.drop(columns="Valor mostrado"), f"costo_capital_{date.today()}.csv",
                              "Descargar ficha (CSV)", clave="dl_ficha")
        with c2:
            st.download_button("Descargar supuestos (JSON)",
                               json.dumps({"fecha": date.today().isoformat(), "supuestos": asdict(s),
                                           "fuentes": fuentes, "resultados": r}, ensure_ascii=False, indent=2),
                               file_name=f"supuestos_costo_capital_{date.today()}.json",
                               mime="application/json", icon=":material/download:")

    # --- Sensibilidad --------------------------------------------------------------
    def mapa_calor(df: pd.DataFrame, titulo_x: str, titulo_y: str, fmt_x, fmt_y) -> go.Figure:
        z = df.values * 100
        fig = go.Figure(go.Heatmap(
            z=z, x=[fmt_x(v) for v in df.columns], y=[fmt_y(v) for v in df.index],
            # Solo la mitad clara de la rampa, para que el texto oscuro sea legible en todas las celdas.
            colorscale=[[i / 3, c] for i, c in enumerate(ui.RAMPA_AZUL[:4])],
            text=[[ui.pct(v, fraccion=False) for v in fila] for fila in z], texttemplate="%{text}",
            hovertemplate=f"{titulo_x}: %{{x}}<br>{titulo_y}: %{{y}}<br>Resultado: %{{text}}<extra></extra>",
            colorbar=dict(title="%", thickness=10), xgap=2, ygap=2,
        ))
        fig.update_layout(height=380, margin=dict(l=8, r=8, t=8, b=8), separators=",.",
                          xaxis=dict(title=titulo_x, type="category"),
                          yaxis=dict(title=titulo_y, type="category"))
        return fig

    with sen:
        st.markdown("**WACC (COP) ante estructura de capital y prima de riesgo país**")
        valores_de = [0, 0.25, 0.5, 0.75, 1.0, 1.5]
        valores_crp = sorted({max(0.0, round(crp + d, 4)) for d in (-0.02, -0.01, 0, 0.01, 0.02)})
        ui.mostrar(mapa_calor(cc.sensibilidad(s, "de", valores_de, "crp", valores_crp),
                              "D/E", "CRP", lambda v: ui.pct(v, 0), lambda v: ui.pct(v)))
        st.markdown("**Ke (COP) ante beta desapalancada y prima de mercado**")
        valores_bu = [round(v, 2) for v in np.arange(0.6, 1.61, 0.2)]
        valores_erp = sorted({round(erp + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)})
        ui.mostrar(mapa_calor(cc.sensibilidad(s, "beta_u", valores_bu, "erp", valores_erp, "ke_cop"),
                              "βU", "ERP", lambda v: ui.num(v, 1), lambda v: ui.pct(v)))
        st.caption("El resto de supuestos se mantiene en los valores elegidos a la izquierda.")

    # --- Por industria ---------------------------------------------------------------
    with ind:
        st.markdown(f"Aplica los supuestos de mercado actuales a cada industria del universo "
                    f"**{universos[universo]}**, con la beta y el D/E propios de cada una.")
        filtro = st.text_input("Filtrar industria", placeholder="p. ej. Bank, Utility, Retail")
        tabla_ind = cc.wacc_por_industria(betas, s, columna_beta=col_beta)
        if filtro:
            tabla_ind = tabla_ind[tabla_ind["Industria"].str.contains(filtro, case=False)]
        vista = tabla_ind.copy()
        for c in ["D/E", "Ke USD", "Ke COP", "WACC COP"]:
            vista[c] = vista[c] * 100
        st.dataframe(
            vista.sort_values("WACC COP", ascending=False), hide_index=True, width="stretch",
            column_config={
                "βU": st.column_config.NumberColumn(format="%.3f"),
                "βL": st.column_config.NumberColumn(format="%.3f"),
                "D/E": st.column_config.NumberColumn(format="%.1f %%"),
                "Ke USD": st.column_config.NumberColumn(format="%.2f %%"),
                "Ke COP": st.column_config.NumberColumn(format="%.2f %%"),
                "WACC COP": st.column_config.ProgressColumn(
                    format="%.2f %%", min_value=0, max_value=float(vista["WACC COP"].max() or 1)),
            })
        ui.boton_descarga(tabla_ind, f"wacc_industrias_{universo}_{date.today()}.csv",
                          "Descargar tabla (CSV)", clave="dl_ind")
        st.caption("Industrias según la clasificación de Damodaran (datos de empresas globales/emergentes, "
                   "no exclusivamente colombianas).")

    # --- Historial ---------------------------------------------------------------------
    with hist:
        st.markdown("Cada vez que Damodaran publica supuestos nuevos se guarda una fila. "
                    "Esto permite reproducir cálculos hechos en fechas anteriores.")
        h = almacen.leer_historial_parametros()
        if h is not None:
            st.dataframe(h, hide_index=True, width="stretch")
        st.markdown("**Contexto de mercado para el riesgo país**")
        ui.mostrar(ui.lineas({"Diferencial TES 10A − Tesoro 10A": ui.serie("spread_tes_ust")}, "p.p.",
                             altura=300))
        st.caption("El diferencial en pesos mezcla riesgo país y diferencial de inflación; "
                   "no debe usarse directamente como CRP en USD.")

# =============================== DOCENCIA ===========================================
with st.expander("¿Cómo leer este cálculo? (nota didáctica)", icon=":material/school:"):
    st.markdown("**1. Beta apalancada (Hamada).** La beta de la industria se desapalanca y se "
                "vuelve a apalancar con la estructura de capital de la empresa analizada:")
    st.latex(r"\beta_L = \beta_U\,[1 + (1-t)\,D/E]")
    st.markdown("**2. Costo del patrimonio en dólares.** Se parte de un mercado maduro y se suma el "
                "riesgo adicional de invertir en Colombia:")
    st.latex(r"K_e^{USD} = r_f + \beta_L \cdot ERP_{madura} + \lambda \cdot CRP")
    st.markdown("Con λ = 1 todas las empresas colombianas asumen el mismo riesgo país; con λ = βL "
                "el riesgo país crece con la sensibilidad de la empresa al mercado.")
    st.markdown("**3. Conversión a pesos (paridad de Fisher).** Una tasa en USD se convierte a COP "
                "con el diferencial de inflación esperada:")
    st.latex(r"K_e^{COP} = (1+K_e^{USD})\,\frac{1+\pi_{COL}}{1+\pi_{USA}} - 1")
    st.markdown("**4. WACC.** Promedio ponderado del costo del patrimonio y de la deuda después "
                "de impuestos:")
    st.latex(r"WACC = \frac{E}{V}K_e + \frac{D}{V}K_d(1-t)")
    st.markdown("**Advertencias.** No hay un único modelo aceptado para mercados emergentes. Los "
                "resultados son sensibles a la elección de rf, CRP y λ, por eso conviene reportar "
                "siempre la tabla de supuestos y el análisis de sensibilidad.")
