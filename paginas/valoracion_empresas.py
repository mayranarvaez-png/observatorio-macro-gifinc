"""Valoración de empresas por flujo de caja libre descontado y múltiplos."""
import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import almacen, seleccion, tema, ui, yahoo
from nucleo import carga_archivos as carga
from nucleo import supersociedades as ss
from nucleo import componentes as comp
from nucleo import valoracion as val

tema.encabezado("Valoración de empresas", "DCF del flujo de caja libre (FCFF) al **WACC del sector**, con diagnóstico financiero (ROIC, EVA), puente de valor, sensibilidad y contraste con múltiplos.", seccion="Análisis financiero", chips=["DCF · FCFF", "EVA · ROIC", "Superintendencia de Sociedades"])
st.caption("Valores en millones de COP. Trae los estados financieros de la Supersociedades, de un archivo propio o usa el caso de ejemplo.")

MEM_HIST = "_mem_val_historico"
if MEM_HIST not in st.session_state:
    st.session_state[MEM_HIST] = val.historico_ejemplo()

pasos = st.tabs(["① Estados financieros", "② Escenario macro", "③ Costo de capital",
                 "④ Supuestos de proyección", "⑤ Valoración", "Guía"])

# ===================================== ① HISTÓRICOS ==================================
NOMBRE_EJEMPLO = "Alimentos del Valle S.A. (caso ficticio)"
st.session_state.setdefault("val_nombre", st.session_state.get("_mem_val_nombre", NOMBRE_EJEMPLO))


@st.cache_data(ttl=86_400, show_spinner=False)
def _buscar(texto: str) -> pd.DataFrame:
    return ss.buscar(texto)


@st.cache_data(ttl=86_400, show_spinner=False)
def _descargar(nit: str) -> pd.DataFrame:
    return ss.descargar(nit)


@st.cache_data(ttl=86_400, show_spinner=False)
def _caratula(nit: str) -> dict:
    return ss.caratula(nit)


def _usar(tabla: pd.DataFrame, nombre: str, origen: str, traza: pd.DataFrame | None = None,
          avisos: list[str] | None = None) -> None:
    """Reemplaza los estados financieros del modelo y reinicia el editor."""
    st.session_state[MEM_HIST] = tabla.astype(float)
    st.session_state["val_nombre"] = nombre
    st.session_state["_mem_val_nombre"] = nombre
    st.session_state["_val_origen"] = {"origen": origen, "traza": traza, "avisos": avisos or []}
    st.session_state.pop("val_editor", None)
    if not origen.startswith("Yahoo Finance"):
        st.session_state.pop("_val_mercado", None)        # el precio de bolsa solo aplica a empresas cargadas de Yahoo
    # Los supuestos por defecto salen del histórico: se reinician para la nueva empresa.
    for k in ("val_margen", "val_capex", "val_dya", "val_ktno"):
        st.session_state.pop(k, None)
    st.rerun()


def _acotar(valor: float, minimo: float, maximo: float, defecto: float) -> float:
    """Valor inicial de un deslizador dentro de su rango (un histórico atípico no debe romper la página)."""
    if valor is None or pd.isna(valor):
        return defecto
    return float(min(max(valor, minimo), maximo))


@st.cache_data(show_spinner=False)
def _trm_anual() -> pd.Series:
    trm = almacen.leer_serie("trm")
    return pd.Series(dtype=float) if trm is None else trm.set_index("fecha")["valor"].groupby(lambda f: f.year).mean()


