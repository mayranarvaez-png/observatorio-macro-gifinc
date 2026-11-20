"""Metodología propia: cómo se construyó el beta latinoamericano por sector, con sus resultados y estadísticas."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import almacen, beta_propio, tema, ui

tema.encabezado(
    "Metodología propia: beta latinoamericano por sector",
    "Cómo se estimó, paso a paso, el beta de cada sector con **acciones de toda Latinoamérica**, qué resultados dio y qué "
    "tan confiable es. Todas las cifras y gráficos salen de la corrida del cuaderno cargada en el tablero.",
    seccion="Costo de capital", chips=["Yahoo Finance", "Retornos semanales en USD", "Bottom-up", "Bootstrap"])

emp = almacen.leer_empresas_propias()
prop = almacen.leer_betas_propios()
meta = almacen.leer_meta_propia() or {}
dam = almacen.leer_betas("emergentes")
if emp is None or prop is None or dam is None:
    st.info("Todavía no hay una corrida del cuaderno cargada en el tablero.")
    st.stop()
estab = almacen.leer_extra_propio("estabilidad")
por_pais = almacen.leer_extra_propio("beta_por_pais")

emp["incluir"] = emp["incluir"].astype(bool)
inc = emp[emp["incluir"]]
exc = emp[~emp["incluir"]]
base = prop.merge(dam[["industria", "beta_desapalancada_caja"]].rename(columns={"beta_desapalancada_caja": "bu_dam"}),
                  on="industria", how="left")
base["dif"] = base["beta_desapalancada_caja"] - base["bu_dam"]
fuerte = base[(base["n_empresas"] >= 5) & ~base["financiera"].astype(bool)]
COLOR_CONF = {"Alta": ui.VERDE, "Media": ui.AMBAR, "Baja": ui.ROJO}


def tarjeta(col, titulo: str, texto: str) -> None:
    with col.container(border=True):
        st.markdown(f"#### {titulo}")
        st.caption(texto)


def layout(fig: go.Figure, alto: int = 340, **ejes) -> go.Figure:
    fig.update_layout(height=alto, margin=dict(l=8, r=8, t=28, b=8), **ejes)
    return fig


m = ui.tarjetas(5, ancho=200)
m[0].metric("Acciones analizadas", f"{len(emp)}", border=True)
m[1].metric("Países", f"{emp['pais_es'].nunique()}", border=True)
m[2].metric("Acciones que pasan los filtros", f"{len(inc)}", border=True, help=f"{ui.pct(len(inc) / len(emp), 0)} del universo")
m[3].metric("Sectores con beta propio", f"{len(prop)}", border=True)
m[4].metric("Sectores con 5 o más firmas", f"{int((prop['n_empresas'] >= 5).sum())}", border=True)
st.caption(f"Corrida del cuaderno: {meta.get('fecha_corrida', '—')}. {meta.get('fuente', '')}")

t1, t2, t3, t4, t5, t6, t7 = st.tabs(["① La idea", "② Datos", "③ Beta de cada acción", "④ Filtros de calidad",
                                      "⑤ Beta del sector", "⑥ Resultados", "⑦ Límites"])

# =============================== ① LA IDEA ==========================================
with t1:
    tema.lectura([
        "Colombia tiene **pocas empresas en bolsa por sector**, así que el beta de un sector no se puede medir solo con acciones colombianas.",
        "Damodaran resuelve el problema con miles de empresas de **todos** los mercados emergentes, donde China, India o Taiwán pesan mucho.",
        "La propuesta de este proyecto es medir el beta con empresas de **Latinoamérica**, una región más parecida a Colombia en "
        "tamaño de mercado, riesgo macroeconómico y estructura de los sectores.",
        "La pregunta de investigación: **¿el beta latinoamericano por sector es distinto del de Damodaran, y cuál conviene usar para Colombia?**",
    ], titulo="¿Por qué un beta propio?", tono="neutro")
    st.markdown("##### La ruta, en seis pasos")
    pasos = [("1 · Universo", "585 acciones de 13 países, clasificadas en las industrias de Damodaran."),
             ("2 · Datos", "Precios semanales de Yahoo Finance, convertidos a dólares; retornos logarítmicos."),
             ("3 · Beta por acción", "Regresión de cada acción contra el ETF de su país, con errores robustos."),
             ("4 · Filtros", "Se descartan acciones ilíquidas, con poca historia o con retornos extremos."),
             ("5 · Beta del sector", "Promedio balanceado por país, intervalo bootstrap y desapalancamiento."),
             ("6 · Comparación", "Contra Damodaran, y un beta combinado que pondera ambos.")]
    for fila in (pasos[:3], pasos[3:]):
        cols = st.columns(3, gap="small")
        for col, (t, d) in zip(cols, fila):
            tarjeta(col, t, d)

# =============================== ② DATOS ============================================
with t2:
    st.markdown("**De dónde salen los datos.** El universo parte de la lista de empresas latinoamericanas de Damodaran, con su "
                "clasificación industrial. Cada empresa se tradujo a su símbolo de Yahoo Finance y se verificó que existiera "
                "(por ejemplo, `.SA` Brasil, `.MX` México, `.SN` Chile, `.BA` Argentina, `.CL` Colombia; sin sufijo, las listadas en EE. UU.).")
    tabla = emp.groupby("pais_es").agg(Acciones=("ticker", "size"), Incluidas=("incluir", "sum")).sort_values("Acciones", ascending=False)
    if por_pais is not None:
        tabla = tabla.join(por_pais.set_index("pais_es")[["indice"]].rename(columns={"indice": "Mercado de referencia"}))
    tabla["% incluidas"] = tabla["Incluidas"] / tabla["Acciones"]
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        fig = go.Figure()
        fig.add_bar(y=tabla.index, x=tabla["Acciones"], orientation="h", name="Universo", marker_color="#C9C9CF")
        fig.add_bar(y=tabla.index, x=tabla["Incluidas"], orientation="h", name="Pasan los filtros", marker_color=ui.ROJO)
        ui.mostrar(layout(fig, 420, barmode="overlay", yaxis=dict(autorange="reversed"), xaxis=dict(title="Número de acciones"),
                          legend=dict(orientation="h", y=1.08, x=0)))
        st.caption("La barra roja es la parte de cada país que entra al cálculo. Brasil aporta el mayor número de empresas.")
    with c2:
        st.dataframe(tabla.style.format({"% incluidas": lambda v: ui.pct(v, 0)}), width="stretch", height=420)
    st.markdown("**Cómo se preparan los precios**")
    st.latex(r"r_{i,t} = \ln\!\left(\frac{P^{USD}_{i,t}}{P^{USD}_{i,t-1}}\right)")
    st.markdown("""
