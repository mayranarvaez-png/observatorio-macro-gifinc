"""Guía didáctica: qué es el costo de capital, cómo se estima y qué hace el tablero."""
from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import almacen, mercado, tema, ui
from nucleo import costo_capital as cc

tema.encabezado(
    "¿Qué es el costo de capital?",
    "Una guía paso a paso para entender la **rentabilidad mínima** que exigen quienes financian una empresa, cómo se "
    "estima en Colombia con el CAPM y por qué este tablero construye un **beta propio de Latinoamérica**.",
    seccion="Guía", chips=["Ke · Kd · WACC", "CAPM", "Beta bottom-up", "Con datos del día"])

ref = mercado.supuestos_referencia()
pais = almacen.leer_parametros_pais()
tes10 = mercado.opciones_kd_base()["TES 10A + spread"]
betas = almacen.leer_betas("emergentes")
if ref is None or pais is None or tes10 is None or betas is None:
    st.warning("Faltan datos de mercado para los ejemplos con cifras del día. La explicación sigue siendo válida.",
               icon=":material/info:")
s0 = ref[0] if ref else None


def tarjeta(col, titulo: str, subtitulo: str, texto: str) -> None:
    """Tarjeta didáctica con borde: título, idea clave y explicación corta."""
    with col.container(border=True):
        st.markdown(f"#### {titulo}")
        if subtitulo:
            st.markdown(f"**{subtitulo}**")
        st.caption(texto)

# =============================== 1. LA IDEA =========================================
st.subheader("1. La idea en una frase")
tema.lectura([
    "El costo de capital es la **rentabilidad mínima** que exigen quienes ponen el dinero en una empresa o un proyecto.",
    "Si una inversión rinde **menos** que su costo de capital, **destruye valor** aunque tenga utilidades contables; si rinde más, lo crea.",
    "Por eso es la **tasa de descuento** que se usa para valorar empresas y para decidir si un proyecto conviene (VPN y TIR).",
], titulo="En pocas palabras", tono="ok")

st.markdown("Una empresa se financia con dinero de **dos tipos de personas**, y cada una cobra algo distinto:")
c1, c2, c3 = st.columns(3, gap="medium")
tarjeta(c1, "Ke", "Costo del patrimonio · lo exigen los accionistas",
        "No se ve en ningún extracto: hay que estimarlo con un modelo (el CAPM). Es el más alto, porque el accionista "
        "cobra solo lo que sobra después de pagarles a todos los demás.")
tarjeta(c2, "Kd", "Costo de la deuda · lo cobran bancos y bonistas",
        "Sí se observa: es la tasa de los créditos o de los bonos. Como los intereses se descuentan de impuestos, "
        "el costo real es Kd × (1 − t).")
tarjeta(c3, "WACC", "Costo promedio ponderado · la mezcla de los dos",
        "Se pondera según cuánto pesan el patrimonio y la deuda. Es la tasa con la que se descuentan los flujos de "
        "caja de toda la empresa.")
st.latex(r"WACC = \frac{E}{V}\,K_e + \frac{D}{V}\,K_d\,(1-t)")

st.markdown("##### Una analogía: ¿cuánto le cobrarías a cada uno?")
st.markdown("Imagina que tienes 10 millones y tres opciones para invertirlos. Mientras más riesgo asumes, más rentabilidad "
            "**exiges** a cambio:")
a1, a2, a3 = st.columns(3, gap="medium")
tarjeta(a1, "① Prestarle al Gobierno", "Casi sin riesgo → tasa libre (TES)",
        "El Gobierno colombiano casi siempre paga. Es el piso: ninguna inversión con riesgo debería rendir menos.")
tarjeta(a2, "② Prestarle a una empresa", "Algo de riesgo → costo de la deuda (Kd)",
        "La empresa podría no pagar, así que le cobras más que al Gobierno. Pero si quiebra, cobras antes que los socios.")