def _panel_yahoo() -> None:
    st.caption("Estados financieros anuales que reporta Yahoo Finance para empresas que cotizan en bolsa (hasta 4 años): "
               "Colombia, Latinoamérica, EE. UU., Europa y más. Ideal para Ecopetrol, ISA, Nutresa, Cementos Argos, etc.")
    cat = seleccion.catalogo()
    acciones = cat[cat["tipo"] == "Acción"]
    acciones = pd.concat([acciones[acciones["pais"] == "Colombia"], acciones[acciones["pais"] != "Colombia"]])
    etiquetas = dict(zip(acciones["ticker"], acciones["ticker"] + " · " + acciones["nombre"] + " (" + acciones["pais"] + ")"))
    t = st.selectbox("Empresa (escribe el nombre o el ticker)", list(etiquetas), index=None, key="yf_ticker",
                     format_func=lambda x: etiquetas.get(x, x), accept_new_options=True,
                     placeholder="p. ej. Ecopetrol, ISA, Nutresa, Apple…",
                     help="También puedes escribir cualquier símbolo de Yahoo Finance y pulsar Enter.")
    if not t:
        return
    t = str(t).strip().upper()
    with st.spinner("Consultando Yahoo Finance…"):
        datos = yahoo.estados_anuales(t)
        perfil = yahoo.perfil(t) or {}
    if datos is None:
        st.warning(f"Yahoo Finance no tiene estados financieros para **{t}**. Revisa el símbolo o usa otra fuente.")
        return
    crudo, moneda = datos
    tabla, avisos = yahoo.a_rubros(crudo)
    nota_moneda = ""
    if moneda and moneda != "COP":
        trm = _trm_anual()
        if moneda == "USD" and not trm.empty:
            factor = pd.Series({a: trm.get(a, trm.iloc[-1]) for a in tabla.columns})
            tabla = tabla * factor
            nota_moneda = (f" Yahoo reporta en **USD**; se convirtió a pesos con la TRM promedio de cada año "
                           f"(último año: {ui.num(factor.iloc[-1], 0)} COP/USD).")
        else:
            nota_moneda = (f" Yahoo reporta en **{moneda}** y no se convirtió: las cifras quedan en millones de {moneda}. "
                           "El modelo usa supuestos macro de Colombia, así que interpreta el resultado con cuidado.")
    nombre = perfil.get("nombre") or t
    st.caption(f"**{nombre}** · {perfil.get('sector') or 'sector sin dato'} · reporta en {moneda or 'moneda sin dato'}. "
               f"Cifras en millones de COP.{nota_moneda} Elige el sector equivalente de Damodaran en el paso ③.")
    st.dataframe(tabla.style.format(lambda x: ui.num(x, 1)), width="stretch")
    for a in avisos:
        st.caption(f":orange[⚠ {a}]")
    mercado = yahoo.acciones_y_precio(t)
    acc = mercado.get("acciones") or perfil.get("acciones_circulacion")
    precio, moneda_px = mercado.get("precio"), mercado.get("moneda")
    es_adr_colombiano = "." not in t and t in set(acciones.loc[acciones["pais"] == "Colombia", "ticker"])
    # Solo se compara con el precio cuando la acción cotiza en pesos: un ADR agrupa varias acciones y una empresa
    # extranjera se está valorando con supuestos macro de Colombia, así que la comparación engañaría.
    precio_cop = float(precio) if precio and moneda_px == "COP" and not es_adr_colombiano else None
    if acc:
        st.caption(f"Acciones en circulación según Yahoo: **{ui.num(acc / 1e6, 1)} millones**"
                   + (f" (reporte de {mercado['fecha_acciones']})" if mercado.get("fecha_acciones") else "")
                   + ". Se cargarán en el modelo.")
    else:
        st.warning("Yahoo no informa las acciones en circulación de esta empresa: escríbelas en «Acciones en circulación "
                   "(millones)» debajo de la tabla del modelo; sin ellas el valor por acción no es correcto.", icon=":material/warning:")
    if precio:
        st.caption(f"Precio en bolsa: **{ui.num(precio, 2)} {moneda_px}**.")
    if moneda and moneda != "COP" and not es_adr_colombiano:
        st.caption(":orange[⚠ Empresa extranjera: el modelo usa supuestos de Colombia (riesgo país, inflación y PIB), así que el "
                   "resultado sirve como ejercicio y no se compara con su precio en bolsa.]")
    if es_adr_colombiano:
        st.caption(":orange[⚠ Este símbolo es un ADR que cotiza en EE. UU.: cada ADR agrupa varias acciones ordinarias, así que su precio "
                   "no se compara directamente con el valor por acción. Para empresas colombianas usa el símbolo de la BVC (termina en .CL).]")
    if st.button("Usar estos estados financieros", type="primary", icon=":material/check:", key="yf_usar"):
        if acc:
            st.session_state["val_acciones"] = float(round(acc / 1e6, 2))
        st.session_state["_val_mercado"] = {"ticker": t, "precio_cop": precio_cop, "precio": precio, "moneda": moneda_px}
        _usar(tabla, nombre, f"Yahoo Finance · {t}" + (f" · convertido de {moneda}" if moneda and moneda != "COP" else ""),
              None, avisos)


