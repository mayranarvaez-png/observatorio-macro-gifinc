"""Evaluación financiera de proyectos de inversión."""
from dataclasses import asdict, fields

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nucleo import componentes as comp
from nucleo import escenarios as esc
from nucleo import finmat, tema, ui
from nucleo import proyectos as pr

tema.encabezado("Evaluación de proyectos de inversión",
                "Construye el flujo de caja de un proyecto, descuéntalo con el **WACC del sector** y analiza su riesgo con "
                "tornado, escenarios macro y simulación Monte Carlo. Valores en millones de COP nominales; el caso inicial es un ejemplo editable.",
                seccion="Análisis financiero", chips=["VPN · TIR · TIRM · APV", "Escenarios macro", "Monte Carlo"])

# --- Definición de los campos del formulario -----------------------------------------
# (campo, etiqueta, factor de presentación, paso, ayuda)
CAMPOS = {
    "Inversión": [
        ("inversion_inicial", "Inversión inicial (millones COP)", 1, 100.0, "Activos fijos en t = 0."),
        ("vida_util", "Vida útil fiscal (años)", 1, 1, "Depreciación en línea recta."),
        ("salvamento_pct", "Valor de salvamento (% de la inversión)", 100, 5.0,
         "Valor de mercado de los activos al final del horizonte."),
        ("horizonte", "Horizonte de evaluación (años)", 1, 1, None),
    ],
    "Demanda y precio": [
        ("cantidad_inicial", "Cantidad año 1 (unidades)", 1, 10_000.0, None),
        ("elasticidad_pib", "Elasticidad de la demanda al PIB", 1, 0.1,
         "Crecimiento de cantidades = elasticidad × PIB real + crecimiento adicional."),
        ("crecimiento_adicional", "Crecimiento adicional de cantidades (%)", 100, 0.5,
         "Ganancia de participación de mercado, por encima del efecto del PIB."),
        ("precio_inicial", "Precio año 1 (COP por unidad)", 1, 500.0, None),
        ("ajuste_real_precio", "Crecimiento real del precio (%)", 100, 0.5, "Por encima del índice elegido."),
    ],
    "Costos": [
        ("costo_variable_unitario", "Costo variable año 1 (COP por unidad)", 1, 250.0, None),
        ("costos_fijos", "Costos fijos año 1 (millones COP)", 1, 50.0, "Se indexan a la inflación."),
    ],
    "Capital de trabajo": [
        ("dias_cartera", "Días de cartera", 1, 5.0, "Ventas a crédito: ingresos × días / 365."),
        ("dias_inventario", "Días de inventario", 1, 5.0, "Sobre costos variables."),
        ("dias_proveedores", "Días de proveedores", 1, 5.0, "Financiación de proveedores (resta)."),
    ],
    "Financiación e impuestos": [
        ("pct_deuda", "Financiación con deuda (% de la inversión)", 100, 5.0, None),
        ("tasa_deuda", "Tasa del crédito (% E.A.)", 100, 0.25, "Por ejemplo, IBR + spread."),
        ("plazo_deuda", "Plazo del crédito (años)", 1, 1, None),
        ("tasa_impuesto", "Tasa de impuesto de renta (%)", 100, 1.0, "Tarifa general: 35 %."),
    ],
}
SELECTORES = {
    "indexacion_precio": ("Indexación del precio", pr.INDEXACIONES,
                          "TRM si el producto se exporta o compite con importaciones."),
    "indexacion_costos": ("Indexación de los costos variables", pr.INDEXACIONES,
                          "TRM si los insumos son importados."),
    "sistema_deuda": ("Sistema de amortización", pr.SISTEMAS_DEUDA, None),
}
ENTEROS = {"vida_util", "horizonte", "plazo_deuda"}
MEMORIA = "_mem_proyecto"