tarjeta(a3, "③ Volverte socio", "Más riesgo → costo del patrimonio (Ke)",
        "No tienes pago fijo y cobras de último. Por eso exiges la rentabilidad más alta de las tres.")
if tes10 is not None and pais is not None:
    escalon_kd = tes10 + 0.02
    escalon_ke = (tes10 - pais["spread_default_calificacion"]) + 1.0 * pais["erp_total_calificacion"]
    fig = go.Figure(go.Bar(
        x=["① Gobierno (TES 10A)", "② Deuda de una empresa", "③ Patrimonio (β = 1)"],
        y=[tes10 * 100, escalon_kd * 100, escalon_ke * 100], marker_color=[ui.GRIS, ui.AZUL, ui.ROJO],
        text=[ui.pct(v) for v in (tes10, escalon_kd, escalon_ke)], textposition="outside",
        hovertemplate="%{x}: %{text}<extra></extra>"))
    fig.update_layout(height=320, margin=dict(l=8, r=8, t=24, b=8), showlegend=False,
                      yaxis=dict(title="Rentabilidad exigida (%)", rangemode="tozero"))
    st.markdown("**La escalera del riesgo, con las cifras de hoy**")
    ui.mostrar(fig)
    st.caption("TES 10A: último dato del BanRep. Deuda: TES + 2 puntos (supuesto ilustrativo). Patrimonio: empresa de riesgo "
               "promedio (β = 1) con la prima de riesgo de Colombia de Damodaran. Son cifras de ejemplo, no de una empresa real.")

# =============================== 2. PARA QUÉ SIRVE ==================================
st.subheader("2. ¿Por qué importa tanto la tasa?")
st.markdown("Un mismo flujo futuro vale muy distinto hoy según la tasa con la que se descuente. "
            "Mueve la tasa y mira cuánto valen hoy **100 millones que se recibirán en 5 años**:")
cc1, cc2 = st.columns([1, 2], gap="large")
with cc1:
    tasa = st.slider("Tasa de descuento (%)", 4.0, 25.0, 15.0, 0.5, key="guia_tasa") / 100
    anios = st.slider("Años hasta recibir el dinero", 1, 15, 5, key="guia_anios")
    vp = 100 / (1 + tasa) ** anios
    st.metric("Valor hoy", f"{ui.num(vp, 1)} millones", border=True,
              delta=f"{ui.num(vp - 100, 1)} frente a 100", delta_color="off")
with cc2:
    tasas = np.arange(0.04, 0.2501, 0.005)
    fig = go.Figure(go.Scatter(x=tasas * 100, y=100 / (1 + tasas) ** anios, mode="lines", line=dict(color=ui.AZUL, width=3),
                               hovertemplate="Tasa %{x:.1f} %: vale %{y:.1f} hoy<extra></extra>"))
    fig.add_scatter(x=[tasa * 100], y=[vp], mode="markers", marker=dict(size=14, color=ui.ROJO, line=dict(width=2, color="white")),
                    hoverinfo="skip")
    fig.update_layout(height=300, margin=dict(l=8, r=8, t=24, b=8), showlegend=False,
                      xaxis=dict(title="Tasa de descuento (%)"), yaxis=dict(title=f"Valor hoy de 100 en {anios} años"))
    ui.mostrar(fig)
st.caption("Por eso un error de 2 o 3 puntos en el costo de capital puede cambiar la decisión de invertir o el precio de una empresa.")

# =============================== 3. EL CAPM =========================================
st.subheader("3. Cómo se estima el Ke: el CAPM")
st.latex(r"K_e = R_f + \beta \times ERP")
st.markdown("Se lee así: **lo que pagaría una inversión sin riesgo, más un premio por el riesgo que el accionista no puede "
            "eliminar diversificando**. Cada ingrediente tiene una fuente:")
