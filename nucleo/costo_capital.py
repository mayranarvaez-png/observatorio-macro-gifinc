"""Costo de capital para Colombia: CAPM global + prima de riesgo país y WACC.

Todas las tasas se manejan como fracciones (0.05 = 5 %).

Modelo (Damodaran, 2024; Hamada, 1972):
    beta_L  = beta_U * (1 + (1 - t) * D/E)
    Ke_USD  = rf + beta_L * ERP_madura + lambda * CRP
              lambda = 1      (enfoque aditivo / "bludgeon")
              lambda = beta_L (enfoque "beta", el CRP escala con la exposición)
    Ke_COP  = (1 + Ke_USD) * (1 + pi_COL) / (1 + pi_USA) - 1      (paridad de Fisher)
    WACC    = E/V * Ke_COP + D/V * Kd_COP * (1 - t)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

MODOS_CRP = {
    "aditivo": "Aditivo: todo activo colombiano asume el CRP completo (λ = 1)",
    "beta": "Proporcional a β: el CRP se escala con la beta apalancada (λ = β)",
}


@dataclass
class Supuestos:
    rf: float                 # Tasa libre de riesgo USD (Tesoro 10A)
    beta_u: float             # Beta desapalancada
    de: float                 # Deuda / Patrimonio (a valor de mercado)
    tasa_impuesto: float      # Tasa impositiva marginal
    erp: float                # Prima de riesgo de mercado madura
    crp: float                # Prima de riesgo país
    infl_col: float           # Inflación esperada Colombia (largo plazo)
    infl_usa: float           # Inflación esperada EE. UU. (largo plazo)
    kd_cop: float             # Costo de la deuda antes de impuestos, en COP
    modo_crp: str = "aditivo"


def beta_apalancada(beta_u: float, de: float, t: float) -> float:
    return beta_u * (1 + (1 - t) * de)


def fisher(tasa: float, infl_destino: float, infl_origen: float) -> float:
    return (1 + tasa) * (1 + infl_destino) / (1 + infl_origen) - 1


def calcular(s: Supuestos) -> dict:
    bl = beta_apalancada(s.beta_u, s.de, s.tasa_impuesto)
    lam = 1.0 if s.modo_crp == "aditivo" else bl
    prima_mercado = bl * s.erp
    prima_pais = lam * s.crp
    ke_usd = s.rf + prima_mercado + prima_pais
    ke_cop = fisher(ke_usd, s.infl_col, s.infl_usa)
    peso_d = s.de / (1 + s.de)
    peso_e = 1 - peso_d
    kd_neto = s.kd_cop * (1 - s.tasa_impuesto)
    wacc_cop = peso_e * ke_cop + peso_d * kd_neto
    wacc_usd = fisher(wacc_cop, s.infl_usa, s.infl_col)
    return {
        "beta_apalancada": bl,
        "lambda": lam,
        "prima_mercado": prima_mercado,
        "prima_pais": prima_pais,
        "ke_usd": ke_usd,
        "ke_cop": ke_cop,
        "peso_patrimonio": peso_e,
        "peso_deuda": peso_d,
        "kd_neto": kd_neto,
        "wacc_cop": wacc_cop,
        "wacc_usd": wacc_usd,
    }


def tabla_paso_a_paso(s: Supuestos, r: dict, fuentes: dict[str, str]) -> pd.DataFrame:
    """Tabla citable: cada insumo y resultado con su fórmula y fuente."""
    filas = [
        ("Insumo", "Tasa libre de riesgo (rf, USD)", s.rf, "—", fuentes.get("rf", "")),
        ("Insumo", "Beta desapalancada (βU)", s.beta_u, "—", fuentes.get("beta_u", "")),
        ("Insumo", "Deuda / Patrimonio (D/E)", s.de, "—", fuentes.get("de", "")),
        ("Insumo", "Tasa impositiva (t)", s.tasa_impuesto, "—", fuentes.get("t", "")),
        ("Insumo", "Prima de mercado madura (ERP)", s.erp, "—", fuentes.get("erp", "")),
        ("Insumo", "Prima de riesgo país (CRP)", s.crp, "—", fuentes.get("crp", "")),
        ("Insumo", "Inflación esperada Colombia (πCOL)", s.infl_col, "—", fuentes.get("infl_col", "")),
        ("Insumo", "Inflación esperada EE. UU. (πUSA)", s.infl_usa, "—", fuentes.get("infl_usa", "")),
        ("Insumo", "Costo de la deuda antes de impuestos (Kd, COP)", s.kd_cop, "—", fuentes.get("kd", "")),
        ("Resultado", "Beta apalancada (βL)", r["beta_apalancada"], "βU·[1+(1−t)·D/E]", "Hamada (1972)"),
        ("Resultado", "Prima de mercado ajustada", r["prima_mercado"], "βL·ERP", ""),
        ("Resultado", "Prima país aplicada", r["prima_pais"], "λ·CRP", MODOS_CRP[s.modo_crp]),
        ("Resultado", "Costo del patrimonio (Ke, USD)", r["ke_usd"], "rf + βL·ERP + λ·CRP", "CAPM global + CRP"),
        ("Resultado", "Costo del patrimonio (Ke, COP)", r["ke_cop"], "(1+Ke_USD)(1+πCOL)/(1+πUSA) − 1", "Paridad de Fisher"),
        ("Resultado", "Peso del patrimonio (E/V)", r["peso_patrimonio"], "1/(1+D/E)", ""),
        ("Resultado", "Peso de la deuda (D/V)", r["peso_deuda"], "(D/E)/(1+D/E)", ""),
        ("Resultado", "Costo de la deuda después de impuestos", r["kd_neto"], "Kd·(1−t)", ""),
        ("Resultado", "WACC (COP nominal)", r["wacc_cop"], "E/V·Ke + D/V·Kd·(1−t)", ""),
        ("Resultado", "WACC (USD nominal)", r["wacc_usd"], "Fisher inverso", ""),
    ]
    df = pd.DataFrame(filas, columns=["Tipo", "Concepto", "Valor", "Fórmula", "Fuente / nota"])
    return df


def sensibilidad(s: Supuestos, eje_x: str, valores_x, eje_y: str, valores_y,
                 salida: str = "wacc_cop") -> pd.DataFrame:
    """Matriz de sensibilidad de `salida` ante dos supuestos."""
    base = asdict(s)
    matriz = np.empty((len(valores_y), len(valores_x)))
    for i, vy in enumerate(valores_y):
        for j, vx in enumerate(valores_x):
            matriz[i, j] = calcular(Supuestos(**{**base, eje_x: vx, eje_y: vy}))[salida]
    return pd.DataFrame(matriz, index=list(valores_y), columns=list(valores_x))


def wacc_por_industria(betas: pd.DataFrame, s: Supuestos, usar_de_industria: bool = True,
                       columna_beta: str = "beta_desapalancada") -> pd.DataFrame:
    """Aplica los supuestos de mercado a cada industria de Damodaran."""
    base = asdict(s)
    filas = []
    for _, fila in betas.iterrows():
        de = fila["de"] if usar_de_industria else s.de
        r = calcular(Supuestos(**{**base, "beta_u": fila[columna_beta], "de": de}))
        filas.append({
            "Industria": fila["industria"],
            "N.º empresas": int(fila["n_empresas"]),
            "βU": fila[columna_beta],
            "D/E": de,
            "βL": r["beta_apalancada"],
            "Ke USD": r["ke_usd"],
            "Ke COP": r["ke_cop"],
            "WACC COP": r["wacc_cop"],
        })
    return pd.DataFrame(filas)
