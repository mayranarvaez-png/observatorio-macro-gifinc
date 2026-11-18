"""Indicadores de acciones y matemática de portafolio (funciones puras, sin red ni Streamlit).

Todo se calcula con retornos **simples semanales** (cierre de viernes, ajustado por dividendos y splits).
Anualización: 52 semanas. Las tasas libres de riesgo entran como tasa anual (fracción).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SEMANAS = 52


# =============================== Retornos y riesgo ==================================
def retornos(precios: pd.DataFrame | pd.Series) -> pd.DataFrame | pd.Series:
    return precios.pct_change(fill_method=None).dropna(how="all")


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    return float((1 + r).prod() ** (SEMANAS / len(r)) - 1) if len(r) else np.nan


def vol_anual(r: pd.Series) -> float:
    return float(r.dropna().std(ddof=1) * np.sqrt(SEMANAS))


def sharpe(r: pd.Series, rf: float) -> float:
    r = r.dropna()
    v = vol_anual(r)
    return float((r.mean() * SEMANAS - rf) / v) if v > 0 else np.nan


def sortino(r: pd.Series, rf: float) -> float:
    r = r.dropna()
    exceso = r - rf / SEMANAS
    abajo = np.sqrt(np.mean(np.minimum(exceso, 0) ** 2)) * np.sqrt(SEMANAS)
    return float((r.mean() * SEMANAS - rf) / abajo) if abajo > 0 else np.nan


def curva_acumulada(r: pd.Series) -> pd.Series:
    return (1 + r.dropna()).cumprod()


def caida(r: pd.Series) -> pd.Series:
    c = curva_acumulada(r)
    return c / c.cummax() - 1


def caida_maxima(r: pd.Series) -> float:
    return float(caida(r).min())


def var_historico(r: pd.Series, nivel: float = 0.95) -> float:
    """Pérdida semanal que no se supera con probabilidad `nivel` (positiva = pérdida)."""
    return float(-np.quantile(r.dropna(), 1 - nivel))


def cvar_historico(r: pd.Series, nivel: float = 0.95) -> float:
    r = r.dropna()
    corte = np.quantile(r, 1 - nivel)
    cola = r[r <= corte]
    return float(-cola.mean()) if len(cola) else np.nan


def beta_alfa(r: pd.Series, rm: pd.Series, rf: float) -> dict:
    """Regresión OLS del exceso de retorno sobre el del mercado. Alfa de Jensen anualizado."""
    d = pd.concat([r, rm], axis=1, keys=["r", "m"]).dropna()
    if len(d) < 20:
        return {"beta": np.nan, "alfa": np.nan, "corr": np.nan, "r2": np.nan, "n": len(d)}
    rfw = rf / SEMANAS
    y, x = d["r"] - rfw, d["m"] - rfw
    beta = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))
    alfa = float((y.mean() - beta * x.mean()) * SEMANAS)
    corr = float(np.corrcoef(d["r"], d["m"])[0, 1])
    return {"beta": beta, "alfa": alfa, "corr": corr, "r2": corr ** 2, "n": len(d)}


def estadisticas(ret: pd.DataFrame, bench: pd.Series | None, rf: float) -> pd.DataFrame:
    """Una fila por activo con los indicadores de retorno y riesgo."""
    filas = {}
    for c in ret.columns:
        r = ret[c].dropna()
        if len(r) < 20:
            continue
        fila = {"Retorno anual": cagr(r), "Volatilidad": vol_anual(r), "Sharpe": sharpe(r, rf),
                "Sortino": sortino(r, rf), "Caída máxima": caida_maxima(r),
                "VaR 95 % (sem.)": var_historico(r), "CVaR 95 % (sem.)": cvar_historico(r),
                "Semanas": len(r)}
        if bench is not None:
            ba = beta_alfa(r, bench, rf)
            fila.update({"Beta": ba["beta"], "Alfa anual": ba["alfa"], "Correlación": ba["corr"], "R²": ba["r2"]})
        filas[c] = fila
    return pd.DataFrame(filas).T


def retornos_por_periodo(precios: pd.DataFrame) -> pd.DataFrame:
    """Rentabilidad acumulada a 1, 3, 6 meses, año corrido, 1, 3 y 5 años (simple, no anualizada salvo 3A y 5A)."""
    filas = {}
    for c in precios.columns:
        p = precios[c].dropna()
        if len(p) < 5:
            continue
        ult, fecha = p.iloc[-1], p.index[-1]
        fila = {}
        for nombre, meses in (("1 mes", 1), ("3 meses", 3), ("6 meses", 6), ("1 año", 12)):
            previo = p[p.index <= fecha - pd.DateOffset(months=meses)]
            fila[nombre] = ult / previo.iloc[-1] - 1 if len(previo) else np.nan
        ini_anio = p[p.index < pd.Timestamp(year=fecha.year, month=1, day=1)]
        fila["Año corrido"] = ult / ini_anio.iloc[-1] - 1 if len(ini_anio) else np.nan
        for nombre, anios in (("3 años (anual)", 3), ("5 años (anual)", 5)):
            previo = p[p.index <= fecha - pd.DateOffset(years=anios)]
            fila[nombre] = (ult / previo.iloc[-1]) ** (1 / anios) - 1 if len(previo) else np.nan
        filas[c] = fila
    return pd.DataFrame(filas).T[["1 mes", "3 meses", "6 meses", "Año corrido", "1 año", "3 años (anual)", "5 años (anual)"]]


# =============================== Portafolio =========================================
def pesos_validos(w) -> np.ndarray:
    w = np.asarray(w, dtype=float)
    if (w < 0).any() or w.sum() <= 0:
        raise ValueError("Los pesos deben ser no negativos y sumar más de cero.")
    return w / w.sum()


def retorno_portafolio(ret: pd.DataFrame, w) -> pd.Series:
    """Retorno semanal con pesos constantes (rebalanceo semanal) sobre el periodo común a todos los activos."""
    comun = ret.dropna()
    return pd.Series(comun.to_numpy() @ pesos_validos(w), index=comun.index, name="Portafolio")


def media_cov(ret: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    comun = ret.dropna()
    return comun.mean().to_numpy() * SEMANAS, comun.cov().to_numpy() * SEMANAS


def contribucion_riesgo(cov: np.ndarray, w) -> np.ndarray:
    """Participación de cada activo en la volatilidad del portafolio (suma 1)."""
    w = pesos_validos(w)
    sigma = float(np.sqrt(w @ cov @ w))
    return w * (cov @ w) / sigma / sigma if sigma > 0 else np.zeros_like(w)


def n_efectivo(w) -> float:
    """Número efectivo de posiciones (inverso de Herfindahl): 1/Σw². Igual ponderado con n activos → n."""
    w = pesos_validos(w)
    return float(1 / np.sum(w ** 2))


def ratio_diversificacion(cov: np.ndarray, w) -> float:
    """Σ wᵢσᵢ / σ_portafolio. Es 1 si todo está perfectamente correlacionado; crece con la diversificación."""
    w = pesos_validos(w)
    sigma = float(np.sqrt(w @ cov @ w))
    return float((w @ np.sqrt(np.diag(cov))) / sigma) if sigma > 0 else np.nan


def _metricas(mu, cov, rf, W):
    ret = W @ mu
    vol = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
    return ret, vol, (ret - rf) / vol


def nube(mu, cov, rf, n: int = 15000, seed: int = 7) -> pd.DataFrame:
    """Portafolios aleatorios sin ventas en corto. Mezcla pesos repartidos y concentrados para cubrir los bordes."""
    rng = np.random.default_rng(seed)
    k = len(mu)
    partes = [rng.dirichlet(np.ones(k), n // 2), rng.dirichlet(np.full(k, 0.25), n - n // 2)]
    W = np.vstack(partes + [np.eye(k)])
    ret, vol, sh = _metricas(mu, cov, rf, W)
    return pd.DataFrame({"retorno": ret, "vol": vol, "sharpe": sh, "pesos": list(W)})


def _refinar(mu, cov, rf, w0, objetivo: str, iteraciones: int = 4000, seed: int = 11) -> np.ndarray:
    """Búsqueda local desde `w0`: mejora la mínima varianza ('varianza') o el Sharpe ('sharpe') sin ventas en corto."""
    rng = np.random.default_rng(seed)
    f = (lambda w: -(w @ mu - rf) / np.sqrt(w @ cov @ w)) if objetivo == "sharpe" else (lambda w: np.sqrt(w @ cov @ w))
    mejor, f_mejor, paso = w0.copy(), f(w0), 0.10
    for i in range(iteraciones):
        cand = np.clip(mejor + rng.normal(0, paso, len(mejor)), 0, None)
        if cand.sum() <= 0:
            continue
        cand /= cand.sum()
        fc = f(cand)
        if fc < f_mejor:
            mejor, f_mejor = cand, fc
        if i % 500 == 499:
            paso *= 0.5
    mejor[mejor < 1e-4] = 0
    return mejor / mejor.sum()


def optimos(mu, cov, rf, semilla: pd.DataFrame | None = None) -> dict[str, np.ndarray]:
    """Portafolio de mínima varianza y de máximo Sharpe (sin ventas en corto), partiendo de la mejor muestra aleatoria."""
    nb = semilla if semilla is not None else nube(mu, cov, rf)
    w_min = nb.loc[nb["vol"].idxmin(), "pesos"]
    w_sh = nb.loc[nb["sharpe"].idxmax(), "pesos"]
    return {"minima_varianza": _refinar(mu, cov, rf, np.asarray(w_min), "varianza"),
            "maximo_sharpe": _refinar(mu, cov, rf, np.asarray(w_sh), "sharpe")}


def resumen_portafolio(ret: pd.DataFrame, w, bench: pd.Series | None, rf: float) -> dict:
    r = retorno_portafolio(ret, w)
    _, cov = media_cov(ret)
    est = estadisticas(pd.DataFrame({"Portafolio": r}), bench, rf).iloc[0].to_dict()
    est.update({"n_efectivo": n_efectivo(w), "ratio_diversificacion": ratio_diversificacion(cov, w),
                "desde": r.index[0], "hasta": r.index[-1]})
    return est