def _panel_supersociedades() -> None:
    st.caption("Estados financieros NIIF que las sociedades reportan a la Superintendencia de Sociedades "
               f"(2015 en adelante), vía datos.gov.co. [Ver la fuente]({ss.URL_FUENTE})")
    q = st.text_input("Buscar empresa por nombre o NIT", placeholder="Ej.: Alpina, Colombina, 860025900",
                      key="ss_q")
    if not q:
        return
    try:
        with st.spinner("Buscando en la base de la Supersociedades…"):
            res = _buscar(q)
    except Exception as e:  # noqa: BLE001 - error de red: se informa al estudiante
        st.error(f"No fue posible consultar datos.gov.co ({e}). Intenta de nuevo o carga un archivo.")
        return
    if res.empty:
        por_nit = q.replace(".", "").replace("-", "").strip().isdigit()
        st.info(f"No se encontró {'ese NIT' if por_nit else 'ninguna sociedad con ese nombre'} en la base de la "
                "Supersociedades. Las empresas inscritas en bolsa (p. ej. Éxito, Nutresa, Ecopetrol) y las "
                "entidades financieras reportan a la **Superintendencia Financiera** y no están aquí; a veces sí "
                "aparecen sus filiales. Para esas empresas descarga sus estados financieros de su página de "
                "relación con inversionistas y súbelos en **Cargar archivo**.")
        return
    i = st.selectbox("Empresa", range(len(res)), key="ss_empresa",
                     format_func=lambda k: f"{res.loc[k, 'Razón social']} · NIT {res.loc[k, 'NIT']} · "
                                           f"último reporte {res.loc[k, 'Último corte']}")
    nit = res.loc[i, "NIT"]
    try:
        with st.spinner("Descargando estados financieros…"):
            raw = _descargar(nit)
            info = _caratula(nit)
    except Exception as e:  # noqa: BLE001
        st.error(f"No fue posible descargar los estados financieros ({e}).")
        return
    if raw.empty:
        st.warning("Esta sociedad no tiene estados financieros de cierre anual en la base.")
        return
    unidad = (info.get("unidad") or "MILES DE PESOS").upper()
    divisor = 1.0 if "MILLONES" in unidad else (1_000.0 if "MILES" in unidad else 1_000_000.0)
    c1, c2 = st.columns(2)
    categoria = c1.radio("Tipo de estados financieros", ss.puntos_de_entrada(raw), horizontal=True,
                         key=f"ss_cat_{nit}", help="Consolidado incluye a las subsidiarias.")
    tabla, traza, avisos = ss.a_rubros(raw, categoria, divisor)
    if tabla.empty:
        st.warning(" ".join(avisos))
        return
    n_max = len(tabla.columns)
    n = c2.slider("Años a usar (los más recientes)", 1, n_max, min(5, n_max), key=f"ss_n_{nit}") if n_max > 1 else 1
    tabla = tabla.iloc[:, -n:]
    traza = traza[traza["Año"].isin(tabla.columns)]
    st.caption(f"Actividad: **{info.get('ciiu') or 'sin dato'}** · {info.get('ciudad') or ''} · "
               f"reportado en {unidad.lower()}, convertido a millones de COP. "
               "Elige el sector equivalente de Damodaran en el paso ③.")
    st.dataframe(tabla.style.format(lambda x: ui.num(x, 1)), width="stretch")
    for a in avisos:
        st.caption(f":orange[⚠ {a}]")
    with st.expander("¿De dónde sale cada cifra? (cuentas NIIF usadas)", icon=":material/fact_check:"):
        st.dataframe(traza.sort_values(["Usado en", "Año"]), hide_index=True, width="stretch",
                     column_config={"Valor (millones COP)": st.column_config.NumberColumn(format="%.1f")})
        st.caption("Gastos operacionales sin D&A = Ventas − Costo de ventas − Utilidad operativa − D&A. "
                   "KTNO = cuentas por cobrar + inventarios − cuentas por pagar comerciales.")
    if st.button("Usar estos estados financieros", type="primary", icon=":material/check:", key="ss_usar"):
        _usar(tabla, info.get("razon_social") or res.loc[i, "Razón social"],
              f"Supersociedades · NIT {nit} · {categoria}", traza, avisos)


