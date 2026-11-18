"""Almacenamiento local en CSV/JSON (legible, versionable con git y citable).

datos/
  series/<id>.csv                  fecha,valor
  registro_actualizacion.json      estado de la última descarga por serie
  damodaran/betas_<universo>.csv
  damodaran/parametros_colombia.json
  damodaran/historial_parametros.csv   una fila por versión distinta de supuestos
  latam/betas_latam_propio.csv     beta propio por industria (cuaderno de Yahoo Finance)
  latam/empresas_latam.csv         acciones detrás de cada industria
  latam/metadatos.json             fecha de la corrida, cobertura y τ del beta combinado
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent / "datos"
DIR_SERIES = RAIZ / "series"
DIR_DAMODARAN = RAIZ / "damodaran"
DIR_LATAM = RAIZ / "latam"
REGISTRO = RAIZ / "registro_actualizacion.json"


def _asegurar() -> None:
    DIR_SERIES.mkdir(parents=True, exist_ok=True)
    DIR_DAMODARAN.mkdir(parents=True, exist_ok=True)


# --- Series --------------------------------------------------------------------
def guardar_serie(id_serie: str, df: pd.DataFrame) -> None:
    _asegurar()
    df.to_csv(DIR_SERIES / f"{id_serie}.csv", index=False, date_format="%Y-%m-%d")


def leer_serie(id_serie: str) -> pd.DataFrame | None:
    ruta = DIR_SERIES / f"{id_serie}.csv"
    if not ruta.exists():
        return None
    return pd.read_csv(ruta, parse_dates=["fecha"])


def leer_registro() -> dict:
    if not REGISTRO.exists():
        return {}
    return json.loads(REGISTRO.read_text(encoding="utf-8"))


def guardar_registro(registro: dict) -> None:
    _asegurar()
    REGISTRO.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Damodaran -----------------------------------------------------------------
_CAMPOS_HISTORIAL = [
    "fecha_archivo", "erp_madura", "calificacion_moodys", "spread_default_calificacion",
    "crp_calificacion", "cds_neto", "crp_cds", "tasa_impositiva_marginal",
]


def guardar_damodaran(paquete: dict) -> None:
    _asegurar()
    for universo, df in paquete["betas"].items():
        df.to_csv(DIR_DAMODARAN / f"betas_{universo}.csv", index=False)
    if "multiplos" in paquete:
        paquete["multiplos"].to_csv(DIR_DAMODARAN / "multiplos_emergentes.csv", index=False)
    pais = dict(paquete["pais"], fechas_betas=paquete["fechas_betas"],
                fecha_multiplos=paquete.get("fecha_multiplos", ""),
                descargado=paquete["descargado"])
    (DIR_DAMODARAN / "parametros_colombia.json").write_text(
        json.dumps(pais, ensure_ascii=False, indent=2), encoding="utf-8")

    # Historial: solo se agrega una fila cuando cambian los supuestos.
    ruta = DIR_DAMODARAN / "historial_parametros.csv"
    nueva = pd.DataFrame([{**{c: pais[c] for c in _CAMPOS_HISTORIAL},
                           "descargado": paquete["descargado"]}])
    if ruta.exists():
        hist = pd.read_csv(ruta)
        ultima = hist.iloc[-1][_CAMPOS_HISTORIAL].astype(str).tolist()
        if ultima == nueva.iloc[0][_CAMPOS_HISTORIAL].astype(str).tolist():
            return
        hist = pd.concat([hist, nueva], ignore_index=True)
    else:
        hist = nueva
    hist.to_csv(ruta, index=False)


UNIVERSOS_PROPIOS = ("latam_propio", "latam_combinado")


def leer_betas(universo: str, tau: float | None = None) -> pd.DataFrame | None:
    """Betas por industria. Universos de Damodaran (emergentes, global, eeuu) o propios de LatAm."""
    if universo in UNIVERSOS_PROPIOS:
        propio = leer_betas_propios()
        if propio is None:
            return None
        if universo == "latam_propio":
            return propio
        dam = leer_betas("emergentes")
        if dam is None:
            return None
        from . import beta_propio
        if tau is None:
            tau = (leer_meta_propia() or {}).get("tau")
        return beta_propio.combinar(propio, dam, tau)
    ruta = DIR_DAMODARAN / f"betas_{universo}.csv"
    return pd.read_csv(ruta) if ruta.exists() else None


# --- Beta propio de Latinoamérica (cuaderno de Yahoo Finance) -------------------------
def guardar_betas_propios(propio: pd.DataFrame, empresas: pd.DataFrame, meta: dict) -> None:
    DIR_LATAM.mkdir(parents=True, exist_ok=True)
    propio.to_csv(DIR_LATAM / "betas_latam_propio.csv", index=False)
    empresas.to_csv(DIR_LATAM / "empresas_latam.csv", index=False)
    (DIR_LATAM / "metadatos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                              encoding="utf-8")


def leer_betas_propios() -> pd.DataFrame | None:
    ruta = DIR_LATAM / "betas_latam_propio.csv"
    return pd.read_csv(ruta) if ruta.exists() else None


def leer_empresas_propias() -> pd.DataFrame | None:
    ruta = DIR_LATAM / "empresas_latam.csv"
    return pd.read_csv(ruta) if ruta.exists() else None


def leer_meta_propia() -> dict | None:
    ruta = DIR_LATAM / "metadatos.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def leer_multiplos() -> pd.DataFrame | None:
    ruta = DIR_DAMODARAN / "multiplos_emergentes.csv"
    return pd.read_csv(ruta) if ruta.exists() else None


def leer_parametros_pais() -> dict | None:
    ruta = DIR_DAMODARAN / "parametros_colombia.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def leer_historial_parametros() -> pd.DataFrame | None:
    ruta = DIR_DAMODARAN / "historial_parametros.csv"
    return pd.read_csv(ruta) if ruta.exists() else None


def ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")
