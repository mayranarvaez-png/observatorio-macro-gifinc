"""Metodología, fuentes, estado de actualización y referencias."""
import pandas as pd
import streamlit as st

from nucleo import almacen, damodaran, tema
from nucleo.catalogo import SERIES

tema.encabezado("Metodología y fuentes", "Cómo se calculan los indicadores, de dónde sale cada dato y qué límites tiene.", seccion="Referencia")

st.markdown("""
### Propósito
Herramienta del grupo de investigación para **monitorear la coyuntura macroeconómica de Colombia**
y **estimar el costo de capital** con supuestos trazables. Cada cifra conserva su fuente, su
fecha de corte y el método de cálculo, para que pueda citarse en artículos, tesis y clases.

### Principios
1. **Fuentes oficiales y públicas.** BanRep, DANE (vía OCDE), Superfinanciera (datos.gov.co),
   Reserva Federal (FRED), Banco Mundial, Aswath Damodaran (NYU Stern) y estados financieros NIIF
   de la Superintendencia de Sociedades (datos.gov.co), consultados en línea por empresa.
2. **Datos locales y versionables.** La descarga se hace aparte (`actualizar_datos.py`) y queda
   en archivos CSV/JSON dentro de `datos/`. El tablero no depende de que las APIs respondan.
3. **Supuestos explícitos.** El usuario elige y ve cada supuesto del costo de capital. Los
   parámetros de Damodaran tienen historial por versión.
4. **Sin cifras inventadas.** Si una fuente falla, se muestra el último dato válido y se marca el error.
""")

st.subheader("Estado de las series")
registro = almacen.leer_registro()
filas = []
for s in SERIES:
    reg = registro.get(s.id, {})
    filas.append({
        "Serie": s.nombre, "Bloque": s.bloque, "Fuente": s.fuente, "Frecuencia": s.frecuencia,
        "Unidad": s.unidad, "Último dato": reg.get("ultimo_dato", "—"),
        "Descargada": reg.get("actualizado", "—"),
        "Estado": "OK" if reg.get("estado") == "ok" else ("Error" if reg.get("estado") else "Pendiente"),
        "ID": s.id,
    })
dam = registro.get("damodaran", {})
filas.append({"Serie": "Betas, ERP, CRP e impuestos", "Bloque": "Costo de capital",
              "Fuente": "Damodaran (NYU Stern)", "Frecuencia": "Anual / semestral", "Unidad": "varias",
              "Último dato": dam.get("ultimo_dato", "—"), "Descargada": dam.get("actualizado", "—"),
              "Estado": "OK" if dam.get("estado") == "ok" else ("Error" if dam else "Pendiente"),
              "ID": "damodaran"})
st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")

st.subheader("Cálculos derivados")
st.markdown("""
| Indicador | Método |
|---|---|
| PIB real – variación anual | (PIBₜ / PIBₜ₋₄ − 1) × 100 sobre el PIB trimestral en volumen encadenado y desestacionalizado |
| Inflación EE. UU. | (CPIₜ / CPIₜ₋₁₂ − 1) × 100 |
| Diferencial TES − Tesoro | Promedio mensual del TES 10A (cero cupón) − promedio mensual del DGS10 |
| Tasa real ex post (Coyuntura) | (1 + TPM) / (1 + IPC anual) − 1 |
| Pendiente de la curva | TES 10A − TES 1A |
""")

st.subheader("Costo de capital")
st.markdown("""
- **Modelo:** CAPM global con prima de riesgo país (Damodaran). Beta reapalancada con Hamada.
- **Tasa libre de riesgo:** Tesoro de EE. UU. a 10 años (último dato o promedio de 12 meses).
- **ERP madura:** prima implícita del S&P 500 neta del spread de default de EE. UU. (Damodaran).
- **CRP:** spread de default soberano (por calificación o por CDS) × volatilidad relativa
  acciones/bonos (Damodaran).
- **Conversión a COP:** paridad de Fisher con inflación esperada de largo plazo.
- **WACC:** ponderaciones a valor de mercado según D/E; tasa marginal de renta del 35 %.
- **Beta por industria:** se puede elegir entre Damodaran (emergentes, global, EE. UU.), un beta propio de
  Latinoamérica estimado con acciones de Yahoo Finance, o un combinado de ambos. La comparación, el peso del
  combinado y los límites están en la página «Beta propio vs Damodaran».

**Extensiones previstas (Fase 2):** comparación con Godfrey-Espinosa (1996), D-CAPM de Estrada (2002)
y el modelo de Lessard (1996), además de una serie histórica del WACC por sector.
""")
st.caption(f"Archivos de Damodaran: {damodaran.URL_DATOS}")

st.subheader("Referencias")
st.markdown("""
- Damodaran, A. (2024). *Country Risk: Determinants, Measures and Implications – The 2024 Edition*. SSRN.
- Damodaran, A. (2025). *Equity Risk Premiums (ERP): Determinants, Estimation, and Implications*. SSRN.
- Hamada, R. S. (1972). The effect of the firm's capital structure on the systematic risk of common
  stocks. *The Journal of Finance, 27*(2), 435–452.
- Fisher, I. (1930). *The Theory of Interest*. Macmillan.
- Godfrey, S., & Espinosa, R. (1996). A practical approach to calculating costs of equity for
  investments in emerging markets. *Journal of Applied Corporate Finance, 9*(3), 80–90.
- Estrada, J. (2002). Systematic risk in emerging markets: the D-CAPM. *Emerging Markets Review, 3*(4), 365–379.
- Lessard, D. (1996). Incorporating country risk in the valuation of offshore projects.
  *Journal of Applied Corporate Finance, 9*(3), 52–63.
""")
st.caption("Verifica siempre las cifras críticas contra la fuente oficial antes de publicarlas.")