- **Barras semanales** (cierre de viernes): reducen el ruido de los días sin negociación y alinean mercados con feriados distintos.
- **Todo en dólares:** cada precio se convierte con el tipo de cambio de Yahoo, para comparar países con la misma vara.
- **Mercado de referencia = ETF del país en dólares** (EWZ, EWW, ECH, EPU, ARGT, e ICOLCAP convertido a dólares para Colombia).
  Se mide cada acción contra **su propio mercado**, como pide el CAPM local; no se usa un índice regional único porque el ETF de
  Latinoamérica (ILF) está dominado por Brasil.
- **Historial completo** de cada acción, con un mínimo de 3 años (156 semanas).
""")

# =============================== ③ BETA POR ACCIÓN ==================================
with t3:
    st.markdown("Para cada acción se estima la regresión de su retorno contra el retorno de su mercado:")
    st.latex(r"r_{i,t} = \alpha_i + \beta_i \, r_{m,t} + \varepsilon_{i,t}")
    c1, c2, c3 = st.columns(3)
    tarjeta(c1, "Errores robustos", "El error estándar del beta se calcula con Newey-West (4 rezagos), que tolera autocorrelación y "
            "varianza cambiante en los retornos.")
    tarjeta(c2, "Beta de Dimson", "Suma el efecto del mercado de la semana anterior y la siguiente. Corrige el beta de acciones que se "
            "negocian poco y reaccionan con rezago.")
    tarjeta(c3, "Beta de Blume", "0,67 × β + 0,33. Acerca el beta a 1, porque los betas extremos tienden a moderarse con el tiempo.")

    med, q1, q3 = inc["beta_vs_indice_pais"].median(), inc["beta_vs_indice_pais"].quantile(.25), inc["beta_vs_indice_pais"].quantile(.75)
    tema.lectura([
        f"El beta mediano de las {len(inc)} acciones incluidas es **{ui.num(med)}**; la mitad central está entre {ui.num(q1)} y {ui.num(q3)}.",
        f"El **{ui.pct((inc['beta_vs_indice_pais'] < 1).mean(), 0)}** de las acciones tiene beta menor que 1: la mayoría se mueve menos que su mercado, "
        "algo esperable porque los índices de la región están concentrados en pocas empresas grandes.",
        f"El R² mediano es **{ui.pct(inc['r2'].median(), 0)}**: el mercado explica una parte del movimiento de cada acción y el resto es riesgo propio "
        "de la empresa, que se diversifica.",
    ] + ([f"El error estándar mediano de un beta individual es **{ui.num(inc['se'].median())}**: por eso no conviene usar el beta de una sola acción."]
         if "se" in inc else []), titulo="Lo que muestran los datos", tono="neutro")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Distribución de los betas (acciones incluidas)**")
        fig = go.Figure(go.Histogram(x=inc["beta_vs_indice_pais"], nbinsx=40, marker_color=ui.AZUL, marker_line=dict(width=1, color="white"),
                                     hovertemplate="β %{x}: %{y} acciones<extra></extra>"))
        fig.add_vline(x=med, line=dict(color=ui.ROJO, width=2, dash="dash"), annotation_text=f"Mediana {ui.num(med)}")
        fig.add_vline(x=1, line=dict(color=ui.GRIS_REF, width=1, dash="dot"), annotation_text="β = 1", annotation_position="bottom right")
        ui.mostrar(layout(fig, 330, showlegend=False, xaxis=dict(title="Beta contra el ETF del país"), yaxis=dict(title="Acciones")))
    with c2:
        st.markdown("**Beta por país**")
        paises = inc["pais_es"].value_counts()
        paises = paises[paises >= 3].index.tolist()
        fig = go.Figure()
        for i, p in enumerate(paises):
            fig.add_box(y=inc.loc[inc["pais_es"] == p, "beta_vs_indice_pais"], name=p, marker_color=ui.PALETA[i % len(ui.PALETA)],
                        boxmean=True, line=dict(width=1.5))
        fig.add_hline(y=1, line=dict(color=ui.GRIS_REF, width=1, dash="dot"))
        ui.mostrar(layout(fig, 330, showlegend=False, yaxis=dict(title="Beta")))
        st.caption("Caja: 50 % central; línea: mediana; línea punteada dentro de la caja: promedio. Solo países con 3 o más acciones.")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**¿Cuánto explica el mercado? (R²)**")
        fig = go.Figure(go.Histogram(x=inc["r2"] * 100, nbinsx=30, marker_color=ui.GRIS, marker_line=dict(width=1, color="white"),
                                     hovertemplate="R² %{x:.0f} %: %{y} acciones<extra></extra>"))
        ui.mostrar(layout(fig, 300, showlegend=False, xaxis=dict(title="R² (%)"), yaxis=dict(title="Acciones")))
    with c2:
        if "beta_dimson" in inc:
            st.markdown("**Beta normal vs beta de Dimson**")
            fig = go.Figure(go.Scatter(x=inc["beta_vs_indice_pais"], y=inc["beta_dimson"], mode="markers",
                                       marker=dict(size=6, color=ui.AZUL, opacity=0.55), text=inc["ticker"],
                                       hovertemplate="%{text}<br>β %{x:.2f} · Dimson %{y:.2f}<extra></extra>"))
            lim = [0, float(np.nanmax(inc[["beta_vs_indice_pais", "beta_dimson"]].to_numpy())) * 1.05]
            fig.add_scatter(x=lim, y=lim, mode="lines", line=dict(color=ui.GRIS_REF, dash="dot"), hoverinfo="skip")
            ui.mostrar(layout(fig, 300, showlegend=False, xaxis=dict(title="Beta de la regresión"), yaxis=dict(title="Beta de Dimson")))
            st.caption("Los puntos sobre la diagonal son acciones que reaccionan con rezago: su beta normal subestima el riesgo.")

# =============================== ④ FILTROS ==========================================
with t4:
    st.markdown("""Antes de promediar, se descartan las acciones cuyo beta no es confiable:
- **Poca historia:** menos de 3 años (156 semanas) de traslape con su mercado.
- **Iliquidez:** más de 25 % de semanas sin cambio de precio.
- **Retornos extremos:** los retornos semanales se recortan a ±50 % (logarítmico); si una acción tiene más de 3 semanas recortadas, se excluye.""")
    motivos = exc["motivo_exclusion"].fillna("otro").str.split(";").explode().str.strip().value_counts()
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Del universo a la muestra final**")
        etapas = ["Universo", "Pasan los filtros", "Sectores con beta", "Sectores con 5+ firmas"]
        valores = [len(emp), len(inc), len(prop), int((prop["n_empresas"] >= 5).sum())]
        fig = go.Figure(go.Funnel(y=etapas, x=valores, marker=dict(color=[ui.GRIS, ui.AZUL, ui.ROJO, ui.VERDE]),
                                  textinfo="value", hovertemplate="%{y}: %{x}<extra></extra>"))
        ui.mostrar(layout(fig, 320))
        st.caption("Las dos primeras barras son acciones; las dos últimas, sectores.")
    with c2:
        st.markdown("**Motivos de exclusión**")
        fig = go.Figure(go.Bar(y=motivos.index, x=motivos.values, orientation="h", marker_color=ui.ROJO,
                               text=motivos.values, textposition="outside", hovertemplate="%{y}: %{x} acciones<extra></extra>"))
        ui.mostrar(layout(fig, 320, showlegend=False, yaxis=dict(autorange="reversed"), xaxis=dict(title="Acciones")))
        st.caption("Una acción puede tener más de un motivo.")

    # ¿Los filtros sesgan el beta?
    med_inc, med_exc = inc["beta_vs_indice_pais"].median(), exc["beta_vs_indice_pais"].median()
    co = emp[emp["ticker"].str.endswith(".CL")]
    co_inc = int(co["incluir"].sum())
    st.markdown("**¿Los filtros cambian el resultado?** Comparación del beta de las acciones incluidas y excluidas:")
    fig = go.Figure()
    fig.add_histogram(x=inc["beta_vs_indice_pais"], name=f"Incluidas ({len(inc)})", marker_color=ui.AZUL, opacity=0.65, nbinsx=40)
    fig.add_histogram(x=exc["beta_vs_indice_pais"].clip(-0.5, 3), name=f"Excluidas ({len(exc)})", marker_color=ui.ROJO, opacity=0.55, nbinsx=40)
    ui.mostrar(layout(fig, 320, barmode="overlay", xaxis=dict(title="Beta contra el ETF del país"), yaxis=dict(title="Acciones"),
                      legend=dict(orientation="h", y=1.1, x=0)))
    por_motivo = exc.assign(m=exc["motivo_exclusion"].fillna("otro")).groupby("m")["beta_vs_indice_pais"].median()
    med_ili = por_motivo.get("iliquidez", np.nan)
    med_ext = por_motivo.get("retornos extremos", np.nan)
    tema.lectura([
        f"Beta mediano de las incluidas: **{ui.num(med_inc)}**. De las excluidas por **iliquidez**: **{ui.num(med_ili)}**; por "
        f"**retornos extremos** (solo ese motivo): **{ui.num(med_ext)}**.",
        "Las acciones ilíquidas tienen betas artificialmente bajos (su precio no reacciona a tiempo), así que excluirlas es correcto. "
        "Las excluidas por retornos extremos tienen un beta parecido al de las incluidas: en el conjunto de la región, el filtro no sesga el resultado.",
    ], titulo="¿Los filtros sesgan el beta?", tono="neutro")
    fx_ok = co_inc >= 10          # con el tipo de cambio corregido entran la mayoría de las colombianas
    if fx_ok:
        motivos_co = co.loc[~co["incluir"], "motivo_exclusion"].fillna("otro").str.split(";").explode().str.strip().value_counts()
        tema.lectura([
            f"De las **{len(co)} acciones colombianas de la BVC**, **{co_inc}** pasan los filtros. Las demás se excluyen por "
            + ", ".join(f"{m} ({n})" for m, n in motivos_co.items()) + ".",
            "Esta corrida ya usa el **tipo de cambio corregido**: TRM oficial para el peso colombiano y limpieza de los saltos falsos de Yahoo "
            "(la serie `COP=X` tiene tres semanas erradas por un factor de 100 en 2014-2015).",
            f"Beta mediano de las colombianas incluidas: **{ui.num(co.loc[co['incluir'], 'beta_vs_indice_pais'].median())}**, "
            "contra el ETF ICOLCAP en dólares.",
        ], titulo="Colombia en la muestra", tono="ok")
    else:
        tema.lectura([
        f"De las **{len(co)} acciones colombianas de la BVC**, solo **{co_inc}** {'pasa' if co_inc == 1 else 'pasan'} los filtros, "
        "casi todas por «retornos extremos».",
        "**La causa es un error de datos de Yahoo Finance**, no las crisis: la serie del dólar en pesos (`COP=X`) tiene tres semanas "
        "(diciembre de 2014, febrero de 2015 y diciembre de 2015) en las que el dólar aparece **100 veces más barato**. La TRM oficial de "
        "esas semanas era de unos 2.400 pesos.",
        "Al convertir los precios a dólares, cada error crea dos semanas con retornos falsos de ±460 % (logarítmico). Eso excluye a "
        "las acciones colombianas con historia en esos años y distorsiona su beta y el del ETF ICOLCAP usado como mercado.",
        "**Consecuencia: en esta corrida, Colombia casi no aporta acciones al beta latinoamericano.** Hay que volver a correr el cuaderno "
        "con el tipo de cambio corregido (TRM oficial o limpieza de esos saltos). El tablero ya usa la TRM oficial en sus propias conversiones.",
        ], titulo="Advertencia: error en el tipo de cambio de Yahoo", tono="riesgo")
    with st.expander("Ver las acciones colombianas y su motivo de exclusión", icon=":material/flag:"):
        t = co[["ticker", "empresa", "industria", "beta_vs_indice_pais", "incluir", "motivo_exclusion"]].copy()
        t["incluir"] = np.where(t["incluir"], "Sí", "No")
        t.columns = ["Ticker", "Empresa", "Industria", "Beta", "Incluida", "Motivo"]
        st.dataframe(t.style.format({"Beta": lambda v: ui.num(v)}), hide_index=True, width="stretch")

# =============================== ⑤ BETA DEL SECTOR ==================================
with t5:
    st.markdown("**1. Promedio balanceado por país.** Primero se promedia el beta dentro de cada país y luego se promedian los países, "
                "para que Brasil (con muchas más empresas) no determine solo el resultado:")
    st.latex(r"\beta_{sector} = \frac{1}{K}\sum_{k=1}^{K}\left(\frac{1}{n_k}\sum_{i \in k}\beta_i\right)")
    st.markdown("**2. Intervalo de confianza por bootstrap.** Se remuestrean las empresas del sector 1.000 veces y se toma el rango "
                "que contiene el 95 % de los promedios. Requiere al menos 3 empresas.")
    st.markdown("**3. Desapalancar.** Se quita el efecto de la deuda con el D/E promedio del sector (Damodaran, emergentes), una tasa "
                "de impuestos regional de 25 % y la corrección por caja:")
    st.latex(r"\beta_u = \frac{\beta_{sector}}{\left[1 + (1-0{,}25)\,D/E\right]\left(1 - \text{caja}/V\right)}")
    st.markdown("**4. Nivel de confianza** según el número de firmas: **Alta** (10 o más), **Media** (5 a 9) y **Baja** (menos de 5).")

    c1, c2 = st.columns([2, 3], gap="large")
    with c1:
        st.markdown("**Firmas por sector (25 sectores con más firmas)**")
        top = prop.sort_values("n_empresas", ascending=False).head(25).iloc[::-1]
        fig = go.Figure(go.Bar(y=top["industria"], x=top["n_empresas"], orientation="h",
                               marker_color=[COLOR_CONF.get(c, ui.GRIS) for c in top["confianza"]],
                               text=top["confianza"], textposition="outside",
                               hovertemplate="%{y}: %{x} firmas<extra></extra>"))
        ui.mostrar(layout(fig, 640, showlegend=False, xaxis=dict(title="Firmas")))
        st.caption(f"Verde: confianza alta · ámbar: media · rojo: baja. {int((prop['n_empresas'] < 5).sum())} de {len(prop)} sectores tienen menos de 5 firmas.")
    with c2:
        st.markdown("**βu propio con su intervalo, frente a Damodaran (sectores con 5 o más firmas)**")
        g = base[base["n_empresas"] >= 5].sort_values("beta_desapalancada_caja")
        fig = go.Figure()
        fig.add_scatter(x=g["beta_desapalancada_caja"], y=g["industria"], mode="markers", name="Propio LatAm",
                        marker=dict(color=ui.ROJO, size=10),
                        error_x=dict(type="data", symmetric=False, array=(g["bu_hi"] - g["beta_desapalancada_caja"]).fillna(0),
                                     arrayminus=(g["beta_desapalancada_caja"] - g["bu_lo"]).fillna(0), color=ui.ROJO, thickness=1.5),
                        hovertemplate="%{y}: %{x:.2f}<extra>Propio</extra>")
        fig.add_scatter(x=g["bu_dam"], y=g["industria"], mode="markers", name="Damodaran emergentes",
                        marker=dict(color=ui.AZUL, size=10, symbol="diamond"), hovertemplate="%{y}: %{x:.2f}<extra>Damodaran</extra>")
        ui.mostrar(layout(fig, 640, legend=dict(orientation="h", y=1.04, x=0), xaxis=dict(title="βu (desapalancada, con caja)"),
                          hovermode="closest"))
        st.caption("La barra roja es el intervalo bootstrap al 95 %. Si el rombo azul cae fuera, la diferencia con Damodaran no es solo ruido.")

# =============================== ⑥ RESULTADOS =======================================
with t6:
    fuera = fuerte[(fuerte["bu_dam"] < fuerte["bu_lo"]) | (fuerte["bu_dam"] > fuerte["bu_hi"])]
    corr = fuerte["beta_desapalancada_caja"].corr(fuerte["bu_dam"])
    k = ui.tarjetas(4, ancho=230)
    k[0].metric("Sectores comparados", f"{len(fuerte)}", border=True, help="No financieros con 5 o más firmas.")
    k[1].metric("Correlación con Damodaran", ui.num(corr), border=True)
    k[2].metric("Diferencia promedio", ui.num(fuerte["dif"].mean()), border=True, help="βu propio − βu Damodaran (con signo).")
    k[3].metric("Fuera del intervalo", f"{len(fuera)} de {len(fuerte)}", border=True)
    mayor = fuerte.loc[fuerte["dif"].abs().idxmax()]
    tema.lectura([
        f"El beta propio **se mueve en la misma dirección** que el de Damodaran (correlación de {ui.num(corr)}): los sectores riesgosos "
        "lo son en ambas mediciones.",
        f"En promedio la diferencia es de {ui.num(fuerte['dif'].mean())} ({'propio mayor' if fuerte['dif'].mean() > 0 else 'propio menor'}), "
        f"y en valor absoluto de {ui.num(fuerte['dif'].abs().mean())}.",
        f"En **{len(fuera)} de {len(fuerte)}** sectores Damodaran queda fuera del intervalo de confianza del beta propio: ahí la región "
        f"sí parece tener un riesgo distinto. La mayor diferencia está en **{mayor['industria']}** "
        f"(propio {ui.num(mayor['beta_desapalancada_caja'])} vs Damodaran {ui.num(mayor['bu_dam'])}).",
        ("La corrida usa el tipo de cambio corregido (TRM oficial), de modo que Colombia sí aporta sus acciones líquidas (pestaña ④)."
         if co_inc >= 10 else
         "Antes de sacar conclusiones, hay que repetir la corrida con el tipo de cambio corregido: hoy Colombia casi no aporta acciones (pestaña ④)."),
    ], titulo="Análisis de los resultados", tono="neutro")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**Propio vs Damodaran por sector**")
        sc = base[base["n_empresas"] >= 3]
        fig = go.Figure()
        tope = float(np.nanmax(sc[["beta_desapalancada_caja", "bu_dam"]].to_numpy())) * 1.08
        fig.add_scatter(x=[0, tope], y=[0, tope], mode="lines", line=dict(color=ui.GRIS_REF, dash="dot"), hoverinfo="skip", showlegend=False)
        for nivel in ("Alta", "Media", "Baja"):
            d = sc[sc["confianza"] == nivel]
            fig.add_scatter(x=d["bu_dam"], y=d["beta_desapalancada_caja"], mode="markers", name=f"Confianza {nivel.lower()}",
                            marker=dict(color=COLOR_CONF[nivel], size=7 + 1.3 * np.sqrt(d["n_empresas"]), opacity=0.85,
                                        line=dict(width=1, color="white")),
                            text=d["industria"] + " (" + d["n_empresas"].astype(str) + " firmas)",
                            hovertemplate="%{text}<br>Damodaran %{x:.2f} · propio %{y:.2f}<extra></extra>")
        ui.mostrar(layout(fig, 400, legend=dict(orientation="h", y=1.08, x=0), hovermode="closest",
                          xaxis=dict(title="βu Damodaran emergentes"), yaxis=dict(title="βu propio LatAm")))
        st.caption("Sobre la diagonal, el beta propio es mayor. Sectores con 3 o más firmas; el tamaño crece con el número de firmas.")
    with c2:
        if por_pais is not None:
            st.markdown("**Beta mediano por país (con rango del 10 % al 90 %)**")
            bp = por_pais.sort_values("beta_mediano")
            fig = go.Figure(go.Scatter(x=bp["beta_mediano"], y=bp["pais_es"], mode="markers", marker=dict(size=11, color=ui.ROJO),
                                       error_x=dict(type="data", symmetric=False, array=bp["p90"] - bp["beta_mediano"],
                                                    arrayminus=bp["beta_mediano"] - bp["p10"], color=ui.GRIS, thickness=1.5),
                                       text=bp["acciones"].astype(str) + " acciones",
                                       hovertemplate="%{y}: mediana %{x:.2f} · %{text}<extra></extra>"))
            fig.add_vline(x=1, line=dict(color=ui.GRIS_REF, dash="dot"))
            ui.mostrar(layout(fig, 400, showlegend=False, xaxis=dict(title="Beta contra el ETF del país")))
            st.caption("Cada beta se mide contra el mercado de su propio país, así que los niveles no se comparan entre países: "
                       "lo relevante es la dispersión.")

    if estab is not None:
        st.markdown("**¿Es estable el beta en el tiempo?**")
        e = estab.dropna(subset=["beta_completo"])
        dif5 = (e["beta_completo"] - e["beta_5a"]).abs()
        difm = (e["beta_mitad1"] - e["beta_mitad2"]).abs()
        c1, c2 = st.columns(2, gap="large")
        with c1:
            fig = go.Figure(go.Scatter(x=e["beta_5a"], y=e["beta_completo"], mode="markers", text=e["ticker"],
                                       marker=dict(size=6, color=ui.AZUL, opacity=0.55),
                                       hovertemplate="%{text}<br>5 años %{x:.2f} · completo %{y:.2f}<extra></extra>"))
            lim = [-0.2, float(np.nanmax(e[["beta_5a", "beta_completo"]].to_numpy())) * 1.05]
            fig.add_scatter(x=lim, y=lim, mode="lines", line=dict(color=ui.GRIS_REF, dash="dot"), hoverinfo="skip")
            ui.mostrar(layout(fig, 330, showlegend=False, xaxis=dict(title="Beta de los últimos 5 años"), yaxis=dict(title="Beta con todo el historial")))
        with c2:
            fig = go.Figure(go.Histogram(x=difm, nbinsx=30, marker_color=ui.AMBAR, marker_line=dict(width=1, color="white"),
                                         hovertemplate="|diferencia| %{x:.2f}: %{y} acciones<extra></extra>"))
            fig.add_vline(x=0.3, line=dict(color=ui.ROJO, dash="dash"), annotation_text="0,30")
            ui.mostrar(layout(fig, 330, showlegend=False, xaxis=dict(title="|β primera mitad − β segunda mitad|"), yaxis=dict(title="Acciones")))
        tema.lectura([
            f"Entre el beta con todo el historial y el de los últimos 5 años, solo el **{ui.pct((dif5 > 0.3).mean(), 0)}** de las acciones difiere más de 0,30.",
            f"Entre la primera y la segunda mitad del historial, el **{ui.pct((difm > 0.3).mean(), 0)}** difiere más de 0,30: el beta de una acción "
            "cambia en el tiempo, y por eso es mejor trabajar con el promedio de un sector que con una acción.",
        ], titulo="Estabilidad", tono="neutro")

    st.markdown("**Tabla de resultados por sector**")
    tabla = base.sort_values("n_empresas", ascending=False)[["industria", "n_empresas", "paises", "beta_apalancada",
                                                              "beta_desapalancada_caja", "bu_lo", "bu_hi", "bu_dam", "dif", "confianza"]]
    tabla.columns = ["Sector", "Firmas", "Países", "β apalancado", "βu propio", "IC bajo", "IC alto", "βu Damodaran", "Diferencia", "Confianza"]
    f2 = lambda v: ui.num(v)
    st.dataframe(tabla.style.format({c: f2 for c in ["β apalancado", "βu propio", "IC bajo", "IC alto", "βu Damodaran", "Diferencia"]}, na_rep="—"),
                 hide_index=True, width="stretch", height=420)
    ui.boton_descarga(tabla, "beta_propio_por_sector.csv", "Descargar resultados (CSV)", clave="dl_met_propia")

# =============================== ⑦ LÍMITES ==========================================
with t7:
    st.markdown(f"""
