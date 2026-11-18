"""Catálogo de series: qué se descarga, de dónde y cómo se describe.

Cada entrada es la "ficha técnica" de una serie. Para agregar un indicador
nuevo basta con añadir una entrada aquí; el actualizador y el tablero la
toman automáticamente.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Serie:
    id: str
    nombre: str
    bloque: str
    unidad: str
    frecuencia: str            # Diaria, Mensual, Trimestral, Anual
    fuente: str                # Entidad productora del dato
    proveedor: str             # banrep | datos_gov | fred | oecd | banco_mundial | derivada
    parametros: dict = field(default_factory=dict)
    url_consulta: str = ""     # Página pública para citar/verificar
    nota: str = ""
    transformacion: str = ""   # p. ej. "var_anual" (calculada sobre niveles)
    es_tasa: bool = True       # True si se expresa en % (permite comparar series)


BLOQUES = [
    "Actividad y empleo",
    "Precios",
    "Política monetaria y tasas",
    "Mercado de deuda y acciones",
    "Sector externo",
    "Fiscal",
    "Referencia internacional",
]

_BANREP = "https://www.banrep.gov.co/es/estadisticas"

SERIES: list[Serie] = [
    # --- Actividad y empleo -------------------------------------------------
    Serie(
        "pib_var_anual", "PIB real – variación anual", "Actividad y empleo",
        "%", "Trimestral", "DANE (vía OCDE, Quarterly National Accounts)", "oecd",
        {"flujo": "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1",
         "clave": "Q.Y.COL.S1.S1.B1GQ._Z._Z._Z.XDC.L.N.T0102"},
        "https://www.dane.gov.co/index.php/estadisticas-por-tema/cuentas-nacionales/cuentas-nacionales-trimestrales",
        "Calculada como variación anual del PIB en volumen encadenado (precios 2015), "
        "serie desestacionalizada.",
        transformacion="var_anual",
    ),
    Serie(
        "desempleo", "Tasa de desempleo (desestacionalizada)", "Actividad y empleo",
        "%", "Mensual", "DANE – GEIH (vía OCDE)", "oecd",
        {"flujo": "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
         "clave": "COL..._Z.Y._T.Y_GE15..M"},
        "https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo",
        "Población de 15 años y más, total nacional, ajustada por estacionalidad.",
    ),
    # --- Precios ------------------------------------------------------------
    Serie(
        "ipc_anual", "Inflación anual (IPC total)", "Precios",
        "%", "Mensual", "DANE (vía OCDE, Prices)", "oecd",
        {"flujo": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
         "clave": "COL.M.N.CPI.PA._T.N.GY"},
        "https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc",
        "Variación porcentual anual del índice de precios al consumidor.",
    ),
    Serie(
        "ipc_nucleo", "Inflación básica (sin alimentos ni energía)", "Precios",
        "%", "Mensual", "DANE (vía OCDE, Prices)", "oecd",
        {"flujo": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0",
         "clave": "COL.M.N.CPI.PA._TXCP01_NRG.N.GY"},
        "https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc",
        "IPC excluyendo alimentos y energía; aproxima la inflación subyacente.",
    ),
    # --- Política monetaria y tasas -----------------------------------------
    Serie(
        "tpm", "Tasa de política monetaria (BanRep)", "Política monetaria y tasas",
        "% E.A.", "Diaria", "Banco de la República", "banrep",
        {"flujo": "DF_CBR_DAILY_HIST", "filtro": {"SUBJECT": "IRCBRM01"}},
        _BANREP, "Tasa de intervención fijada por la Junta Directiva del BanRep.",
    ),
    Serie(
        "ibr_on", "IBR overnight (efectiva)", "Política monetaria y tasas",
        "% E.A.", "Diaria", "Banco de la República", "banrep",
        {"flujo": "DF_IBR_DAILY_HIST", "filtro": {"SUBJECT": "IRIBRM00", "UNIT_MEASURE": "ER"}},
        _BANREP, "Indicador Bancario de Referencia a un día, tasa efectiva anual.",
    ),
    Serie(
        "ibr_3m", "IBR 3 meses (efectiva)", "Política monetaria y tasas",
        "% E.A.", "Diaria", "Banco de la República", "banrep",
        {"flujo": "DF_IBR_DAILY_HIST", "filtro": {"SUBJECT": "IRIBRM03", "UNIT_MEASURE": "ER"}},
        _BANREP, "Indicador Bancario de Referencia a tres meses, tasa efectiva anual.",
    ),
    # --- Mercado de deuda y acciones ----------------------------------------
    Serie(
        "tes_1", "TES tasa fija – 1 año", "Mercado de deuda y acciones",
        "%", "Mensual", "Banco de la República", "banrep",
        {"flujo": "DF_TES_MONTHLY_HIST", "filtro": {"SUBJECT": "IRGBRY01"}, "escala": 100},
        _BANREP, "Rendimiento de TES en pesos a 1 año (curva cero cupón, promedio mensual).",
    ),
    Serie(
        "tes_5", "TES tasa fija – 5 años", "Mercado de deuda y acciones",
        "%", "Mensual", "Banco de la República", "banrep",
        {"flujo": "DF_TES_MONTHLY_HIST", "filtro": {"SUBJECT": "IRGBRY05"}, "escala": 100},
        _BANREP, "Rendimiento de TES en pesos a 5 años (curva cero cupón, promedio mensual).",
    ),
    Serie(
        "tes_10", "TES tasa fija – 10 años", "Mercado de deuda y acciones",
        "%", "Mensual", "Banco de la República", "banrep",
        {"flujo": "DF_TES_MONTHLY_HIST", "filtro": {"SUBJECT": "IRGBRY10"}, "escala": 100},
        _BANREP, "Rendimiento de TES en pesos a 10 años (curva cero cupón, promedio mensual).",
    ),
    Serie(
        "colcap", "Índice COLCAP", "Mercado de deuda y acciones",
        "puntos", "Mensual", "Bolsa de Valores de Colombia (vía BanRep)", "banrep",
        {"flujo": "DF_COLCAP_MONTHLY_HIST", "filtro": {"SUBJECT": "SP"}},
        _BANREP, "Índice de capitalización bursátil de la BVC, cierre mensual.",
        es_tasa=False,
    ),
    Serie(
        "spread_tes_ust", "Diferencial TES 10A – Tesoro EE. UU. 10A", "Mercado de deuda y acciones",
        "p.p.", "Mensual", "Cálculo propio con BanRep y FRED", "derivada",
        {"formula": ("tes_10", "ust_10")},
        "", "Diferencia en puntos porcentuales entre el TES 10 años en pesos y el "
            "Tesoro de EE. UU. a 10 años (promedio mensual). Mezcla riesgo país y "
            "diferencial de inflación esperada; no es un CRP puro.",
    ),
    # --- Sector externo -----------------------------------------------------
    Serie(
        "trm", "Tasa Representativa del Mercado (TRM)", "Sector externo",
        "COP por USD", "Diaria", "Superintendencia Financiera (datos.gov.co)", "datos_gov",
        {"recurso": "32sa-8pi3"},
        "https://www.datos.gov.co/Econom-a-y-Finanzas/Tasa-de-Cambio-Representativa-del-Mercado-Historic/mcec-87by",
        "Tasa de cambio oficial certificada diariamente.",
        es_tasa=False,
    ),
    Serie(
        "cuenta_corriente", "Cuenta corriente (% del PIB)", "Sector externo",
        "% PIB", "Anual", "Banco Mundial – WDI (con datos BanRep)", "banco_mundial",
        {"indicador": "BN.CAB.XOKA.GD.ZS"},
        "https://data.worldbank.org/indicator/BN.CAB.XOKA.GD.ZS?locations=CO",
    ),
    Serie(
        "ied", "Inversión extranjera directa neta (% del PIB)", "Sector externo",
        "% PIB", "Anual", "Banco Mundial – WDI", "banco_mundial",
        {"indicador": "BX.KLT.DINV.WD.GD.ZS"},
        "https://data.worldbank.org/indicator/BX.KLT.DINV.WD.GD.ZS?locations=CO",
    ),
    # --- Fiscal -------------------------------------------------------------
    Serie(
        "deuda_gobierno", "Deuda del gobierno central (% del PIB)", "Fiscal",
        "% PIB", "Anual", "Banco Mundial – WDI (FMI GFS)", "banco_mundial",
        {"indicador": "GC.DOD.TOTL.GD.ZS"},
        "https://data.worldbank.org/indicator/GC.DOD.TOTL.GD.ZS?locations=CO",
        "Para cifras oficiales recientes contrastar con el Marco Fiscal de Mediano Plazo (MinHacienda).",
    ),
    Serie(
        "balance_fiscal", "Balance del gobierno central (% del PIB)", "Fiscal",
        "% PIB", "Anual", "Banco Mundial – WDI (FMI GFS)", "banco_mundial",
        {"indicador": "GC.NLD.TOTL.GD.ZS"},
        "https://data.worldbank.org/indicator/GC.NLD.TOTL.GD.ZS?locations=CO",
        "Préstamo neto (+) / endeudamiento neto (−).",
    ),
    # --- Referencia internacional -------------------------------------------
    Serie(
        "ust_10", "Tesoro EE. UU. 10 años", "Referencia internacional",
        "%", "Diaria", "Federal Reserve (vía FRED)", "fred",
        {"serie": "DGS10"}, "https://fred.stlouisfed.org/series/DGS10",
        "Tasa libre de riesgo de referencia en USD para el CAPM.",
    ),
    Serie(
        "breakeven_10", "Inflación esperada EE. UU. 10 años (breakeven)", "Referencia internacional",
        "%", "Diaria", "Federal Reserve (vía FRED)", "fred",
        {"serie": "T10YIE"}, "https://fred.stlouisfed.org/series/T10YIE",
        "Diferencia entre bono nominal y TIPS a 10 años; insumo para la paridad de Fisher.",
    ),
    Serie(
        "ipc_usa", "Inflación anual EE. UU. (CPI-U)", "Referencia internacional",
        "%", "Mensual", "BLS (vía FRED)", "fred",
        {"serie": "CPIAUCSL"}, "https://fred.stlouisfed.org/series/CPIAUCSL",
        "Calculada como variación a 12 meses del índice desestacionalizado.",
        transformacion="var_anual",
    ),
]

POR_ID: dict[str, Serie] = {s.id: s for s in SERIES}


def series_de_bloque(bloque: str) -> list[Serie]:
    return [s for s in SERIES if s.bloque == bloque]
