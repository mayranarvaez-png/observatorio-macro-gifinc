"""Coyuntura: resumen ejecutivo de la economía colombiana."""
import pandas as pd
import streamlit as st

from nucleo import costo_capital as cc
from nucleo import mercado, tema, ui
from nucleo.catalogo import POR_ID

tema.encabezado("Coyuntura macro-financiera de Colombia",
                "Los indicadores que mueven el costo de capital y las decisiones de inversión, con su variación frente a hace "
                "12 meses y un **análisis automático** de la coyuntura. Pasa el cursor sobre ⓘ para ver la fuente de cada tarjeta.",
                seccion="Monitoreo", chips=["Banco de la República", "DANE / OCDE", "FRED", "Damodaran"])

# --- Tarjetas -----------------------------------------------------------------------
# Contenedor horizontal: las tarjetas pasan a la fila siguiente cuando no caben.
TARJETAS = [
    ("pib_var_anual", "Crecimiento PIB (anual)", 2, "normal"),
    ("ipc_anual", "Inflación anual", 2, "inverse"),
    ("tpm", "Tasa de política BanRep", 2, "off"),
    ("desempleo", "Desempleo", 1, "inverse"),
    ("tes_10", "TES 10 años", 2, "off"),
    ("ust_10", "Tesoro EE. UU. 10 años", 2, "off"),
    ("trm", "TRM (COP/USD)", 0, "off"),
    ("colcap", "COLCAP", 0, "normal"),
]
@st.dialog("Gráfico del indicador", width="large")
def abrir_grafico(id_serie: str, etiqueta: str) -> None:
    """Ventana con el gráfico completo de una tarjeta, su ficha técnica y la descarga de los datos."""
    s = POR_ID[id_serie]
    st.markdown(f"### {etiqueta}")
    rango = st.segmented_control("Periodo", list(ui.RANGOS), default="5 años", key=f"rango_dlg_{id_serie}")
    df = ui.recortar(ui.serie(id_serie), ui.RANGOS[rango or "5 años"])
    if df.empty:
        st.info("Sin datos para este indicador. Usa **Actualizar datos ahora**.")
        return
    ui.mostrar(ui.lineas({etiqueta: df}, s.unidad, altura=380))
    ui.boton_descarga(df.rename(columns={"valor": etiqueta}), f"{id_serie}.csv", "Descargar datos (CSV)", clave=f"dl_dlg_{id_serie}")
    with st.expander("Ficha técnica", icon=":material/info:"):
        ui.ficha(s)


for fila in (TARJETAS[:4], TARJETAS[4:]):
    for col, (id_serie, etiqueta, dec, color) in zip(st.columns(4, gap="small"), fila):
        with col:
            ui.tarjeta(id_serie, etiqueta, decimales=dec, color_delta=color)
            if st.button("Ver gráfico", key=f"ver_{id_serie}", icon=":material/open_in_full:", type="tertiary", width="stretch"):
                abrir_grafico(id_serie, etiqueta)

# --- Análisis de coyuntura -----------------------------------------------------------
st.subheader("Análisis de la coyuntura")
_, ipc = ui.ultimo("ipc_anual")
_, tpm = ui.ultimo("tpm")
_, tes1 = ui.ultimo("tes_1")
_, tes10 = ui.ultimo("tes_10")
_, ust = ui.ultimo("ust_10")
trm_prev = ui.valor_hace("trm", 12)
_, trm = ui.ultimo("trm")

puntos, tono_coy = [], "neutro"
if ipc is not None:
    if ipc > 4:
        estado, tono_coy = "por **encima** del rango meta del BanRep (3 % ± 1 p.p.): presiona a la política monetaria a mantenerse restrictiva", "alerta"
    elif ipc < 2:
        estado, tono_coy = "por **debajo** del rango meta del BanRep (3 % ± 1 p.p.): da espacio para recortes de tasa", "alerta"
    else:
        estado = "**dentro** del rango meta del BanRep (3 % ± 1 p.p.)"
    puntos.append(f"**Inflación:** {ui.pct(ipc, fraccion=False)} anual, {estado}.")
