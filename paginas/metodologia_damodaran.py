"""Metodología de Damodaran: betas por industria, prima de mercado, riesgo país y armado del Ke, con datos reales."""
from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import almacen, mercado, tema, ui
from nucleo import costo_capital as cc

tema.encabezado(
    "Metodología de Damodaran",
    "Cómo construye **Aswath Damodaran** (NYU Stern) los insumos más usados para estimar el costo de capital en mercados "
    "emergentes: betas por industria, prima de mercado y prima de riesgo país. Cada paso se muestra con sus cifras reales.",
    seccion="Costo de capital", chips=["Betas por industria", "ERP implícita", "Riesgo país", "Datos de enero de cada año"])

pais = almacen.leer_parametros_pais()
em, gl, us = almacen.leer_betas("emergentes"), almacen.leer_betas("global"), almacen.leer_betas("eeuu")
ref = mercado.supuestos_referencia()
if pais is None or em is None:
    st.info("Faltan los datos de Damodaran. Usa **Actualizar datos ahora**.")
    st.stop()


def tarjeta(col, titulo: str, texto: str) -> None:
    with col.container(border=True):
        st.markdown(f"#### {titulo}")
        st.caption(texto)


tema.lectura([
    "Damodaran es profesor de finanzas en la Universidad de Nueva York (NYU Stern). Cada enero publica bases de datos gratuitas con "
    "betas por industria, primas de riesgo por país, tasas de impuestos y múltiplos, que se usan en valoración en todo el mundo.",
    f"El tablero usa sus archivos de **{pais['fecha_archivo']}**: betas de {len(em)} industrias calculadas con "
    f"**{int(em['n_empresas'].sum()):,} empresas de mercados emergentes**, y la prima de riesgo de Colombia.".replace(",", "."),
    "Su método se resume en cuatro piezas: **beta del negocio por industria**, **prima de un mercado maduro**, **prima de riesgo país** "
    "y una forma de **combinarlas** en el Ke.",
], titulo="¿Quién es Damodaran y qué publica?", tono="neutro")

t1, t2, t3, t4, t5 = st.tabs(["① Beta por industria", "② Prima de mercado (ERP)", "③ Riesgo país (CRP)",
                              "④ Armar el Ke", "⑤ Ventajas y límites"])

