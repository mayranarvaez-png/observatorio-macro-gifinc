"""Matemática financiera básica (funciones puras, sin dependencias de interfaz).

Convención: flujos[0] ocurre hoy (t = 0), flujos[t] al final del año t.
Tasas como fracciones (0.12 = 12 %).
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def vpn(tasa: float, flujos: Sequence[float]) -> float:
    t = np.arange(len(flujos))
    return float(np.sum(np.asarray(flujos, dtype=float) / (1 + tasa) ** t))


def cambios_de_signo(flujos: Sequence[float]) -> int:
    signos = [np.sign(f) for f in flujos if abs(f) > 1e-9]
    return sum(1 for a, b in zip(signos, signos[1:]) if a != b)


def tir(flujos: Sequence[float], minimo: float = -0.99, maximo: float = 10.0) -> float | None:
    """TIR por bisección. Devuelve None si no hay cambio de signo del VPN en el intervalo."""
    f_min, f_max = vpn(minimo, flujos), vpn(maximo, flujos)
    if np.sign(f_min) == np.sign(f_max):
        return None
    a, b = minimo, maximo
    for _ in range(200):
        m = (a + b) / 2
        f_m = vpn(m, flujos)
        if abs(f_m) < 1e-9 or (b - a) < 1e-12:
            return m
        if np.sign(f_m) == np.sign(f_min):
            a, f_min = m, f_m
        else:
            b = m
    return (a + b) / 2


def tirm(flujos: Sequence[float], tasa_financiacion: float, tasa_reinversion: float) -> float | None:
    """TIR modificada: negativos descontados a t=0, positivos capitalizados al final."""
    n = len(flujos) - 1
    if n <= 0:
        return None
    flujos = np.asarray(flujos, dtype=float)
    t = np.arange(n + 1)
    vp_neg = -np.sum(np.where(flujos < 0, flujos, 0) / (1 + tasa_financiacion) ** t)
    vf_pos = np.sum(np.where(flujos > 0, flujos, 0) * (1 + tasa_reinversion) ** (n - t))
    if vp_neg <= 0 or vf_pos <= 0:
        return None
    return float((vf_pos / vp_neg) ** (1 / n) - 1)


def recuperacion_descontada(tasa: float, flujos: Sequence[float]) -> float | None:
    """Años (con fracción) hasta que el VPN acumulado se vuelve positivo."""
    acumulado = 0.0
    for t, f in enumerate(flujos):
        vp = f / (1 + tasa) ** t
        if acumulado < 0 <= acumulado + vp and t > 0:
            return t - 1 + (-acumulado / vp)
        acumulado += vp
    return None


def indice_rentabilidad(tasa: float, flujos: Sequence[float]) -> float | None:
    """VP de los flujos futuros / VP de la inversión (flujos negativos)."""
    flujos = np.asarray(flujos, dtype=float)
    t = np.arange(len(flujos))
    vp = flujos / (1 + tasa) ** t
    inversion = -vp[vp < 0].sum()
    return None if inversion == 0 else float(vp[vp > 0].sum() / inversion)


def anualidad(valor_presente: float, tasa: float, periodos: int) -> float:
    if tasa == 0:
        return valor_presente / periodos
    return valor_presente * tasa / (1 - (1 + tasa) ** -periodos)
