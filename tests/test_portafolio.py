"""Pruebas de los indicadores y del portafolio con series sintéticas de resultado conocido."""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import portafolio as pf  # noqa: E402
from nucleo import yahoo  # noqa: E402


def serie(valores):
    return pd.Series(valores, index=pd.date_range("2020-01-03", periods=len(valores), freq="W-FRI"))


def test_cagr_de_retorno_constante():
    r = serie([0.01] * 52)
    assert math.isclose(pf.cagr(r), 1.01 ** 52 - 1)


def test_volatilidad_anualiza_con_raiz_de_52():
    r = serie([0.01, -0.01] * 26)
    assert math.isclose(pf.vol_anual(r), r.std(ddof=1) * math.sqrt(52))


def test_caida_maxima():
    # sube 10 %, cae 50 %, sube 10 %: la caída desde el pico es −50 %
    assert math.isclose(pf.caida_maxima(serie([0.10, -0.50, 0.10])), -0.5)


def test_var_y_cvar_historicos():
    r = serie(list(np.linspace(-0.10, 0.10, 101)))
    assert math.isclose(pf.var_historico(r, 0.95), 0.09, abs_tol=1e-9)
    assert pf.cvar_historico(r, 0.95) > pf.var_historico(r, 0.95)


def test_beta_de_activo_apalancado_dos_veces():
    rng = np.random.default_rng(3)
    m = serie(rng.normal(0.002, 0.02, 300))
    ba = pf.beta_alfa(2 * m, m, rf=0.0)
    assert math.isclose(ba["beta"], 2.0, rel_tol=1e-9)
    assert math.isclose(ba["corr"], 1.0, rel_tol=1e-9)
    assert abs(ba["alfa"]) < 1e-9


def test_sharpe_signo_y_valor():
    r = serie([0.01, 0.00] * 26)
    esperado = (r.mean() * 52 - 0.02) / (r.std(ddof=1) * math.sqrt(52))
    assert math.isclose(pf.sharpe(r, 0.02), esperado)


def test_pesos_se_normalizan_y_rechazan_negativos():
    assert math.isclose(pf.pesos_validos([2, 2]).sum(), 1.0)
    try:
        pf.pesos_validos([1, -1])
    except ValueError:
        pass
    else:
        raise AssertionError("debía rechazar pesos negativos")


def test_n_efectivo_y_diversificacion():
    assert math.isclose(pf.n_efectivo([1, 1, 1, 1]), 4.0)
    assert math.isclose(pf.n_efectivo([1, 0, 0, 0]), 1.0)
    cov = np.array([[0.04, 0.04], [0.04, 0.04]])          # correlación perfecta
    assert math.isclose(pf.ratio_diversificacion(cov, [0.5, 0.5]), 1.0)
    cov0 = np.array([[0.04, 0.0], [0.0, 0.04]])           # sin correlación
    assert math.isclose(pf.ratio_diversificacion(cov0, [0.5, 0.5]), math.sqrt(2))


def test_contribucion_al_riesgo_suma_uno():
    cov = np.array([[0.04, 0.01, 0.0], [0.01, 0.09, 0.02], [0.0, 0.02, 0.16]])
    c = pf.contribucion_riesgo(cov, [0.3, 0.3, 0.4])
    assert math.isclose(c.sum(), 1.0)
    assert c[2] > 0.4          # el activo más volátil aporta más que su peso


def test_minima_varianza_elige_el_activo_sin_correlacion_de_menor_riesgo():
    mu = np.array([0.08, 0.10])
    cov = np.array([[0.01, 0.0], [0.0, 0.04]])
    w = pf.optimos(mu, cov, 0.02)["minima_varianza"]
    # solución analítica: w1 = σ2²/(σ1²+σ2²) = 0.8
    assert math.isclose(w[0], 0.8, abs_tol=0.03)


def test_maximo_sharpe_supera_al_igual_ponderado():
    mu = np.array([0.05, 0.12, 0.09])
    cov = np.array([[0.02, 0.0, 0.0], [0.0, 0.06, 0.01], [0.0, 0.01, 0.04]])
    w = pf.optimos(mu, cov, 0.02)["maximo_sharpe"]
    sh = lambda x: (x @ mu - 0.02) / math.sqrt(x @ cov @ x)
    assert sh(w) >= sh(np.ones(3) / 3) - 1e-9
    assert math.isclose(w.sum(), 1.0) and (w >= 0).all()


def test_retornos_por_periodo():
    idx = pd.date_range("2018-01-05", "2024-06-28", freq="W-FRI")
    p = pd.DataFrame({"A": np.linspace(100, 200, len(idx))}, index=idx)
    t = pf.retornos_por_periodo(p)
    assert t.loc["A", "1 año"] > 0 and t.loc["A", "5 años (anual)"] > 0
    assert t.loc["A", "1 mes"] < t.loc["A", "1 año"]


