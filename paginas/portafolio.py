"""Portafolio de inversión: pesos, desempeño, riesgo, correlaciones y frontera eficiente."""
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import lecturas, seleccion, tema, ui, yahoo
from nucleo import portafolio as pf

tema.encabezado(
    "Portafolio de inversión",
    "Arma un portafolio con las acciones que elijas, asígnales pesos y mira su **desempeño, riesgo, diversificación** y la "
    "**frontera eficiente**. Es una herramienta de análisis y aprendizaje, no una recomendación de inversión.",
    seccion="Inversión", chips=["Fuente: Yahoo Finance", "Solo posiciones largas", "Rebalanceo semanal supuesto"])

sel = seleccion.selector("pf", min_tickers=2)
if sel is None:
    st.stop()
datos = seleccion.cargar(sel)
if datos is None:
    st.stop()
px, ret, ref_px, ret_ref, metas = datos
tickers = list(px.columns)
if len(tickers) < 2:
    st.info("Se necesitan al menos dos acciones con datos para armar un portafolio.")
    st.stop()
if sel.base == "LOCAL" and len({m.get("moneda_origen") for m in metas.values()}) > 1:
    st.warning("Estás combinando acciones de **monedas distintas** sin convertirlas: los retornos y la volatilidad del portafolio "
               "no son comparables. Elige COP o USD como moneda de análisis.", icon=":material/warning:")
comun = ret[tickers].dropna()
if len(comun) < 52:
    st.error(f"El periodo común de las acciones tiene solo {len(comun)} semanas (se necesitan al menos 52). "
             "Quita las acciones de historial más corto o elige otras.")
    st.stop()

est = pf.estadisticas(ret[tickers], ret_ref, sel.rf)
est_ref = pf.estadisticas(ret_ref.to_frame("ref"), None, sel.rf).iloc[0] if ret_ref is not None else None
COLOR = {t: (ui.PALETA[i] if i < len(ui.PALETA) else "#9A9A9A") for i, t in enumerate(tickers)}
base_txt = "su moneda local" if sel.base == "LOCAL" else sel.base
pct = lambda v: ui.pct(v)
f2 = lambda v: ui.num(v, 2)


@st.cache_data(show_spinner=False)
def _optimizar(mu: np.ndarray, cov: np.ndarray, rf: float):
    nb = pf.nube(mu, cov, rf)
    return nb, pf.optimos(mu, cov, rf, nb)


mu, cov = pf.media_cov(ret[tickers])
nube, opt = _optimizar(mu, cov, sel.rf)

# =============================== PESOS ==============================================
llave = "|".join(tickers)
estado = st.session_state.setdefault("_pf_pesos", {})
if estado.get("llave") != llave:
    estado.clear()
    estado.update({"llave": llave, "w": np.ones(len(tickers)) / len(tickers), "version": 0})

st.subheader("Pesos del portafolio")
b1, b2, b3, _ = st.columns([1, 1, 1, 2])
if b1.button("Igual ponderado", icon=":material/balance:", width="stretch"):
    estado.update({"w": np.ones(len(tickers)) / len(tickers), "version": estado["version"] + 1})
    st.rerun()
if b2.button("Mínima varianza", icon=":material/shield:", width="stretch",
             help="Pesos que minimizan la volatilidad con los datos históricos (sin ventas en corto)."):
    estado.update({"w": opt["minima_varianza"], "version": estado["version"] + 1})
    st.rerun()
if b3.button("Máximo Sharpe", icon=":material/trending_up:", width="stretch",
             help="Pesos con el mejor retorno por unidad de riesgo histórico. Es muy sensible a los datos: úsalo como ejercicio."):
    estado.update({"w": opt["maximo_sharpe"], "version": estado["version"] + 1})
    st.rerun()

