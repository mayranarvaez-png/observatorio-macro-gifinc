"""Importa al tablero el resultado del cuaderno Beta_Latinoamerica_CAPM.ipynb.

Uso:
    python importar_beta_latam.py ruta/a/resultados_beta_latam.xlsx

Lee las hojas «Beta por sector» y «Acciones», las convierte al formato de los betas de
Damodaran y las guarda en datos/latam/. Requiere haber ejecutado antes `actualizar_datos.py`
(necesita los betas de Damodaran de mercados emergentes).
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from nucleo import almacen, beta_propio


def importar_archivo(ruta: Path, fecha: str | None = None) -> dict:
    dam = almacen.leer_betas("emergentes")
    if dam is None:
        raise SystemExit("Faltan los betas de Damodaran. Ejecuta primero: python actualizar_datos.py")
    resultado = beta_propio.importar(Path(ruta).read_bytes(), dam, fecha or date.today().isoformat())
    almacen.guardar_betas_propios(resultado["propio"], resultado["empresas"], resultado["meta"])
    return resultado["meta"]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    meta = importar_archivo(Path(sys.argv[1]))
    print(f"Importado: {meta['acciones_incluidas']} acciones incluidas de {meta['acciones_total']}, "
          f"{meta['sectores']} sectores ({meta['sectores_5_o_mas']} con 5 o más firmas), "
          f"τ = {meta['tau']:.3f}.")
    if meta["sectores_sin_equivalente_en_damodaran"]:
        print("Sectores sin equivalente en Damodaran (omitidos):",
              meta["sectores_sin_equivalente_en_damodaran"])
