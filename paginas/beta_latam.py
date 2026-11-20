"""Beta propio de Latinoamérica (Yahoo Finance) frente a Damodaran, y elección de la fuente."""
import zipfile
from dataclasses import asdict
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import acceso, almacen, beta_propio, mercado, tema, ui
from nucleo import costo_capital as cc

tema.encabezado("Beta propio de Latinoamérica vs Damodaran",
                "Compara el beta por industria estimado con **acciones de la región** (cuaderno de Yahoo Finance) con el de "
                "Damodaran, y elige cuál usar en la valoración de empresas y en la evaluación de proyectos.",
                seccion="Análisis financiero", chips=["Beta bottom-up", "Balanceado por país", "Intervalo bootstrap"])

FUENTES = {
    "emergentes": "Damodaran · emergentes",
    "global": "Damodaran · global",
    "latam_propio": "Propio LatAm",
    "latam_combinado": "Combinado",
}
DESCRIPCION = {
    "emergentes": "Beta de las empresas de mercados emergentes del archivo de Damodaran.",
    "global": "Beta de las empresas de todo el mundo del archivo de Damodaran.",
    "latam_propio": "Beta estimado con acciones latinoamericanas de Yahoo Finance. Solo hay dato en las "
                    "industrias donde se encontraron acciones; con pocas firmas es poco confiable.",
    "latam_combinado": "Promedio del beta propio y el de Damodaran emergentes, con más peso al propio "
                       "donde está bien medido. Las industrias sin beta propio quedan igual a Damodaran.",
}

dam_em = almacen.leer_betas("emergentes")
dam_gl = almacen.leer_betas("global")
pais = almacen.leer_parametros_pais()
if dam_em is None or dam_gl is None or pais is None:
    st.error("Faltan los datos de Damodaran. Usa **Actualizar datos ahora** en la barra lateral.")
    st.stop()

prop = almacen.leer_betas_propios()
meta = almacen.leer_meta_propia() or {}

# =============================== IMPORTAR CORRIDA ===================================
# Solo para administradores: en el modo público nadie puede reemplazar los datos del servidor.
if acceso.es_admin():
    with st.expander("Actualizar con una nueva corrida del cuaderno", icon=":material/upload_file:",
                     expanded=prop is None):
        st.markdown("Ejecuta `Beta_Latinoamerica_CAPM.ipynb` en Colab, descarga `resultados_beta_latam.xlsx` "
                    "y súbelo aquí. También se puede hacer por consola: "
                    "`python importar_beta_latam.py resultados_beta_latam.xlsx`.")
        archivo = st.file_uploader("resultados_beta_latam.xlsx", type="xlsx", key="subida_beta_latam")
        if archivo is not None and st.button("Importar resultados", icon=":material/check:"):
            try:
                res = beta_propio.importar(archivo.getvalue(), dam_em, date.today().isoformat())
            except (ValueError, KeyError, zipfile.BadZipFile) as e:
                st.error(f"No se pudo importar el archivo: {e}")
            else:
                almacen.guardar_betas_propios(res["propio"], res["empresas"], res["meta"], res.get("extras"))
                st.session_state.pop("_mem_tau", None)
                st.rerun()

if prop is None:
    st.info("Todavía no hay beta propio cargado. "
            + ("Sube el archivo del cuaderno para ver la comparación." if acceso.es_admin()
               else "Vuelve a consultar más tarde."))
    st.stop()

# =============================== DECISIÓN ===========================================
memoria = st.session_state.get("_mem_universo", "emergentes")
elegida = st.segmented_control(
    "Fuente de beta para Valoración y Proyectos", list(FUENTES), format_func=FUENTES.get,
    default=memoria if memoria in FUENTES else "emergentes", key="fuente_beta",
    help="La elección se recuerda al pasar a las demás páginas; allí se puede cambiar.") or memoria
if elegida not in FUENTES:
    elegida = "emergentes"
st.session_state["_mem_universo"] = elegida
st.caption(f"**{FUENTES[elegida]}.** {DESCRIPCION[elegida]}")