editor = st.data_editor(
    pd.DataFrame({"Acción": tickers, "Peso (%)": np.round(estado["w"] * 100, 2)}),
    hide_index=True, width="stretch", disabled=["Acción"], key=f"pesos_{estado['version']}",
    column_config={"Peso (%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=1.0, format="%.2f")})
bruto = editor["Peso (%)"].fillna(0).to_numpy(dtype=float)
if bruto.sum() <= 0:
    st.error("Los pesos suman cero. Asigna al menos un peso mayor que cero.")
    st.stop()
w = pf.pesos_validos(bruto)
estado["w"] = w
st.caption(f"Los pesos suman {ui.num(bruto.sum())} %; se normalizan automáticamente a 100 %. Puedes editarlos en la tabla.")

res = pf.resumen_portafolio(ret[tickers], w, ret_ref, sel.rf)
r_port = pf.retorno_portafolio(ret[tickers], w)
contrib = pf.contribucion_riesgo(cov, w)

# =============================== RESULTADOS =========================================
pts, tono = lecturas.portafolio(res, tickers, w, contrib, est, est_ref, sel.nombre_ref, sel.rf)
tema.lectura(pts, titulo="Análisis del portafolio", tono=tono, nota=lecturas.NOTA_ESTADISTICA)

k = ui.tarjetas(6, ancho=200)
k[0].metric("Retorno anual", pct(res["Retorno anual"]), border=True, help=f"Compuesto, en {base_txt}, con rebalanceo semanal.")
k[1].metric("Volatilidad", pct(res["Volatilidad"]), border=True)
k[2].metric("Sharpe", f2(res["Sharpe"]), border=True, help=f"Frente a una tasa libre de {ui.pct(sel.rf)}.")
k[3].metric("Caída máxima", pct(res["Caída máxima"]), border=True)
k[4].metric("VaR 95 % semanal", pct(res["VaR 95 % (sem.)"]), border=True, help="Pérdida semanal superada 1 de cada 20 semanas.")
k[5].metric(f"Beta vs {sel.nombre_ref.split(' (')[0]}", f2(res["Beta"]) if pd.notna(res.get("Beta")) else "—", border=True)

tab_des, tab_comp, tab_riesgo, tab_corr, tab_fr = st.tabs(
    ["Desempeño", "Composición", "Riesgo", "Correlaciones", "Frontera eficiente"])

# =============================== DESEMPEÑO ==========================================
with tab_des:
    ew = pf.retorno_portafolio(ret[tickers], np.ones(len(tickers)))
    inicio = r_port.index[0]
    fig = go.Figure()
    fig.add_scatter(x=r_port.index, y=pf.curva_acumulada(r_port) * 100, name="Tu portafolio", mode="lines",
                    line=dict(color=ui.ROJO, width=3), hovertemplate="%{y:,.0f}<extra>Tu portafolio</extra>")
    fig.add_scatter(x=ew.index, y=pf.curva_acumulada(ew) * 100, name="Igual ponderado", mode="lines",
                    line=dict(color=ui.AZUL, width=1.8), hovertemplate="%{y:,.0f}<extra>Igual ponderado</extra>")
    if ret_ref is not None:
        rr = ret_ref.loc[inicio:]
        fig.add_scatter(x=rr.index, y=pf.curva_acumulada(rr) * 100, name=sel.nombre_ref, mode="lines",
                        line=dict(color=ui.GRIS_REF, width=2, dash="dot"), hovertemplate="%{y:,.0f}<extra>" + sel.nombre_ref + "</extra>")
    fig.update_layout(height=410, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0), yaxis=dict(title=f"Valor de 100 invertidos ({base_txt})"))
    st.markdown("**Crecimiento de 100 invertidos**")
    ui.mostrar(fig)
    st.caption(f"Periodo común: {ui.fecha_txt(res['desde'])} – {ui.fecha_txt(res['hasta'])} ({len(r_port)} semanas). "
               "Sin costos de transacción ni impuestos; dividendos reinvertidos.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Caída desde el máximo**")
        fig = go.Figure()
        d = pf.caida(r_port)
        fig.add_scatter(x=d.index, y=d * 100, name="Tu portafolio", mode="lines", fill="tozeroy",
                        line=dict(color=ui.ROJO, width=1.8), fillcolor="rgba(233,29,38,.15)", hovertemplate="%{y:.1f} %<extra></extra>")
        if ret_ref is not None:
            dr = pf.caida(ret_ref.loc[inicio:])
            fig.add_scatter(x=dr.index, y=dr * 100, name=sel.nombre_ref, mode="lines",
                            line=dict(color=ui.GRIS_REF, width=1.6, dash="dot"), hovertemplate="%{y:.1f} %<extra></extra>")
        fig.update_layout(height=320, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
                          legend=dict(orientation="h", y=1.1, x=0), yaxis=dict(title="%"))
        ui.mostrar(fig)
    with c2:
        st.markdown("**Retorno por año calendario**")
        anual = (1 + r_port).groupby(r_port.index.year).prod() - 1
        fig = go.Figure(go.Bar(x=[str(a) for a in anual.index], y=anual.values * 100,
                               marker_color=[ui.POS if x >= 0 else ui.NEG for x in anual.values],
                               text=[ui.pct(x, 1) for x in anual.values], textposition="outside",
                               hovertemplate="%{x}: %{y:.1f} %<extra></extra>"))
        fig.add_hline(y=0, line=dict(color=ui.GRIS_REF, width=1))
        fig.update_layout(height=320, margin=dict(l=8, r=8, t=24, b=8), showlegend=False, yaxis=dict(title="%"))
        ui.mostrar(fig)
        st.caption("El primer y último año pueden ser parciales.")

# =============================== COMPOSICIÓN ========================================
with tab_comp:
    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        st.markdown("**Peso de cada acción**")
        mask = w > 0
        fig = go.Figure(go.Pie(labels=np.array(tickers)[mask], values=w[mask] * 100, hole=0.55, sort=False,
                               marker=dict(colors=[COLOR[t] for t in np.array(tickers)[mask]], line=dict(color="white", width=2)),
                               textinfo="label+percent", hovertemplate="%{label}: %{value:.1f} %<extra></extra>"))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8), showlegend=False,
                          annotations=[dict(text=f"{ui.num(res['n_efectivo'], 1)}<br>posiciones<br>efectivas", showarrow=False, font=dict(size=14))])
        ui.mostrar(fig)
    with c2:
        st.markdown("**Peso frente a aporte al riesgo**")
        fig = go.Figure()
        fig.add_bar(x=tickers, y=w * 100, name="Peso en el capital", marker_color=ui.GRIS_REF)
        fig.add_bar(x=tickers, y=contrib * 100, name="Aporte a la volatilidad", marker_color=ui.ROJO)
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8), barmode="group", yaxis=dict(title="%"),
                          legend=dict(orientation="h", y=1.08, x=0))
        ui.mostrar(fig)
        st.caption("Una barra roja más alta que la gris indica una posición que aporta más riesgo que capital.")
    tabla = pd.DataFrame({"Peso": w, "Retorno anual": est["Retorno anual"], "Volatilidad": est["Volatilidad"],
                          "Sharpe": est["Sharpe"], "Caída máxima": est["Caída máxima"], "Aporte al riesgo": contrib}, index=tickers)
    st.dataframe(tabla.style.format({"Peso": pct, "Retorno anual": pct, "Volatilidad": pct, "Sharpe": f2,
                                     "Caída máxima": pct, "Aporte al riesgo": pct}, na_rep="—"), width="stretch")
    ui.boton_descarga(tabla.reset_index(names="Ticker"), f"portafolio_{date.today()}.csv", "Descargar composición (CSV)", clave="dl_pf")

