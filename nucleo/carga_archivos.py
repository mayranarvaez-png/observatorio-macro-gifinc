"""Lectura flexible de estados financieros desde Excel o CSV.

Acepta archivos con cualquier nombre de cuentas: primera columna con los conceptos y
una columna por año. El estudiante asigna qué filas forman cada rubro del modelo
(con sugerencias automáticas por palabras clave).
"""
from __future__ import annotations

import io
import re

import pandas as pd

from .supersociedades import norm
from .valoracion import RUBROS

UNIDADES = {"Millones de pesos": 1.0, "Miles de pesos": 1_000.0, "Pesos": 1_000_000.0}

# Palabras clave (sin tildes) para sugerir filas. KTNO se arma sumando y restando.
SUGERENCIAS = {
    "Ventas": ["ingresos de actividades ordinarias", "ventas netas", "ingresos operacionales", "ventas"],
    "Costo de ventas": ["costo de ventas", "costos de ventas", "costo de venta"],
    "Gastos operacionales (sin D&A)": ["gastos de administracin", "gastos de administracion", "gastos de ventas",
                                       "costos de distribucin", "costos de distribucion", "gastos operacionales"],
    "Depreciación y amortización": ["depreciacin", "depreciacion", "amortizacin", "amortizacion"],
    "CAPEX": ["capex", "compras de propiedades", "adquisicin de propiedades", "adquisicion de propiedades",
              "inversiones en activos fijos"],
    "KTNO (+)": ["cuentas comerciales por cobrar", "cuentas por cobrar", "deudores", "inventario"],
    "KTNO (−)": ["cuentas por pagar comerciales", "cuentas comerciales por pagar", "proveedores", "cuentas por pagar"],
    "Activo fijo neto": ["propiedades planta y equipo", "propiedad planta y equipo", "activos fijos",
                         "activos intangibles"],
    "Deuda financiera": ["obligaciones financieras", "pasivos financieros", "prstamos", "prestamos", "deuda financiera"],
    "Caja e inversiones temporales": ["efectivo y equivalentes", "efectivo", "caja", "disponible"],
}


def leer(archivo) -> dict[str, pd.DataFrame]:
    """Devuelve {nombre de hoja: DataFrame crudo sin encabezado}."""
    nombre = archivo.name.lower()
    datos = archivo.getvalue()
    if nombre.endswith(".csv"):
        texto = datos.decode("utf-8-sig", errors="replace")
        separador = ";" if texto.count(";") > texto.count(",") else ","
        return {"CSV": pd.read_csv(io.StringIO(texto), sep=separador, header=None, dtype=str)}
    return pd.read_excel(io.BytesIO(datos), sheet_name=None, header=None, dtype=str)


def _a_numero(x) -> float:
    """Convierte '1.234.567,8', '1,234,567.8', '(1.234)' o '-' en número."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return float("nan")
    s = str(x).strip().replace(" ", "").replace("$", "")
    if s in ("", "-", "nan", "None"):
        return float("nan")
    negativo = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if "," in s and "." in s:
        # El separador que aparece de último es el decimal.
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        # Un solo tipo de separador: si se repite o va seguido de exactamente 3 dígitos, es de miles
        # (convención colombiana: "350.000" = trescientos cincuenta mil); si no, es decimal.
        for sep in (".", ","):
            if sep in s:
                partes = s.split(sep)
                s = s.replace(sep, "") if len(partes) > 2 or len(partes[-1]) == 3 else s.replace(sep, ".")
    try:
        v = float(s)
    except ValueError:
        return float("nan")
    return -v if negativo else v


def _anio(encabezado) -> int | None:
    m = re.search(r"(19|20)\d{2}", str(encabezado))
    return int(m.group(0)) if m else None


def estructurar(crudo: pd.DataFrame) -> pd.DataFrame:
    """Detecta la fila de encabezados (la que tiene más años) y arma conceptos × años."""
    mejor, fila_enc = 0, 0
    for i in range(min(len(crudo), 30)):
        n = sum(_anio(v) is not None for v in crudo.iloc[i, 1:])
        if n > mejor:
            mejor, fila_enc = n, i
    if mejor == 0:
        raise ValueError("No encontré una fila con años (por ejemplo 2023, 2024) como encabezados de columna.")
    encabezados = crudo.iloc[fila_enc]
    cols = {j: _anio(v) for j, v in encabezados.items() if j != crudo.columns[0] and _anio(v)}
    cuerpo = crudo.iloc[fila_enc + 1:]
    conceptos = cuerpo.iloc[:, 0].astype(str).str.strip()
    tabla = pd.DataFrame({anio: cuerpo[j].map(_a_numero).to_numpy() for j, anio in cols.items()},
                         index=conceptos.to_numpy())
    tabla = tabla[~tabla.index.isin(["", "nan", "None"])].dropna(how="all")
    tabla = tabla.loc[:, ~tabla.columns.duplicated()]
    return tabla[sorted(tabla.columns)]


def es_plantilla(tabla: pd.DataFrame) -> bool:
    return all(r in tabla.index for r in RUBROS)


def sugerir(tabla: pd.DataFrame) -> dict[str, list[str]]:
    """Filas sugeridas para cada rubro según palabras clave (sin repetir filas entre rubros)."""
    usadas, salida = set(), {}
    normalizados = {c: norm(c) for c in tabla.index}
    for rubro, claves in SUGERENCIAS.items():
        elegidas = []
        for clave in claves:
            for concepto, n in normalizados.items():
                if concepto in usadas or concepto in elegidas:
                    continue
                if clave in n and "total" not in n and "no corriente" not in n:
                    elegidas.append(concepto)
            if elegidas and rubro in ("Ventas", "Costo de ventas", "Caja e inversiones temporales"):
                break       # estos rubros suelen ser una sola línea
        usadas.update(elegidas)
        salida[rubro] = elegidas
    return salida


def armar(tabla: pd.DataFrame, asignacion: dict[str, list[str]], divisor: float,
          restar_dya: bool = True) -> pd.DataFrame:
    """Construye la tabla de rubros del modelo (millones de COP) a partir de la asignación.

    En los estados financieros la depreciación suele estar incluida en costos y gastos;
    con `restar_dya` se descuenta de los gastos para obtener el rubro "sin D&A"
    (así EBITDA = ventas − costo − gastos sin D&A queda bien medido)."""
    def suma(filas):
        return tabla.loc[filas].abs().sum() if filas else pd.Series(0.0, index=tabla.columns)

    resultado = pd.DataFrame({
        "Ventas": suma(asignacion["Ventas"]),
        "Costo de ventas": suma(asignacion["Costo de ventas"]),
        "Gastos operacionales (sin D&A)": suma(asignacion["Gastos operacionales (sin D&A)"])
        - (suma(asignacion["Depreciación y amortización"]) if restar_dya else 0.0),
        "Depreciación y amortización": suma(asignacion["Depreciación y amortización"]),
        "CAPEX": suma(asignacion["CAPEX"]),
        "Capital de trabajo neto operativo (KTNO)": suma(asignacion["KTNO (+)"]) - suma(asignacion["KTNO (−)"]),
        "Activo fijo neto": suma(asignacion["Activo fijo neto"]),
        "Deuda financiera": suma(asignacion["Deuda financiera"]),
        "Caja e inversiones temporales": suma(asignacion["Caja e inversiones temporales"]),
    }).T
    return (resultado.loc[RUBROS] / divisor).fillna(0.0).round(1)