tau_def = float(meta.get("tau", 0.18))
tau = float(st.session_state.get("_mem_tau") or tau_def)
with st.expander("Ajustar el beta combinado", icon=":material/tune:"):
    tau = st.number_input("τ: desacuerdo típico entre el beta propio y el de Damodaran (en βU)",
                          min_value=0.02, max_value=1.0, value=round(tau, 3), step=0.01, format="%.3f",
                          help="Con un τ pequeño el combinado se acerca a Damodaran; con uno grande, al beta propio. "
                               f"Valor estimado con los datos de la corrida: {tau_def:.3f}.")
    st.session_state["_mem_tau"] = None if abs(tau - tau_def) < 1e-9 else float(tau)
    st.caption("Peso del beta propio = τ² / (τ² + EE²), donde EE es el error estándar del beta propio de la "
               "industria. El peso mide la **precisión estadística** del beta propio, no si las empresas "
               "encontradas representan bien a la industria.")

# =============================== COMPARACIÓN ========================================
comb = almacen.leer_betas("latam_combinado", tau=tau)
base = dam_em[["industria", "n_empresas", "de", "beta_desapalancada_caja"]].rename(
    columns={"n_empresas": "n_dam", "beta_desapalancada_caja": "bu_dam_em"})
base = base.merge(dam_gl[["industria", "beta_desapalancada_caja"]].rename(
    columns={"beta_desapalancada_caja": "bu_dam_gl"}), on="industria", how="left")
base = base.merge(prop[["industria", "n_empresas", "paises", "beta_desapalancada_caja", "bu_lo", "bu_hi",
                        "error_est", "confianza", "financiera"]].rename(
    columns={"n_empresas": "n_prop", "beta_desapalancada_caja": "bu_propio"}), on="industria", how="left")
base = base.merge(comb[["industria", "beta_desapalancada_caja", "peso_propio"]].rename(
    columns={"beta_desapalancada_caja": "bu_comb"}), on="industria", how="left")
base["financiera"] = base["financiera"].astype("boolean").fillna(False).astype(bool)
base["dif"] = base["bu_propio"] - base["bu_dam_em"]


def lectura(f) -> str:
    if pd.isna(f["bu_propio"]):
        return "Sin beta propio"
    if f["n_prop"] < beta_propio.MIN_FIRMAS_IC:
        return "Muestra muy pequeña (1-2 firmas)"
    dentro = f["bu_lo"] <= f["bu_dam_em"] <= f["bu_hi"]
    texto = ("Consistente con Damodaran (dentro del intervalo)" if dentro
             else "Difiere de Damodaran (fuera del intervalo)")
    return texto + ("" if f["n_prop"] >= 5 else " · muestra pequeña")


base["lectura"] = base.apply(lectura, axis=1)

st.markdown(f"Corrida del **{meta.get('fecha_corrida', '—')}**: **{meta.get('acciones_incluidas', '—')}** "
            f"acciones incluidas de {meta.get('acciones_total', '—')}, **{meta.get('sectores', '—')}** industrias "
            f"({meta.get('sectores_5_o_mas', '—')} con 5 o más firmas) en {len(meta.get('paises', []))} países.")
st.caption(meta.get("fuente", ""))

tab_cmp, tab_ke, tab_emp, tab_met = st.tabs(
    ["Comparación por industria", "Ke con cada fuente", "Empresas de cada industria", "Metodología y límites"])

