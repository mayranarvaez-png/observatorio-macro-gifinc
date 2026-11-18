"""Escenarios macroeconómicos para proyectar flujos de caja.

No son pronósticos: son trayectorias de convergencia transparentes que el
estudiante puede editar. Cada variable parte del último dato observado y
converge linealmente a un ancla de largo plazo.

    x_t = x_0 + (x_LP − x_0) · min(t / T, 1)

La TRM se proyecta por paridad de poder adquisitivo relativa:
    TRM_t = TRM_{t−1} · (1 + π_COL,t) / (1 + π_USA,t)
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import almacen

ESCENARIOS = {
    # Desplazamientos (en puntos porcentuales) frente al escenario base.
    "Base": {"pib": 0.0, "inflacion": 0.0, "devaluacion": 0.0},
    "Pesimista": {"pib": -1.5, "inflacion": 1.0, "devaluacion": 3.0},
    "Optimista": {"pib": 1.0, "inflacion": -0.5, "devaluacion": -2.0},
}


@dataclass
class Anclas:
    pib_inicial: float          # % real anual
    pib_largo_plazo: float
    inflacion_inicial: float    # % anual
    inflacion_largo_plazo: float
    inflacion_usa: float
    trm_inicial: float
    anios_convergencia: int = 3


def _ultimo(id_serie: str, defecto: float) -> float:
    df = almacen.leer_serie(id_serie)
    return defecto if df is None or df.empty else float(df["valor"].iloc[-1])


def anclas_por_defecto() -> Anclas:
    """Punto de partida con los últimos datos descargados. Las anclas de largo plazo
    son supuestos editables: meta de inflación del BanRep y un crecimiento potencial
    de referencia."""
    return Anclas(
        pib_inicial=_ultimo("pib_var_anual", 2.5),
        pib_largo_plazo=3.0,
        inflacion_inicial=_ultimo("ipc_anual", 4.0),
        inflacion_largo_plazo=3.0,
        inflacion_usa=_ultimo("breakeven_10", 2.3),
        trm_inicial=_ultimo("trm", 4000.0),
    )


def _converger(inicial: float, final: float, anios: int, t: int) -> float:
    peso = 1.0 if anios <= 0 else min(t / anios, 1.0)
    return inicial + (final - inicial) * peso


def construir(anclas: Anclas, n: int, escenario: str = "Base", anio_inicial: int | None = None) -> pd.DataFrame:
    """Tabla anual t = 1..n con PIB real, inflación, crecimiento nominal y TRM."""
    d = ESCENARIOS[escenario]
    anio_inicial = anio_inicial or pd.Timestamp.today().year
    filas, trm = [], anclas.trm_inicial
    for t in range(1, n + 1):
        pib = _converger(anclas.pib_inicial, anclas.pib_largo_plazo, anclas.anios_convergencia, t) + d["pib"]
        pi = _converger(anclas.inflacion_inicial, anclas.inflacion_largo_plazo,
                        anclas.anios_convergencia, t) + d["inflacion"]
        trm = trm * (1 + pi / 100) / (1 + anclas.inflacion_usa / 100) * (1 + d["devaluacion"] / 100)
        filas.append({
            "Año": anio_inicial + t - 1,
            "t": t,
            "PIB real (%)": pib,
            "Inflación Colombia (%)": pi,
            "Inflación EE. UU. (%)": anclas.inflacion_usa,
            "Crecimiento nominal (%)": ((1 + pib / 100) * (1 + pi / 100) - 1) * 100,
            "TRM fin de año": trm,
        })
    return pd.DataFrame(filas)


def extender(tabla: pd.DataFrame, n: int) -> pd.DataFrame:
    """Repite el último año si un modelo necesita más años que el escenario."""
    if len(tabla) >= n:
        return tabla.iloc[:n].reset_index(drop=True)
    ultima = tabla.iloc[-1]
    extra = []
    for k in range(1, n - len(tabla) + 1):
        fila = ultima.copy()
        fila["t"] = ultima["t"] + k
        fila["Año"] = ultima["Año"] + k
        extra.append(fila)
    return pd.concat([tabla, pd.DataFrame(extra)], ignore_index=True)
