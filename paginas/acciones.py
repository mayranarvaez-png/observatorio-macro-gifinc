"""Comparador de acciones: retorno, riesgo, valoración y solidez con datos de Yahoo Finance."""
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import almacen, lecturas, seleccion, tema, ui, yahoo
from nucleo import portafolio as pf

tema.encabezado(
    "Comparador de acciones",
    "Elige acciones de Colombia, Latinoamérica o cualquier mercado y compáralas con **indicadores clave**: retorno, "
    "riesgo, valoración y solidez financiera. Cada bloque trae un análisis automático de lo que muestran los datos.",
    seccion="Inversión", chips=["Fuente: Yahoo Finance", "Barras semanales ajustadas por dividendos", "Material académico"])

sel = seleccion.selector("acc", min_tickers=1)
if sel is None:
    st.stop()
datos = seleccion.cargar(sel)
if datos is None:
    st.stop()
px, ret, ref_px, ret_ref, metas = datos
tickers = list(px.columns)
with st.spinner("Leyendo indicadores de las empresas…"):
    perfiles = yahoo.perfiles(tickers)

est = pf.estadisticas(ret, ret_ref, sel.rf)
if est.empty:
    st.error("Las series son demasiado cortas (menos de 20 semanas) para calcular indicadores.")
    st.stop()
tickers = [t for t in tickers if t in est.index]
est_ref = (pf.estadisticas(ret_ref.to_frame("ref"), None, sel.rf).iloc[0] if ret_ref is not None else None)
corr = ret[tickers].dropna().corr() if len(tickers) > 1 else None
COLOR = {t: (ui.PALETA[i] if i < len(ui.PALETA) else "#9A9A9A") for i, t in enumerate(tickers)}
NOMBRE = {t: (perfiles.get(t) or {}).get("nombre") or t for t in tickers}
base_txt = "su moneda local" if sel.base == "LOCAL" else sel.base

pct = lambda v: ui.pct(v)
f2 = lambda v: ui.num(v, 2)
f1x = lambda v: f"{ui.num(v, 1)}x"


