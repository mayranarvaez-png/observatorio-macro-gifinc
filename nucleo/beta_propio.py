"""Beta desapalancada propia de Latinoamérica (Yahoo Finance) y su combinación con Damodaran.

El cuaderno `Beta_Latinoamerica_CAPM.ipynb` estima, con acciones de la región, el beta de cada
industria de Damodaran y lo exporta a `resultados_beta_latam.xlsx`. Este módulo:

1. convierte esa salida al mismo formato que los archivos de Damodaran (`betas_<universo>.csv`),
   de modo que el selector de sector del tablero pueda usarla sin cambios;
2. calcula un beta "combinado" que le da más peso al beta propio cuando está bien medido y
   más peso a Damodaran cuando la muestra es pequeña (contracción tipo Bayes empírico).

Todo son funciones puras (sin Streamlit ni acceso a disco) para poder probarlas.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

# El cuaderno desapalanca con 25 % (TAX_DESAPALANCAR) y divide por (1 − caja/valor de la firma).
TASA_DESAPALANCAR = 0.25
Z95 = 1.96                 # el intervalo del cuaderno es bootstrap percentil al 95 %
MIN_FIRMAS_IC = 3          # el cuaderno solo calcula intervalo con 3 o más firmas
MIN_FIRMAS_TAU = 5         # sectores usados para estimar el desacuerdo entre métodos
TAU_MIN = 0.05             # piso del desacuerdo (evita pesos de 100 % al beta propio)

# Mismas industrias que el cuaderno trata como financieras (no se desapalancan allá).
FIN_KEYS = ("Bank", "Insurance", "Reinsurance", "Brokerage", "Financial Svcs", "Investments & Asset")

COLS_SECTOR = ["industria", "firmas", "paises", "beta_prom", "ic_lo", "ic_hi", "confianza"]
COLS_ACCIONES = ["ticker", "empresa", "pais_es", "industria", "beta_vs_indice_pais", "r2",
                 "anios", "incluir", "motivo_exclusion"]
# Columnas adicionales de la hoja «Acciones» que se guardan si existen (para los gráficos de la metodología).
COLS_ACCIONES_EXTRA = ["pais", "moneda", "n_sem", "se", "beta_dimson", "beta_blume", "beta_ilf", "sem_sin_cambio",
                       "n_recortes", "max_abs_ret"]
COLS_DAMODARAN = ["industria", "n_empresas", "beta_apalancada", "de", "caja_valor_firma",
                  "beta_desapalancada", "beta_desapalancada_caja"]
COLS_BETA = ["beta_apalancada", "beta_desapalancada", "beta_desapalancada_caja"]

FUENTE_TEXTO = ("Yahoo Finance, retornos logarítmicos semanales en USD, historial completo de cada "
                "acción (mínimo 3 años), contra el ETF de su país; promedio balanceado por país; "
                "desapalancado con el D/E y la caja de Damodaran (emergentes).")


def es_financiera(industria: str) -> bool:
    return str(industria).startswith(FIN_KEYS)


def desapalancar(beta_l, de, caja=0.0, t: float = TASA_DESAPALANCAR):
    """βU = βL / [1 + (1 − t)·D/E] / (1 − caja/valor de la firma)."""
    return beta_l / (1 + (1 - t) * de) / (1 - caja)


# =============================== Importación ========================================
def _exigir(df: pd.DataFrame, columnas: list[str], hoja: str) -> None:
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise ValueError(f"La hoja «{hoja}» no tiene las columnas {faltan}. "
                         "¿Es el archivo resultados_beta_latam.xlsx que genera el cuaderno?")


def construir_propio(sectores: pd.DataFrame, dam_em: pd.DataFrame,
                     acciones: pd.DataFrame | None = None) -> pd.DataFrame:
    """Hoja «Beta por sector» del cuaderno → formato de los betas de Damodaran del tablero.

    Se parte del beta apalancado promedio (balanceado por país) y se desapalanca aquí con el D/E y
    la caja de Damodaran del propio tablero. Así las industrias financieras quedan en el mismo
    espacio que la columna de Damodaran (donde también se desapalancan), y la comparación es justa.

    `error_est` es el error estándar de βU que se usa para ponderar: el mayor entre el del bootstrap
    (intervalo del cuaderno) y la dispersión entre empresas dividida por √n. Con 3 o 4 firmas el
    bootstrap suele subestimar la incertidumbre, y el segundo término lo corrige.
    """
    _exigir(sectores, COLS_SECTOR, "Beta por sector")
    dam = dam_em[["industria", "de", "caja_valor_firma"]]
    m = sectores[COLS_SECTOR].merge(dam, on="industria", how="inner")
    t = TASA_DESAPALANCAR
    out = pd.DataFrame({
        "industria": m["industria"],
        "n_empresas": m["firmas"].astype(int),
        "paises": m["paises"].astype(int),
        "beta_apalancada": m["beta_prom"],
        "de": m["de"],
        "caja_valor_firma": m["caja_valor_firma"],
        "beta_desapalancada": desapalancar(m["beta_prom"], m["de"], 0.0, t),
        "beta_desapalancada_caja": desapalancar(m["beta_prom"], m["de"], m["caja_valor_firma"], t),
    })
    lo = desapalancar(m["ic_lo"], m["de"], m["caja_valor_firma"], t)
    hi = desapalancar(m["ic_hi"], m["de"], m["caja_valor_firma"], t)
    out["bu_lo"], out["bu_hi"] = lo, hi
    out["error_est"] = (hi - lo) / (2 * Z95)
    if acciones is not None:
        ok = acciones[acciones["incluir"].astype(bool)]
        g = ok.groupby("industria")["beta_vs_indice_pais"]
        disp = (g.std(ddof=1) / np.sqrt(g.count())).reindex(out["industria"]).to_numpy()
        factor = (1 / (1 + (1 - t) * out["de"]) / (1 - out["caja_valor_firma"])).to_numpy()
        out["error_est"] = np.fmax(out["error_est"].to_numpy(), disp * factor)
        out.loc[out["n_empresas"] < MIN_FIRMAS_IC, "error_est"] = np.nan
    out["confianza"] = m["confianza"]
    out["financiera"] = m["industria"].map(es_financiera)
    return out.sort_values("n_empresas", ascending=False).reset_index(drop=True)


def importar(contenido: bytes, dam_em: pd.DataFrame, fecha_corrida: str) -> dict:
    """Lee el Excel del cuaderno. Devuelve {propio, empresas, meta} listos para guardar."""
    libro = pd.read_excel(io.BytesIO(contenido), sheet_name=None)
    for hoja in ("Beta por sector", "Acciones"):
        if hoja not in libro:
            raise ValueError(f"El archivo no tiene la hoja «{hoja}».")
    sectores, acciones = libro["Beta por sector"], libro["Acciones"]
    _exigir(acciones, COLS_ACCIONES, "Acciones")
    propio = construir_propio(sectores, dam_em, acciones)
    perdidos = sorted(set(sectores["industria"]) - set(propio["industria"]))
    empresas = acciones[COLS_ACCIONES + [c for c in COLS_ACCIONES_EXTRA if c in acciones.columns]].copy()
    empresas["incluir"] = empresas["incluir"].astype(bool)
    dam_bu = dam_em.set_index("industria")["beta_desapalancada_caja"]
    tau = estimar_tau(propio, dam_bu)
    meta = {
        "fecha_corrida": fecha_corrida,
        "fuente": FUENTE_TEXTO,
        "acciones_total": int(len(empresas)),
        "acciones_incluidas": int(empresas["incluir"].sum()),
        "sectores": int(len(propio)),
        "sectores_5_o_mas": int((propio["n_empresas"] >= 5).sum()),
        "paises": sorted(empresas.loc[empresas["incluir"], "pais_es"].dropna().unique().tolist()),
        "tau": float(tau),
        "sectores_sin_equivalente_en_damodaran": perdidos,
    }
    extras = {}
    if "Estabilidad" in libro:
        extras["estabilidad"] = libro["Estabilidad"]
    if "Beta por pais" in libro:
        extras["beta_por_pais"] = libro["Beta por pais"]
    return {"propio": propio, "empresas": empresas, "meta": meta, "extras": extras}


# =============================== Combinación ========================================
def estimar_tau(propio: pd.DataFrame, dam_bu: pd.Series) -> float:
    """Desacuerdo típico entre el beta propio y el de Damodaran (desviación, en unidades de βU).

    τ² = E[(βU propio − βU Damodaran)²] − E[error estándar²], con piso en TAU_MIN². Se calcula con
    los sectores de 5 o más firmas, donde el beta propio está razonablemente medido. Es una
    heurística de Bayes empírico: no pretende ser un parámetro «verdadero».
    """
    x = propio[(propio["n_empresas"] >= MIN_FIRMAS_TAU) & propio["error_est"].notna()]
    x = x[x["industria"].isin(dam_bu.index)]
    if x.empty:
        return 0.15
    dif = x["beta_desapalancada_caja"].to_numpy() - dam_bu.loc[x["industria"]].to_numpy()
    tau2 = float(np.mean(dif ** 2) - np.mean(x["error_est"].to_numpy() ** 2))
    return float(np.sqrt(max(tau2, TAU_MIN ** 2)))


def pesos(propio: pd.DataFrame, tau: float) -> pd.Series:
    """Peso del beta propio: τ² / (τ² + EE²). Cero si no hay error estándar (menos de 3 firmas)."""
    ee = propio["error_est"].where(propio["n_empresas"] >= MIN_FIRMAS_IC)
    w = tau ** 2 / (tau ** 2 + ee ** 2)
    return w.fillna(0.0).set_axis(propio["industria"])


def combinar(propio: pd.DataFrame, dam_em: pd.DataFrame, tau: float | None = None) -> pd.DataFrame:
    """Beta combinado para TODAS las industrias de Damodaran (emergentes).

    βU combinado = w·βU propio + (1 − w)·βU Damodaran, con w según el error estándar del beta
    propio. Las industrias sin beta propio quedan igual a Damodaran (w = 0).
    """
    dam = dam_em[COLS_DAMODARAN].copy()
    if tau is None:
        tau = estimar_tau(propio, dam_em.set_index("industria")["beta_desapalancada_caja"])
    w = pesos(propio, tau)
    p = propio.set_index("industria")
    out = dam.set_index("industria")
    peso = w.reindex(out.index).fillna(0.0)
    for c in COLS_BETA:
        propio_c = p[c].reindex(out.index)
        out[c] = np.where(peso > 0, peso * propio_c + (1 - peso) * out[c], out[c])
    out["n_empresas"] = out["n_empresas"].astype(int) + p["n_empresas"].reindex(out.index).fillna(0).astype(int)
    out["peso_propio"] = peso
    return out.reset_index()
