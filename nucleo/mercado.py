"""Supuestos de mercado por defecto, derivados de los datos descargados.

Centraliza las elecciones por defecto para que la página de inicio y la
calculadora usen exactamente los mismos números.
"""
from __future__ import annotations

import pandas as pd

from . import almacen
from .costo_capital import Supuestos

META_INFLACION_BANREP = 0.03
META_INFLACION_FED = 0.02
TASA_RENTA_COLOMBIA = 0.35   # Art. 240 Estatuto Tributario (respaldo si falta Damodaran)


def _ultimo(id_serie: str) -> float | None:
    df = almacen.leer_serie(id_serie)
    return None if df is None or df.empty else float(df["valor"].iloc[-1]) / 100


def _promedio_12m(id_serie: str) -> float | None:
    df = almacen.leer_serie(id_serie)
    if df is None or df.empty:
        return None
    ventana = df[df["fecha"] > df["fecha"].max() - pd.DateOffset(months=12)]
    return float(ventana["valor"].mean()) / 100


def opciones_rf() -> dict[str, float | None]:
    return {
        "Tesoro 10A – último dato": _ultimo("ust_10"),
        "Tesoro 10A – promedio 12 meses": _promedio_12m("ust_10"),
    }


def opciones_infl_col() -> dict[str, float | None]:
    return {
        "Meta del BanRep (3,0 %)": META_INFLACION_BANREP,
        "IPC anual – último dato": _ultimo("ipc_anual"),
    }


def opciones_infl_usa() -> dict[str, float | None]:
    return {
        "Breakeven 10A (mercado)": _ultimo("breakeven_10"),
        "Meta de la Fed (2,0 %)": META_INFLACION_FED,
    }


def opciones_kd_base() -> dict[str, float | None]:
    return {
        "TES 10A + spread": _ultimo("tes_10"),
        "IBR 3M + spread": _ultimo("ibr_3m"),
    }


def supuestos_referencia() -> tuple[Supuestos, dict] | None:
    """Ke/WACC de referencia: β desapalancada = 1, sin deuda (mercado colombiano promedio)."""
    pais = almacen.leer_parametros_pais()
    rf = _ultimo("ust_10")
    infl_usa = _ultimo("breakeven_10")
    if pais is None or rf is None or infl_usa is None:
        return None
    s = Supuestos(
        rf=rf, beta_u=1.0, de=0.0,
        tasa_impuesto=pais.get("tasa_impositiva_marginal", TASA_RENTA_COLOMBIA),
        erp=pais["erp_madura"], crp=pais["crp_calificacion"],
        infl_col=META_INFLACION_BANREP, infl_usa=infl_usa,
        kd_cop=_ultimo("tes_10") or 0.0,
    )
    return s, pais