def tinte(df: pd.DataFrame, mayor_mejor: dict[str, bool]):
    """Verde al mejor grupo y rojo al peor grupo de cada columna (con 3 o más acciones). El valor siempre se muestra."""
    def f(col):
        if col.name not in mayor_mejor or col.notna().sum() < 3:
            return [""] * len(col)
        k = max(1, col.notna().sum() // 3)
        orden = col.dropna().sort_values(ascending=not mayor_mejor[col.name])
        mejores, peores = set(orden.index[-k:]), set(orden.index[:k])
        return ["background-color:#DDF3EA" if i in mejores else "background-color:#FBDADB" if i in peores else ""
                for i in col.index]
    return df.style.apply(f, axis=0)


tab_res, tab_precio, tab_rr, tab_val, tab_ficha = st.tabs(
    ["Resumen", "Precio y retorno", "Riesgo y retorno", "Valoración y solidez", "Ficha de una acción"])

# =============================== RESUMEN ============================================
with tab_res:
    pts, tono = lecturas.comparador(est.loc[tickers], corr, perfiles, sel.nombre_ref, sel.base)
    tema.lectura(pts, tono=tono, nota=lecturas.NOTA_ESTADISTICA)

    por = pf.retornos_por_periodo(px[tickers])
    filas = pd.DataFrame(index=tickers)
    filas["Empresa"] = [NOMBRE[t] for t in tickers]
    filas["Sector"] = [(perfiles.get(t) or {}).get("sector") or "—" for t in tickers]
    filas["Rend. 1 año"] = por["1 año"]
    filas["Retorno anual"] = est["Retorno anual"]
    filas["Volatilidad"] = est["Volatilidad"]
    filas["Sharpe"] = est["Sharpe"]
    filas["Caída máx."] = est["Caída máxima"]
    if "Beta" in est:
        filas["Beta"] = est["Beta"]
    for etq, k in (("P/E", "pe"), ("P/B", "pb"), ("Dividendo", "div_yield"), ("ROE", "roe"),
                   ("Margen neto", "margen_neto"), ("D/E", "de")):
        filas[etq] = [(perfiles.get(t) or {}).get(k) for t in tickers]
    for c in ("P/E", "P/B", "Dividendo", "ROE", "Margen neto", "D/E"):
        filas[c] = pd.to_numeric(filas[c], errors="coerce")
    filas.loc[(filas["P/E"] <= 0) | (filas["P/E"] > 300), "P/E"] = np.nan   # utilidad negativa o extrema
    filas.loc[filas["P/B"] < 0.05, "P/B"] = np.nan                           # error de unidades típico en ADR

    mm = {"Rend. 1 año": True, "Retorno anual": True, "Volatilidad": False, "Sharpe": True, "Caída máx.": True,
          "P/E": False, "P/B": False, "Dividendo": True, "ROE": True, "Margen neto": True, "D/E": False}
    fmt = {"Rend. 1 año": pct, "Retorno anual": pct, "Volatilidad": pct, "Sharpe": f2, "Caída máx.": pct, "Beta": f2,
           "P/E": f1x, "P/B": f1x, "Dividendo": pct, "ROE": pct, "Margen neto": pct, "D/E": lambda v: ui.pct(v, 0)}
    st.markdown("##### Cuadro comparativo")
    st.dataframe(tinte(filas, mm).format(fmt, na_rep="—"), width="stretch", height=min(560, 90 + 36 * len(filas)))
    st.caption(f"Retornos y riesgo en **{base_txt}**, con barras semanales ajustadas por dividendos. Verde: mejor tercio del "
               "grupo; rojo: peor tercio (con 3 o más acciones). Los múltiplos solo se comparan dentro de un mismo sector. "
               "Dividendo, ROE, margen y D/E vienen de los últimos estados financieros que reporta Yahoo.")
    ui.boton_descarga(filas.reset_index(names="Ticker"), f"comparador_{date.today()}.csv", "Descargar cuadro (CSV)", clave="dl_acc")

# =============================== PRECIO Y RETORNO ===================================
with tab_precio:
    comun = px[tickers].dropna()
    inicio_comun = comun.index[0] if len(comun) > 10 else None
    serie_idx = px[tickers] if inicio_comun is None else px.loc[inicio_comun:, tickers]
    idx = serie_idx / serie_idx.apply(lambda s: s.dropna().iloc[0]) * 100
    st.markdown("**Evolución del valor de 100 invertidos**")
    fig = go.Figure()
    for t in tickers:
        fig.add_scatter(x=idx.index, y=idx[t], mode="lines", name=t, line=dict(color=COLOR[t], width=2),
                        hovertemplate="%{y:,.0f}<extra>" + t + "</extra>")
    if ref_px is not None:
        r_idx = ref_px.loc[idx.index[0]:]
        fig.add_scatter(x=r_idx.index, y=r_idx / r_idx.iloc[0] * 100, mode="lines", name=sel.nombre_ref,
                        line=dict(color=ui.GRIS_REF, width=2, dash="dot"),
                        hovertemplate="%{y:,.0f}<extra>" + sel.nombre_ref + "</extra>")
    fig.update_layout(height=400, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0), yaxis=dict(title=f"Base 100 ({base_txt})"))
    ui.mostrar(fig)
    st.caption("Incluye dividendos reinvertidos. "
               + (f"Base 100 en {ui.fecha_txt(idx.index[0])}, primera fecha con datos de todas las acciones." if inicio_comun is not None
                  else "Las series no comparten fechas suficientes; cada una parte de su primer dato."))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Caída desde el máximo anterior (drawdown)**")
        fig = go.Figure()
        for t in tickers:
            d = pf.caida(ret[t].dropna())
            fig.add_scatter(x=d.index, y=d * 100, mode="lines", name=t, line=dict(color=COLOR[t], width=1.6),
                            hovertemplate="%{y:.1f} %<extra>" + t + "</extra>")
        fig.update_layout(height=330, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
                          legend=dict(orientation="h", y=1.1, x=0), yaxis=dict(title="%", ticksuffix=" "))
        ui.mostrar(fig)
        st.caption("Cuánto se perdió en cada momento frente al mejor valor alcanzado hasta entonces.")
    with c2:
        st.markdown("**Volatilidad móvil de 26 semanas (anualizada)**")
        fig = go.Figure()
        for t in tickers:
            v = ret[t].dropna().rolling(26).std() * np.sqrt(pf.SEMANAS) * 100
            fig.add_scatter(x=v.index, y=v, mode="lines", name=t, line=dict(color=COLOR[t], width=1.6),
                            hovertemplate="%{y:.1f} %<extra>" + t + "</extra>")
        fig.update_layout(height=330, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified",
                          legend=dict(orientation="h", y=1.1, x=0), yaxis=dict(title="%"))
        ui.mostrar(fig)
        st.caption("Los picos coinciden con episodios de estrés de mercado; una volatilidad que sube indica más incertidumbre.")

    st.markdown("**Rentabilidad por periodo**")
    por_v = por.copy()
    st.dataframe(por_v.style.format(pct, na_rep="—").map(
        lambda v: "" if pd.isna(v) else ("background-color:#DDF3EA" if v > 0 else "background-color:#FBDADB")),
        width="stretch")
    st.caption("1 año y menos: rentabilidad acumulada. 3 y 5 años: tasa anual compuesta. Verde: ganancia; rojo: pérdida.")

