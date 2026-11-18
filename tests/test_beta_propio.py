"""Pruebas del beta propio de LatAm y de su combinación con Damodaran."""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo import beta_propio as bp  # noqa: E402


def dam():
    return pd.DataFrame({
        "industria": ["Power", "Bank (Money Center)", "Steel", "Shoe"],
        "n_empresas": [300, 100, 200, 50],
        "beta_apalancada": [0.9, 0.8, 1.2, 1.0],
        "de": [1.0, 2.0, 0.5, 0.3],
        "caja_valor_firma": [0.05, 0.10, 0.04, 0.06],
        "beta_desapalancada": [0.5, 0.3, 0.9, 0.8],
        "beta_desapalancada_caja": [0.52, 0.33, 0.94, 0.85],
    })


def sectores():
    return pd.DataFrame({
        "industria": ["Power", "Bank (Money Center)", "Shoe", "Sector inexistente"],
        "firmas": [12, 8, 1, 4], "paises": [4, 3, 1, 2],
        "beta_prom": [0.70, 0.90, 0.65, 1.0],
        "ic_lo": [0.64, 0.80, np.nan, 0.9], "ic_hi": [0.78, 1.00, np.nan, 1.1],
        "confianza": ["Alta", "Media", "Baja", "Baja"],
    })


def test_desapalancar_manual():
    # 0.70 / (1 + 0.75·1.0) / (1 − 0.05) = 0.4211
    assert math.isclose(bp.desapalancar(0.70, 1.0, 0.05), 0.70 / 1.75 / 0.95)


def test_construir_propio_descarta_industrias_que_damodaran_no_tiene():
    p = bp.construir_propio(sectores(), dam())
    assert set(p["industria"]) == {"Power", "Bank (Money Center)", "Shoe"}


def test_financieras_se_desapalancan_y_se_marcan():
    p = bp.construir_propio(sectores(), dam()).set_index("industria")
    assert bool(p.loc["Bank (Money Center)", "financiera"]) and not bool(p.loc["Power", "financiera"])
    esperado = 0.90 / (1 + 0.75 * 2.0) / (1 - 0.10)
    assert math.isclose(p.loc["Bank (Money Center)", "beta_desapalancada_caja"], esperado)


def test_error_estandar_del_intervalo_y_sin_ic_con_pocas_firmas():
    p = bp.construir_propio(sectores(), dam()).set_index("industria")
    bu_lo = bp.desapalancar(0.64, 1.0, 0.05)
    bu_hi = bp.desapalancar(0.78, 1.0, 0.05)
    assert math.isclose(p.loc["Power", "error_est"], (bu_hi - bu_lo) / (2 * 1.96))
    assert np.isnan(p.loc["Shoe", "error_est"])


def test_error_estandar_usa_la_dispersion_entre_empresas_si_es_mayor():
    acciones = pd.DataFrame({"industria": ["Power"] * 3, "incluir": [True, True, True],
                             "beta_vs_indice_pais": [0.4, 0.7, 1.0]})
    sin = bp.construir_propio(sectores(), dam()).set_index("industria")
    con = bp.construir_propio(sectores(), dam(), acciones).set_index("industria")
    assert con.loc["Power", "error_est"] > sin.loc["Power", "error_est"]
    # sd = 0.3, n = 3 → 0.3/√3 en espacio apalancado, luego desapalancado
    esperado = 0.3 / math.sqrt(3) / (1 + 0.75 * 1.0) / (1 - 0.05)
    assert math.isclose(con.loc["Power", "error_est"], esperado)
    # sectores sin acciones en la tabla conservan el error del bootstrap
    assert math.isclose(con.loc["Bank (Money Center)", "error_est"], sin.loc["Bank (Money Center)", "error_est"])


def test_pesos_en_cero_sin_error_estandar_y_crecen_con_la_precision():
    p = bp.construir_propio(sectores(), dam())
    w = bp.pesos(p, tau=0.2)
    assert w["Shoe"] == 0.0
    assert 0 < w["Bank (Money Center)"] < w["Power"] < 1


def test_combinar_cubre_todo_damodaran_y_respeta_extremos():
    p = bp.construir_propio(sectores(), dam())
    c = bp.combinar(p, dam(), tau=0.2).set_index("industria")
    assert len(c) == 4
    d = dam().set_index("industria")
    # sin beta propio (Steel) o con una sola firma (Shoe): igual a Damodaran
    assert c.loc["Steel", "beta_desapalancada_caja"] == d.loc["Steel", "beta_desapalancada_caja"]
    assert c.loc["Shoe", "beta_desapalancada_caja"] == d.loc["Shoe", "beta_desapalancada_caja"]
    # con beta propio: queda entre el propio y el de Damodaran
    pw = p.set_index("industria").loc["Power", "beta_desapalancada_caja"]
    lo, hi = sorted([pw, d.loc["Power", "beta_desapalancada_caja"]])
    assert lo <= c.loc["Power", "beta_desapalancada_caja"] <= hi
    # τ enorme → casi todo el peso al beta propio; τ mínimo → cerca de Damodaran
    grande = bp.combinar(p, dam(), tau=50).set_index("industria")
    assert math.isclose(grande.loc["Power", "beta_desapalancada_caja"], pw, rel_tol=1e-3)
    chico = bp.combinar(p, dam(), tau=0.001).set_index("industria")
    assert math.isclose(chico.loc["Power", "beta_desapalancada_caja"],
                        d.loc["Power", "beta_desapalancada_caja"], rel_tol=0.02)


def test_combinar_suma_las_empresas_propias_y_expone_el_peso():
    p = bp.construir_propio(sectores(), dam())
    c = bp.combinar(p, dam(), tau=0.2).set_index("industria")
    assert c.loc["Power", "n_empresas"] == 300 + 12
    assert c.loc["Steel", "n_empresas"] == 200 and c.loc["Steel", "peso_propio"] == 0.0


def test_estimar_tau_tiene_piso():
    p = bp.construir_propio(sectores(), dam())
    p["n_empresas"] = 10
    p["beta_desapalancada_caja"] = dam().set_index("industria").loc[p["industria"], "beta_desapalancada_caja"].to_numpy()
    assert bp.estimar_tau(p, dam().set_index("industria")["beta_desapalancada_caja"]) == bp.TAU_MIN


def test_importar_exige_las_hojas_y_columnas():
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        sectores().to_excel(w, sheet_name="Beta por sector", index=False)
    try:
        bp.importar(buf.getvalue(), dam(), "2026-01-01")
    except ValueError as e:
        assert "Acciones" in str(e)
    else:
        raise AssertionError("debía fallar por la hoja faltante")
