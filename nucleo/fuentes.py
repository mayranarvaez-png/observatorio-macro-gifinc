"""Conectores a las fuentes oficiales.

Todas las funciones devuelven un DataFrame con columnas ``fecha`` (datetime)
y ``valor`` (float), ordenado por fecha y sin duplicados.
"""
from __future__ import annotations

import io
import os
import xml.etree.ElementTree as ET

import pandas as pd
import requests

from .catalogo import Serie

TIEMPO_ESPERA = 90
INICIO = "2005-01-01"
_SESION = requests.Session()
_SESION.headers["User-Agent"] = "ObservatorioMacroColombia/1.0 (grupo de investigacion en finanzas)"


def _normalizar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=["fecha", "valor"])
    df = df.drop_duplicates("fecha", keep="last").sort_values("fecha")
    return df.reset_index(drop=True)[["fecha", "valor"]]


def _fecha_periodo(texto: pd.Series) -> pd.Series:
    """Convierte '20261013', '2026-09', '2026-Q2' o '2025' en fechas."""
    texto = texto.astype(str)
    if texto.str.contains("Q").any():
        return pd.PeriodIndex(texto.str.replace("-", ""), freq="Q").to_timestamp(how="start")
    if texto.str.fullmatch(r"\d{8}").all():
        return pd.to_datetime(texto, format="%Y%m%d")
    if texto.str.fullmatch(r"\d{4}").all():
        return pd.to_datetime(texto, format="%Y")
    return pd.to_datetime(texto)


# --- Banco de la República (SDMX) -------------------------------------------
def banrep(flujo: str, filtro: dict, escala: float = 1.0) -> pd.DataFrame:
    url = f"https://totoro.banrep.gov.co/nsi-jax-ws/rest/data/ESTAT,{flujo},1.0/all/ALL/"
    r = _SESION.get(
        url,
        params={"startPeriod": INICIO[:7]},
        headers={"Accept": "application/vnd.sdmx.structurespecificdata+xml;version=2.1"},
        timeout=TIEMPO_ESPERA,
    )
    r.raise_for_status()
    raiz = ET.fromstring(r.content)
    filas = []
    for serie in raiz.iter():
        if not serie.tag.endswith("Series"):
            continue
        if any(serie.attrib.get(k) != v for k, v in filtro.items()):
            continue
        for obs in serie:
            filas.append((obs.attrib.get("TIME_PERIOD"), obs.attrib.get("OBS_VALUE")))
    if not filas:
        raise ValueError(f"BanRep {flujo}: ninguna serie coincide con {filtro}")
    df = pd.DataFrame(filas, columns=["fecha", "valor"])
    df["fecha"] = _fecha_periodo(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce") * escala
    return _normalizar(df)


# --- datos.gov.co (Socrata) --------------------------------------------------
def datos_gov(recurso: str) -> pd.DataFrame:
    r = _SESION.get(
        f"https://www.datos.gov.co/resource/{recurso}.json",
        params={"$select": "vigenciadesde,valor", "$where": f"vigenciadesde >= '{INICIO}'",
                "$order": "vigenciadesde", "$limit": 50000},
        timeout=TIEMPO_ESPERA,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json()).rename(columns={"vigenciadesde": "fecha"})
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return _normalizar(df)


# --- FRED (St. Louis Fed) ----------------------------------------------------
def _yahoo_diario(simbolo: str) -> pd.DataFrame:
    """Serie diaria de cierre desde Yahoo Finance (respaldo cuando FRED no responde)."""
    import time
    fin = int(time.time())
    ini = int(pd.Timestamp(INICIO).timestamp())
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{simbolo}",
                     params={"period1": ini, "period2": fin, "interval": "1d"},
                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=(10, 40))
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    df = pd.DataFrame({"fecha": pd.to_datetime(res["timestamp"], unit="s").normalize(),
                       "valor": res["indicators"]["quote"][0]["close"]})
    return _normalizar(df)


# Respaldo por serie de FRED: (símbolo de Yahoo, factor). ^TNX está en % (4,96 = 4,96 %).
_RESPALDO_FRED = {"DGS10": ("^TNX", 1.0)}


def _fred_directo(serie: str) -> pd.DataFrame:
    clave = os.environ.get("FRED_API_KEY")
    if clave:
        r = _SESION.get("https://api.stlouisfed.org/fred/series/observations",
                        params={"series_id": serie, "api_key": clave, "file_type": "json",
                                "observation_start": INICIO}, timeout=(10, 40))
        r.raise_for_status()
        df = pd.DataFrame(r.json()["observations"])[["date", "value"]]
    else:
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                         params={"id": serie, "cosd": INICIO},
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "*/*"},
                         timeout=(10, 40))
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["fecha", "valor"]
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return _normalizar(df)


