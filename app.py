"""Observatorio Macro-Financiero de Colombia.

Ejecutar con:  streamlit run app.py
"""
from pathlib import Path

import streamlit as st

from actualizar_datos import actualizar
from nucleo import acceso, almacen, tema

ASSETS = Path(__file__).resolve().parent / "assets"

st.set_page_config(
    page_title="Observatorio Macro-Financiero Colombia · GIFINC",
    page_icon=str(ASSETS / "icono_gifinc.png"),
    layout="wide",
)
tema.aplicar()
st.logo(str(ASSETS / "logo_gifinc.png"), icon_image=str(ASSETS / "icono_gifinc.png"), size="large")

paginas = st.navigation({
    "Monitoreo": [
        st.Page("paginas/inicio.py", title="Coyuntura", icon=":material/dashboard:", default=True),
        st.Page("paginas/indicadores.py", title="Indicadores", icon=":material/show_chart:"),
    ],
    "Análisis financiero": [
        st.Page("paginas/costo_capital.py", title="Costo de capital", icon=":material/calculate:"),
        st.Page("paginas/beta_latam.py", title="Beta propio vs Damodaran", icon=":material/compare_arrows:"),
        st.Page("paginas/evaluacion_proyectos.py", title="Evaluación de proyectos", icon=":material/account_tree:"),
        st.Page("paginas/valoracion_empresas.py", title="Valoración de empresas", icon=":material/domain:"),
    ],
    "Inversión": [
        st.Page("paginas/acciones.py", title="Comparador de acciones", icon=":material/query_stats:"),
        st.Page("paginas/portafolio.py", title="Portafolio", icon=":material/pie_chart:"),
    ],
    "Referencia": [
        st.Page("paginas/metodologia.py", title="Metodología y fuentes", icon=":material/menu_book:"),
    ],
})

with st.sidebar:
    st.markdown("### Observatorio Macro-Financiero")
    st.caption("Grupo de Investigación en Finanzas Cuantitativa · GIFINC")
    registro = almacen.leer_registro()
    fechas = [v.get("actualizado") for v in registro.values() if v.get("actualizado")]
    errores = [k for k, v in registro.items() if v.get("estado") == "error"]
    st.caption(f"Última actualización: **{max(fechas) if fechas else 'nunca'}**")
    if errores:
        st.caption(f":orange[{len(errores)} fuente(s) con error en la última descarga]")
    acceso.panel_admin()
    if acceso.es_admin() and st.button("Actualizar datos ahora", icon=":material/refresh:", width="stretch"):
        with st.status("Descargando de BanRep, DANE/OCDE, FRED, Banco Mundial y Damodaran…") as estado:
            actualizar(aviso=st.write)
            estado.update(label="Datos actualizados", state="complete")
        st.cache_data.clear()
        st.rerun()

if not almacen.leer_registro():
    if acceso.es_admin():
        st.info("Aún no hay datos descargados. Usa **Actualizar datos ahora** en la barra lateral "
                "o ejecuta `python actualizar_datos.py`.")
    else:
        st.info("Los datos se están preparando. Vuelve a consultar en unos minutos.")

paginas.run()

st.divider()
st.caption("**GIFINC · Grupo de Investigación en Finanzas Cuantitativa.** Material académico y de consulta: "
           "no constituye asesoría de inversión. Fuentes: Banco de la República, DANE/OCDE, Superfinanciera, "
           "FRED, Banco Mundial, Damodaran (NYU Stern), Yahoo Finance y Superintendencia de Sociedades.")