# =============================== RIESGO Y RETORNO ===================================
with tab_rr:
    st.markdown("**Mapa riesgo–retorno**")
    fig = go.Figure()
    for t in tickers:
        fig.add_scatter(x=[est.loc[t, "Volatilidad"] * 100], y=[est.loc[t, "Retorno anual"] * 100], mode="markers+text",
                        name=t, text=[t], textposition="top center", marker=dict(size=15, color=COLOR[t], line=dict(width=2, color="white")),
                        hovertemplate=f"{NOMBRE[t]}<br>Volatilidad %{{x:.1f}} %<br>Retorno %{{y:.1f}} %<extra></extra>")
    if est_ref is not None:
        fig.add_scatter(x=[est_ref["Volatilidad"] * 100], y=[est_ref["Retorno anual"] * 100], mode="markers+text",
                        name=sel.nombre_ref, text=[sel.nombre_ref], textposition="bottom center",
                        marker=dict(size=14, color=ui.GRIS_REF, symbol="diamond", line=dict(width=2, color="white")),
                        hovertemplate=f"{sel.nombre_ref}<br>Volatilidad %{{x:.1f}} %<br>Retorno %{{y:.1f}} %<extra></extra>")
    fig.add_hline(y=sel.rf * 100, line=dict(color=ui.GRIS_REF, dash="dot", width=1),
                  annotation_text=f"Tasa libre {ui.pct(sel.rf)}", annotation_position="bottom right")
    fig.update_layout(height=470, margin=dict(l=8, r=8, t=24, b=8), showlegend=False,
                      xaxis=dict(title="Volatilidad anual (%)", rangemode="tozero"), yaxis=dict(title=f"Retorno anual, {base_txt} (%)"))
    ui.mostrar(fig)
    st.caption("Arriba y a la izquierda es mejor: más retorno con menos riesgo. Por debajo de la línea punteada, el "
               "retorno no superó a la tasa libre de riesgo.")

    if "Beta" in est:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Beta frente a {sel.nombre_ref}**")
            b = est.loc[tickers, "Beta"]
            fig = go.Figure(go.Bar(y=tickers, x=b, orientation="h", marker_color=[COLOR[t] for t in tickers],
                                   text=[ui.num(v) for v in b], textposition="outside",
                                   hovertemplate="%{y}: beta %{x:.2f}<extra></extra>"))
            fig.add_vline(x=1, line=dict(color=ui.GRIS_REF, dash="dash", width=1), annotation_text="Mercado = 1")
            fig.update_layout(height=60 + 46 * len(tickers), margin=dict(l=8, r=40, t=24, b=8), showlegend=False,
                              yaxis=dict(autorange="reversed"), xaxis=dict(title="Beta (semanal)"))
            ui.mostrar(fig)
            st.caption("Beta > 1: amplifica los movimientos del índice; < 1: los atenúa.")
        with c2:
            st.markdown("**Correlación entre las acciones**")
            if corr is not None:
                fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, zmin=-0.2, zmax=1,
                                           colorscale=[[i / 3, c] for i, c in enumerate(ui.RAMPA[:4])],
                                           text=[[ui.num(v) for v in fila] for fila in corr.values], texttemplate="%{text}",
                                           xgap=2, ygap=2, colorbar=dict(thickness=10, title="ρ"),
                                           hovertemplate="%{y} · %{x}: %{z:.2f}<extra></extra>"))
                fig.update_layout(height=60 + 46 * len(tickers), margin=dict(l=8, r=8, t=24, b=8),
                                  yaxis=dict(autorange="reversed"))
                ui.mostrar(fig)
                st.caption("Cuanto más baja, más diversifican entre sí. Calculada con retornos semanales del periodo común.")
            else:
                st.info("Elige al menos dos acciones para ver correlaciones.")

    st.markdown("**Indicadores de riesgo**")
    cols = [c for c in ["Volatilidad", "Sharpe", "Sortino", "Caída máxima", "VaR 95 % (sem.)", "CVaR 95 % (sem.)", "Beta",
                        "Alfa anual", "Correlación", "R²", "Semanas"] if c in est.columns]
    ft = {c: (f2 if c in ("Sharpe", "Sortino", "Beta", "Correlación", "R²") else (lambda v: ui.num(v, 0)) if c == "Semanas" else pct) for c in cols}
    st.dataframe(est.loc[tickers, cols].style.format(ft, na_rep="—"), width="stretch")
    st.caption("VaR 95 %: pérdida semanal superada solo 1 de cada 20 semanas. CVaR: pérdida promedio en ese 5 % peor. "
               "Alfa: retorno anual no explicado por el índice (Jensen). Con menos de 3 años, el alfa y el beta son poco fiables.")