def _cargar_en_estado(datos: dict) -> None:
    for grupo in CAMPOS.values():
        for campo, _, factor, _, _ in grupo:
            st.session_state[f"py_{campo}"] = (int(datos[campo]) if campo in ENTEROS
                                               else float(datos[campo]) * factor)
    for campo in SELECTORES:
        st.session_state[f"py_{campo}"] = datos[campo]
    st.session_state["py_nombre"] = datos["nombre"]
    st.session_state["py_compensar_perdidas"] = bool(datos.get("compensar_perdidas", True))
    st.session_state[MEMORIA] = datos


# Inicializa el formulario con la memoria de la sesión o con el caso de ejemplo.
if "py_inversion_inicial" not in st.session_state:
    _cargar_en_estado(st.session_state.get(MEMORIA, asdict(pr.Proyecto())))

pasos = st.tabs(["① Escenario macro", "② Supuestos del proyecto", "③ Tasa de descuento",
                 "④ Resultados", "⑤ Riesgo", "Guía"])

# ===================================== ② SUPUESTOS ===================================
with pasos[1]:
    c_nombre, c_ej = st.columns([3, 1])
    c_nombre.text_input("Nombre del proyecto", key="py_nombre")
    if c_ej.button("Restaurar ejemplo", icon=":material/restart_alt:", width="stretch"):
        _cargar_en_estado(asdict(pr.Proyecto()))
        st.rerun()
    columnas = st.columns(3)
    for i, (grupo, items) in enumerate(CAMPOS.items()):
        with columnas[i % 3].container(border=True):
            st.markdown(f"**{grupo}**")
            for campo, etiqueta, factor, paso, ayuda in items:
                if campo in ENTEROS:
                    st.number_input(etiqueta, min_value=1, max_value=30, step=int(paso), key=f"py_{campo}", help=ayuda)
                else:
                    st.number_input(etiqueta, step=float(paso), key=f"py_{campo}", help=ayuda)
            if grupo == "Demanda y precio":
                st.selectbox(*SELECTORES["indexacion_precio"][:2], key="py_indexacion_precio",
                             help=SELECTORES["indexacion_precio"][2])
            if grupo == "Costos":
                st.selectbox(*SELECTORES["indexacion_costos"][:2], key="py_indexacion_costos",
                             help=SELECTORES["indexacion_costos"][2])
            if grupo == "Financiación e impuestos":
                st.selectbox(*SELECTORES["sistema_deuda"][:2], key="py_sistema_deuda")
                st.toggle("Compensar pérdidas fiscales", key="py_compensar_perdidas",
                          help="Las pérdidas de un año reducen la base gravable de años siguientes (Art. 147 E.T.).")

datos = {"nombre": st.session_state["py_nombre"],
         "compensar_perdidas": st.session_state["py_compensar_perdidas"]}
for items in CAMPOS.values():
    for campo, _, factor, _, _ in items:
        valor = st.session_state[f"py_{campo}"]
        datos[campo] = int(valor) if campo in ENTEROS else float(valor) / factor
for campo in SELECTORES:
    datos[campo] = st.session_state[f"py_{campo}"]
st.session_state[MEMORIA] = datos
p = pr.Proyecto.desde_dict(datos)

with pasos[1]:
    cargado = comp.guardar_y_cargar_caso("py", {"tipo": "proyecto", **datos}, "caso_proyecto.json")
    if cargado:
        _cargar_en_estado({**asdict(pr.Proyecto()), **cargado})
        st.rerun()

# ===================================== ① ESCENARIO ===================================
with pasos[0]:
    st.markdown("Las cantidades crecen con el **PIB** y los precios y costos se ajustan con la **inflación** "
                "o la **TRM** de este escenario. Mueve los controles y observa cómo cambian los resultados.")
    escenario = comp.escenario_macro("py", p.horizonte)