# =============================== RIESGO =============================================
with tab_riesgo:
    c1, c2 = st.columns([3, 2], gap="large")
    var95, cvar95 = res["VaR 95 % (sem.)"], res["CVaR 95 % (sem.)"]
    with c1:
        st.markdown("**Distribución de los retornos semanales**")
        fig = go.Figure(go.Histogram(x=r_port * 100, nbinsx=45, marker_color=ui.AZUL, marker_line=dict(width=1, color="white"),
                                     hovertemplate="%{x:.1f} %: %{y} semanas<extra></extra>"))
        fig.add_vline(x=-var95 * 100, line=dict(color=ui.ROJO, width=2, dash="dash"), annotation_text="VaR 95 %", annotation_position="top left")
        fig.add_vline(x=-cvar95 * 100, line=dict(color=ui.ROJO, width=2), annotation_text="CVaR", annotation_position="top left")
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=24, b=8), showlegend=False,
                          xaxis=dict(title="Retorno semanal (%)"), yaxis=dict(title="Semanas"))
        ui.mostrar(fig)
        st.caption(f"En 1 de cada 20 semanas el portafolio perdió al menos {ui.pct(var95)}; en promedio, {ui.pct(cvar95)} dentro de ese 5 % peor.")
    with c2:
        st.markdown("**Las 5 peores semanas**")
        peores = r_port.nsmallest(5)
        df = pd.DataFrame({"Semana que termina": [ui.fecha_txt(i) for i in peores.index], "Retorno": peores.values})
        st.dataframe(df.style.format({"Retorno": pct}), hide_index=True, width="stretch")
        st.caption("Suelen coincidir con eventos de mercado (marzo de 2020, por ejemplo); es un recordatorio de la cola de pérdidas.")
    r2 = ui.tarjetas(4, ancho=200)
    r2[0].metric("Sortino", f2(res["Sortino"]), border=True, help="Como el Sharpe, pero solo penaliza la volatilidad a la baja.")
    r2[1].metric("Ratio de diversificación", f2(res["ratio_diversificacion"]), border=True, help="Volatilidad promedio ponderada / volatilidad del portafolio. 1 = sin diversificación.")
    r2[2].metric("Posiciones efectivas", ui.num(res["n_efectivo"], 1), border=True, help="1/Σw². Con pesos iguales coincide con el número de acciones.")
    r2[3].metric("Alfa anual vs referencia", pct(res["Alfa anual"]) if pd.notna(res.get("Alfa anual")) else "—", border=True)

