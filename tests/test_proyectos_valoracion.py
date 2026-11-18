"""Pruebas de matemática financiera, evaluación de proyectos y valoración."""
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import escenarios as esc  # noqa: E402
from nucleo import finmat  # noqa: E402
from nucleo import proyectos as pr  # noqa: E402
from nucleo import valoracion as val  # noqa: E402

ANCLAS = esc.Anclas(pib_inicial=3.0, pib_largo_plazo=3.0, inflacion_inicial=4.0,
                    inflacion_largo_plazo=3.0, inflacion_usa=2.0, trm_inicial=4000.0)
ESC = esc.construir(ANCLAS, 12, anio_inicial=2027)


# --- Matemática financiera ---------------------------------------------------------
def test_vpn_y_tir_libro():
    flujos = [-1000, 300, 400, 500]
    assert math.isclose(finmat.vpn(0.10, flujos), -1000 + 300 / 1.1 + 400 / 1.21 + 500 / 1.331)
    r = finmat.tir(flujos)
    assert abs(finmat.vpn(r, flujos)) < 1e-6


def test_tir_inexistente():
    assert finmat.tir([100, 100, 100]) is None


def test_tirm_reinversion_igual_a_tir_da_tir():
    flujos = [-1000, 600, 600]
    r = finmat.tir(flujos)
    assert math.isclose(finmat.tirm(flujos, r, r), r, rel_tol=1e-6)


def test_recuperacion_descontada():
    # Sin descuento: recupera exactamente a los 2 años.
    assert math.isclose(finmat.recuperacion_descontada(0.0, [-200, 100, 100, 100]), 2.0)


def test_cuota_fija():
    assert math.isclose(finmat.anualidad(1000, 0.0, 4), 250)


# --- Escenarios ----------------------------------------------------------------------
def test_escenario_converge_y_ppa():
    assert math.isclose(ESC["PIB real (%)"].iloc[-1], 3.0)
    assert math.isclose(ESC["Inflación Colombia (%)"].iloc[5], 3.0)
    # TRM año 1 = TRM0 · (1+πCOL)/(1+πUSA)
    pi1 = ESC["Inflación Colombia (%)"].iloc[0] / 100
    assert math.isclose(ESC["TRM fin de año"].iloc[0], 4000 * (1 + pi1) / 1.02)


# --- Proyectos -------------------------------------------------------------------------
def test_capital_de_trabajo_se_recupera():
    m = pr.calcular(pr.Proyecto(), ESC)
    fila = m["flujos"].loc["(−) Inversión en capital de trabajo"]
    assert abs(fila.sum()) < 1e-6


def test_identidad_flujo_inversionista():
    p = pr.Proyecto()
    m = pr.calcular(p, ESC)
    f = m["flujos"]
    reconstruido = (f.loc["Flujo de caja libre del proyecto"] + f.loc["(−) Intereses"]
                    + f.loc["(+) Escudo fiscal de intereses"] + f.loc["(−) Abonos a capital"]
                    + f.loc["(+) Desembolso del crédito"])
    assert np.allclose(reconstruido, m["fci"])


def test_deuda_se_paga_completa():
    for sistema in pr.SISTEMAS_DEUDA:
        d = pr.tabla_deuda(1000, 0.12, 5, sistema, 8)
        assert math.isclose(d["Abono a capital"].sum(), 1000, abs_tol=1e-6)
        assert abs(d["Saldo final"].iloc[-1]) < 1e-6


def test_sin_deuda_vpn_igual_apv_con_ku():
    p = replace(pr.Proyecto(), pct_deuda=0.0)
    ind = pr.indicadores(pr.calcular(p, ESC), 0.13, 0.13, 0.13, 0.10)
    assert math.isclose(ind["vpn"], ind["apv"])
    assert math.isclose(ind["vpn"], ind["vpn_inversionista"])


def test_perdidas_fiscales():
    imp = pr.impuestos_con_perdidas(np.array([-100.0, 60.0, 80.0]), 0.35, True)
    assert np.allclose(imp, [0, 0, 40 * 0.35])
    imp_sin = pr.impuestos_con_perdidas(np.array([-100.0, 60.0, 80.0]), 0.35, False)
    assert np.allclose(imp_sin, [0, 60 * 0.35, 80 * 0.35])


def test_montecarlo_sin_variacion_reproduce_base():
    p = pr.Proyecto()
    sim = pr.montecarlo(p, ESC, 0.13, {"precio_inicial": (0.0, 0.0)}, n_sim=20)
    base = finmat.vpn(0.13, pr.calcular(p, ESC)["fclp"])
    assert np.allclose(sim["VPN"], base)


# --- Valoración -------------------------------------------------------------------------
def test_roic_igual_wacc_crecer_no_crea_valor():
    """Con ROIC = WACC, el valor terminal no depende de g (VT = NOPAT_{n+1}/WACC... ajustado)."""
    s = val.SupuestosValoracion()
    w = 0.12
    v1 = val.proyectar(replace(s, g_terminal=0.02), ESC, w)["vt"]
    v2 = val.proyectar(replace(s, g_terminal=0.05), ESC, w)["vt"]
    nopat_n = val.proyectar(s, ESC, w)["tabla"].loc["NOPAT"].iloc[-1]
    # VT = NOPAT_n(1+g)(1 − g/WACC)/(WACC − g) = NOPAT_n(1+g)/WACC
    assert math.isclose(v1, nopat_n * 1.02 / w, rel_tol=1e-9)
    assert math.isclose(v2, nopat_n * 1.05 / w, rel_tol=1e-9)


def test_puente_de_valor():
    v = val.proyectar(val.SupuestosValoracion(), ESC, 0.12)
    assert math.isclose(v["ev"], v["vp_flujos"] + v["vp_vt"])
    assert math.isclose(v["patrimonio"], v["ev"] - v["deuda"] + v["caja"])


def test_alerta_g_mayor_que_wacc():
    v = val.proyectar(replace(val.SupuestosValoracion(), g_terminal=0.13), ESC, 0.12)
    assert any(tipo == "error" for tipo, _ in v["alertas"])


# --- Carga de estados financieros -----------------------------------------------------------
from nucleo import carga_archivos as carga  # noqa: E402
from nucleo import supersociedades as ss  # noqa: E402


def test_numeros_formato_colombiano():
    assert carga._a_numero("12.500.000") == 12_500_000
    assert carga._a_numero("(7.400.000)") == -7_400_000
    assert carga._a_numero("350.000") == 350_000
    assert carga._a_numero("1.234,56") == 1234.56
    assert carga._a_numero("3,5") == 3.5


def test_normalizacion_tildes_danadas():
    assert ss.norm("Ganancia (pérdida) por actividades de operación") == \
        ss.norm("Ganancia (p\ufffdrdida) por actividades de operaci\ufffdn")
    assert ss.reparar("Elaboraci\ufffdn de productos l\ufffdcteos") == "Elaboración de productos lácteos"


def test_armar_resta_depreciacion_de_gastos():
    tabla = pd.DataFrame({2025: [100.0, 60.0, 20.0, 5.0]},
                         index=["Ventas", "Costo de ventas", "Gastos de administración", "Depreciación"])
    asignacion = {r: [] for r in carga.SUGERENCIAS}
    asignacion.update({"Ventas": ["Ventas"], "Costo de ventas": ["Costo de ventas"],
                       "Gastos operacionales (sin D&A)": ["Gastos de administración"],
                       "Depreciación y amortización": ["Depreciación"]})
    r = carga.armar(tabla, asignacion, 1.0)
    assert r.loc["Gastos operacionales (sin D&A)", 2025] == 15.0