# =============================== ① BETA POR INDUSTRIA ===============================
with t1:
    cols = st.columns(4, gap="small")
    for col, (t, d) in zip(cols, [
            ("1 · Regresión", "Calcula el beta de cada empresa con sus retornos históricos contra un índice de mercado."),
            ("2 · Promedio", "Promedia los betas de todas las empresas de la industria (cientos o miles)."),
            ("3 · Desapalancar", "Quita el efecto de la deuda con el D/E y la tasa de impuestos promedio de la industria."),
            ("4 · Corregir por caja", "Quita el efecto del efectivo, que tiene riesgo casi nulo y «diluye» el beta del negocio.")]):
        tarjeta(col, t, d)
    st.latex(r"\beta_u = \frac{\beta_L}{1+(1-t)\,D/E} \qquad\qquad \beta_u^{caja} = \frac{\beta_u}{1-\text{caja}/V}")

    industrias = em["industria"].tolist()
    ind = st.selectbox("Mira el cálculo de una industria", industrias,
                       index=industrias.index("Food Processing") if "Food Processing" in industrias else 0, key="dam_ind")
    f = em[em["industria"] == ind].iloc[0]
    bu_rec = f["beta_apalancada"] / (1 + (1 - f["tasa_efectiva"]) * f["de"])
    k = ui.tarjetas(5, ancho=190)
    k[0].metric("Empresas", f"{int(f['n_empresas']):,}".replace(",", "."), border=True)
    k[1].metric("β apalancado promedio", ui.num(f["beta_apalancada"]), border=True)
    k[2].metric("D/E promedio", ui.pct(f["de"], 0), border=True, help=f"Tasa efectiva de impuestos: {ui.pct(f['tasa_efectiva'], 1)}")
    k[3].metric("βu (sin deuda)", ui.num(f["beta_desapalancada"]), border=True,
                help=f"Con la fórmula de Hamada y la tasa efectiva publicada da {ui.num(bu_rec)}; Damodaran trabaja con promedios de "
                     "la industria, por eso puede haber una diferencia pequeña.")
    k[4].metric("βu corregido por caja", ui.num(f["beta_desapalancada_caja"]), border=True,
                help=f"{ui.num(f['beta_desapalancada'])} / (1 − {ui.pct(f['caja_valor_firma'], 1)}) = {ui.num(f['beta_desapalancada_caja'])}")
    st.markdown(f"**La receta con números:** {ui.num(f['beta_apalancada'])} ÷ [1 + (1 − {ui.pct(f['tasa_efectiva'], 1)}) × "
                f"{ui.pct(f['de'], 0)}] ≈ **{ui.num(f['beta_desapalancada'])}**, y al corregir por caja: "
                f"{ui.num(f['beta_desapalancada'])} ÷ (1 − {ui.pct(f['caja_valor_firma'], 1)}) = **{ui.num(f['beta_desapalancada_caja'])}**.")

    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.markdown("**βu corregido por caja: las industrias más y menos riesgosas (emergentes)**")
        orden = em.sort_values("beta_desapalancada_caja")
        g = pd.concat([orden.head(10), orden.tail(10)])
        if ind not in set(g["industria"]):
            g = pd.concat([g, em[em["industria"] == ind]]).sort_values("beta_desapalancada_caja")
        fig = go.Figure(go.Bar(y=g["industria"], x=g["beta_desapalancada_caja"], orientation="h",
                               marker_color=[ui.ROJO if i == ind else "#B8B8C0" for i in g["industria"]],
                               text=[ui.num(v) for v in g["beta_desapalancada_caja"]], textposition="outside",
                               hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
        fig.update_layout(height=620, margin=dict(l=8, r=40, t=24, b=8), showlegend=False, xaxis=dict(title="βu corregido por caja"))
        ui.mostrar(fig)
        st.caption("Las 10 industrias de menor y de mayor beta del negocio; la elegida va en rojo.")
    with c2:
        st.markdown(f"**{ind}: emergentes, global y EE. UU.**")
        vals = []
        for nombre, df in (("Emergentes", em), ("Global", gl), ("EE. UU.", us)):
            if df is not None and ind in set(df["industria"]):
                r = df[df["industria"] == ind].iloc[0]
                vals.append((nombre, float(r["beta_desapalancada_caja"]), int(r["n_empresas"])))
        fig = go.Figure(go.Bar(x=[v[0] for v in vals], y=[v[1] for v in vals], marker_color=[ui.ROJO, ui.AZUL, ui.GRIS][:len(vals)],
                               text=[f"{ui.num(v[1])}<br>{v[2]:,} emp.".replace(",", ".") for v in vals], textposition="outside",
                               hovertemplate="%{x}: %{y:.2f}<extra></extra>"))
        fig.update_layout(height=360, margin=dict(l=8, r=8, t=24, b=8), showlegend=False, yaxis=dict(title="βu corregido por caja", rangemode="tozero"))
        ui.mostrar(fig)
        st.caption("Para empresas colombianas se suele usar el universo de mercados emergentes o el global.")

# =============================== ② ERP ==============================================
with t2:
    st.markdown("La **prima de riesgo de mercado (ERP)** es lo que los inversionistas exigen por tener acciones en lugar de bonos "
                "del Gobierno de EE. UU. Hay dos formas de estimarla:")
    c1, c2 = st.columns(2, gap="large")
    tarjeta(c1, "Histórica", "Promedio de lo que rindieron las acciones por encima de los bonos en el pasado. Es simple, pero muy "
            "inestable: depende del periodo elegido y su error es de varios puntos.")
    tarjeta(c2, "Implícita (la de Damodaran)", "Parte del precio actual del S&P 500 y de los dividendos y recompras esperados, y "
            "encuentra la rentabilidad que iguala ambos. Mira hacia adelante y se actualiza con el mercado.")
    k = ui.tarjetas(2, ancho=260)
    k[0].metric("ERP de un mercado maduro", ui.pct(pais["erp_madura"]), border=True,
                help="Prima implícita del S&P 500, neta del spread de default de EE. UU.")
    k[1].metric("ERP de EE. UU.", ui.pct(pais["erp_eeuu"]), border=True)
    hist = almacen.leer_historial_parametros()
    if hist is not None and len(hist) > 1:
        st.markdown("**Historial de los supuestos descargados**")
        st.dataframe(hist, hide_index=True, width="stretch")
    st.caption(f"Archivo de Damodaran de {pais['fecha_archivo']}. La prima madura es la base a la que se suma el riesgo de cada país.")

# =============================== ③ CRP ==============================================
with t3:
    st.markdown("Invertir en Colombia tiene un riesgo adicional al de un mercado maduro: **la prima de riesgo país (CRP)**. "
                "Damodaran la estima a partir del riesgo de impago del Gobierno, ajustado porque las acciones son más volátiles que los bonos:")
    st.latex(r"CRP = \text{spread de default soberano} \times \frac{\sigma_{acciones}}{\sigma_{bonos}}")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Ruta por calificación (la que usa el tablero por defecto)**")
        st.markdown(f"""
- Calificación de Moody's de Colombia: **{pais['calificacion_moodys']}**
- Spread de default de esa calificación: **{ui.pct(pais['spread_default_calificacion'])}**
- Multiplicador de volatilidad (σ acciones / σ bonos): **{ui.num(pais['multiplicador_volatilidad'])}**
- CRP = {ui.pct(pais['spread_default_calificacion'])} × {ui.num(pais['multiplicador_volatilidad'])} = **{ui.pct(pais['crp_calificacion'])}**
- **ERP total de Colombia** = {ui.pct(pais['erp_madura'])} + {ui.pct(pais['crp_calificacion'])} = **{ui.pct(pais['erp_total_calificacion'])}**
""")
    with c2:
        st.markdown("**Ruta por CDS (el seguro contra impago que cotiza el mercado)**")
        st.markdown(f"""
- CDS neto de Colombia: **{ui.pct(pais['cds_neto'])}**
- CRP = CDS × multiplicador = **{ui.pct(pais['crp_cds'])}**
- **ERP total de Colombia** = {ui.pct(pais['erp_madura'])} + {ui.pct(pais['crp_cds'])} = **{ui.pct(pais['erp_total_cds'])}**
""")
    fig = go.Figure()
    for nombre, crp in (("Por calificación", pais["crp_calificacion"]), ("Por CDS", pais["crp_cds"])):
        fig.add_bar(name="Prima madura" if nombre == "Por calificación" else None, x=[nombre], y=[pais["erp_madura"] * 100],
                    marker_color=ui.GRIS, showlegend=nombre == "Por calificación", text=[ui.pct(pais["erp_madura"])], textposition="inside")
        fig.add_bar(name="Riesgo país" if nombre == "Por calificación" else None, x=[nombre], y=[crp * 100], marker_color=ui.ROJO,
                    showlegend=nombre == "Por calificación", text=[ui.pct(crp)], textposition="inside")
    fig.update_layout(height=330, barmode="stack", margin=dict(l=8, r=8, t=24, b=8), yaxis=dict(title="Prima total de Colombia (%)"),
                      legend=dict(orientation="h", y=1.1, x=0))
    st.markdown("**Cómo se forma la prima total de Colombia**")
    ui.mostrar(fig)
    tema.lectura([
        f"La ruta por CDS da una prima **{ui.num((pais['crp_cds'] - pais['crp_calificacion']) * 100)} puntos mayor** que la de calificación: "
        "el mercado está cobrando hoy más riesgo del que refleja la calificación.",
        "Por eso conviene reportar el Ke con las dos rutas, como un rango, y no como una cifra única.",
    ], titulo="Lectura", tono="alerta" if pais["crp_cds"] > pais["crp_calificacion"] * 1.3 else "neutro")

# =============================== ④ ARMAR EL KE ======================================
with t4:
    st.markdown("Con las tres piezas, el costo del patrimonio para una empresa colombiana se arma en dólares y luego se lleva a pesos:")
    st.latex(r"K_e^{USD} = R_f^{USA} + \beta_L \times ERP_{madura} + \lambda \times CRP")
    st.latex(r"K_e^{COP} = (1+K_e^{USD})\,\frac{1+\pi_{COL}}{1+\pi_{USA}} - 1")
    c1, c2 = st.columns(2, gap="large")
    tarjeta(c1, "λ = 1 (aditivo)", "Toda empresa colombiana asume el riesgo país completo, sin importar su sector. Es la opción más común.")
    tarjeta(c2, "λ = βL (proporcional)", "El riesgo país crece con la sensibilidad de la empresa al mercado: un sector defensivo paga menos riesgo país.")
    if ref is None:
        st.info("Faltan datos de mercado para el ejemplo.")
    else:
        s0, _ = ref
        f = em[em["industria"] == st.session_state.get("dam_ind", "Food Processing")]
        f = (f if len(f) else em).iloc[0]
        r = cc.calcular(cc.Supuestos(**{**asdict(s0), "beta_u": float(f["beta_desapalancada_caja"]), "de": float(f["de"])}))
        st.markdown(f"**Ejemplo con {f['industria']}** (la industria elegida en la pestaña ①, con su D/E promedio):")
        fig = go.Figure(go.Waterfall(
            x=["Tasa libre (Tesoro)", "βL × ERP madura", "Riesgo país", "Ke en USD", "Paso a pesos", "Ke en COP"],
            measure=["relative", "relative", "relative", "total", "relative", "total"],
            y=[s0.rf * 100, r["prima_mercado"] * 100, r["prima_pais"] * 100, 0, (r["ke_cop"] - r["ke_usd"]) * 100, 0],
            text=[ui.pct(v) for v in (s0.rf, r["prima_mercado"], r["prima_pais"], r["ke_usd"], r["ke_cop"] - r["ke_usd"], r["ke_cop"])],
            textposition="outside", increasing=dict(marker=dict(color=ui.GRIS)), decreasing=dict(marker=dict(color=ui.AZUL)),
            totals=dict(marker=dict(color=ui.ROJO)), connector=dict(line=dict(color=ui.GRIS_REF, dash="dot")),
            hovertemplate="%{x}: %{text}<extra></extra>"))
        fig.update_layout(height=360, margin=dict(l=8, r=8, t=28, b=8), showlegend=False,
                          yaxis=dict(title="%", range=[0, max(r["ke_cop"], r["ke_usd"]) * 100 * 1.2]))
        ui.mostrar(fig)
        st.caption(f"βL = {ui.num(r['beta_apalancada'])} (βu {ui.num(f['beta_desapalancada_caja'])} reapalancada con D/E de "
                   f"{ui.pct(f['de'], 0)} e impuesto de {ui.pct(s0.tasa_impuesto, 0)}). Inflación supuesta: Colombia "
                   f"{ui.pct(s0.infl_col)}, EE. UU. {ui.pct(s0.infl_usa)}.")
        st.page_link("paginas/costo_capital.py", label="Hacer el cálculo completo con tus supuestos", icon=":material/calculate:")

# =============================== ⑤ VENTAJAS Y LÍMITES ===============================
with t5:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Ventajas")
        st.markdown("""
- **Muchas empresas por industria:** el error del beta promedio es pequeño.
- **Transparente y citable:** datos públicos, con fecha y metodología documentada.
- **Comparable:** la misma metodología para todos los países, usada por analistas y académicos.
- **Separa el riesgo del negocio de la deuda:** permite reapalancar con la estructura de cada empresa.
""")
    with c2:
        st.markdown("#### Límites para Colombia")
        st.markdown(f"""
- **No es específico de Colombia ni de Latinoamérica:** el universo emergente de {int(em['n_empresas'].sum()):,} empresas está dominado por Asia.
- **Promedios de industria:** el D/E, los impuestos y la caja son promedios, no los de la empresa analizada.
- **Se actualiza una vez al año** (enero), con un ajuste del riesgo país a mitad de año.
- **El riesgo país es una estimación:** la ruta por calificación y la ruta por CDS pueden diferir varios puntos.
""".replace(",", "."))
    tema.lectura([
        "Por estos límites, el tablero construye además un **beta propio con empresas latinoamericanas** y lo compara con el de Damodaran.",
        "Ninguno de los dos es «el correcto»: la decisión depende de cuántas empresas tenga el sector y de qué tan parecida sea la región a Colombia.",
    ], titulo="¿Y entonces?", tono="ok")
    b1, b2 = st.columns(2)
    b1.page_link("paginas/metodologia_propia.py", label="Ver la metodología propia", icon=":material/science:")
    b2.page_link("paginas/beta_latam.py", label="Comparar ambos betas", icon=":material/compare_arrows:")
