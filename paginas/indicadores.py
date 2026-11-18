"""Explorador de indicadores con ficha técnica y descarga."""
import streamlit as st

from nucleo import tema, ui
from nucleo.catalogo import BLOQUES, POR_ID, SERIES, series_de_bloque

tema.encabezado("Indicadores macroeconómicos", "20 series de Colombia y EE. UU. con ficha técnica, descarga y comparador. "
                "Elige el periodo y explora por bloque temático.", seccion="Monitoreo",
                chips=["BanRep", "DANE / OCDE", "FRED", "Banco Mundial"])

rango = st.segmented_control("Periodo", list(ui.RANGOS), default="10 años", key="rango_ind")
anios = ui.RANGOS[rango or "10 años"]

pestanas = st.tabs(BLOQUES + ["Comparar series"])

# --- Un bloque por pestaña ----------------------------------------------------------
for pestana, bloque in zip(pestanas[:-1], BLOQUES):
    with pestana:
        for s in series_de_bloque(bloque):
            df = ui.serie(s.id)
            st.markdown(f"#### {s.nombre}")
            if df.empty:
                st.warning("Serie sin datos. Ejecuta la actualización.")
                continue
            fecha, valor = ui.ultimo(s.id)
            st.caption(f"Último dato: **{ui.num(valor)} {s.unidad}** "
                       f"({ui.periodo_txt(fecha, s.frecuencia)}) · {s.fuente}")
            referencias = [(3, "Meta 3 %")] if s.id in ("ipc_anual", "ipc_nucleo") else None
            if s.id in ("pib_var_anual", "cuenta_corriente", "balance_fiscal"):
                referencias = [(0, "")]
            ui.mostrar(ui.lineas({s.nombre: ui.recortar(df, anios)}, s.unidad,
                                 altura=280, referencias=referencias))
            c1, c2 = st.columns([3, 1])
            with c1:
                with st.expander("Ficha técnica"):
                    ui.ficha(s)
            with c2:
                ui.boton_descarga(df.rename(columns={"valor": f"{s.id} ({s.unidad})"}),
                                  f"{s.id}.csv", clave=f"dl_{s.id}")

# --- Comparador -----------------------------------------------------------------------
with pestanas[-1]:
    st.markdown("Compara series en un mismo eje. Las tasas se comparan en su unidad (%). "
                "Para series de distinta escala usa **índice base 100**, que evita el doble eje.")
    modo = st.radio("Modo", ["Tasas en %", "Índice base 100"], horizontal=True)
    if modo == "Tasas en %":
        candidatas = [s for s in SERIES if s.es_tasa]
        default = ["tpm", "ibr_3m", "tes_10", "ipc_anual"]
    else:
        candidatas = SERIES
        default = ["trm", "colcap"]
    elegidas = st.multiselect(
        "Series (máximo 6)", [s.id for s in candidatas], default=default, max_selections=6,
        format_func=lambda i: POR_ID[i].nombre)
    frecuencia = st.radio("Frecuencia común", ["Mensual", "Original"], horizontal=True,
                          help="Mensual promedia las series diarias; recomendado al combinar frecuencias.")
    if elegidas:
        # Orden fijo del catálogo: cada serie conserva su color aunque cambie el orden de selección.
        elegidas = sorted(elegidas, key=lambda i: SERIES.index(POR_ID[i]))
        datos = {}
        for i in elegidas:
            df = ui.serie(i)
            if frecuencia == "Mensual" and POR_ID[i].frecuencia == "Diaria":
                df = df.set_index("fecha")["valor"].resample("MS").mean().dropna().reset_index()
            datos[POR_ID[i].nombre] = ui.recortar(df, anios)
        if modo == "Índice base 100":
            inicio = max(d["fecha"].min() for d in datos.values())
            for k, d in datos.items():
                d = d[d["fecha"] >= inicio].copy()
                d["valor"] = d["valor"] / d["valor"].iloc[0] * 100 if not d.empty else d["valor"]
                datos[k] = d
            st.caption(f"Base 100 = primer dato común ({ui.fecha_txt(inicio)}).")
        unidad = "%" if modo == "Tasas en %" else "índice"
        ui.mostrar(ui.lineas(datos, unidad, altura=420))

        tabla = None
        for nombre, d in datos.items():
            d = d.rename(columns={"valor": nombre}).set_index("fecha")
            tabla = d if tabla is None else tabla.join(d, how="outer")
        tabla = tabla.reset_index()
        with st.expander("Ver tabla"):
            st.dataframe(tabla.sort_values("fecha", ascending=False), hide_index=True,
                         width="stretch")
        ui.boton_descarga(tabla, "comparacion_series.csv", "Descargar comparación (CSV)",
                          clave="dl_comp")