with tab_cmp:
    f1, f2, f3 = st.columns([1, 1, 2])
    solo_propio = f1.toggle("Solo industrias con beta propio", value=True)
    minimo = f2.selectbox("Confianza mínima", ["Todas", "Media o alta", "Alta"])
    texto = f3.text_input("Filtrar industria", placeholder="p. ej. Bank, Power, Retail")
    v = base.copy()
    if solo_propio:
        v = v[v["bu_propio"].notna()]
    if minimo != "Todas":
        v = v[v["confianza"].isin(["Alta"] if minimo == "Alta" else ["Alta", "Media"])]
    if texto:
        v = v[v["industria"].str.contains(texto, case=False)]

    ref = v[(v["n_prop"] >= 5) & ~v["financiera"]]
    if len(ref) >= 3:
        fuera = ref[ref["lectura"].str.startswith("Difiere")]
        mayor = ref.loc[ref["dif"].abs().idxmax()]
        corr_ref = ref["bu_propio"].corr(ref["bu_dam_em"])
        tema.lectura([
            f"En las **{len(ref)} industrias no financieras con 5 o más firmas**, el beta propio y el de Damodaran emergentes "
            f"tienen una correlación de {ui.num(corr_ref)} y difieren en promedio {ui.num(ref['dif'].abs().mean())} (en valor absoluto).",
            f"**{len(fuera)}** de ellas quedan fuera del intervalo de confianza del beta propio: ahí la diferencia no es solo ruido de muestreo.",
            f"La mayor diferencia es en **{mayor['industria']}** (propio {ui.num(mayor['bu_propio'])}, Damodaran {ui.num(mayor['bu_dam_em'])}).",
            "Con menos de 5 firmas el beta propio es poco confiable; en ese caso el combinado se acerca a Damodaran.",
        ], titulo="Análisis de la comparación", tono="alerta" if len(fuera) > len(ref) / 3 else "neutro")
    m = ui.tarjetas(4)
    m[0].metric("Industrias mostradas", len(v), border=True)
    m[1].metric("Con 5+ firmas (no financieras)", len(ref), border=True)
    if len(ref) >= 3:
        m[2].metric("Correlación βU propio vs Damodaran", ui.num(ref["bu_propio"].corr(ref["bu_dam_em"]), 2),
                    border=True, help="Entre las industrias no financieras con 5 o más firmas propias.")
        m[3].metric("Diferencia media absoluta", ui.num(ref["dif"].abs().mean(), 2), border=True,
                    help="|βU propio − βU Damodaran emergentes|, promedio de esas industrias.")
    else:
        m[2].metric("Correlación βU propio vs Damodaran", "—", border=True)
        m[3].metric("Diferencia media absoluta", "—", border=True)

    vista = v.sort_values("n_prop", ascending=False, na_position="last").copy()
    vista["peso_propio"] = vista["peso_propio"] * 100
    tabla = vista[["industria", "n_prop", "paises", "bu_dam_em", "bu_dam_gl", "bu_propio", "bu_lo", "bu_hi",
                   "bu_comb", "peso_propio", "dif", "confianza", "lectura"]]
    tabla.columns = ["Industria", "Firmas propias", "Países", "βU Damodaran emerg.", "βU Damodaran global",
                     "βU propio", "IC 95 % bajo", "IC 95 % alto", "βU combinado", "Peso del propio",
                     "Propio − Damodaran", "Confianza", "Interpretación"]
    num2 = st.column_config.NumberColumn(format="%.2f")
    st.dataframe(tabla, hide_index=True, width="stretch", height=430, column_config={
        "Firmas propias": st.column_config.NumberColumn(format="%d"),
        "Países": st.column_config.NumberColumn(format="%d"),
        "βU Damodaran emerg.": num2, "βU Damodaran global": num2, "βU propio": num2,
        "IC 95 % bajo": num2, "IC 95 % alto": num2, "βU combinado": num2, "Propio − Damodaran": num2,
        "Peso del propio": st.column_config.NumberColumn(format="%.0f %%"),
    })
    ui.boton_descarga(tabla, f"beta_propio_vs_damodaran_{date.today()}.csv", "Descargar tabla (CSV)",
                      clave="dl_cmp")
    st.caption("βU = beta desapalancada y corregida por caja, con el D/E y la caja de Damodaran. "
               "En las industrias financieras el beta se desapalanca igual que en la columna de Damodaran; "
               "se muestran por transparencia, pero el D/E de bancos y aseguradoras es poco informativo.")

    g = v[v["bu_propio"].notna()].sort_values("n_prop", ascending=False).head(25)
    if not g.empty:
        gizq, gder = st.columns([3, 2], gap="large")
        with gizq:
            st.markdown("**Beta propio (con intervalo) frente a Damodaran**")
            g = g.iloc[::-1]
            fig = go.Figure()
            fig.add_scatter(
                x=g["bu_propio"], y=g["industria"], mode="markers", name="Propio LatAm",
                marker=dict(color=ui.PALETA[0], size=9),
                error_x=dict(type="data", symmetric=False, color=ui.PALETA[0], thickness=1.5,
                             array=(g["bu_hi"] - g["bu_propio"]).fillna(0),
                             arrayminus=(g["bu_propio"] - g["bu_lo"]).fillna(0)),
                hovertemplate="%{y}: %{x:.2f}<extra>Propio LatAm</extra>")
            fig.add_scatter(x=g["bu_dam_em"], y=g["industria"], mode="markers", name="Damodaran emergentes",
                            marker=dict(color=ui.PALETA[1], size=9, symbol="diamond"),
                            hovertemplate="%{y}: %{x:.2f}<extra>Damodaran emergentes</extra>")
            fig.add_scatter(x=g["bu_dam_gl"], y=g["industria"], mode="markers", name="Damodaran global",
                            marker=dict(color=ui.PALETA[3], size=9, symbol="circle-open", line=dict(width=2)),
                            hovertemplate="%{y}: %{x:.2f}<extra>Damodaran global</extra>")
            fig.add_scatter(x=g["bu_comb"], y=g["industria"], mode="markers", name="Combinado",
                            marker=dict(color=ui.PALETA[2], size=7, symbol="x"),
                            hovertemplate="%{y}: %{x:.2f}<extra>Combinado</extra>")
            fig.update_layout(height=max(360, 26 * len(g) + 110), margin=dict(l=8, r=8, t=28, b=8),
                              separators=",.", hovermode="closest",
                              legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
                              xaxis=dict(title="βU (desapalancada, con caja)"), yaxis=dict(title=None))
            ui.mostrar(fig)
            st.caption("Hasta 25 industrias, ordenadas por número de firmas propias. "
                       "La barra es el intervalo bootstrap al 95 % del beta propio.")
        with gder:
            st.markdown("**Propio vs Damodaran emergentes**")
            colores = {"Alta": ui.VERDE, "Media": ui.AMBAR, "Baja": ui.ROJO}
            s = v[v["bu_propio"].notna()]
            fig = go.Figure()
            tope = float(np.nanmax(s[["bu_propio", "bu_dam_em"]].to_numpy())) * 1.1
            fig.add_scatter(x=[0, tope], y=[0, tope], mode="lines", showlegend=False, hoverinfo="skip",
                            line=dict(color=ui.GRIS_REF, dash="dot", width=1))
            for nivel in ["Alta", "Media", "Baja"]:
                c = s[s["confianza"] == nivel]
                if c.empty:
                    continue
                fig.add_scatter(x=c["bu_dam_em"], y=c["bu_propio"], mode="markers", name=f"Confianza {nivel.lower()}",
                                marker=dict(color=colores[nivel], size=6 + 1.2 * np.sqrt(c["n_prop"]), opacity=0.8),
                                text=c["industria"] + " (" + c["n_prop"].astype(int).astype(str) + " firmas)",
                                hovertemplate="%{text}<br>Damodaran %{x:.2f} · propio %{y:.2f}<extra></extra>")
            fig.update_layout(height=max(360, 26 * len(g) + 110), margin=dict(l=8, r=8, t=28, b=8),
                              separators=",.", hovermode="closest",
                              legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, title=None),
                              xaxis=dict(title="βU Damodaran emergentes"), yaxis=dict(title="βU propio"))
            ui.mostrar(fig)
            st.caption("Sobre la diagonal, el beta propio es mayor que el de Damodaran. "
                       "El tamaño del punto crece con el número de firmas.")

