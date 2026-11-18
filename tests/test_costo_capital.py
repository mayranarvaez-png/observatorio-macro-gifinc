"""Pruebas del motor de costo de capital (valores verificables a mano)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import costo_capital as cc  # noqa: E402


def base(**cambios):
    valores = dict(rf=0.045, beta_u=0.8, de=0.5, tasa_impuesto=0.35, erp=0.045, crp=0.03,
                   infl_col=0.03, infl_usa=0.02, kd_cop=0.12, modo_crp="aditivo")
    valores.update(cambios)
    return cc.Supuestos(**valores)


def test_hamada():
    # 0.8 * (1 + 0.65 * 0.5) = 1.06
    assert math.isclose(cc.beta_apalancada(0.8, 0.5, 0.35), 1.06)


def test_ke_usd_aditivo():
    r = cc.calcular(base())
    assert math.isclose(r["ke_usd"], 0.045 + 1.06 * 0.045 + 0.03)


def test_ke_usd_beta():
    r = cc.calcular(base(modo_crp="beta"))
    assert math.isclose(r["ke_usd"], 0.045 + 1.06 * 0.045 + 1.06 * 0.03)


def test_fisher_ida_y_vuelta():
    x = cc.fisher(0.10, 0.03, 0.02)
    assert math.isclose(cc.fisher(x, 0.02, 0.03), 0.10)


def test_wacc():
    s = base()
    r = cc.calcular(s)
    esperado = (1 / 1.5) * r["ke_cop"] + (0.5 / 1.5) * 0.12 * 0.65
    assert math.isclose(r["wacc_cop"], esperado)


def test_sin_deuda_wacc_igual_ke():
    r = cc.calcular(base(de=0.0))
    assert math.isclose(r["wacc_cop"], r["ke_cop"])
    assert math.isclose(r["beta_apalancada"], 0.8)


def test_sensibilidad_forma():
    m = cc.sensibilidad(base(), "de", [0, 0.5, 1], "crp", [0.02, 0.03])
    assert m.shape == (2, 3)
    assert math.isclose(m.loc[0.03, 0.5], cc.calcular(base())["wacc_cop"])