def fred(serie: str) -> pd.DataFrame:
    """Usa la API oficial si hay FRED_API_KEY (gratuita en fredaccount.stlouisfed.org); si no, la descarga pública en CSV.

    FRED suele tardar o rechazar las conexiones desde servidores compartidos (GitHub Actions, Streamlit Cloud): por eso se
    reintenta con tiempos cortos y, para el Tesoro a 10 años, se usa Yahoo Finance como respaldo. Para el breakeven y el
    CPI de EE. UU. la solución estable es definir FRED_API_KEY.
    """
    import time
    ultimo_error: Exception | None = None
    for intento in range(3):
        try:
            return _fred_directo(serie)
        except requests.RequestException as e:
            ultimo_error = e
            time.sleep(2 * (intento + 1))
    if serie in _RESPALDO_FRED:
        simbolo, factor = _RESPALDO_FRED[serie]
        try:
            df = _yahoo_diario(simbolo)
            df["valor"] = df["valor"] * factor
            return df
        except (requests.RequestException, KeyError, IndexError, ValueError):
            pass
    raise ultimo_error


# --- OCDE (SDMX) -------------------------------------------------------------
def oecd(flujo: str, clave: str) -> pd.DataFrame:
    r = _SESION.get(f"https://sdmx.oecd.org/public/rest/data/{flujo}/{clave}",
                    params={"startPeriod": INICIO[:4], "format": "csv"}, timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    if r.text.startswith("NoRecordsFound"):
        raise ValueError(f"OCDE {flujo}/{clave}: sin registros")
    df = pd.read_csv(io.StringIO(r.text))
    df = df.rename(columns={"TIME_PERIOD": "fecha", "OBS_VALUE": "valor"})
    df["fecha"] = _fecha_periodo(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return _normalizar(df)


# --- Banco Mundial -----------------------------------------------------------
def banco_mundial(indicador: str) -> pd.DataFrame:
    r = _SESION.get(f"https://api.worldbank.org/v2/country/COL/indicator/{indicador}",
                    params={"format": "json", "per_page": 200, "date": f"{INICIO[:4]}:2100"},
                    timeout=TIEMPO_ESPERA)
    r.raise_for_status()
    datos = r.json()
    if len(datos) < 2 or not datos[1]:
        raise ValueError(f"Banco Mundial {indicador}: sin datos")
    df = pd.DataFrame([(d["date"], d["value"]) for d in datos[1]], columns=["fecha", "valor"])
    df["fecha"] = _fecha_periodo(df["fecha"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return _normalizar(df)


# --- Transformaciones ----------------------------------------------------------
def variacion_anual(df: pd.DataFrame, frecuencia: str) -> pd.DataFrame:
    rezagos = {"Mensual": 12, "Trimestral": 4, "Anual": 1}[frecuencia]
    s = df.set_index("fecha")["valor"]
    s = (s / s.shift(rezagos) - 1) * 100
    return _normalizar(s.rename("valor").reset_index())


def a_mensual(df: pd.DataFrame) -> pd.Series:
    """Promedio mensual indexado al primer día del mes."""
    return df.set_index("fecha")["valor"].resample("MS").mean()


def descargar(serie: Serie, disponibles: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    p = serie.parametros
    if serie.proveedor == "banrep":
        df = banrep(p["flujo"], p["filtro"], p.get("escala", 1.0))
    elif serie.proveedor == "datos_gov":
        df = datos_gov(p["recurso"])
    elif serie.proveedor == "fred":
        df = fred(p["serie"])
    elif serie.proveedor == "oecd":
        df = oecd(p["flujo"], p["clave"])
    elif serie.proveedor == "banco_mundial":
        df = banco_mundial(p["indicador"])
    elif serie.proveedor == "derivada":
        a, b = p["formula"]
        disponibles = disponibles or {}
        if a not in disponibles or b not in disponibles:
            raise ValueError(f"Faltan insumos para {serie.id}: {a}, {b}")
        dif = (a_mensual(disponibles[a]) - a_mensual(disponibles[b])).dropna()
        df = _normalizar(dif.rename("valor").rename_axis("fecha").reset_index())
    else:
        raise ValueError(f"Proveedor desconocido: {serie.proveedor}")

    if serie.transformacion == "var_anual":
        df = variacion_anual(df, serie.frecuencia)
    return df
