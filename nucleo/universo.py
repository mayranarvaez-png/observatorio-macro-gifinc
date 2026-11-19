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


def _wiki(url: str, columna_simbolo: tuple[str, ...], min_filas: int = 50) -> pd.DataFrame:
    r = requests.get(url, headers=UA, timeout=(10, 60))
    r.raise_for_status()
    for t in pd.read_html(io.StringIO(r.text)):
        if any(c in t.columns for c in columna_simbolo) and len(t) >= min_filas:
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


# =============================== Índices de otros países ============================
def _sufijo_fijo(suf: str):
    return lambda t: simbolo_yahoo(t) + suf


def _hong_kong(t: str) -> str:
    return f"{int(re.sub(r'[^0-9]', '', str(t))):04d}.HK"


# índice → (url, columna del ticker, columna del nombre, columna del sector, conversión a símbolo de Yahoo)
INDICES_GLOBALES = {
    "FTSE 100": ("https://en.wikipedia.org/wiki/FTSE_100_Index", "Ticker", "Company", "FTSE industry", _sufijo_fijo(".L")),
    "DAX": ("https://en.wikipedia.org/wiki/DAX", "Ticker", "Company", "Prime Standard Sector", str),
    "CAC 40": ("https://en.wikipedia.org/wiki/CAC_40", "Ticker", "Company", "Sector", str),
    "Euro Stoxx 50": ("https://en.wikipedia.org/wiki/EURO_STOXX_50", "Ticker", "Name", "Sector", str),
    "IBEX 35": ("https://en.wikipedia.org/wiki/IBEX_35", "Ticker", "Company", "Sector", str),
    "FTSE MIB": ("https://en.wikipedia.org/wiki/FTSE_MIB", "Ticker", "Company", "ICB Sector", str),
    "AEX": ("https://en.wikipedia.org/wiki/AEX_index", "Ticker", "Company", "ICB Sector", str),
    "SMI": ("https://en.wikipedia.org/wiki/Swiss_Market_Index", "Ticker", "Name", "Sector", _sufijo_fijo(".SW")),
    "S&P/TSX 60": ("https://en.wikipedia.org/wiki/S%26P/TSX_60", "Symbol", "Company", "Sector", _sufijo_fijo(".TO")),
    "Hang Seng": ("https://en.wikipedia.org/wiki/Hang_Seng_Index", "Ticker", "Name", "Sub-index", _hong_kong),
}
PAIS_POR_SUFIJO = {
    ".CL": "Colombia", ".SA": "Brasil", ".MX": "México", ".SN": "Chile", ".BA": "Argentina", ".LM": "Perú",
    ".L": "Reino Unido", ".DE": "Alemania", ".F": "Alemania", ".PA": "Francia", ".AS": "Países Bajos", ".MI": "Italia",
    ".MC": "España", ".SW": "Suiza", ".BR": "Bélgica", ".HE": "Finlandia", ".IR": "Irlanda", ".I": "Irlanda",
    ".LS": "Portugal", ".CO": "Dinamarca", ".ST": "Suecia", ".OL": "Noruega", ".VI": "Austria", ".TO": "Canadá",
    ".HK": "Hong Kong", ".T": "Japón",
}
MERCADO_POR_SUFIJO = {
    ".CL": "BVC", ".SA": "B3", ".MX": "BMV", ".SN": "Bolsa de Santiago", ".BA": "BYMA", ".LM": "BVL", ".L": "Londres",
    ".DE": "Xetra", ".F": "Fráncfort", ".PA": "Euronext París", ".AS": "Euronext Ámsterdam", ".MI": "Borsa Italiana",
    ".MC": "BME Madrid", ".SW": "SIX Suiza", ".BR": "Euronext Bruselas", ".HE": "Nasdaq Helsinki", ".IR": "Euronext Dublín",
    ".I": "Euronext Dublín", ".LS": "Euronext Lisboa", ".CO": "Nasdaq Copenhague", ".ST": "Nasdaq Estocolmo",
    ".OL": "Oslo Børs", ".VI": "Viena", ".TO": "Toronto", ".HK": "Hong Kong", ".T": "Tokio",
}


def sufijo(ticker: str) -> str:
    m = re.search(r"\.[A-Z]{1,2}$", str(ticker))
    return m.group(0) if m else ""


def _columna(t: pd.DataFrame, nombre: str) -> pd.Series:
    """Columna por prefijo (Wikipedia agrega notas como «[35]» a los encabezados)."""
    for c in t.columns:
        if str(c).startswith(nombre):
            return t[c]
    return pd.Series([None] * len(t), index=t.index)


