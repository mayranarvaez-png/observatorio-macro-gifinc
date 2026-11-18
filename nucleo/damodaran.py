"""Descarga y lectura de los insumos de Aswath Damodaran (NYU Stern).

- Betas por industria (mercados emergentes, global y EE. UU.).
- Prima de riesgo de mercado madura (ERP), prima de riesgo país (CRP) y
  tasa impositiva marginal para Colombia.

Damodaran actualiza estos archivos en enero (y la prima de riesgo país también
a mitad de año). Cada descarga se registra en un historial para poder citar la
versión exacta de los supuestos.
"""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import requests

BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
ARCHIVOS_BETA = {
    "emergentes": "betaemerg.xls",
    "global": "betaGlobal.xls",
    "eeuu": "betas.xls",
}
ARCHIVO_PAIS = "ctryprem.xlsx"
ARCHIVOS_MULTIPLOS = {"ev_ebitda": "vebitdaemerg.xls", "pe": "peemerg.xls"}
URL_DATOS = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html"

_COLUMNAS_BETA = {
    "Industry Name": "industria",
    "Number of firms": "n_empresas",
    "Beta": "beta_apalancada",
    "D/E Ratio": "de",
    "Effective Tax rate": "tasa_efectiva",
    "Unlevered beta": "beta_desapalancada",
    "Cash/Firm value": "caja_valor_firma",
    "Unlevered beta corrected for cash": "beta_desapalancada_caja",
}


def _bajar(nombre: str) -> bytes:
    r = requests.get(BASE + nombre, timeout=120)
    r.raise_for_status()
    return r.content


def _fecha_en_hoja(hoja: pd.DataFrame) -> str:
    for _, fila in hoja.head(6).iterrows():
        if str(fila.iloc[0]).lower().startswith("date"):
            valor = fila.iloc[1]
            try:
                return pd.Timestamp(valor).date().isoformat()
            except (ValueError, TypeError):
                return str(valor)
    return ""


def leer_betas(contenido: bytes) -> tuple[pd.DataFrame, str]:
    hoja = pd.read_excel(io.BytesIO(contenido), sheet_name="Industry Averages", header=None)
    fecha = _fecha_en_hoja(hoja)
    fila_titulos = hoja.index[hoja.iloc[:, 0].astype(str).str.strip() == "Industry Name"][0]
    df = hoja.iloc[fila_titulos + 1:].copy()
    df.columns = [str(c).strip() for c in hoja.iloc[fila_titulos]]
    df = df[list(_COLUMNAS_BETA)].rename(columns=_COLUMNAS_BETA)
    df = df.dropna(subset=["industria", "beta_desapalancada"])
    df = df[~df["industria"].astype(str).str.contains("Total Market", case=False)]
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True), fecha


def leer_parametros_pais(contenido: bytes, pais: str = "Colombia") -> dict:
    libro = io.BytesIO(contenido)
    hoja = pd.read_excel(libro, sheet_name="ERPs by country", header=None)
    fecha = _fecha_en_hoja(hoja)

    def valor_de_etiqueta(texto: str) -> float:
        fila = hoja[hoja.iloc[:, 0].astype(str).str.contains(texto, case=False, regex=False)].iloc[0]
        return float(pd.to_numeric(fila.iloc[1:], errors="coerce").dropna().iloc[0])

    erp_madura = valor_de_etiqueta("risk premium for a mature equity market")
    erp_eeuu = valor_de_etiqueta("risk premium for the US")
    multiplicador = valor_de_etiqueta("multiplier to use on the default spread")

    fila = hoja[hoja.iloc[:, 0].astype(str).str.strip() == pais].iloc[0]
    # Columnas: país, región, calificación, spread, ERP total, CRP, CDS neto, ERP total (CDS), CRP (CDS)
    calificacion, spread, erp_total, crp, cds, erp_total_cds, crp_cds = fila.iloc[2:9]

    impuestos = pd.read_excel(io.BytesIO(contenido), sheet_name="Country Tax Rates", header=None)
    fila_imp = impuestos[impuestos.iloc[:, 0].astype(str).str.strip() == pais]
    tasa = float(fila_imp.iloc[0, 1]) if not fila_imp.empty else float("nan")

    return {
        "pais": pais,
        "fecha_archivo": fecha,
        "erp_madura": erp_madura,
        "erp_eeuu": erp_eeuu,
        "multiplicador_volatilidad": multiplicador,
        "calificacion_moodys": str(calificacion),
        "spread_default_calificacion": float(spread),
        "crp_calificacion": float(crp),
        "erp_total_calificacion": float(erp_total),
        "cds_neto": float(cds),
        "crp_cds": float(crp_cds),
        "erp_total_cds": float(erp_total_cds),
        "tasa_impositiva_marginal": tasa,
    }


def _tabla_industria(contenido: bytes) -> tuple[pd.DataFrame, str]:
    hoja = pd.read_excel(io.BytesIO(contenido), sheet_name="Industry Averages", header=None)
    fila = hoja.index[hoja.iloc[:, 0].astype(str).str.strip() == "Industry Name"][0]
    return hoja.iloc[fila + 1:].reset_index(drop=True), _fecha_en_hoja(hoja)


def leer_multiplos(ev_ebitda: bytes, pe: bytes) -> tuple[pd.DataFrame, str]:
    """Múltiplos de mercados emergentes por industria.

    EV/EBITDA: bloque "Only positive EBITDA firms" (columna 3 del archivo).
    P/E: "Current PE" (columna 3).
    """
    ev, fecha = _tabla_industria(ev_ebitda)
    per, _ = _tabla_industria(pe)
    a = pd.DataFrame({"industria": ev.iloc[:, 0], "ev_ebitda": pd.to_numeric(ev.iloc[:, 3], errors="coerce")})
    b = pd.DataFrame({"industria": per.iloc[:, 0], "pe": pd.to_numeric(per.iloc[:, 3], errors="coerce")})
    df = a.merge(b, on="industria", how="outer").dropna(subset=["industria"])
    df = df[~df["industria"].astype(str).str.contains("Total Market", case=False)]
    return df.reset_index(drop=True), fecha


def descargar_todo() -> dict:
    """Descarga los archivos y devuelve betas por universo y parámetros país."""
    salida = {"betas": {}, "fechas_betas": {}, "descargado": date.today().isoformat()}
    for universo, archivo in ARCHIVOS_BETA.items():
        df, fecha = leer_betas(_bajar(archivo))
        salida["betas"][universo] = df
        salida["fechas_betas"][universo] = fecha
    salida["pais"] = leer_parametros_pais(_bajar(ARCHIVO_PAIS))
    salida["multiplos"], salida["fecha_multiplos"] = leer_multiplos(
        _bajar(ARCHIVOS_MULTIPLOS["ev_ebitda"]), _bajar(ARCHIVOS_MULTIPLOS["pe"]))
    return salida