filas = [
    ("Rf · tasa libre de riesgo", "Lo que rinde prestarle al Gobierno.",
     f"TES 10 años: {ui.pct(tes10)}" if tes10 else "TES 10 años (BanRep)",
     f"Tesoro EE. UU. 10 años: {ui.pct(s0.rf)}" if s0 else "Tesoro EE. UU. 10 años (FRED)"),
    ("ERP · prima de mercado", "Cuánto más rinden las acciones que los bonos, en promedio.",
     f"Prima total de Colombia: {ui.pct(pais['erp_total_calificacion'])}" if pais else "Damodaran",
     f"Mercado maduro: {ui.pct(pais['erp_madura'])}" if pais else "Damodaran"),
    ("CRP · riesgo país", "El riesgo adicional de invertir en Colombia.",
     "Ya va incluido en la prima total", f"{ui.pct(pais['crp_calificacion'])} (calificación {pais['calificacion_moodys']})" if pais else "Damodaran"),
    ("β · beta", "Cuánto se mueve la acción cuando se mueve el mercado.", "Del sector (ver punto 4)", "Del sector (ver punto 4)"),
]
st.dataframe(pd.DataFrame(filas, columns=["Ingrediente", "Qué significa", "Si se trabaja en pesos", "Si se trabaja en dólares"]),
             hide_index=True, width="stretch")
if pais:
    st.caption(f"Primas de Damodaran (NYU Stern), archivo de {pais['fecha_archivo']}. Tasas del último dato descargado.")

st.markdown("**¿Cómo se lee el beta?** Si el mercado sube 10 %…")
c1, c2, c3 = st.columns(3)
tarjeta(c1, "β = 0,5", "Defensiva: sube cerca de 5 %", "Se mueve menos que el mercado. Ejemplos típicos: energía eléctrica, alimentos básicos.")
tarjeta(c2, "β = 1,0", "Como el mercado: sube cerca de 10 %", "Tiene el riesgo de una empresa promedio.")
tarjeta(c3, "β = 1,5", "Agresiva: sube cerca de 15 %", "Amplifica el mercado, para bien y para mal. Ejemplos típicos: construcción, tecnología.")
st.caption("Y al revés: si el mercado cae 10 %, la de β = 1,5 cae cerca de 15 %. Por ese riesgo extra, el accionista exige más.")

# =============================== 4. EL BETA EN COLOMBIA =============================
st.subheader("4. El problema del beta en Colombia y el método bottom-up")
tema.lectura([
    "El beta de **una sola acción** se mide con una regresión y tiene un error grande (±0,2 a ±0,3 es normal).",
    "En la Bolsa de Colombia hay **pocas empresas por sector**, muchas se negocian poco y varios sectores no tienen ninguna.",
    "Por eso no se usa el beta de una empresa sino el **del negocio**, medido con muchas empresas comparables: es el método *bottom-up* de Damodaran.",
], titulo="Por qué no basta con medir una acción colombiana", tono="alerta")
pasos = [
    ("1. Medir", "Beta de muchas acciones comparables del mismo sector (aquí, de toda Latinoamérica)."),
    ("2. Desapalancar", "Quitar el efecto de la deuda de cada empresa para quedarse con el riesgo del negocio (βu)."),
    ("3. Promediar", "Promedio por sector: con muchas empresas el error baja."),
    ("4. Reapalancar", "Volver a poner la deuda y los impuestos de la empresa que se analiza (βL)."),
]
cols = st.columns(4, gap="small")
for col, (t, d) in zip(cols, pasos):
    tarjeta(col, t, "", d)
st.latex(r"\beta_u = \frac{\beta_L}{1+(1-t)\,D/E} \qquad\qquad \beta_L = \beta_u\,[\,1+(1-t)\,D/E\,]")
st.markdown("Damodaran ya publica betas por sector, pero con empresas de **todos** los mercados emergentes (China, India…). "
            "La pregunta de este proyecto es si el beta medido con **empresas latinoamericanas** es distinto, y cuál conviene "
            "usar para Colombia. La comparación está en la página **Beta propio vs Damodaran**.")