def _panel_archivo() -> None:
    st.caption("Sube los estados financieros en Excel o CSV con **una columna por año** y los nombres de las "
               "cuentas en la primera columna. No importa el formato: tú indicas qué filas forman cada rubro.")
    archivo = st.file_uploader("Archivo", type=["xlsx", "xls", "csv"], key="val_archivo")
    if archivo is None:
        return
    try:
        hojas = carga.leer(archivo)
        nombre_hoja = (st.selectbox("Hoja", list(hojas), key=f"hoja_{archivo.file_id}")
                       if len(hojas) > 1 else next(iter(hojas)))
        tabla = carga.estructurar(hojas[nombre_hoja])
    except Exception as e:  # noqa: BLE001 - se informa al estudiante
        st.error(f"No se pudo leer el archivo: {e}")
        return
    st.caption(f"Detecté {len(tabla)} cuentas y los años {', '.join(map(str, tabla.columns))}.")
    nombre = archivo.name.rsplit(".", 1)[0]
    if carga.es_plantilla(tabla):
        st.success("El archivo tiene el formato de la plantilla del tablero.")
        if st.button("Usar estos estados financieros", type="primary", key="arch_plantilla"):
            _usar(tabla.loc[val.RUBROS], nombre, f"Archivo: {archivo.name}")
        return
    unidad = st.selectbox("Unidades del archivo", list(carga.UNIDADES), index=1, key=f"unid_{archivo.file_id}")
    sugeridas = carga.sugerir(tabla)
    st.markdown("**Asigna las cuentas a cada rubro** (puedes elegir varias; se suman). "
                "Las sugerencias se hicieron por palabras clave: revísalas.")
    asignacion = {}
    cols = st.columns(2)
    etiquetas = {"KTNO (+)": "Capital de trabajo: suma (cartera, inventarios)",
                 "KTNO (−)": "Capital de trabajo: resta (proveedores, cuentas por pagar)"}
    for k, rubro in enumerate(carga.SUGERENCIAS):
        asignacion[rubro] = cols[k % 2].multiselect(etiquetas.get(rubro, rubro), list(tabla.index),
                                                    default=sugeridas[rubro],
                                                    key=f"map_{rubro}_{archivo.file_id}")
    restar = st.toggle("Los gastos elegidos incluyen la depreciación (restarla para obtener gastos sin D&A)",
                       value=True, key=f"restar_{archivo.file_id}")
    resultado = carga.armar(tabla, asignacion, carga.UNIDADES[unidad], restar)
    st.dataframe(resultado.style.format(lambda x: ui.num(x, 1)), width="stretch")
    if st.button("Usar estos estados financieros", type="primary", icon=":material/check:", key="arch_usar"):
        _usar(resultado, nombre, f"Archivo: {archivo.name} ({unidad.lower()})")


def _panel_manual() -> None:
    st.caption("Edita directamente la tabla de abajo o descarga la plantilla, llénala en Excel y súbela en "
               "**Cargar archivo**.")
    c1, c2 = st.columns(2)
    plantilla = io.BytesIO()
    st.session_state[MEM_HIST].to_excel(plantilla, sheet_name="Historico")
    c1.download_button("Descargar plantilla (Excel)", plantilla.getvalue(), "plantilla_valoracion.xlsx",
                       icon=":material/download:", width="stretch")
    if c2.button("Restaurar el caso de ejemplo", icon=":material/restart_alt:", width="stretch", key="val_reset"):
        _usar(val.historico_ejemplo(), NOMBRE_EJEMPLO, "Caso de ejemplo (ficticio)")