# =============================== VALORACIÓN Y SOLIDEZ ===============================
with tab_val:
    v = pd.DataFrame(index=tickers)
    v["P/E"], v["P/B"], v["EV/EBITDA"] = filas["P/E"], filas["P/B"], [(perfiles.get(t) or {}).get("ev_ebitda") for t in tickers]
    v["Dividendo"], v["ROE"], v["Margen neto"] = filas["Dividendo"], filas["ROE"], filas["Margen neto"]
    v["Margen operativo"] = [(perfiles.get(t) or {}).get("margen_operativo") for t in tickers]
    v["D/E"], v["Crec. ingresos"] = filas["D/E"], [(perfiles.get(t) or {}).get("crec_ingresos") for t in tickers]
    for c in v.columns:
        v[c] = pd.to_numeric(v[c], errors="coerce")
    pts, tono = lecturas.valoracion(v, {t: perfiles.get(t) for t in tickers})
    tema.lectura(pts, titulo="Análisis de valoración y solidez", tono=tono)

    metricas = [("P/E", "Precio / utilidad (veces)", f1x, False), ("P/B", "Precio / valor en libros (veces)", f1x, False),
                ("EV/EBITDA", "EV / EBITDA (veces)", f1x, False), ("Dividendo", "Rentabilidad por dividendo", pct, True),
                ("ROE", "Retorno sobre patrimonio (ROE)", pct, True), ("Margen neto", "Margen neto", pct, True),
                ("D/E", "Deuda / patrimonio", lambda x: ui.pct(x, 0), False), ("Crec. ingresos", "Crecimiento de ingresos", pct, True)]
    cols3 = st.columns(3)
    for i, (c, titulo, f, _) in enumerate(metricas):
        s = v[c].dropna()
        with cols3[i % 3]:
            st.markdown(f"**{titulo}**")
            if s.empty:
                st.caption("Sin datos en Yahoo para estas acciones.")
                continue
            fig = go.Figure(go.Bar(y=s.index, x=s.values, orientation="h", marker_color=[COLOR[t] for t in s.index],
                                   text=[f(x) for x in s.values], textposition="outside",
                                   hovertemplate="%{y}: %{text}<extra></extra>"))
            fig.update_layout(height=70 + 38 * len(s), margin=dict(l=8, r=60, t=8, b=8), showlegend=False,
                              yaxis=dict(autorange="reversed"), xaxis=dict(showticklabels=False))
            ui.mostrar(fig)
    st.caption("Cada barra usa el color de su acción en todos los gráficos. Faltan datos cuando Yahoo no los publica para la emisora "
               "(frecuente en Colombia) o cuando se descartaron por no ser confiables (P/E negativo o extremo, P/B con error de monedas).")
    ctx = pd.DataFrame({"Empresa": [NOMBRE[t] for t in tickers], "Sector": [(perfiles.get(t) or {}).get("sector") or "—" for t in tickers],
                        "Industria": [(perfiles.get(t) or {}).get("industria") or "—" for t in tickers],
                        "País": [(perfiles.get(t) or {}).get("pais") or "—" for t in tickers],
                        "Moneda de reporte": [(perfiles.get(t) or {}).get("moneda") or "—" for t in tickers]}, index=tickers)
    st.dataframe(ctx, width="stretch")