# =============================== KE POR FUENTE ======================================
with tab_ke:
    referencia = mercado.supuestos_referencia()
    if referencia is None:
        st.info("Faltan datos de mercado (Tesoro 10A, breakeven). Usa **Actualizar datos ahora**.")
    else:
        s0, _ = referencia
        sectores = sorted(base["industria"])
        previo = st.session_state.get("_mem_sector_beta_latam", "Food Processing")
        k1, k2 = st.columns([2, 1])
        sector = k1.selectbox("Industria", sectores, key="sector_beta_latam",
                              index=sectores.index(previo) if previo in sectores else 0)
        st.session_state["_mem_sector_beta_latam"] = sector
        f = base[base["industria"] == sector].iloc[0]
        a1, a2, a3, a4 = st.columns(4)
        de = a1.number_input("D/E (%)", value=round(float(f["de"]) * 100, 1), step=5.0,
                             key=f"de_cmp_{sector}", help="Por defecto, el D/E de la industria (Damodaran).") / 100
        tes10 = mercado.opciones_kd_base()["TES 10A + spread"] or 0.12
        kd = a2.number_input("Kd antes de impuestos (%)", value=round((tes10 + 0.02) * 100, 2), step=0.25,
                             key="kd_cmp", help="Por defecto: TES 10A + 2 p.p.") / 100
        crp_nombre = a3.radio("Prima de riesgo país", ["Calificación", "CDS"], horizontal=True, key="crp_cmp")
        crp = pais["crp_calificacion"] if crp_nombre == "Calificación" else pais["crp_cds"]
        modo = a4.radio("Aplicación del CRP", ["aditivo", "beta"], horizontal=True, key="modo_cmp",
                        format_func=lambda m: "λ = 1" if m == "aditivo" else "λ = βL")

        def resultado(bu: float) -> dict:
            return cc.calcular(cc.Supuestos(**{**asdict(s0), "beta_u": bu, "de": de, "crp": crp,
                                               "modo_crp": modo, "kd_cop": kd}))

        fuentes = [("emergentes", f["bu_dam_em"]), ("global", f["bu_dam_gl"]),
                   ("latam_propio", f["bu_propio"]), ("latam_combinado", f["bu_comb"])]
        filas, grafico = [], []
        for clave, bu in fuentes:
            if pd.isna(bu):
                filas.append({"Fuente": FUENTES[clave], "βU": np.nan, "βL": np.nan, "Ke (COP)": np.nan,
                              "WACC (COP)": np.nan, "Elegida": clave == elegida})
                continue
            r = resultado(float(bu))
            filas.append({"Fuente": FUENTES[clave], "βU": float(bu), "βL": r["beta_apalancada"],
                          "Ke (COP)": r["ke_cop"] * 100, "WACC (COP)": r["wacc_cop"] * 100,
                          "Elegida": clave == elegida})
            err = (0.0, 0.0)
            if clave == "latam_propio" and pd.notna(f["bu_lo"]):
                err = (r["ke_cop"] - resultado(float(f["bu_lo"]))["ke_cop"],
                       resultado(float(f["bu_hi"]))["ke_cop"] - r["ke_cop"])
            grafico.append((FUENTES[clave], r["ke_cop"] * 100, err[0] * 100, err[1] * 100, clave))
        tabla_ke = pd.DataFrame(filas)

        if pd.isna(f["bu_propio"]):
            st.info(f"No hay beta propio para **{sector}**: el combinado queda igual a Damodaran emergentes.")
        elif f["n_prop"] < 5:
            st.warning(f"Solo hay {int(f['n_prop'])} firma(s) propia(s) en **{sector}**: el beta propio es "
                       "poco confiable. Considera el combinado o Damodaran.", icon=":material/warning:")
        if f["financiera"]:
            st.caption("Industria financiera: el D/E de bancos y aseguradoras es poco informativo; "
                       "interpreta el Ke con cautela en cualquiera de las fuentes.")

        sel = tabla_ke[tabla_ke["Elegida"]].iloc[0] if tabla_ke["Elegida"].any() else None
        if sel is not None and pd.notna(sel["Ke (COP)"]):
            ref_dam = tabla_ke.iloc[0]
            mm = ui.tarjetas(3)
            mm[0].metric(f"Ke (COP) · {sel['Fuente']}", ui.pct(sel["Ke (COP)"], fraccion=False), border=True,
                         delta=f"{'+' if sel['Ke (COP)'] >= ref_dam['Ke (COP)'] else '−'}"
                               f"{ui.num(abs(sel['Ke (COP)'] - ref_dam['Ke (COP)']))} p.p. vs Damodaran emerg.",
                         delta_color="off")
            mm[1].metric("βU elegida", ui.num(sel["βU"], 2), border=True)
            mm[2].metric(f"WACC (COP) · {sel['Fuente']}", ui.pct(sel["WACC (COP)"], fraccion=False), border=True)
            st.caption("Esta es la fuente que quedó elegida arriba y la que verán Valoración y Proyectos.")
            if sel["Ke (COP)"] < tes10 * 100:
                st.warning(f"El Ke en pesos ({ui.pct(sel['Ke (COP)'], fraccion=False)}) es menor que el TES 10A "
                           f"({ui.pct(tes10)}). Suele indicar que la inflación de la paridad de Fisher (meta del "
                           "BanRep) es menor que la que descuenta el mercado; revísala en «Costo de capital».",
                           icon=":material/warning:")
        elif sel is not None:
            st.warning(f"La fuente elegida ({sel['Fuente']}) no tiene dato para **{sector}**.")

        izq, der = st.columns([3, 2], gap="large")
        with izq:
            fig = go.Figure(go.Bar(
                y=[g_[0] for g_ in grafico], x=[g_[1] for g_ in grafico], orientation="h",
                marker=dict(color=[ui.PALETA[0] if g_[4] == elegida else ui.RAMPA_AZUL[1] for g_ in grafico]),
                error_x=dict(type="data", symmetric=False, array=[g_[3] for g_ in grafico],
                             arrayminus=[g_[2] for g_ in grafico], color=ui.GRIS_REF),
                text=[ui.pct(g_[1], fraccion=False) for g_ in grafico], textposition="inside",
                hovertemplate="%{y}: %{text}<extra></extra>"))
            fig.update_layout(height=300, margin=dict(l=8, r=8, t=28, b=8), separators=",.", showlegend=False,
                              xaxis=dict(title="Ke (COP), %", rangemode="tozero"),
                              yaxis=dict(title=None, autorange="reversed"))
            ui.mostrar(fig)
            st.caption("La barra de error del beta propio es su intervalo bootstrap al 95 %. "
                       "La fuente elegida va en azul oscuro.")
        with der:
            vista_ke = tabla_ke.drop(columns="Elegida")
            st.dataframe(vista_ke, hide_index=True, width="stretch", column_config={
                "βU": st.column_config.NumberColumn(format="%.2f"),
                "βL": st.column_config.NumberColumn(format="%.2f"),
                "Ke (COP)": st.column_config.NumberColumn(format="%.2f %%"),
                "WACC (COP)": st.column_config.NumberColumn(format="%.2f %%")})
        st.caption("Todas las fuentes usan los mismos supuestos de mercado de la página «Costo de capital» "
                   "(Tesoro 10A, ERP madura, CRP de Damodaran, Fisher) y el mismo D/E; solo cambia la beta. "
                   "Mira la pestaña de metodología para entender qué tan comparables son.")

