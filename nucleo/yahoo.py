"""Datos de acciones desde Yahoo Finance (API pública que usa su propio sitio web).

- Precios semanales ajustados por dividendos y splits (`chart`).
- Perfil e indicadores fundamentales (`quoteSummary`, requiere un «crumb» que Yahoo entrega con una cookie).
- Tipo de cambio contra el dólar (`COP=X`, `BRL=X`… = unidades de moneda local por USD).

Las funciones `parsear_*` no usan red, de modo que se pueden probar con respuestas guardadas.
Yahoo no es una fuente oficial: puede tener huecos, errores de unidades (sobre todo en ADR) y cambios
sin aviso. Cada indicador sospechoso se marca en `banderas` en vez de ocultarse.
"""
from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
import streamlit as st

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"}
BASE = "https://query1.finance.yahoo.com"
MODULOS = "price,summaryDetail,defaultKeyStatistics,financialData,assetProfile"


# =============================== Sesión y red =======================================
@st.cache_resource(ttl=3600, show_spinner=False)
def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


@st.cache_resource(ttl=3600, show_spinner=False)
def _crumb() -> str | None:
    """Cookie y «crumb» que Yahoo exige solo para `quoteSummary`. Se piden de forma perezosa y con tiempos cortos."""
    s = _sesion()
    try:
        s.get("https://fc.yahoo.com", timeout=(4, 6))
    except requests.RequestException:
        pass
    try:
        r = s.get(f"{BASE}/v1/test/getcrumb", timeout=(4, 6))
        return r.text if r.status_code == 200 and r.text and "<" not in r.text else None
    except requests.RequestException:
        return None


def _get(url: str, params: dict | None = None, intentos: int = 3):
    s = _sesion()
    params = dict(params or {})
    if "quoteSummary" in url:
        crumb = _crumb()
        if crumb:
            params["crumb"] = crumb
    for k in range(intentos):
        try:
            r = s.get(url, params=params, timeout=(5, 20))
        except requests.RequestException:
            time.sleep(1 + k)
            continue
        if r.status_code == 429:
            time.sleep(2 + 3 * k)
            continue
        return r
    return None


# =============================== Precios ============================================
def parsear_chart(js: dict) -> tuple[pd.DataFrame, dict]:
    """Respuesta de `chart` → (DataFrame con `cierre` y `ajustado`, meta). Lanza ValueError si no hay datos."""
    res = (js.get("chart", {}).get("result") or [None])[0]
    if not res or not res.get("timestamp"):
        raise ValueError("Yahoo no devolvió precios para este símbolo.")
    ind = res["indicators"]
    cierre = ind["quote"][0]["close"]
    ajust = (ind.get("adjclose") or [{}])[0].get("adjclose", cierre)
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    df = pd.DataFrame({"cierre": cierre, "ajustado": ajust}, index=idx).dropna(how="all")
    df = df[~df.index.duplicated(keep="last")]
    return df, res.get("meta", {})


def a_semanal(df: pd.DataFrame) -> pd.DataFrame:
    """Barras semanales con cierre de viernes (así se alinean mercados con feriados distintos)."""
    semanal = df.resample("W-FRI").last().dropna(how="all")
    # La semana en curso aún no cierra: su etiqueta (viernes) queda en el futuro y desalinea mercados. Se descarta.
    hoy = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    return semanal[semanal.index <= hoy]


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def precios(ticker: str, anios: int = 10) -> tuple[pd.DataFrame, dict] | None:
    """Precios semanales (`cierre`, `ajustado`) y metadatos. None si Yahoo no responde o no existe el símbolo."""
    fin = int(time.time())
    ini = fin - int(anios * 365.25 * 86400)
    r = _get(f"{BASE}/v8/finance/chart/{ticker}",
             {"period1": ini, "period2": fin, "interval": "1wk", "events": "div,splits",
              "includeAdjustedClose": "true"})
    if r is None or r.status_code != 200:
        return None
    try:
        df, meta = parsear_chart(r.json())
    except (ValueError, KeyError, IndexError):
        return None
    return a_semanal(df), meta


def precios_varios(tickers: list[str], anios: int = 10) -> dict[str, tuple[pd.DataFrame, dict] | None]:
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda t: precios(t, anios), tickers))
    return dict(zip(tickers, res))


# =============================== Tipo de cambio =====================================
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fx_por_usd(moneda: str, anios: int = 10) -> pd.Series | None:
    """Unidades de `moneda` por 1 USD, semanal. USD → serie de unos (se arma con el índice de otra serie)."""
    if moneda == "USD":
        return None
    r = precios(f"{moneda}=X", anios)
    return None if r is None else r[0]["cierre"].dropna()


def convertir(px: pd.Series, moneda: str, destino: str, anios: int = 10) -> pd.Series | None:
    """Convierte una serie de precios de `moneda` a `destino` pasando por USD. None si falta el tipo de cambio."""
    if moneda == destino:
        return px
    usd = px
    if moneda != "USD":
        f = fx_por_usd(moneda, anios)
        if f is None:
            return None
        usd = px / f.reindex(px.index, method="ffill")
    if destino == "USD":
        return usd.dropna()
    g = fx_por_usd(destino, anios)
    if g is None:
        return None
    return (usd * g.reindex(usd.index, method="ffill")).dropna()