1. **Calidad del tipo de cambio.** Yahoo tiene semanas erradas por un factor de 100 (`COP=X` en 2014-2015). {"Esta corrida usa la TRM oficial y limpia esos saltos" if co_inc >= 10 else "Esta corrida todavía no lo corrige"}; de las acciones colombianas de la BVC entran {co_inc} de {len(co)} (pestaña ④).
2. **Muestras pequeñas.** {int((prop['n_empresas'] < 5).sum())} de {len(prop)} sectores tienen menos de 5 firmas; ahí el beta propio es
   poco confiable y el combinado se acerca a Damodaran.
3. **D/E y caja de Damodaran.** Se desapalanca con el promedio de la industria, no con el de cada empresa.
4. **Historial completo.** Mezcla periodos distintos de la economía; la pestaña ⑥ mide cuánto cambia el beta en el tiempo.
5. **Argentina.** Los cambios de régimen cambiario agregan ruido a los retornos en dólares.
6. **Yahoo Finance.** Tiene sesgo de supervivencia (faltan empresas que dejaron de cotizar) y puede traer errores de precio.
7. **El beta mide el pasado.** Supone que la sensibilidad histórica al mercado se mantiene.
""")
    st.caption(f"Parámetros de la corrida: mínimo 156 semanas; recorte de retornos semanales a ±0,50 (log); exclusión con más de 3 semanas "
               f"recortadas o más de 25 % de semanas sin cambio; Newey-West con 4 rezagos; 1.000 réplicas bootstrap; impuesto para "
               f"desapalancar 25 %; τ del combinado {ui.num(meta.get('tau', np.nan), 3)}.")
    st.page_link("paginas/beta_latam.py", label="Comparar y elegir la fuente de beta", icon=":material/compare_arrows:")