# =============================== CORRELACIONES ======================================
with tab_corr:
    corr = ret[tickers].dropna().corr()
    fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, zmin=-0.2, zmax=1,
                               colorscale=[[i / 3, c] for i, c in enumerate(ui.RAMPA[:4])],
                               text=[[ui.num(v) for v in fila] for fila in corr.values], texttemplate="%{text}",
                               xgap=2, ygap=2, colorbar=dict(thickness=10, title="ρ"),
                               hovertemplate="%{y} · %{x}: %{z:.2f}<extra></extra>"))
    fig.update_layout(height=120 + 52 * len(tickers), margin=dict(l=8, r=8, t=24, b=8), yaxis=dict(autorange="reversed"))
    ui.mostrar(fig)
    m = corr.to_numpy()[np.triu_indices(len(tickers), 1)]
    i, j = np.unravel_index(np.argmax(np.triu(corr.to_numpy(), 1)), corr.shape)
    k2, l2 = np.unravel_index(np.argmin(np.where(np.triu(np.ones_like(corr), 1) > 0, corr.to_numpy(), 9)), corr.shape)
    tema.lectura([f"Correlación promedio: **{ui.num(float(m.mean()))}**. Más alta: {tickers[i]}–{tickers[j]} ({ui.num(corr.iloc[i, j])}). "
                  f"Más baja: {tickers[k2]}–{tickers[l2]} ({ui.num(corr.iloc[k2, l2])}).",
                  "Las correlaciones **suben en las crisis**: la diversificación que se ve en periodos tranquilos suele ser menor justo cuando más se necesita."],
                 titulo="Análisis de correlaciones", tono="alerta" if float(m.mean()) > 0.7 else "neutro")
    st.caption("Calculada con retornos semanales del periodo común. Con acciones de distintas monedas, parte de la correlación viene del tipo de cambio.")