# =============================== Perfil e indicadores ===============================
def _raw(d: dict, modulo: str, clave: str):
    v = (d.get(modulo) or {}).get(clave)
    if isinstance(v, dict):
        v = v.get("raw")
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return v


def parsear_perfil(js: dict, ticker: str) -> dict:
    """Respuesta de `quoteSummary` → diccionario plano con unidades uniformes (fracciones, no porcentajes)."""
    res = (js.get("quoteSummary", {}).get("result") or [None])[0]
    if not res:
        raise ValueError("Yahoo no devolvió información de la empresa.")
    g = lambda m, k: _raw(res, m, k)
    de = g("financialData", "debtToEquity")
    out = {
        "ticker": ticker,
        "nombre": (res.get("price") or {}).get("longName") or (res.get("price") or {}).get("shortName") or ticker,
        "moneda": (res.get("price") or {}).get("currency"),
        "bolsa": (res.get("price") or {}).get("exchangeName"),
        "sector": (res.get("assetProfile") or {}).get("sector"),
        "industria": (res.get("assetProfile") or {}).get("industry"),
        "pais": (res.get("assetProfile") or {}).get("country"),
        "resumen": (res.get("assetProfile") or {}).get("longBusinessSummary"),
        "cap_mercado": g("price", "marketCap") or g("summaryDetail", "marketCap"),
        "pe": g("summaryDetail", "trailingPE"),
        "pe_adelantado": g("summaryDetail", "forwardPE"),
        "pb": g("defaultKeyStatistics", "priceToBook"),
        "ev_ebitda": g("defaultKeyStatistics", "enterpriseToEbitda"),
        "div_yield": g("summaryDetail", "dividendYield"),
        "payout": g("summaryDetail", "payoutRatio"),
        "roe": g("financialData", "returnOnEquity"),
        "roa": g("financialData", "returnOnAssets"),
        "margen_neto": g("financialData", "profitMargins") or g("defaultKeyStatistics", "profitMargins"),
        "margen_operativo": g("financialData", "operatingMargins"),
        "de": None if de is None else de / 100,          # Yahoo lo entrega en porcentaje
        "crec_ingresos": g("financialData", "revenueGrowth"),
        "beta_yahoo": g("defaultKeyStatistics", "beta") or g("summaryDetail", "beta"),
    }
    out["banderas"] = banderas(out)
    return out


def banderas(p: dict) -> list[str]:
    """Avisos de calidad de dato. No corrigen nada: solo advierten para no sacar conclusiones de un error de unidades."""
    av = []
    if p.get("pb") is not None and p["pb"] < 0.05:
        av.append("P/B dudoso (posible mezcla de monedas entre precio y patrimonio, típico en ADR).")
    if p.get("pe") is not None and (p["pe"] < 0 or p["pe"] > 300):
        av.append("P/E negativo o extremo: la utilidad es negativa o muy pequeña, no es comparable.")
    if p.get("div_yield") is not None and p["div_yield"] > 0.4:
        av.append("Rentabilidad por dividendo mayor a 40 %: revisa la unidad en Yahoo.")
    if p.get("roe") is not None and abs(p["roe"]) > 1.5:
        av.append("ROE fuera de ±150 %: suele ser patrimonio muy pequeño o negativo.")
    return av


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def perfil(ticker: str) -> dict | None:
    r = _get(f"{BASE}/v10/finance/quoteSummary/{ticker}", {"modules": MODULOS})
    if r is None or r.status_code != 200:
        return None
    try:
        return parsear_perfil(r.json(), ticker)
    except (ValueError, KeyError, IndexError):
        return None


def perfiles(tickers: list[str]) -> dict[str, dict | None]:
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(perfil, tickers))
    return dict(zip(tickers, res))


# =============================== Serie en la moneda de análisis =====================
def serie_en(ticker: str, moneda_base: str, anios: int, campo: str = "ajustado") -> tuple[pd.Series, str] | None:
    """Precio semanal del ticker en `moneda_base` ('LOCAL' = la propia). Devuelve (serie, moneda) o None."""
    r = precios(ticker, anios)
    if r is None:
        return None
    df, meta = r
    moneda = meta.get("currency") or "USD"
    px = df[campo].dropna()
    if moneda_base == "LOCAL" or moneda == moneda_base:
        return px, moneda
    conv = convertir(px, moneda, moneda_base, anios)
    return (None if conv is None else (conv, moneda_base))


def panel(tickers: list[str], moneda_base: str, anios: int) -> tuple[pd.DataFrame, dict, list[str]]:
    """Precios en una tabla común. Devuelve (panel, metadatos por ticker, tickers que fallaron)."""
    cuerpo, metas, fallos = {}, {}, []
    datos = precios_varios(tickers, anios)
    for t in tickers:
        if datos.get(t) is None:
            fallos.append(t)
            continue
        s = serie_en(t, moneda_base, anios)
        if s is None:
            fallos.append(t)
            continue
        cuerpo[t] = s[0]
        metas[t] = {**datos[t][1], "moneda_origen": datos[t][1].get("currency"), "moneda_analisis": s[1]}
    df = pd.DataFrame(cuerpo).sort_index()
    return df, metas, fallos
