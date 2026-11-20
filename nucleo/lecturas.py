"""Interpretaciones automáticas, con reglas explícitas, para acompañar tablas y gráficos.

Cada función devuelve (viñetas, tono). Describen lo que muestran los datos y sus límites; **no son
recomendaciones de compra o venta**. El tono ('ok', 'neutro', 'alerta', 'riesgo') cambia el color de la tarjeta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ui

NOTA_ESTADISTICA = ("Análisis estadístico con datos históricos de Yahoo Finance; el pasado no garantiza resultados "
                    "futuros y esto no es una recomendación de inversión.")


def _nombre(t: str, perfiles: dict | None) -> str:
    p = (perfiles or {}).get(t)
    return f"{t}" if not p or not p.get("nombre") else f"{p['nombre'].title()} ({t})"


def _mejor(serie: pd.Series, mayor: bool = True):
    s = serie.dropna()
    if s.empty:
        return None, None
    t = s.idxmax() if mayor else s.idxmin()
    return t, float(s[t])


# =============================== Comparador =========================================
def comparador(est: pd.DataFrame, corr: pd.DataFrame | None, perfiles: dict, bench: str,
               base: str) -> tuple[list[str], str]:
    pts, tono = [], "neutro"
    if est.empty:
        return pts, tono
    n = len(est)
    t, v = _mejor(est["Sharpe"])
    if t:
        pts.append(f"**Mejor retorno ajustado por riesgo:** {_nombre(t, perfiles)}, con Sharpe de {ui.num(v)} "
                   f"(retorno anual {ui.pct(est.loc[t, 'Retorno anual'])} con volatilidad de {ui.pct(est.loc[t, 'Volatilidad'])}).")
    tv, vv = _mejor(est["Volatilidad"], mayor=False)
    if tv and n > 1:
        pts.append(f"**Menor volatilidad:** {_nombre(tv, perfiles)} ({ui.pct(vv)} anual); la más alta es "
                   f"{ui.pct(est['Volatilidad'].max())}, es decir {ui.num(est['Volatilidad'].max() / max(vv, 1e-9), 1)} veces más.")
    tc, vc = _mejor(est["Caída máxima"], mayor=False)
    if tc:
        pts.append(f"**Mayor caída desde un máximo:** {_nombre(tc, perfiles)} ({ui.pct(vc)}). Es la pérdida que un "
                   "inversionista que hubiera comprado en el pico habría soportado en el periodo.")
        if vc < -0.5:
            tono = "alerta"
    if "Beta" in est:
        altos = est.index[est["Beta"] > 1.2].tolist()
        bajos = est.index[est["Beta"] < 0.8].tolist()
        if altos:
            pts.append(f"**Amplifican el mercado** (beta > 1,2 frente a {bench}): {', '.join(altos)}. "
                       "Suben y bajan más que el índice de referencia.")
        if bajos:
            pts.append(f"**Defensivas** (beta < 0,8): {', '.join(bajos)}. Se mueven menos que el índice.")
        pos = est.index[est["Alfa anual"] > 0.02].tolist()
        if pos:
            pts.append(f"**Alfa anual mayor a 2 %** frente a {bench}: {', '.join(pos)}. Con series cortas el alfa "
                       "es muy inestable; no debe leerse como habilidad persistente.")
    if corr is not None and n >= 2:
        m = corr.to_numpy()[np.triu_indices(n, 1)]
        c = float(np.nanmean(m))
        nivel = "alta" if c > 0.6 else ("moderada" if c > 0.3 else "baja")
        pts.append(f"**Correlación promedio entre las acciones:** {ui.num(c)} ({nivel}). "
                   + ("Poca diversificación entre ellas: tienden a moverse juntas." if c > 0.6 else
                      "Combinarlas reduce el riesgo frente a mantener una sola." if c < 0.5 else
                      "Hay algo de diversificación, pero se concentra en el mismo ciclo de mercado."))
        if c > 0.7:
            tono = "alerta"
    if len({p.get("moneda") for p in perfiles.values() if p}) > 1 and base != "LOCAL":
        pts.append(f"Las series se convirtieron a **{base}**: el retorno incluye el efecto del tipo de cambio.")
    return pts, tono


def valoracion(tabla: pd.DataFrame, perfiles: dict) -> tuple[list[str], str]:
    """`tabla` con columnas P/E, P/B, EV/EBITDA, Dividendo, ROE, Margen neto, D/E (fracciones)."""
    pts, tono = [], "neutro"
    pe = tabla["P/E"].where((tabla["P/E"] > 0) & (tabla["P/E"] < 300))
    t, v = _mejor(pe, mayor=False)
    if t and pe.notna().sum() > 1:
        pts.append(f"**Múltiplo P/E más bajo:** {_nombre(t, perfiles)} ({ui.num(v, 1)}x). Un P/E bajo puede indicar "
                   "precio atractivo, pero también bajas expectativas de crecimiento o utilidades extraordinarias.")
    t, v = _mejor(tabla["Dividendo"])
    if t and tabla["Dividendo"].notna().sum() > 1:
        pts.append(f"**Mayor rentabilidad por dividendo:** {_nombre(t, perfiles)} ({ui.pct(v)}). Conviene mirar si el "
                   "pago es sostenible con el flujo de caja (razón de pago y deuda).")
    t, v = _mejor(tabla["ROE"])
    if t and tabla["ROE"].notna().sum() > 1:
        pts.append(f"**Mayor ROE:** {_nombre(t, perfiles)} ({ui.pct(v)}). Un ROE alto con deuda alta puede reflejar apalancamiento, no solo eficiencia.")
    t, v = _mejor(tabla["D/E"])
    if t and v is not None and v > 1.5:
        pts.append(f"**Mayor apalancamiento:** {_nombre(t, perfiles)} con deuda/patrimonio de {ui.pct(v, 0)}. "
                   "Eso aumenta la sensibilidad de la utilidad a la tasa de interés y al ciclo.")
        tono = "alerta"
    sectores = {p.get("sector") for p in perfiles.values() if p and p.get("sector")}
    if len(sectores) > 1:
        pts.append("Las acciones son de **sectores distintos** (" + ", ".join(sorted(sectores)) + "): los múltiplos "
                   "solo son comparables dentro de un mismo sector.")
        tono = "alerta"
    avisos = [f"{_nombre(t, perfiles)}: {b}" for t, p in perfiles.items() if p for b in p.get("banderas", [])]
    if avisos:
        pts.append("**Calidad de datos:** " + " · ".join(avisos))
        tono = "alerta"
    return pts, tono


# =============================== Ficha de una acción ================================
def accion(t: str, fila: pd.Series, perfil: dict | None, bench: str, rf: float) -> tuple[list[str], str]:
    pts, tono = [], "neutro"
    pts.append(f"En el periodo, rindió **{ui.pct(fila['Retorno anual'])} anual** con una volatilidad de "
               f"**{ui.pct(fila['Volatilidad'])}**: Sharpe de {ui.num(fila['Sharpe'])} frente a una tasa libre de riesgo de {ui.pct(rf)}.")
    if fila["Sharpe"] < 0:
        pts.append("El retorno **no compensó** el riesgo asumido frente a la tasa libre.")
        tono = "riesgo"
    pts.append(f"La peor caída desde un máximo fue **{ui.pct(fila['Caída máxima'])}**; en una semana mala (1 de cada 20) "
               f"la pérdida fue de al menos {ui.pct(fila['VaR 95 % (sem.)'])}, y en promedio {ui.pct(fila['CVaR 95 % (sem.)'])} dentro de ese 5 % peor.")
    if "Beta" in fila and pd.notna(fila["Beta"]):
        forma = "más" if fila["Beta"] > 1.05 else ("menos" if fila["Beta"] < 0.95 else "casi igual")
        pts.append(f"Su beta frente a {bench} es **{ui.num(fila['Beta'])}**: se mueve {forma} que el índice. "
                   f"La correlación es {ui.num(fila['Correlación'])} (R² de {ui.pct(fila['R²'], 0)}): "
                   + ("el índice explica poco de su comportamiento, así que el beta es poco fiable."
                      if fila["R²"] < 0.2 else "el índice explica una parte relevante de su comportamiento."))
    if perfil:
        if perfil.get("pe") and 0 < perfil["pe"] < 300:
            pts.append(f"Cotiza a **{ui.num(perfil['pe'], 1)} veces** utilidades (P/E)"
                       + (f" y {ui.num(perfil['pb'], 2)} veces su valor en libros." if perfil.get("pb") and perfil["pb"] >= 0.05 else "."))
        if perfil.get("banderas"):
            pts.append("**Dato dudoso:** " + " ".join(perfil["banderas"]))
            tono = "alerta" if tono == "neutro" else tono
    return pts, tono


# =============================== Portafolio =========================================
def portafolio(res: dict, tickers: list[str], w: np.ndarray, contrib: np.ndarray, est_activos: pd.DataFrame,
               est_bench: pd.Series | None, bench: str, rf: float) -> tuple[list[str], str]:
    pts, tono = [], "neutro"
    pts.append(f"El portafolio rindió **{ui.pct(res['Retorno anual'])} anual** con volatilidad de "
               f"**{ui.pct(res['Volatilidad'])}** (Sharpe {ui.num(res['Sharpe'])}), entre "
               f"{ui.fecha_txt(res['desde'])} y {ui.fecha_txt(res['hasta'])}. Es el periodo común a todos los activos.")
    vol_prom = float(w @ est_activos.loc[tickers, "Volatilidad"].to_numpy())
    reduccion = 1 - res["Volatilidad"] / vol_prom if vol_prom > 0 else 0
    pts.append(f"**Diversificación:** la volatilidad del portafolio es {ui.pct(res['Volatilidad'])}, frente a "
               f"{ui.pct(vol_prom)} del promedio ponderado de sus activos: una reducción de {ui.pct(max(reduccion, 0), 0)}. "
               f"Ratio de diversificación {ui.num(res['ratio_diversificacion'])} y {ui.num(res['n_efectivo'], 1)} posiciones efectivas "
               f"de {len(tickers)}.")
    if res["n_efectivo"] < 0.6 * len(tickers):
        pts.append("El portafolio está **concentrado**: pocas posiciones concentran la mayor parte del peso.")
        tono = "alerta"
    i = int(np.argmax(contrib))
    if contrib[i] > w[i] + 0.10:
        pts.append(f"**{tickers[i]}** pesa {ui.pct(w[i], 0)} pero aporta {ui.pct(contrib[i], 0)} del riesgo: "
                   "es la posición que más pesa en la volatilidad.")
        tono = "alerta"
    mejor = est_activos.loc[tickers, "Sharpe"].idxmax()
    if res["Sharpe"] < est_activos.loc[mejor, "Sharpe"]:
        pts.append(f"Un activo individual tuvo mejor Sharpe que el portafolio: {mejor} ({ui.num(est_activos.loc[mejor, 'Sharpe'])} "
                   f"frente a {ui.num(res['Sharpe'])}), con volatilidad de {ui.pct(est_activos.loc[mejor, 'Volatilidad'])} "
                   f"frente a {ui.pct(res['Volatilidad'])} del portafolio. Mirar solo el mejor resultado pasado "
                   "concentra el riesgo en una sola posición.")
    if est_bench is not None and pd.notna(res.get("Beta")):
        pts.append(f"Frente a {bench}: beta **{ui.num(res['Beta'])}**, correlación {ui.num(res['Correlación'])}, "
                   f"alfa anual {ui.pct(res['Alfa anual'])}. El índice rindió {ui.pct(est_bench['Retorno anual'])} "
                   f"con volatilidad de {ui.pct(est_bench['Volatilidad'])}.")
    if res["Caída máxima"] < -0.35:
        pts.append(f"**Caída máxima de {ui.pct(res['Caída máxima'])}:** el portafolio sufrió una pérdida profunda en el periodo.")
        tono = "riesgo"
    return pts, tono


# =============================== Macro y costo de capital ===========================
def ke(r: dict, s, fuente_beta: str, tes10: float | None) -> tuple[list[str], str]:
    """Lectura de la descomposición del Ke (r = resultado de cc.calcular, s = Supuestos)."""
    pts, tono = [], "neutro"
    total = r["ke_usd"]
    comp = {"tasa libre": s.rf, "prima de mercado (β·ERP)": r["prima_mercado"], "riesgo país": r["prima_pais"]}
    grande = max(comp, key=comp.get)
    pts.append(f"El Ke en dólares es **{ui.pct(total)}**: {ui.pct(s.rf / total, 0)} es tasa libre de riesgo, "
               f"{ui.pct(r['prima_mercado'] / total, 0)} prima de mercado y {ui.pct(r['prima_pais'] / total, 0)} riesgo país. "
               f"El componente mayor es la **{grande}**.")
    pts.append(f"El riesgo país (CRP de {ui.pct(s.crp)}) pesa más en el Ke que la propia prima de mercado cuando β < "
               f"{ui.num(s.crp / s.erp)}; por eso la elección de CRP y de λ (aditivo o proporcional a β) es la que más mueve el resultado."
               if s.crp > r["prima_mercado"] else
               f"La prima de mercado ajustada por beta ({ui.pct(r['prima_mercado'])}) supera al riesgo país ({ui.pct(s.crp)}).")
    pts.append(f"Al pasar a pesos por paridad de Fisher, el Ke queda en **{ui.pct(r['ke_cop'])}** "
               f"({'+' if r['ke_cop'] >= r['ke_usd'] else '−'}{ui.num(abs(r['ke_cop'] - r['ke_usd']) * 100)} p.p.): "
               "el diferencial de inflación esperada entre Colombia y EE. UU.")
    if tes10 is not None:
        if r["ke_cop"] < tes10:
            pts.append(f"**Alerta de coherencia:** el Ke en pesos ({ui.pct(r['ke_cop'])}) es menor que el TES 10A "
                       f"({ui.pct(tes10)}). El patrimonio no puede costar menos que la deuda soberana; revisa la inflación "
                       "usada en Fisher o el CRP.")
            tono = "riesgo"
        else:
            pts.append(f"Prima sobre el TES 10A: **{ui.num((r['ke_cop'] - tes10) * 100)} p.p.**, razonable frente al riesgo de la industria.")
    pts.append(f"La beta usada viene de: {fuente_beta}.")
    return pts, tono