# =============================== 5. CALCULADORA =====================================
st.subheader("5. Pruébalo: arma el Ke de un sector")
if s0 is None or betas is None or tes10 is None:
    st.info("Se necesitan los datos de mercado para la calculadora.")
else:
    industrias = betas["industria"].tolist()
    k1, k2 = st.columns([2, 1])
    sector = k1.selectbox("Sector (clasificación de Damodaran)", industrias,
                          index=industrias.index("Food Processing") if "Food Processing" in industrias else 0, key="guia_sector")
    fila = betas[betas["industria"] == sector].iloc[0]
    de = k2.slider("Deuda / patrimonio (%)", 0, 200, int(round(float(fila["de"]) * 100)), 5, key=f"guia_de_{sector}") / 100
    bu = float(fila["beta_desapalancada_caja"])
    t = float(pais.get("tasa_impositiva_marginal", 0.35))
    bl = cc.beta_apalancada(bu, de, t)

    # Ruta en pesos: TES menos el spread soberano (para no contar dos veces el riesgo país) + βL × prima total.
    rf_cop = tes10 - pais["spread_default_calificacion"]
    ke_pesos = rf_cop + bl * pais["erp_total_calificacion"]
    # Ruta en dólares (la del tablero): Tesoro + βL × prima madura + CRP, convertido a pesos por Fisher.
    r = cc.calcular(cc.Supuestos(**{**asdict(s0), "beta_u": bu, "de": de}))

    m = ui.tarjetas(4, ancho=210)
    m[0].metric("βu del sector", ui.num(bu), border=True, help=f"Damodaran, mercados emergentes ({int(fila['n_empresas'])} empresas).")
    m[1].metric("βL reapalancada", ui.num(bl), border=True, help=f"βu × [1 + (1 − {ui.pct(t, 0)}) × D/E]")
    m[2].metric("Ke · ruta en pesos", ui.pct(ke_pesos), border=True)
    m[3].metric("Ke · ruta en dólares → pesos", ui.pct(r["ke_cop"]), border=True)

    izq, der = st.columns(2, gap="large")
    with izq:
        st.markdown("**Ruta en pesos** (la del cuaderno de Colab)")
        st.latex(r"K_e = (TES - spread) + \beta_L \times ERP_{Colombia}")
        st.markdown(f"= ({ui.pct(tes10)} − {ui.pct(pais['spread_default_calificacion'])}) + {ui.num(bl)} × "
                    f"{ui.pct(pais['erp_total_calificacion'])} = **{ui.pct(ke_pesos)}**")
        st.caption("Se resta el spread soberano del TES porque el riesgo país ya está dentro de la prima total; si no, se contaría dos veces.")
    with der:
        st.markdown("**Ruta en dólares** (la de la página Costo de capital)")
        st.latex(r"K_e^{USD} = R_f^{USA} + \beta_L \times ERP_{madura} + CRP")
        st.markdown(f"= {ui.pct(s0.rf)} + {ui.num(bl)} × {ui.pct(s0.erp)} + {ui.pct(s0.crp)} = **{ui.pct(r['ke_usd'])}** en dólares, "
                    f"que en pesos (Fisher, inflación {ui.pct(s0.infl_col)} vs {ui.pct(s0.infl_usa)}) es **{ui.pct(r['ke_cop'])}**.")
        st.caption("La conversión a pesos depende de la inflación esperada que se suponga para Colombia y EE. UU.")

    dif = abs(ke_pesos - r["ke_cop"])
    puntos = [f"Las dos rutas dan **{ui.pct(ke_pesos)}** y **{ui.pct(r['ke_cop'])}**: una diferencia de {ui.num(dif * 100)} puntos.",
              "Ambas son válidas, pero cada una tiene sus propios supuestos: **no se deben mezclar piezas de una y otra**."]
    tono = "neutro"
    if r["ke_cop"] < tes10:
        puntos.append(f"En la ruta en dólares el Ke en pesos queda **por debajo del TES** ({ui.pct(tes10)}). Eso no tiene sentido "
                      "económico: suele indicar que la inflación supuesta para Colombia (la meta del BanRep) es menor que la que "
                      "descuenta el mercado. Es el aviso amarillo que aparece en Valoración y Proyectos.")
        tono = "alerta"
    tema.lectura(puntos, titulo="Cómo leer el resultado", tono=tono)