def test_parsear_chart_y_perfil_con_respuestas_de_ejemplo():
    js = {"chart": {"result": [{"meta": {"currency": "COP"}, "timestamp": [1700000000, 1700600000, 1701200000],
                                "indicators": {"quote": [{"close": [100, 101, 103]}],
                                               "adjclose": [{"adjclose": [95, 96, 98]}]}}]}}
    df, meta = yahoo.parsear_chart(js)
    assert list(df.columns) == ["cierre", "ajustado"] and meta["currency"] == "COP" and len(df) == 3
    sj = {"quoteSummary": {"result": [{"price": {"currency": "USD", "longName": "X"},
                                       "summaryDetail": {"trailingPE": {"raw": 8.0}},
                                       "defaultKeyStatistics": {"priceToBook": {"raw": 0.0075}},
                                       "financialData": {"debtToEquity": {"raw": 102.0}, "returnOnEquity": {"raw": 0.17}}}]}}
    p = yahoo.parsear_perfil(sj, "X")
    assert math.isclose(p["de"], 1.02) and p["pe"] == 8.0
    assert any("P/B dudoso" in b for b in p["banderas"])      # el caso real de los ADR


def test_a_semanal_descarta_la_semana_en_curso():
    hoy = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    idx = pd.date_range(hoy - pd.Timedelta(days=20), hoy, freq="D")
    df = pd.DataFrame({"cierre": range(len(idx)), "ajustado": range(len(idx))}, index=idx)
    sem = yahoo.a_semanal(df)
    assert (sem.index <= hoy).all()


def test_universo_simbolos_y_paises():
    from nucleo import universo as u
    assert u.simbolo_yahoo("brk.b") == "BRK-B"
    assert u._hong_kong("SEHK:\xa05") == "0005.HK"
    assert u.sufijo("ASML.AS") == ".AS" and u.sufijo("AAPL") == ""
    assert u.PAIS_POR_SUFIJO[u.sufijo("SAN.MC")] == "España"


def test_catalogo_une_fuentes_sin_duplicados():
    from nucleo import universo as u
    us = pd.DataFrame({"ticker": ["AAPL", "SPY", "EC"], "nombre": ["Apple", "SPDR S&P 500", "Ecopetrol ADR"],
                       "bolsa": ["Nasdaq", "NYSE Arca", "NYSE"], "tipo": ["Acción", "ETF", "Acción"],
                       "sp500": [True, False, False], "nasdaq100": [True, False, False], "sector": ["IT", None, None],
                       "industria": [None, None, None]})
    glob = pd.DataFrame({"ticker": ["ASML.AS"], "nombre": ["ASML"], "sector": ["Tech"], "listas": ["AEX"],
                         "pais": ["Países Bajos"], "mercado": ["Euronext Ámsterdam"], "tipo": ["Acción"]})
    cat = u.construir_catalogo(us, glob)
    assert cat["ticker"].is_unique
    fila = cat.set_index("ticker")
    assert fila.loc["AAPL", "listas"] == "S&P 500|Nasdaq-100" and fila.loc["AAPL", "pais"] == "EE. UU."
    assert fila.loc["SPY", "listas"] == "ETF de EE. UU."
    assert fila.loc["ASML.AS", "pais"] == "Países Bajos"
    if u.RUTA_COLOMBIA.exists():                       # EC llega primero desde la lista colombiana
        assert fila.loc["EC", "pais"] == "Colombia"


def test_limpiar_fx_quita_saltos_falsos_y_conserva_devaluaciones():
    idx = pd.date_range("2015-01-02", periods=8, freq="W-FRI")
    fx = pd.Series([2400, 2410, 24.1, 2420, 2430, 3100, 3120, 3130], index=idx, dtype=float)   # error ×100 y devaluación real
    limpio = yahoo.limpiar_fx(fx)
    assert limpio.iloc[2] == 2410                       # la semana errada toma el dato anterior
    assert limpio.iloc[5] == 3100                       # el salto real (que no se revierte) se conserva
    assert limpio.iloc[3] == 2420                       # la semana siguiente queda intacta


def test_rubros_yahoo_conservan_el_ebitda_y_no_dejan_gastos_negativos():
    crudo = pd.DataFrame({2024: {"TotalRevenue": 1000e6, "CostOfRevenue": 700e6, "OperatingIncome": 200e6,
                                 "ReconciledDepreciation": 150e6, "CapitalExpenditure": -80e6, "AccountsReceivable": 90e6,
                                 "Inventory": 60e6, "AccountsPayable": 50e6, "NetPPE": 500e6, "TotalDebt": 300e6,
                                 "CashAndCashEquivalents": 40e6}})
    tabla, avisos = yahoo.a_rubros(crudo)
    v = tabla[2024]
    assert v["Gastos operacionales (sin D&A)"] >= 0                      # la D&A venía dentro del costo
    ebitda = v["Ventas"] - v["Costo de ventas"] - v["Gastos operacionales (sin D&A)"]
    assert math.isclose(ebitda, 200 + 150)                                # utilidad operativa + D&A, en millones
    assert v["CAPEX"] == 80 and v["Capital de trabajo neto operativo (KTNO)"] == 100
    assert any("depreciación venía incluida" in a for a in avisos)