# =============================== EMPRESAS ===========================================
with tab_emp:
    emp = almacen.leer_empresas_propias()
    if emp is None:
        st.info("No hay detalle por empresa en la corrida importada.")
    else:
        con_dato = prop.sort_values("n_empresas", ascending=False)["industria"].tolist()
        sector_e = st.selectbox("Industria", con_dato, key="sector_emp_latam")
        d = emp[emp["industria"] == sector_e].sort_values(["incluir", "pais_es", "ticker"],
                                                          ascending=[False, True, True])
        usadas = int(d["incluir"].sum())
        mm = ui.tarjetas(3)
        mm[0].metric("Acciones usadas", f"{usadas} de {len(d)}", border=True)
        mm[1].metric("Países de las usadas", int(d.loc[d["incluir"], "pais_es"].nunique()), border=True)
        mm[2].metric("Beta mediano (usadas, apalancado)",
                     ui.num(d.loc[d["incluir"], "beta_vs_indice_pais"].median(), 2), border=True)
        t = d[["ticker", "empresa", "pais_es", "anios", "beta_vs_indice_pais", "r2", "incluir", "motivo_exclusion"]].copy()
        t["incluir"] = np.where(t["incluir"], "Sí", "No")
        t.columns = ["Ticker (Yahoo)", "Empresa", "País", "Años de historia", "Beta vs ETF del país", "R²",
                     "Usada", "Motivo de exclusión"]
        st.dataframe(t, hide_index=True, width="stretch", column_config={
            "Años de historia": st.column_config.NumberColumn(format="%.1f"),
            "Beta vs ETF del país": st.column_config.NumberColumn(format="%.2f"),
            "R²": st.column_config.NumberColumn(format="%.2f")})
        ui.boton_descarga(t, f"empresas_{sector_e.replace('/', '-').replace(' ', '_')}_{date.today()}.csv",
                          "Descargar empresas (CSV)", clave="dl_emp")
        st.caption("El beta de cada acción es contra el ETF de su país en dólares (EWZ, EWW, ECH, EPU, ARGT; "
                   "ICOLCAP convertido a USD para Colombia). Las acciones excluidas no entran al promedio.")