# =============================== 6. QUÉ HACE EL TABLERO =============================
st.subheader("6. Cómo encaja cada parte del tablero")
st.dataframe(pd.DataFrame([
    ("Cuaderno de Colab (Beta_Latinoamerica_CAPM)", "Descarga 585 acciones latinoamericanas y calcula el beta propio por sector."),
    ("Beta propio vs Damodaran", "Compara los dos betas sector por sector y permite elegir cuál usar (o un combinado)."),
    ("Costo de capital", "Calcula Ke y WACC con el beta elegido, paso a paso y con fuentes citables."),
    ("Valoración de empresas · Evaluación de proyectos", "Usan ese WACC como tasa de descuento."),
], columns=["Página", "Qué hace"]), hide_index=True, width="stretch")
b1, b2, b3 = st.columns(3)
b1.page_link("paginas/costo_capital.py", label="Calcular Ke y WACC", icon=":material/calculate:")
b2.page_link("paginas/beta_latam.py", label="Comparar betas", icon=":material/compare_arrows:")
b3.page_link("paginas/valoracion_empresas.py", label="Valorar una empresa", icon=":material/domain:")

# =============================== 7. ERRORES COMUNES =================================
st.subheader("7. Errores comunes")
errores = {
    "Usar el beta de una sola acción": "Su error estándar suele ser enorme. Usa el beta del sector (bottom-up) y reapalanca con la deuda de la empresa.",
    "Contar dos veces el riesgo país": "Si la tasa libre es el TES (que ya incluye riesgo soberano) y además se suma el CRP completo, el riesgo país entra dos veces. Resta el spread soberano del TES.",
    "Mezclar monedas": "Flujos en pesos se descuentan con una tasa en pesos; flujos en dólares, con una tasa en dólares. Si se mezclan, el valor queda sesgado por la inflación.",
    "Ke menor que el TES": "El patrimonio siempre es más riesgoso que la deuda del Gobierno. Si el Ke queda por debajo del TES, revisa la inflación supuesta o el riesgo país.",
    "Usar el D/E contable": "Las ponderaciones del WACC y el reapalancamiento deben usar valores de mercado (o un D/E objetivo), no el patrimonio en libros.",
    "Desapalancar bancos y aseguradoras": "En las financieras la deuda es parte del negocio: se trabaja con el beta apalancado del sector.",
}
for titulo, texto in errores.items():
    with st.expander(titulo, icon=":material/report:"):
        st.write(texto)