# =============================== FICHA ==============================================
with tab_ficha:
    t = st.selectbox("Acción", tickers, format_func=lambda x: f"{x} · {NOMBRE[x]}", key="ficha_t")
    p = perfiles.get(t) or {}
    fila = est.loc[t]
    st.markdown(f"### {NOMBRE[t]}")
    st.caption(" · ".join(x for x in [p.get("sector"), p.get("industria"), p.get("pais"), p.get("bolsa")] if x) or "Sin perfil en Yahoo.")
    pts, tono = lecturas.accion(t, fila, perfiles.get(t), sel.nombre_ref, sel.rf)
    tema.lectura(pts, tono=tono, nota=lecturas.NOTA_ESTADISTICA)

    s = px[t].dropna()
    ult = s.iloc[-1]
    ult52 = s.iloc[-52:] if len(s) >= 52 else s
    k = ui.tarjetas(5, ancho=190)
    k[0].metric(f"Último precio ajustado ({base_txt})", ui.num(ult, 2), border=True)
    k[1].metric("Rango de 52 semanas", f"{ui.num(ult52.min(), 0)} – {ui.num(ult52.max(), 0)}", border=True,
                help=f"El precio está {ui.pct(ult / ult52.max() - 1, 1)} frente al máximo de 52 semanas.")
    cap = p.get("cap_mercado")
    cap_txt = "—" if not cap else (f"{ui.num(cap / 1e12, 2)} billones {p.get('moneda') or ''}" if cap >= 1e12
                                   else f"{ui.num(cap / 1e9, 1)} mil millones {p.get('moneda') or ''}")
    k[2].metric("Capitalización", cap_txt, border=True, help="Valor de mercado en la moneda de reporte de Yahoo "
                "(billón = 10¹², mil millones = 10⁹).")
    k[3].metric("P/E", f1x(p["pe"]) if p.get("pe") and 0 < p["pe"] < 300 else "—", border=True)
    k[4].metric("Rentabilidad por dividendo", pct(p["div_yield"]) if p.get("div_yield") else "—", border=True)

    fig = go.Figure()
    fig.add_scatter(x=s.index, y=s, mode="lines", name="Precio ajustado", line=dict(color=COLOR[t], width=2))
    for ventana, color in ((26, ui.AZUL), (52, ui.GRIS)):
        m = s.rolling(ventana).mean()
        fig.add_scatter(x=m.index, y=m, mode="lines", name=f"Media {ventana} sem.", line=dict(color=color, width=1.4, dash="dot"))
    fig.update_layout(height=380, margin=dict(l=8, r=8, t=24, b=8), hovermode="x unified", legend=dict(orientation="h", y=1.1, x=0),
                      yaxis=dict(title=f"Precio ajustado ({base_txt})"))
    ui.mostrar(fig)

    emp = almacen.leer_empresas_propias()
    prop = almacen.leer_betas_propios()
    if emp is not None and prop is not None and t in set(emp["ticker"]):
        fe = emp[emp["ticker"] == t].iloc[0]
        dam = almacen.leer_betas("emergentes")
        fp = prop[prop["industria"] == fe["industria"]]
        fd = dam[dam["industria"] == fe["industria"]]
        st.markdown("##### Conexión con el beta de la industria")
        c = ui.tarjetas(4)
        c[0].metric("Industria (Damodaran)", fe["industria"], border=True)
        c[1].metric("Beta de esta acción (cuaderno)", ui.num(fe["beta_vs_indice_pais"]) if pd.notna(fe["beta_vs_indice_pais"]) else "—",
                    border=True, help="Contra el ETF de su país en USD; apalancado.")
        c[2].metric("βU propio de la industria", ui.num(fp["beta_desapalancada_caja"].iloc[0]) if len(fp) else "—", border=True)
        c[3].metric("βU Damodaran emergentes", ui.num(fd["beta_desapalancada_caja"].iloc[0]) if len(fd) else "—", border=True)
        if str(fe.get("motivo_exclusion", "")) not in ("", "nan"):
            st.caption(f"Esta acción **no entra** al beta de su industria en la corrida cargada ({fe['motivo_exclusion']}).")
    if p.get("resumen"):
        with st.expander("Descripción del negocio (Yahoo Finance, en inglés)"):
            st.write(p["resumen"])
    for b in p.get("banderas", []):
        st.warning(b, icon=":material/warning:")