if ipc is not None and tpm is not None:
    real = ((1 + tpm / 100) / (1 + ipc / 100) - 1) * 100
    postura = "contractiva" if real > 2.5 else ("neutral" if real > 1 else "expansiva")
    puntos.append(f"**Política monetaria:** la tasa real ex post es {ui.pct(real, fraccion=False)} "
                  f"(TPM deflactada por IPC), una postura aproximadamente **{postura}** "
                  "frente a una tasa neutral real de 1–2,5 %. Una postura contractiva encarece el crédito y los flujos descontados.")
if tes1 is not None and tes10 is not None:
    pendiente = tes10 - tes1
    forma = "positiva" if pendiente > 0.25 else ("invertida" if pendiente < -0.25 else "plana")
    puntos.append(f"**Curva de TES:** pendiente **{forma}** (10A − 1A = {ui.num(pendiente)} p.p.)"
                  + (". Una curva invertida suele anticipar recortes de tasa o desaceleración." if forma == "invertida" else "."))
if tes10 is not None and ust is not None:
    puntos.append(f"**Diferencial soberano:** TES 10A − Tesoro 10A = {ui.num(tes10 - ust)} p.p., que combina riesgo "
                  "país y diferencial de inflación esperada; por eso no se usa directamente como prima de riesgo país.")
if trm and trm_prev:
    var = trm / trm_prev - 1
    puntos.append(f"**Tipo de cambio:** el peso se ha {'depreciado' if var > 0 else 'apreciado'} {ui.pct(abs(var), 1)} "
                  "frente al dólar en 12 meses; afecta el costo de la deuda en dólares y los ingresos de los exportadores.")
tema.lectura(puntos or ["Sin datos suficientes."], titulo="Interpretación de los indicadores", tono=tono_coy,
             nota="Análisis generado con reglas fijas a partir de los datos; no reemplaza el criterio del grupo.")

# --- Costo de capital de referencia -------------------------------------------------
st.subheader("Costo de capital de referencia")
ref = mercado.supuestos_referencia()
if ref is None:
    st.info("Faltan datos de Damodaran o FRED. Actualiza los datos.")
else:
    s, pais = ref
    r = cc.calcular(s)
    tarjetas_ref = [
        ("Ke en USD (β = 1)", ui.pct(r["ke_usd"]),
         "rf + ERP madura + CRP (calificación). Empresa promedio, sin deuda."),
        ("Ke en COP (β = 1)", ui.pct(r["ke_cop"]),
         "Ke USD convertido por paridad de Fisher (π COL = meta BanRep; π USA = breakeven 10A)."),
        ("Prima de riesgo país (CRP)", ui.pct(s.crp),
         f"Damodaran, calificación Moody's {pais['calificacion_moodys']} · archivo {pais['fecha_archivo']}"),
        ("Prima de mercado madura (ERP)", ui.pct(s.erp),
         f"Damodaran, ERP implícita del S&P 500 · archivo {pais['fecha_archivo']}"),
    ]
    for col, (etiqueta, valor, ayuda) in zip(st.columns(len(tarjetas_ref), gap="small"), tarjetas_ref):
        with col:
            st.metric(etiqueta, valor, help=ayuda, border=True)
    st.page_link("paginas/costo_capital.py", label="Calcular Ke y WACC para una industria o empresa",
                 icon=":material/arrow_forward:")

# --- Gráficos de contexto -----------------------------------------------------------
st.subheader("Contexto")
rango = st.segmented_control("Periodo", list(ui.RANGOS), default="5 años", key="rango_inicio")
anios = ui.RANGOS[rango or "5 años"]
g1, g2 = st.columns(2)
with g1:
    st.markdown("**Política monetaria e inflación**")
    ui.mostrar(ui.lineas(
        {"Tasa de política": ui.recortar(ui.serie("tpm"), anios),
         "Inflación anual": ui.recortar(ui.serie("ipc_anual"), anios),
         "Inflación básica": ui.recortar(ui.serie("ipc_nucleo"), anios)},
        "%", referencias=[(3, "Meta 3 %")]))
with g2:
    st.markdown("**Tasas largas: Colombia vs. EE. UU.**")
    ust_m = ui.serie("ust_10").set_index("fecha")["valor"].resample("MS").mean().dropna()
    ui.mostrar(ui.lineas(
        {"TES 10 años": ui.recortar(ui.serie("tes_10"), anios),
         "Tesoro EE. UU. 10 años": ui.recortar(ust_m.reset_index(), anios)},
        "%"))