# =============================== 8. COMPRUEBA LO QUE APRENDISTE ======================
st.subheader("8. Comprueba lo que aprendiste")
PREGUNTAS = [
    ("¿Por qué el Ke es más alto que el Kd en la misma empresa?",
     ["Porque los accionistas pagan más impuestos", "Porque el accionista cobra de último y no tiene pago fijo",
      "Porque los bancos prestan barato por ley"], 1,
     "El accionista asume más riesgo: solo recibe lo que sobra después de pagar a proveedores, trabajadores, bancos y al Estado."),
    ("Una acción tiene β = 1,4. Si el mercado cae 10 %, ¿qué se espera?",
     ["Que caiga cerca de 14 %", "Que caiga cerca de 4 %", "Que suba 14 %"], 0,
     "El beta multiplica el movimiento del mercado: 1,4 × (−10 %) ≈ −14 %."),
    ("¿Por qué el tablero no usa el beta de una sola empresa colombiana?",
     ["Porque Yahoo no tiene datos de Colombia", "Porque tiene mucho error y hay pocas empresas por sector",
      "Porque el CAPM no aplica en Colombia"], 1,
     "Por eso se usa el beta del sector, medido con muchas empresas comparables (método bottom-up)."),
    ("Si el Ke en pesos sale por debajo del TES, ¿qué conviene revisar?",
     ["Nada, es normal", "Los supuestos de inflación o de riesgo país", "El número de acciones de la empresa"], 1,
     "El patrimonio siempre es más riesgoso que la deuda del Gobierno; un Ke menor que el TES señala un supuesto incoherente."),
]
aciertos = 0
for i, (preg, opciones, correcta, explicacion) in enumerate(PREGUNTAS, 1):
    resp = st.radio(f"**{i}. {preg}**", opciones, index=None, key=f"guia_q{i}")
    if resp is not None:
        if opciones.index(resp) == correcta:
            aciertos += 1
            st.success(f"¡Correcto! {explicacion}", icon=":material/check_circle:")
        else:
            st.error(f"No exactamente. {explicacion}", icon=":material/cancel:")
respondidas = sum(st.session_state.get(f"guia_q{i}") is not None for i in range(1, len(PREGUNTAS) + 1))
if respondidas == len(PREGUNTAS):
    st.metric("Tu resultado", f"{aciertos} de {len(PREGUNTAS)}", border=True)

st.subheader("Resumen en cinco ideas")
tema.lectura([
    "El costo de capital es la **rentabilidad mínima** que exigen quienes financian la empresa; se usa como tasa de descuento.",
    "Tiene dos partes: **Ke** (accionistas, se estima) y **Kd** (deuda, se observa). Su promedio ponderado es el **WACC**.",
    "El Ke se estima con el **CAPM**: tasa libre de riesgo + beta × prima de mercado.",
    "En Colombia el beta se mide **por sector y con muchas empresas comparables** (bottom-up), no con una sola acción.",
    "Hay dos rutas válidas (en pesos o en dólares convertidos a pesos), pero **no se deben mezclar** sus piezas.",
], titulo="Para llevar", tono="ok")

# =============================== 9. GLOSARIO Y REFERENCIAS ==========================
with st.expander("Glosario", icon=":material/menu_book:"):
    st.markdown("""
- **Beta (β):** sensibilidad del retorno de una acción a los movimientos del mercado.
- **βu / βL:** beta desapalancada (solo el negocio) y apalancada (negocio más deuda).
- **CAPM:** modelo de valoración de activos de capital; relaciona el retorno exigido con el beta.
- **CRP:** prima de riesgo país (*country risk premium*).
- **D/E:** deuda sobre patrimonio, a valor de mercado.
- **ERP:** prima de riesgo del mercado accionario (*equity risk premium*).
- **Ke / Kd:** costo del patrimonio / costo de la deuda.
- **Paridad de Fisher:** conversión de una tasa entre monedas con el diferencial de inflación esperada.
- **Rf:** tasa libre de riesgo.
- **WACC:** costo promedio ponderado del capital.
""")
with st.expander("Referencias", icon=":material/school:"):
    st.markdown("""
- Sharpe, W. F. (1964). Capital asset prices: A theory of market equilibrium under conditions of risk. *The Journal of Finance*, 19(3), 425–442.
- Lintner, J. (1965). The valuation of risk assets and the selection of risky investments in stock portfolios and capital budgets. *The Review of Economics and Statistics*, 47(1), 13–37.
- Hamada, R. S. (1972). The effect of the firm's capital structure on the systematic risk of common stocks. *The Journal of Finance*, 27(2), 435–452.
- Damodaran, A. Datos de betas por industria y primas de riesgo por país, NYU Stern (actualización anual).
""")