# ===================================== ③ TASA =========================================
with pasos[2]:
    st.markdown("Elige el **sector** del proyecto: la beta de Damodaran, la prima de riesgo país y las tasas "
                "de mercado de hoy determinan el WACC automáticamente. La estructura de capital y el costo "
                "de la deuda salen de la financiación definida en el paso ②.")
    de_proyecto = p.pct_deuda / (1 - p.pct_deuda) if p.pct_deuda < 1 else 10.0
    tasa = comp.costo_de_capital_sector("py", "Food Processing", de_propio=de_proyecto, kd_propio=p.tasa_deuda,
                                        etiqueta_de=f"D/E del proyecto ({ui.pct(p.pct_deuda, 0)} deuda)",
                                        escenario=escenario)
if tasa is None:
    st.stop()
wacc, ke, ku, kd = tasa["wacc"], tasa["ke"], tasa["ku"], tasa["kd"]

# ===================================== CÁLCULO ========================================
modelo = pr.calcular(p, escenario)
ind = pr.indicadores(modelo, wacc, ke, ku, kd)


def tabla_formato(df: pd.DataFrame, dec: int = 1):
    return df.style.format(lambda x: "" if pd.isna(x) else ui.num(x, dec))


# ===================================== ④ RESULTADOS ===================================
with pasos[3]:
    viable = ind["vpn"] > 0
    st.markdown(f"#### {p.nombre}")
    (st.success if viable else st.error)(
        f"{'El proyecto crea valor' if viable else 'El proyecto destruye valor'} al WACC del sector "
        f"**{tasa['sector']}** ({ui.pct(wacc)}): VPN = **{ui.num(ind['vpn'], 1)} millones COP**.",
        icon=":material/check_circle:" if viable else ":material/cancel:")
    k = ui.tarjetas(4)
    k[0].metric("VPN (proyecto) · millones COP", ui.num(ind["vpn"], 0), border=True,
                help=f"FCLP descontado al WACC. ≈ {ui.en_palabras(ind['vpn'])}")
    k[1].metric("TIR", ui.pct(ind["tir"]) if ind["tir"] is not None else "No definida", border=True,
                delta=f"{ui.num((ind['tir'] - wacc) * 100)} p.p. sobre el WACC" if ind["tir"] is not None else None,
                delta_color="normal")
    k[2].metric("TIR modificada", ui.pct(ind["tirm"]), border=True, help="Reinversión y financiación al WACC")
    k[3].metric("Recuperación descontada", f"{ui.num(ind['recuperacion'], 1)} años"
                if ind["recuperacion"] is not None else "No se recupera", border=True)
    k = ui.tarjetas(4)
    k[0].metric("Índice de rentabilidad", ui.num(ind["ir"], 2), border=True, help="VP de flujos / VP de inversión")
    k[1].metric("APV · millones COP", ui.num(ind["apv"], 0), border=True,
                help=f"VPN al Ku ({ui.pct(ku)}) + VP de los escudos fiscales ({ui.num(ind['vp_escudos'], 0)})")
    k[2].metric("VPN del inversionista · millones COP", ui.num(ind["vpn_inversionista"], 0), border=True,
                help=f"Flujo del inversionista descontado al Ke ({ui.pct(ke)})")
    k[3].metric("TIR del inversionista", ui.pct(ind["tir_inversionista"]) if ind["tir_inversionista"] else "—",
                border=True)
    if ind["cambios_signo"] > 1:
        st.warning(f"El flujo cambia de signo {ind['cambios_signo']} veces: puede haber varias TIR. "
                   "Decide con el VPN o la TIR modificada.")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Flujo de caja libre y VPN acumulado**")
        anios = list(range(p.horizonte + 1))
        acumulado = np.cumsum(modelo["fclp"] / (1 + wacc) ** np.arange(p.horizonte + 1))
        fig = go.Figure()
        fig.add_bar(x=anios, y=modelo["fclp"], name="Flujo de caja libre",
                    marker_color=[ui.NEG if v < 0 else ui.POS for v in modelo["fclp"]],
                    hovertemplate="Año %{x}: %{y:,.1f}<extra>FCLP</extra>")
        fig.add_scatter(x=anios, y=acumulado, name="VPN acumulado", mode="lines+markers",
                        line=dict(color=ui.PALETA[2], width=2), marker=dict(size=8),
                        hovertemplate="Año %{x}: %{y:,.1f}<extra>VPN acumulado</extra>")
        fig.add_hline(y=0, line=dict(color=ui.GRIS_REF, width=1))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=10, b=8), separators=",.",
                          xaxis=dict(title="Año", dtick=1), yaxis=dict(title="Millones COP"),
                          legend=dict(orientation="h", y=1.1), hovermode="x unified")
        ui.mostrar(fig)
    with g2:
        st.markdown("**Perfil del VPN: ¿a qué tasa deja de ser viable?**")
        tasas = np.linspace(0, max(0.6, (ind["tir"] or 0.3) * 1.5), 61)
        fig = go.Figure()
        fig.add_scatter(x=tasas * 100, y=[finmat.vpn(r, modelo["fclp"]) for r in tasas], mode="lines",
                        name="VPN", line=dict(color=ui.AZUL, width=2),
                        hovertemplate="Tasa %{x:.1f} %: VPN %{y:,.1f}<extra></extra>")
        fig.add_hline(y=0, line=dict(color=ui.GRIS_REF, width=1))
        fig.add_vline(x=wacc * 100, line=dict(color=ui.ROJO, dash="dash"),
                      annotation_text=f"WACC {ui.pct(wacc, 1)}", annotation_position="top right",
                      annotation_yshift=-24)
        if ind["tir"] is not None:
            fig.add_vline(x=ind["tir"] * 100, line=dict(color=ui.PALETA[2], dash="dot"),
                          annotation_text=f"TIR {ui.pct(ind['tir'], 1)}", annotation_position="bottom left")
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=10, b=8), separators=",.",
                          xaxis=dict(title="Tasa de descuento (%)"), yaxis=dict(title="VPN (millones COP)"),
                          showlegend=False)
        ui.mostrar(fig)

    t1, t2, t3 = st.tabs(["Flujo de caja", "Estado de resultados", "Tabla del crédito"])
    with t1:
        st.dataframe(tabla_formato(modelo["flujos"]), width="stretch")
    with t2:
        st.dataframe(tabla_formato(modelo["resultados"]), width="stretch")
    with t3:
        st.dataframe(tabla_formato(modelo["deuda"].set_index("t")), width="stretch")
    resumen = pd.DataFrame({"Indicador": ["VPN", "TIR", "TIRM", "Recuperación descontada (años)",
                                          "Índice de rentabilidad", "APV", "VPN inversionista",
                                          "TIR inversionista", "WACC", "Ke", "Ku", "Sector"],
                            "Valor": [ind["vpn"], ind["tir"], ind["tirm"], ind["recuperacion"], ind["ir"],
                                      ind["apv"], ind["vpn_inversionista"], ind["tir_inversionista"],
                                      wacc, ke, ku, tasa["sector"]]})
    st.download_button(
        "Descargar modelo completo (Excel)", icon=":material/download:",
        data=comp.a_excel({"Resumen": resumen.set_index("Indicador"),
                           "Supuestos": pd.Series(datos, name="Valor").to_frame(),
                           "Escenario macro": escenario.set_index("Año"),
                           "Flujo de caja": modelo["flujos"], "Estado de resultados": modelo["resultados"],
                           "Crédito": modelo["deuda"].set_index("t")}),
        file_name="evaluacion_proyecto.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===================================== ⑤ RIESGO =======================================
with pasos[4]:
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Análisis de sensibilidad (tornado)**")
        variacion = st.slider("Variación de cada supuesto (±%)", 5, 30, 10, 5, key="py_var_tornado") / 100
        tor = pr.tornado(p, escenario, wacc, variacion)
        base = tor.attrs["vpn_base"]
        fig = go.Figure()
        fig.add_bar(y=tor["Variable"], x=tor["VPN con −"] - base, base=base, orientation="h",
                    name=f"−{variacion:.0%}", marker_color=ui.NEG,
                    hovertemplate="%{y}: VPN %{x:,.1f}<extra>−</extra>")
        fig.add_bar(y=tor["Variable"], x=tor["VPN con +"] - base, base=base, orientation="h",
                    name=f"+{variacion:.0%}", marker_color=ui.POS,
                    hovertemplate="%{y}: VPN %{x:,.1f}<extra>+</extra>")
        fig.add_vline(x=base, line=dict(color=ui.GRIS_REF, width=1))
        fig.update_layout(barmode="overlay", height=380, margin=dict(l=8, r=8, t=10, b=40), separators=",.",
                          xaxis=dict(title="VPN (millones COP)"), legend=dict(orientation="h", y=-0.2, x=0))
        ui.mostrar(fig)
        st.caption("La barra más larga es la variable que más mueve el VPN: ahí conviene invertir en mejor información.")
    with r2:
        st.markdown("**Escenarios macroeconómicos**")
        guardadas = st.session_state.get("_mem_anclas")
        anclas = esc.Anclas(**guardadas) if guardadas else esc.anclas_por_defecto()
        filas = []
        for nombre in esc.ESCENARIOS:
            e_tab = esc.construir(anclas, p.horizonte, nombre)
            m_e = pr.calcular(p, e_tab)
            filas.append({"Escenario": nombre, "VPN": finmat.vpn(wacc, m_e["fclp"]), "TIR": finmat.tir(m_e["fclp"])})
        df_esc = pd.DataFrame(filas)
        fig = go.Figure(go.Bar(x=df_esc["Escenario"], y=df_esc["VPN"],
                               marker_color=[ui.AZUL, ui.ROJO, ui.VERDE],
                               text=[ui.num(v, 0) for v in df_esc["VPN"]], textposition="outside",
                               hovertemplate="%{x}: VPN %{y:,.1f}<extra></extra>"))
        fig.add_hline(y=0, line=dict(color=ui.GRIS_REF, width=1))
        fig.update_layout(height=300, margin=dict(l=8, r=8, t=24, b=8), separators=",.",
                          yaxis=dict(title="VPN (millones COP)"))
        ui.mostrar(fig)
        pe = pr.punto_equilibrio_precio(p, escenario, wacc)
        if pe:
            st.metric("Precio de equilibrio (VPN = 0)", f"{ui.num(pe, 0)} COP",
                      delta=f"{ui.pct(pe / p.precio_inicial - 1, 1)} frente al precio supuesto",
                      delta_color="off", border=True,
                      help="Precio del año 1 con el que el proyecto apenas recupera el WACC.")

    st.divider()
    st.markdown("**Simulación de Monte Carlo**")
    st.caption("Cada supuesto sigue una distribución triangular: el valor actual es el más probable, y tú "
               "defines cuánto puede bajar o subir. El resultado es la distribución del VPN.")
    s = st.columns(4)
    rangos = {
        "precio_inicial": s[0].slider("Precio (% mín, máx)", -50, 50, (-15, 10), key="mc_precio"),
        "cantidad_inicial": s[1].slider("Cantidad (% mín, máx)", -50, 50, (-25, 15), key="mc_cantidad"),
        "costo_variable_unitario": s[2].slider("Costo variable (% mín, máx)", -50, 50, (-5, 15), key="mc_cv"),
        "inversion_inicial": s[3].slider("Inversión (% mín, máx)", -50, 50, (-5, 20), key="mc_inv"),
    }
    rangos = {k: (v[0] / 100, v[1] / 100) for k, v in rangos.items()}
    s2 = st.columns([2, 1, 1])
    rho = s2[0].slider("Correlación precio–cantidad", -0.9, 0.9, -0.3, 0.1, key="mc_rho",
                       help="Negativa: si sube el precio, se vende menos. Ignorar la correlación subestima el riesgo.")
    n_sim = s2[1].select_slider("Simulaciones", [500, 1000, 2000, 5000], value=1000, key="mc_n")
    if s2[2].button("Simular", type="primary", icon=":material/casino:", width="stretch"):
        with st.spinner("Simulando…"):
            st.session_state["mc_resultado"] = pr.montecarlo(p, escenario, wacc, rangos, rho, n_sim)
    sim = st.session_state.get("mc_resultado")
    if sim is not None:
        v = sim["VPN"]
        m = ui.tarjetas(5)
        m[0].metric("VPN esperado", ui.num(v.mean(), 0), border=True)
        m[1].metric("Probabilidad de VPN < 0", ui.pct((v < 0).mean(), 1), border=True)
        m[2].metric("Percentil 5", ui.num(v.quantile(0.05), 0), border=True, help="VaR al 95 % del VPN")
        m[3].metric("Mediana", ui.num(v.median(), 0), border=True)
        m[4].metric("Percentil 95", ui.num(v.quantile(0.95), 0), border=True)
        fig = go.Figure(go.Histogram(x=v, nbinsx=50, marker_color=ui.AZUL, marker_line=dict(width=1, color="white"),
                                     hovertemplate="VPN %{x:,.0f}: %{y} simulaciones<extra></extra>"))
        fig.add_vline(x=0, line=dict(color=ui.ROJO, width=2), annotation_text="VPN = 0", annotation_position="top left")
        fig.add_vline(x=v.mean(), line=dict(color=ui.GRIS_REF, dash="dash"), annotation_text="Media", annotation_position="top right")
        fig.update_layout(height=320, margin=dict(l=8, r=8, t=24, b=8), separators=",.",
                          xaxis=dict(title="VPN (millones COP)"), yaxis=dict(title="Simulaciones"), bargap=0.02)
        ui.mostrar(fig)
        st.caption("Si cambias supuestos, vuelve a pulsar **Simular** para actualizar la distribución.")

# ===================================== GUÍA ===========================================
with pasos[5]:
    st.markdown("""
#### Cómo usar este módulo
1. **Escenario macro:** define cómo evolucionan el PIB, la inflación y la TRM.
2. **Supuestos:** inversión, demanda, precios, costos, capital de trabajo y financiación.
3. **Tasa de descuento:** elige el sector; el WACC se calcula con su beta.
4. **Resultados:** VPN, TIR, flujos y estados proyectados.
5. **Riesgo:** sensibilidad, escenarios y Monte Carlo.

#### Dos flujos, dos tasas
""")
    st.latex(r"FCLP_t = EBIT_t(1-t) + Dep_t - CAPEX_t - \Delta KTNO_t \;\;\rightarrow\;\; \text{se descuenta al WACC}")
    st.latex(r"FCI_t = FCLP_t - Int_t(1-t) - Abono_t + Desembolso_t \;\;\rightarrow\;\; \text{se descuenta al } K_e")
    st.markdown("""
- El **FCLP** mide si el proyecto es bueno por sí mismo; el **FCI** mide qué recibe el inversionista después de pagar la deuda.
- El **APV** separa el valor del negocio (descontado al costo del patrimonio sin deuda, *Ku*) del valor
  que aporta la deuda (escudo fiscal). Es más exacto que el WACC constante cuando la deuda se amortiza.
- **Cuidado con la TIR:** si el flujo cambia de signo más de una vez puede haber varias TIR. El VPN es el criterio principal.
- **Coherencia:** flujos nominales en pesos se descuentan con tasas nominales en pesos. Este módulo lo garantiza:
  la inflación del escenario mueve los precios y el WACC se convierte a COP con la paridad de Fisher.
""")