# =============================== METODOLOGÍA ========================================
with tab_met:
    st.markdown("""
**Cómo se obtiene el beta propio**

1. Retornos logarítmicos semanales en dólares de cada acción de Yahoo Finance, con todo su historial (mínimo 3 años).
2. Beta por regresión contra el ETF de su país en dólares. Se excluyen acciones poco líquidas o con retornos extremos.
3. Beta de la industria = promedio **balanceado por país** (cada país pesa igual, para que Brasil no domine),
   con intervalo bootstrap al 95 % sobre las empresas.
4. Se desapalanca con el D/E y la caja de Damodaran (emergentes) y se compara con la beta desapalancada de Damodaran.
""")
    st.latex(r"\beta_U = \frac{\beta_L}{[1+(1-t)\,D/E]\,(1-\text{caja}/V)}")
    st.markdown("**Cómo se combina con Damodaran**")
    st.latex(r"\beta_U^{comb} = w\,\beta_U^{propio} + (1-w)\,\beta_U^{Damodaran},\qquad "
             r"w = \frac{\tau^2}{\tau^2 + EE^2}")
    st.markdown(f"""
τ es el desacuerdo típico entre ambos métodos (aquí **{tau:.3f}**) y EE el error estándar del beta propio.
Con menos de 3 firmas no hay error estándar y el peso es cero. El error estándar es el mayor entre el del
bootstrap y la dispersión entre empresas dividida por √n, porque con 3 o 4 firmas el bootstrap subestima la
incertidumbre. Es una heurística de contracción, no un parámetro verdadero.

**Límites que conviene tener presentes**

- **Comparabilidad del Ke.** Los betas propios se miden contra el mercado de cada país en dólares, mientras
  que el Ke de este tablero usa la prima de mercado madura más el riesgo país de Damodaran, pensada para betas
  frente a un mercado global. El cuaderno calcula el Ke con la prima total del país y una tasa libre en pesos
  (TES menos spread). Por eso aquí las fuentes se comparan con una **misma fórmula**, y las diferencias de Ke
  vienen solo de la beta; no equivalen exactamente a los Ke del cuaderno.
- **D/E y caja de Damodaran, no por empresa.** Las empresas de la muestra pueden tener otra estructura de capital.
- **Peso del combinado.** Mide precisión estadística, no representatividad: tres empresas brasileñas del mismo
  sector pueden dar un beta muy estable sin representar al sector latinoamericano.
- **Muestras pequeñas.** Solo {meta.get('sectores_5_o_mas', '—')} industrias tienen 5 o más firmas.
- **Datos de Yahoo Finance.** Sesgo de supervivencia, errores de precio y poca liquidez en algunas bolsas.
  Las cifras de las empresas más importantes conviene validarlas con la fuente oficial de cada bolsa.
- **Historial completo.** Mezcla regímenes de mercado; la estabilidad (3, 5 y 10 años, mitades) se revisa en el cuaderno.
- **Financieras.** El D/E de bancos y aseguradoras es poco informativo para desapalancar.
""")