def indices_globales() -> pd.DataFrame:
    filas = []
    for indice, (url, col_t, col_n, col_s, a_yahoo) in INDICES_GLOBALES.items():
        try:
            t = _wiki(url, (col_t,), min_filas=18)
        except (requests.RequestException, ValueError):
            continue
        for tk, nom, sec in zip(_columna(t, col_t), _columna(t, col_n), _columna(t, col_s)):
            if pd.isna(tk):
                continue
            try:
                y = a_yahoo(str(tk).replace("\xa0", " ").strip())
            except ValueError:
                continue
            filas.append({"ticker": y, "nombre": nom, "sector": sec, "listas": indice})
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    df = df.groupby("ticker", as_index=False).agg(nombre=("nombre", "first"), sector=("sector", "first"),
                                                  listas=("listas", lambda s: "|".join(dict.fromkeys(s))))
    df["pais"] = df["ticker"].map(lambda t: PAIS_POR_SUFIJO.get(sufijo(t), "Otro"))
    df["mercado"] = df["ticker"].map(lambda t: MERCADO_POR_SUFIJO.get(sufijo(t), "—"))
    df["tipo"] = "Acción"
    return df


def validar_en_yahoo(tickers: list[str]) -> set[str]:
    """Devuelve los símbolos que Yahoo reconoce (consulta liviana del último mes)."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    local = threading.local()           # una sesión por hilo: reutiliza la conexión (abrir una nueva es lento)

    def ok(t):
        if not hasattr(local, "s"):
            local.s = requests.Session()
            local.s.headers.update(UA)
        try:
            r = local.s.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}",
                            params={"range": "1mo", "interval": "1wk"}, timeout=(10, 20))
            return t if r.status_code == 200 and r.json()["chart"]["result"] else None
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return None
    with ThreadPoolExecutor(max_workers=8) as ex:
        return {t for t in ex.map(ok, tickers) if t}


# =============================== Catálogo unificado =================================
RUTA_CATALOGO = almacen.RAIZ / "universo" / "catalogo.csv"
RUTA_COLOMBIA = almacen.RAIZ / "universo" / "colombia.csv"
COLUMNAS = ["ticker", "nombre", "pais", "mercado", "tipo", "sector", "listas"]


def construir_catalogo(us: pd.DataFrame | None, globales: pd.DataFrame | None) -> pd.DataFrame:
    """Une Colombia (BVC y ADR), Latinoamérica (cuaderno de betas), EE. UU. y los índices de otros países."""
    partes = []
    if RUTA_COLOMBIA.exists():
        co = pd.read_csv(RUTA_COLOMBIA)
        co["listas"] = co["ticker"].map(lambda t: "Bolsa de Colombia (BVC)" if t.endswith(".CL") else "ADR de empresas colombianas")
        partes.append(co)
    emp = almacen.leer_empresas_propias()
    if emp is not None:
        la = pd.DataFrame({"ticker": emp["ticker"], "nombre": emp["empresa"], "pais": emp["pais_es"],
                           "sector": emp["industria"], "tipo": "Acción", "listas": "Latinoamérica (cuaderno de betas)"})
        la["mercado"] = la["ticker"].map(lambda t: MERCADO_POR_SUFIJO.get(sufijo(t), "EE. UU. (ADR)"))
        partes.append(la)
    if us is not None and not us.empty:
        u = us.copy()
        u["pais"] = "EE. UU."
        u["mercado"] = u["bolsa"]
        u["listas"] = [("|".join(x for x, f in (("S&P 500", a), ("Nasdaq-100", b)) if f))
                       or ("ETF de EE. UU." if t == "ETF" else "Nasdaq y NYSE")
                       for a, b, t in zip(u["sp500"], u["nasdaq100"], u["tipo"])]
        partes.append(u)
    if globales is not None and not globales.empty:
        partes.append(globales)
    df = pd.concat([p.reindex(columns=COLUMNAS) for p in partes], ignore_index=True)
    df = df.drop_duplicates("ticker", keep="first")
    df["nombre"] = df["nombre"].fillna(df["ticker"]).astype(str).str.strip()
    return df[COLUMNAS]


def guardar_catalogo(df: pd.DataFrame) -> None:
    RUTA_CATALOGO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA_CATALOGO, index=False)


def leer_catalogo() -> pd.DataFrame | None:
    return pd.read_csv(RUTA_CATALOGO) if RUTA_CATALOGO.exists() else None