with pasos[0]:
    fuente = st.segmented_control(
        "¿De dónde traes los estados financieros?",
        ["Empresas en bolsa (Yahoo Finance)", "Base de datos Supersociedades", "Cargar archivo (Excel o CSV)",
         "Ejemplo o ingreso manual"],
        default="Empresas en bolsa (Yahoo Finance)", key="val_fuente")
    with st.container(border=True):
        if fuente == "Empresas en bolsa (Yahoo Finance)":
            _panel_yahoo()
        elif fuente == "Base de datos Supersociedades":
            _panel_supersociedades()
        elif fuente == "Cargar archivo (Excel o CSV)":
            _panel_archivo()
        else:
            _panel_manual()

    origen = st.session_state.get("_val_origen", {"origen": "Caso de ejemplo (ficticio)"})
    st.markdown("#### Estados financieros del modelo · millones de COP")
    st.caption(f"Origen: **{origen['origen']}**. Puedes corregir cualquier celda; la valoración usa esta tabla.")
    hist_vista = st.session_state[MEM_HIST].copy()
    hist_vista.columns = [str(c) for c in hist_vista.columns]
    editado = st.data_editor(hist_vista, width="stretch", key="val_editor",
                             column_config={c: st.column_config.NumberColumn(format="%.0f") for c in hist_vista.columns})
    historico = editado.astype(float)
    historico.columns = [int(c) for c in historico.columns]
    st.session_state[MEM_HIST] = historico

    c_nom, c_acc = st.columns([2, 1])
    nombre = c_nom.text_input("Nombre de la empresa", key="val_nombre")
    st.session_state["_mem_val_nombre"] = nombre
    acciones = c_acc.number_input("Acciones en circulación (millones)", value=120.0, step=1.0, key="val_acciones",
                                  help="Con Yahoo Finance se carga solo. Para Supersociedades o un archivo propio, "
                                       "consúltalo en el certificado de existencia o en las notas a los estados financieros.")

# ===================================== ② ESCENARIO ===================================
with pasos[1]:
    st.markdown("Las ventas proyectadas crecen con el **PIB real** (ajustado por la elasticidad del sector) "
                "más la **inflación** de este escenario.")
    horizonte = st.session_state.get("val_horizonte", 5)
    escenario = comp.escenario_macro("val", horizonte)

# ===================================== ③ COSTO DE CAPITAL ============================
with pasos[2]:
    st.markdown("Elige el **sector** de la empresa. El WACC se recalcula al instante con la beta de Damodaran, "
                "la prima de riesgo país de Colombia y las tasas de mercado.")
    tasa = comp.costo_de_capital_sector("val", "Food Processing", escenario=escenario)
if tasa is None:
    st.stop()
wacc = tasa["wacc"]

# ===================================== ④ SUPUESTOS ===================================
diag = val.diagnostico(historico, tasa["t"])
ultimo = historico.columns[-1]
with pasos[3]:
    st.markdown("Los valores por defecto son los **promedios históricos** de la empresa. Ajústalos para "
                "reflejar tu tesis sobre su futuro.")
    a, b, c = st.columns(3)
    with a.container(border=True):
        st.markdown("**Crecimiento**")
        st.slider("Años de proyección explícita", 3, 10, 5, key="val_horizonte")
        elasticidad = st.slider("Elasticidad de las ventas al PIB", 0.0, 3.0, 1.1, 0.1, key="val_elast",
                                help="1,0 = las ventas reales crecen igual que la economía.")
        adicional = st.slider("Crecimiento real adicional (%)", -5.0, 10.0, 0.0, 0.5, key="val_adic") / 100
    with b.container(border=True):
        st.markdown("**Rentabilidad e inversión**")
        margen_hist = float(diag.loc["Margen EBITDA", ultimo])
        margen = st.slider("Margen EBITDA al final del horizonte (%)", -20.0, 70.0,
                           _acotar(round(margen_hist * 100, 1), -20.0, 70.0, 15.0), 0.5, key="val_margen",
                           help=f"Último histórico: {ui.pct(margen_hist, 1)}. Converge linealmente.") / 100
        capex = st.slider("CAPEX / ventas (%)", 0.0, 40.0,
                          _acotar(round(float(diag.loc['CAPEX / ventas'].mean()) * 100, 1), 0.0, 40.0, 5.0),
                          0.1, key="val_capex") / 100
        dya = st.slider("D&A / ventas (%)", 0.0, 30.0,
                        _acotar(round(float(diag.loc['D&A / ventas'].mean()) * 100, 1), 0.0, 30.0, 3.0),
                        0.1, key="val_dya") / 100
        ktno = st.slider("KTNO / ventas (%)", -30.0, 60.0,
                         _acotar(round(float(diag.loc['KTNO / ventas'].mean()) * 100, 1), -30.0, 60.0, 15.0),
                         0.5, key="val_ktno") / 100
    with c.container(border=True):
        st.markdown("**Valor terminal**")
        crec_lp = float(escenario["Crecimiento nominal (%)"].iloc[-1])
        g = st.slider("Crecimiento perpetuo g (%)", 0.0, 10.0, 4.5, 0.1, key="val_g",
                      help=f"Debe ser ≤ crecimiento nominal de largo plazo de la economía ({ui.num(crec_lp)} %).") / 100
        roic_opcion = st.radio("ROIC de largo plazo", ["Igual al WACC (conservador)", "Definir"], key="val_roic_op",
                               help="Igual al WACC: el crecimiento futuro no crea valor; más allá del horizonte "
                                    "la empresa gana exactamente su costo de capital.")
        roic_lp = (st.slider("ROIC de largo plazo (%)", 1.0, 40.0, 15.0, 0.5, key="val_roic") / 100
                   if roic_opcion == "Definir" else None)
        medio = st.toggle("Convención de mitad de año", key="val_medio",
                          help="Supone que los flujos llegan a mitad de cada año, no al final.")

