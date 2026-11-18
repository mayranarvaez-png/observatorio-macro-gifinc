"""Valoración de empresas por flujo de caja libre descontado (FCFF al WACC).

Valores en millones de COP nominales.

    NOPAT       = EBIT · (1 − t)
    FCFF        = NOPAT + D&A − CAPEX − ΔKTNO
    Valor terminal (Gordon con reinversión consistente):
        FCFF_{n+1} = NOPAT_{n+1} · (1 − g / ROIC_LP)
        VT_n       = FCFF_{n+1} / (WACC − g)
    Valor empresa (EV) = Σ FCFF_t/(1+WACC)^t + VT_n/(1+WACC)^n
    Valor patrimonio   = EV − deuda financiera + caja

La reinversión consistente evita el error clásico de suponer crecimiento sin
inversión: para crecer a g con un retorno ROIC hay que reinvertir g/ROIC del NOPAT.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

def _pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


RUBROS = [
    "Ventas",
    "Costo de ventas",
    "Gastos operacionales (sin D&A)",
    "Depreciación y amortización",
    "CAPEX",
    "Capital de trabajo neto operativo (KTNO)",
    "Activo fijo neto",
    "Deuda financiera",
    "Caja e inversiones temporales",
]


def historico_ejemplo() -> pd.DataFrame:
    """Estados financieros de una empresa ficticia, para práctica en clase."""
    anios = [2021, 2022, 2023, 2024, 2025]
    ventas = np.array([52_000, 57_500, 63_800, 68_900, 74_200], dtype=float)
    datos = {
        "Ventas": ventas,
        "Costo de ventas": ventas * np.array([0.615, 0.622, 0.618, 0.610, 0.607]),
        "Gastos operacionales (sin D&A)": ventas * np.array([0.215, 0.212, 0.218, 0.214, 0.211]),
        "Depreciación y amortización": ventas * 0.031,
        "CAPEX": ventas * np.array([0.052, 0.048, 0.055, 0.050, 0.049]),
        "Capital de trabajo neto operativo (KTNO)": ventas * np.array([0.152, 0.149, 0.155, 0.151, 0.148]),
        "Activo fijo neto": ventas * np.array([0.30, 0.295, 0.30, 0.302, 0.298]),
        "Deuda financiera": np.array([15_500, 16_800, 18_200, 18_900, 19_400], dtype=float),
        "Caja e inversiones temporales": np.array([3_100, 3_400, 3_900, 4_200, 4_600], dtype=float),
    }
    return pd.DataFrame(datos, index=anios).T.round(0)


@dataclass
class SupuestosValoracion:
    nombre: str = "Alimentos del Valle S.A. (caso ficticio)"
    horizonte: int = 5
    elasticidad_pib: float = 1.1
    crecimiento_adicional: float = 0.0
    margen_ebitda_objetivo: float | None = None   # None = mantener el último margen
    dya_ventas: float | None = None               # None = promedio histórico
    capex_ventas: float | None = None
    ktno_ventas: float | None = None
    tasa_impuesto: float = 0.35
    g_terminal: float = 0.045
    roic_largo_plazo: float | None = None          # None = igual al WACC (sin creación de valor perpetua)
    medio_periodo: bool = False
    acciones_millones: float = 120.0
    historico: pd.DataFrame = field(default_factory=historico_ejemplo)


def diagnostico(h: pd.DataFrame, tasa_impuesto: float) -> pd.DataFrame:
    v = h.loc["Ventas"]
    ebitda = v - h.loc["Costo de ventas"] - h.loc["Gastos operacionales (sin D&A)"]
    ebit = ebitda - h.loc["Depreciación y amortización"]
    nopat = ebit * (1 - tasa_impuesto)
    capital = h.loc["Activo fijo neto"] + h.loc["Capital de trabajo neto operativo (KTNO)"]
    capital_inicial = capital.shift(1)
    d = pd.DataFrame({
        "Crecimiento ventas": v.pct_change(),
        "Margen bruto": (v - h.loc["Costo de ventas"]) / v,
        "Margen EBITDA": ebitda / v,
        "Margen EBIT": ebit / v,
        "D&A / ventas": h.loc["Depreciación y amortización"] / v,
        "CAPEX / ventas": h.loc["CAPEX"] / v,
        "KTNO / ventas": h.loc["Capital de trabajo neto operativo (KTNO)"] / v,
        "ROIC (sobre capital inicial)": nopat / capital_inicial,
        "Deuda / EBITDA (veces)": h.loc["Deuda financiera"] / ebitda,
    }).T
    d.attrs.update(ebitda=ebitda, nopat=nopat, capital=capital)
    return d


def proyectar(s: SupuestosValoracion, escenario: pd.DataFrame, wacc: float) -> dict:
    h = s.historico
    diag = diagnostico(h, s.tasa_impuesto)
    n = s.horizonte
    esc = escenario.iloc[:n]
    pib = esc["PIB real (%)"].to_numpy() / 100
    infl = esc["Inflación Colombia (%)"].to_numpy() / 100

    ultimo = h.columns[-1]
    v0 = h.loc["Ventas", ultimo]
    margen0 = diag.loc["Margen EBITDA", ultimo]
    margen_obj = margen0 if s.margen_ebitda_objetivo is None else s.margen_ebitda_objetivo
    dya = s.dya_ventas if s.dya_ventas is not None else diag.loc["D&A / ventas"].mean()
    capex = s.capex_ventas if s.capex_ventas is not None else diag.loc["CAPEX / ventas"].mean()
    ktno_v = s.ktno_ventas if s.ktno_ventas is not None else diag.loc["KTNO / ventas"].mean()
    ktno0 = h.loc["Capital de trabajo neto operativo (KTNO)", ultimo]

    crec = (1 + s.elasticidad_pib * pib + s.crecimiento_adicional) * (1 + infl) - 1
    ventas = v0 * np.cumprod(1 + crec)
    margenes = margen0 + (margen_obj - margen0) * np.arange(1, n + 1) / n
    ebitda = ventas * margenes
    da = ventas * dya
    ebit = ebitda - da
    nopat = ebit * (1 - s.tasa_impuesto)
    capex_v = ventas * capex
    ktno = ventas * ktno_v
    delta_kt = np.diff(np.r_[ktno0, ktno])
    fcff = nopat + da - capex_v - delta_kt
    reinversion = capex_v - da + delta_kt

    t = np.arange(1, n + 1) - (0.5 if s.medio_periodo else 0.0)
    factor = 1 / (1 + wacc) ** t
    vp_fcff = fcff * factor

    roic_lp = wacc if s.roic_largo_plazo is None else s.roic_largo_plazo
    g = s.g_terminal
    nopat_n1 = nopat[-1] * (1 + g)
    tasa_reinv_lp = g / roic_lp if roic_lp > 0 else 0.0
    fcff_n1 = nopat_n1 * (1 - tasa_reinv_lp)
    vt = fcff_n1 / (wacc - g) if wacc > g else np.nan
    vp_vt = vt / (1 + wacc) ** (n - (0.5 if s.medio_periodo else 0.0))

    ev = vp_fcff.sum() + vp_vt
    deuda = h.loc["Deuda financiera", ultimo]
    caja = h.loc["Caja e inversiones temporales", ultimo]
    patrimonio = ev - deuda + caja

    anios = [int(ultimo) + k for k in range(1, n + 1)]
    tabla = pd.DataFrame({
        "Crecimiento ventas": crec,
        "Ventas": ventas,
        "Margen EBITDA": margenes,
        "EBITDA": ebitda,
        "(−) D&A": -da,
        "EBIT": ebit,
        "(−) Impuestos operativos": -(ebit - nopat),
        "NOPAT": nopat,
        "(+) D&A": da,
        "(−) CAPEX": -capex_v,
        "(−) Aumento de KTNO": -delta_kt,
        "Flujo de caja libre (FCFF)": fcff,
        "Factor de descuento": factor,
        "VP del FCFF": vp_fcff,
    }, index=anios).T

    alertas = []
    crec_lp = float(escenario["Crecimiento nominal (%)"].iloc[-1]) / 100
    if g >= wacc:
        alertas.append(("error", "g ≥ WACC: el modelo de Gordon no converge. Reduce g o revisa el WACC."))
    if g > crec_lp:
        alertas.append(("warning", f"g ({_pct(g)}) supera el crecimiento nominal de largo plazo de la economía "
                                   f"({_pct(crec_lp)}). Ninguna empresa puede crecer más que la economía para siempre."))
    peso_vt = vp_vt / ev if ev else np.nan
    if peso_vt > 0.75:
        alertas.append(("info", f"El valor terminal explica {_pct(peso_vt)} del valor. Regla práctica: por encima "
                                "de ~75 % la valoración depende sobre todo de supuestos de largo plazo."))
    if tasa_reinv_lp > 1:
        alertas.append(("error", "La tasa de reinversión implícita (g/ROIC) supera el 100 %: el FCFF terminal es negativo."))

    return {
        "tabla": tabla, "diagnostico": diag, "ev": ev, "vp_flujos": vp_fcff.sum(), "vp_vt": vp_vt, "vt": vt,
        "peso_vt": peso_vt, "deuda": deuda, "caja": caja, "patrimonio": patrimonio,
        "por_accion": patrimonio / s.acciones_millones if s.acciones_millones else np.nan,
        "roic_lp": roic_lp, "tasa_reinversion_lp": tasa_reinv_lp,
        "reinversion": reinversion, "ebitda_base": diag.attrs["ebitda"].iloc[-1],
        "ebitda_1": ebitda[0], "alertas": alertas,
    }


def eva(s: SupuestosValoracion, wacc: float) -> pd.DataFrame:
    """Valor económico agregado histórico: (ROIC − WACC) · capital invertido inicial."""
    diag = diagnostico(s.historico, s.tasa_impuesto)
    capital_inicial = diag.attrs["capital"].shift(1)
    nopat = diag.attrs["nopat"]
    df = pd.DataFrame({
        "NOPAT": nopat,
        "Capital invertido inicial": capital_inicial,
        "Cargo por capital (WACC × capital)": capital_inicial * wacc,
        "EVA": nopat - capital_inicial * wacc,
    }).T
    return df.iloc[:, 1:]


def sensibilidad(s: SupuestosValoracion, escenario: pd.DataFrame, waccs, gs, salida: str = "patrimonio") -> pd.DataFrame:
    from dataclasses import replace
    m = np.empty((len(gs), len(waccs)))
    for i, g in enumerate(gs):
        for j, w in enumerate(waccs):
            m[i, j] = proyectar(replace(s, g_terminal=g), escenario, w)[salida] if w > g else np.nan
    return pd.DataFrame(m, index=list(gs), columns=list(waccs))
