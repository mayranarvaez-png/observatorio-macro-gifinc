"""Universo de acciones de EE. UU. para el comparador y el portafolio.

Fuentes públicas:
- Directorio de símbolos de Nasdaq Trader (`nasdaqlisted.txt` y `otherlisted.txt`): todas las emisiones listadas en
  Nasdaq, NYSE, NYSE American y NYSE Arca, con la marca de ETF y de emisión de prueba.
- Wikipedia: composición actual del S&P 500 (con sector GICS). API pública de Nasdaq: composición del Nasdaq-100.

Se guarda un CSV en `datos/universo/acciones_us.csv`. Los símbolos se convierten al formato de Yahoo Finance
(BRK.B → BRK-B). La composición de los índices cambia con el tiempo: `python actualizar_universo.py` la refresca.
"""
from __future__ import annotations

import io
import re

import pandas as pd
import requests

from . import almacen

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
URL_NASDAQ = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
URL_OTROS = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
URL_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
URL_NDX = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
RUTA = almacen.RAIZ / "universo" / "acciones_us.csv"
BOLSAS = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}
# Instrumentos que no son acciones comunes ni ETF: warrants, derechos, unidades, notas y preferentes.
_EXCLUIR = re.compile(r"\b(?:warrants?|rights?|units?|notes?|preferred|debentures?|subordinated|trust preferred)\b", re.I)
_SUFIJOS = re.compile(r"\s*(?:-\s*)?(?:Class [A-Z] )?(?:Common Stock|Ordinary Shares?|Common Shares?|American Depositary (?:Shares|Receipts?)).*$", re.I)


def simbolo_yahoo(s: str) -> str:
    return str(s).strip().upper().replace(".", "-")


def _txt(url: str) -> pd.DataFrame:
    r = requests.get(url, headers=UA, timeout=(10, 60))
    r.raise_for_status()
    lineas = [l for l in r.text.splitlines() if not l.startswith("File Creation Time")]
    return pd.read_csv(io.StringIO("\n".join(lineas)), sep="|", dtype=str)


def _wiki(url: str, columna_simbolo: tuple[str, ...]) -> pd.DataFrame:
    r = requests.get(url, headers=UA, timeout=(10, 60))
    r.raise_for_status()
    for t in pd.read_html(io.StringIO(r.text)):
        if any(c in t.columns for c in columna_simbolo) and len(t) > 50:
            return t
    raise ValueError(f"No se encontró la tabla de composición en {url}")


def _nasdaq100() -> pd.DataFrame:
    """Composición del Nasdaq-100 desde la API pública de Nasdaq (índice = símbolo de Yahoo, columna `Company`)."""
    r = requests.get(URL_NDX, headers={**UA, "Accept": "application/json, text/plain, */*",
                                       "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"},
                     timeout=(10, 30))
    r.raise_for_status()
    filas = r.json()["data"]["data"]["rows"]
    if len(filas) < 90:
        raise ValueError("La API de Nasdaq devolvió una composición incompleta del Nasdaq-100.")
    d = pd.DataFrame(filas)
    return pd.DataFrame({"Company": d["companyName"].to_numpy()}, index=pd.Index(d["symbol"].map(simbolo_yahoo), name="ticker"))


def descargar() -> pd.DataFrame:
    """Construye el universo. Lanza una excepción de red si falla alguna fuente."""
    nq = _txt(URL_NASDAQ)
    nq = pd.DataFrame({"simbolo": nq["Symbol"], "nombre": nq["Security Name"], "bolsa": "Nasdaq",
                       "etf": nq["ETF"].eq("Y"), "prueba": nq["Test Issue"].eq("Y")})
    ot = _txt(URL_OTROS)
    ot = pd.DataFrame({"simbolo": ot["ACT Symbol"], "nombre": ot["Security Name"],
                       "bolsa": ot["Exchange"].map(BOLSAS).fillna("Otra"), "etf": ot["ETF"].eq("Y"),
                       "prueba": ot["Test Issue"].eq("Y")})
    df = pd.concat([nq, ot], ignore_index=True).dropna(subset=["simbolo", "nombre"])
    df = df[~df["prueba"] & ~df["simbolo"].str.contains(r"[\$\^]", regex=True)]
    df = df[~df["nombre"].str.contains(_EXCLUIR)]
    df["ticker"] = df["simbolo"].map(simbolo_yahoo)
    df["nombre"] = df["nombre"].str.replace(_SUFIJOS, "", regex=True).str.strip().str.rstrip(" -")
    df = df.drop_duplicates("ticker")[["ticker", "nombre", "bolsa", "etf"]].set_index("ticker")

    sp = _wiki(URL_SP500, ("Symbol",))
    sp = sp.assign(ticker=sp["Symbol"].map(simbolo_yahoo)).set_index("ticker")
    ndx = _nasdaq100()

    df["sp500"] = df.index.isin(sp.index)
    df["nasdaq100"] = df.index.isin(ndx.index)
    # Los índices pueden traer símbolos que el directorio no lista (p. ej., cambios recientes): se agregan.
    faltan = [t for t in list(sp.index) + list(ndx.index) if t not in df.index]
    if faltan:
        extra = pd.DataFrame({"nombre": [(sp["Security"].get(t) if t in sp.index else ndx["Company"].get(t)) for t in faltan],
                              "bolsa": "—", "etf": False, "sp500": [t in sp.index for t in faltan],
                              "nasdaq100": [t in ndx.index for t in faltan]}, index=pd.Index(faltan, name="ticker"))
        df = pd.concat([df, extra[~extra.index.duplicated()]])
    df["sector"] = sp["GICS Sector"].reindex(df.index)
    df["industria"] = sp["GICS Sub-Industry"].reindex(df.index)
    # Para los índices se prefiere el nombre corto de Wikipedia.
    df.loc[df["sp500"] & df.index.isin(sp.index), "nombre"] = sp["Security"].reindex(df.index[df["sp500"]]).to_numpy()
    df["tipo"] = df["etf"].map({True: "ETF", False: "Acción"})
    return df.drop(columns="etf").reset_index().sort_values(["sp500", "nasdaq100", "ticker"], ascending=[False, False, True])


def guardar(df: pd.DataFrame) -> None:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA, index=False)


def leer() -> pd.DataFrame | None:
    return pd.read_csv(RUTA) if RUTA.exists() else None