s = val.SupuestosValoracion(nombre=nombre, horizonte=st.session_state["val_horizonte"], elasticidad_pib=elasticidad,
                            crecimiento_adicional=adicional, margen_ebitda_objetivo=margen, dya_ventas=dya,
                            capex_ventas=capex, ktno_ventas=ktno, tasa_impuesto=tasa["t"], g_terminal=g,
                            roic_largo_plazo=roic_lp, medio_periodo=medio, acciones_millones=acciones,
                            historico=historico)
v = val.proyectar(s, escenario, wacc)


def formato(df: pd.DataFrame, porcentajes: set[str] = frozenset(), dec: int = 1):
    return df.style.format(lambda x: "" if pd.isna(x) else ui.num(x, dec)).format(
        lambda x: "" if pd.isna(x) else ui.pct(x, 1), subset=pd.IndexSlice[[i for i in df.index if i in porcentajes], :])


# Diagnóstico en el paso ① (necesita el WACC del paso ③)
with pasos[0]:
    st.markdown("#### Diagnóstico financiero")
    st.dataframe(formato(diag.drop(index="Deuda / EBITDA (veces)"), set(diag.index))
                 if len(diag) else diag, width="stretch")
    d1, d2 = st.columns(2)
    with d1:
        roic = diag.loc["ROIC (sobre capital inicial)"].dropna()
        fig = go.Figure()
        fig.add_bar(x=[str(c) for c in roic.index], y=roic * 100, name="ROIC", marker_color=ui.AZUL,
                    hovertemplate="%{x}: %{y:.1f} %<extra>ROIC</extra>")
        fig.add_hline(y=wacc * 100, line=dict(color=ui.ROJO, dash="dash"),
                      annotation_text=f"WACC {ui.pct(wacc, 1)}")
        fig.update_layout(title=dict(text="¿Crea valor? ROIC vs. WACC", font=dict(size=14)), height=300,
                          margin=dict(l=8, r=8, t=40, b=8), separators=",.", yaxis=dict(title="%"))
        ui.mostrar(fig)
    with d2:
        eva = val.eva(s, wacc).loc["EVA"]
        fig = go.Figure(go.Bar(x=[str(c) for c in eva.index], y=eva,
                               marker_color=[ui.VERDE if x >= 0 else ui.NEG for x in eva],
                               hovertemplate="%{x}: %{y:,.0f}<extra>EVA</extra>"))
        fig.update_layout(title=dict(text="Valor económico agregado (EVA)", font=dict(size=14)), height=300,
                          margin=dict(l=8, r=8, t=40, b=8), separators=",.", yaxis=dict(title="Millones COP"))
        ui.mostrar(fig)
    st.caption("EVA = NOPAT − WACC × capital invertido al inicio del año. Positivo = la empresa ganó más que su costo de capital.")