# =============================== FRONTERA EFICIENTE =================================
with tab_fr:
    st.markdown("**Frontera eficiente (sin ventas en corto)**")
    sh_opt = opt["maximo_sharpe"]
    mv_opt = opt["minima_varianza"]

    def punto(wv):
        return float(wv @ mu) * 100, float(np.sqrt(wv @ cov @ wv)) * 100

    fig = go.Figure()
    fig.add_scatter(x=nube["vol"] * 100, y=nube["retorno"] * 100, mode="markers", name="Portafolios posibles",
                    marker=dict(size=4, color=nube["sharpe"], colorscale=[[i / 6, c] for i, c in enumerate(ui.RAMPA)],
                                opacity=0.55, colorbar=dict(title="Sharpe", thickness=10)),
                    hovertemplate="Volatilidad %{x:.1f} %<br>Retorno %{y:.1f} %<extra></extra>")
    vol_max = float(nube["vol"].max()) * 100
    r_sh, v_sh = punto(sh_opt)
    fig.add_scatter(x=[0, vol_max], y=[sel.rf * 100, sel.rf * 100 + (r_sh - sel.rf * 100) / v_sh * vol_max], mode="lines",
                    name="Línea de mercado de capitales", line=dict(color=ui.GRIS, width=1.5, dash="dot"), hoverinfo="skip")
    for t_ in tickers:
        fig.add_scatter(x=[est.loc[t_, "Volatilidad"] * 100], y=[est.loc[t_, "Retorno anual"] * 100], mode="markers+text",
                        text=[t_], textposition="top center", name=t_, showlegend=False,
                        marker=dict(size=10, color=COLOR[t_], line=dict(width=1.5, color="white")),
                        hovertemplate=f"{t_}<br>Volatilidad %{{x:.1f}} %<br>Retorno %{{y:.1f}} %<extra></extra>")
    for nombre, wv, color, simbolo in (("Mínima varianza", mv_opt, ui.AZUL, "square"), ("Máximo Sharpe", sh_opt, ui.VERDE, "star"),
                                       ("Tu portafolio", w, ui.ROJO, "diamond")):
        rx, vx = punto(wv)
        fig.add_scatter(x=[vx], y=[rx], mode="markers", name=nombre,
                        marker=dict(size=17, color=color, symbol=simbolo, line=dict(width=2, color="white")),
                        hovertemplate=f"{nombre}<br>Volatilidad %{{x:.1f}} %<br>Retorno %{{y:.1f}} %<extra></extra>")
    fig.update_layout(height=520, margin=dict(l=8, r=8, t=24, b=8), legend=dict(orientation="h", y=1.1, x=0),
                      xaxis=dict(title="Volatilidad anual (%)", rangemode="tozero"), yaxis=dict(title="Retorno anual esperado (%)"))
    ui.mostrar(fig)
    st.caption("Cada punto es un portafolio posible con las acciones elegidas. La frontera es el borde superior izquierdo: el mayor "
               "retorno para cada nivel de riesgo. Los retornos esperados son los **promedios históricos**, muy inestables; "
               "los pesos óptimos cambian mucho con otra muestra.")
    comp = pd.DataFrame({"Tu portafolio": w, "Mínima varianza": mv_opt, "Máximo Sharpe": sh_opt}, index=tickers)
    for nombre, wv in comp.items():
        pass
    filas = {nombre: {"Retorno": punto(comp[nombre].to_numpy())[0] / 100, "Volatilidad": punto(comp[nombre].to_numpy())[1] / 100}
             for nombre in comp}
    resumen = pd.DataFrame(filas).T
    resumen["Sharpe"] = (resumen["Retorno"] - sel.rf) / resumen["Volatilidad"]
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Pesos de cada portafolio**")
        st.dataframe(comp.style.format(pct), width="stretch")
    with c2:
        st.markdown("**Comparación (promedios históricos)**")
        st.dataframe(resumen.style.format({"Retorno": pct, "Volatilidad": pct, "Sharpe": f2}), width="stretch")
    st.warning("Los portafolios «óptimos» son un ejercicio didáctico: maximizan sobre datos pasados y suelen concentrarse en pocas "
               "acciones. Antes de usarlos en la práctica se necesitan límites de peso, supuestos de retorno más estables y costos de "
               "transacción.", icon=":material/info:")

st.divider()
with st.expander("Supuestos y límites de este análisis", icon=":material/rule:"):
    st.markdown("""
- **Datos:** Yahoo Finance, barras semanales con cierre de viernes, ajustadas por dividendos y splits. Puede haber huecos o errores.
- **Periodo común:** el análisis usa las semanas en que **todas** las acciones tienen dato; la acción más corta limita la muestra.
- **Moneda:** las series se convierten con el tipo de cambio semanal de Yahoo. Los retornos de acciones extranjeras incluyen el efecto cambiario.
- **Pesos constantes:** se supone rebalanceo semanal sin costos de transacción, impuestos ni deslizamiento (*slippage*).
- **Solo posiciones largas:** no hay ventas en corto ni apalancamiento.
- **Retornos esperados históricos:** son ruidosos; la optimización los amplifica. La frontera es descriptiva, no predictiva.
- **VaR y CVaR históricos:** describen la muestra, no garantizan pérdidas máximas futuras.
- **Liquidez:** varias acciones colombianas se negocian poco; el precio de Yahoo puede no ser ejecutable en el tamaño que se desee.
""")