# ===================================== ⑤ VALORACIÓN ==================================
with pasos[4]:
    st.markdown(f"#### {nombre}")
    for tipo, texto in v["alertas"]:
        getattr(st, tipo)(texto)
    mercado = st.session_state.get("_val_mercado")
    k = ui.tarjetas(5 if mercado and mercado.get("precio_cop") else 4)
    k[0].metric("Valor de la empresa (EV) · millones COP", ui.num(v["ev"], 0), border=True,
                delta=f"≈ {ui.en_palabras(v['ev'])}", delta_color="off", delta_arrow="off")
    k[1].metric("Valor del patrimonio · millones COP", ui.num(v["patrimonio"], 0), border=True,
                help="EV − deuda financiera + caja",
                delta=f"≈ {ui.en_palabras(v['patrimonio'])}", delta_color="off", delta_arrow="off")
    k[2].metric("Valor por acción · pesos", ui.num(v["por_accion"], 0), border=True,
                help="Valor del patrimonio (en pesos) ÷ número de acciones")
    k[3].metric("Peso del valor terminal", ui.pct(v["peso_vt"], 1), border=True)
    if mercado and mercado.get("precio_cop"):
        dif = v["por_accion"] / mercado["precio_cop"] - 1
        k[4].metric("Precio en bolsa · pesos", ui.num(mercado["precio_cop"], 0), border=True,
                    delta=f"Valor DCF {'+' if dif >= 0 else '−'}{ui.pct(abs(dif), 1)} vs. precio", delta_color="off",
                    help=f"Último precio de {mercado['ticker']} en Yahoo Finance"
                         + (f" ({ui.num(mercado['precio'], 2)} {mercado['moneda']}, convertido con la última TRM)"
                            if mercado.get("moneda") != "COP" else "")
                         + ". Una diferencia grande suele venir de los supuestos (sector del WACC, margen, crecimiento) "
                           "o de un número de acciones equivocado.")
    st.caption("Todas las cifras de la valoración están en **millones de pesos colombianos (COP)**, "
               "excepto el valor por acción, que está en pesos.")
    st.caption(f"WACC {ui.pct(wacc)} (sector {tasa['sector']}) · g {ui.pct(g)} · ROIC LP {ui.pct(v['roic_lp'])} · "
               f"reinversión terminal {ui.pct(v['tasa_reinversion_lp'], 1)} del NOPAT · "
               f"EV/EBITDA implícito {ui.num(v['ev'] / v['ebitda_base'], 1)}x")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Puente de valor**")
        fig = go.Figure(go.Waterfall(
            x=["VP flujos", "VP terminal", "EV", "Deuda", "Caja", "Patrimonio"],
            measure=["relative", "relative", "total", "relative", "relative", "total"],
            y=[v["vp_flujos"], v["vp_vt"], 0, -v["deuda"], v["caja"], 0],
            text=[ui.num(x, 0) for x in [v["vp_flujos"], v["vp_vt"], v["ev"], -v["deuda"], v["caja"], v["patrimonio"]]],
            textposition="outside",
            increasing=dict(marker=dict(color=ui.AZUL)), decreasing=dict(marker=dict(color=ui.ROJO)),
            totals=dict(marker=dict(color="#3A3A3A")),
            connector=dict(line=dict(color=ui.GRIS_REF, width=1, dash="dot")),
            hovertemplate="%{x}: %{text}<extra></extra>"))
        fig.update_layout(height=360, margin=dict(l=8, r=8, t=24, b=8), separators=",.",
                          yaxis=dict(title="Millones COP"), showlegend=False)
        ui.mostrar(fig)
    with g2:
        st.markdown("**Comparación de métodos (football field)**")
        waccs = [wacc - 0.01, wacc, wacc + 0.01]
        gs = [g - 0.005, g, g + 0.005]
        sens = val.sensibilidad(s, escenario, waccs, gs)
        barras = [("DCF", np.nanmin(sens.values), np.nanmax(sens.values))]
        mult = almacen.leer_multiplos()
        if mult is not None and tasa["sector"] in set(mult["industria"]):
            m_ev = float(mult.loc[mult["industria"] == tasa["sector"], "ev_ebitda"].iloc[0])
            pat_hist = m_ev * v["ebitda_base"] - v["deuda"] + v["caja"]
            pat_fwd = m_ev * v["ebitda_1"] - v["deuda"] + v["caja"]
            barras.append((f"EV/EBITDA {ui.num(m_ev, 1)}x",
                           min(pat_hist, pat_fwd), max(pat_hist, pat_fwd)))
        fig = go.Figure()
        for i, (etq, lo, hi) in enumerate(barras):
            fig.add_bar(y=[etq], x=[hi - lo], base=[lo], orientation="h", marker_color=ui.PALETA[i], width=0.4,
                        hovertemplate=f"{etq}<br>{ui.num(lo, 0)} – {ui.num(hi, 0)}<extra></extra>", showlegend=False)
        fig.add_vline(x=v["patrimonio"], line=dict(color=ui.GRIS_REF, dash="dash"), annotation_text="DCF base")
        fig.update_layout(height=360, margin=dict(l=8, r=8, t=24, b=8), separators=",.",
                          xaxis=dict(title="Valor del patrimonio (millones COP)"), yaxis=dict(automargin=True))
        ui.mostrar(fig)
        st.caption("DCF: rango con WACC ±1 p.p. y g ±0,5 p.p. Múltiplo: EV/EBITDA del sector en mercados "
                   "emergentes (Damodaran, empresas con EBITDA positivo) aplicado al EBITDA histórico y proyectado. "
                   "Una diferencia grande con el DCF obliga a revisar supuestos, no a promediar.")

    t1, t2 = st.tabs(["Proyección del FCFF", "Sensibilidad WACC × g"])
    with t1:
        st.dataframe(formato(v["tabla"], {"Crecimiento ventas", "Margen EBITDA"}), width="stretch")
    with t2:
        waccs = [round(wacc + d, 4) for d in (-0.02, -0.01, 0, 0.01, 0.02)]
        gs = [round(g + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)]
        sens = val.sensibilidad(s, escenario, waccs, gs, "por_accion")
        fig = go.Figure(go.Heatmap(
            z=sens.values, x=[ui.pct(w, 1) for w in waccs], y=[ui.pct(x, 1) for x in gs],
            colorscale=[[i / 3, c] for i, c in enumerate(ui.RAMPA_AZUL[:4])], xgap=2, ygap=2,
            text=[[ui.num(x, 0) for x in fila] for fila in sens.values], texttemplate="%{text}",
            hovertemplate="WACC %{x} · g %{y}: %{text} COP/acción<extra></extra>", colorbar=dict(thickness=10)))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=8, b=8),
                          xaxis=dict(title="WACC", type="category"), yaxis=dict(title="g", type="category"))
        ui.mostrar(fig)
        st.caption("Valor por acción (COP). Las celdas vacías son combinaciones con g ≥ WACC.")

    resumen = pd.Series({"Empresa": nombre, "Sector": tasa["sector"], "WACC": wacc, "g": g,
                         "EV": v["ev"], "Patrimonio": v["patrimonio"], "Valor por acción": v["por_accion"],
                         "Peso valor terminal": v["peso_vt"]}, name="Valor").to_frame()
    st.download_button(
        "Descargar valoración (Excel)", icon=":material/download:",
        data=comp.a_excel({"Resumen": resumen, "Históricos": historico, "Diagnóstico": diag,
                           "Escenario macro": escenario.set_index("Año"), "Proyección FCFF": v["tabla"],
                           "Sensibilidad": sens}),
        file_name="valoracion_empresa.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===================================== GUÍA ===========================================
with pasos[5]:
    st.markdown("#### Lógica de la valoración")
    st.latex(r"FCFF_t = NOPAT_t + D\&A_t - CAPEX_t - \Delta KTNO_t")
    st.latex(r"VT_n = \frac{NOPAT_{n+1}\,(1 - g/ROIC_{LP})}{WACC - g}")
    st.latex(r"EV = \sum_{t=1}^{n}\frac{FCFF_t}{(1+WACC)^t} + \frac{VT_n}{(1+WACC)^n}")
    st.markdown("""
- **Reinversión consistente:** para crecer a *g* con un retorno *ROIC* hay que reinvertir *g/ROIC* del NOPAT.
  Si ROIC = WACC, crecer no agrega valor; así se evita inflar el valor terminal.
- **Límite de g:** ninguna empresa puede crecer para siempre más rápido que la economía en términos nominales.
- **ROIC vs. WACC:** una empresa crea valor solo si su ROIC supera su costo de capital (EVA > 0).
- **Múltiplos:** sirven de contraste, no de reemplazo. Reflejan precios de empresas de otros países y tamaños.
""")
