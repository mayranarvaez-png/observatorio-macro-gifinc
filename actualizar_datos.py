"""Descarga todas las series del catálogo y los insumos de Damodaran.

Uso:
    python actualizar_datos.py              # todo
    python actualizar_datos.py tpm trm      # solo esas series
    python actualizar_datos.py --sin-damodaran

Si una fuente falla, se conserva el último archivo descargado y el error queda
anotado en datos/registro_actualizacion.json.
"""
from __future__ import annotations

import sys

from nucleo import almacen, damodaran, fuentes
from nucleo.catalogo import SERIES


def actualizar(ids: list[str] | None = None, con_damodaran: bool = True, aviso=print) -> dict:
    registro = almacen.leer_registro()
    disponibles = {}
    # Las series derivadas van al final para usar los insumos recién descargados.
    orden = sorted(SERIES, key=lambda s: s.proveedor == "derivada")
    for serie in orden:
        if ids and serie.id not in ids:
            continue
        try:
            if serie.proveedor == "derivada":
                for insumo in serie.parametros["formula"]:
                    if insumo not in disponibles:
                        disponibles[insumo] = almacen.leer_serie(insumo)
            df = fuentes.descargar(serie, disponibles)
            almacen.guardar_serie(serie.id, df)
            disponibles[serie.id] = df
            registro[serie.id] = {
                "estado": "ok",
                "actualizado": almacen.ahora(),
                "ultimo_dato": df["fecha"].max().strftime("%Y-%m-%d"),
                "observaciones": int(len(df)),
            }
            aviso(f"  ✓ {serie.id:<18} {len(df):>6} obs. · último {registro[serie.id]['ultimo_dato']}")
        except Exception as e:  # noqa: BLE001 - se registra cualquier falla de fuente
            previo = registro.get(serie.id, {})
            registro[serie.id] = {**previo, "estado": "error", "error": str(e)[:300],
                                  "intento": almacen.ahora()}
            aviso(f"  ✗ {serie.id:<18} {e}")
    almacen.guardar_registro(registro)

    if con_damodaran:
        try:
            paquete = damodaran.descargar_todo()
            almacen.guardar_damodaran(paquete)
            p = paquete["pais"]
            registro["damodaran"] = {"estado": "ok", "actualizado": almacen.ahora(),
                                     "ultimo_dato": p["fecha_archivo"]}
            aviso(f"  ✓ damodaran          ERP {p['erp_madura']:.2%} · CRP {p['crp_calificacion']:.2%}"
                  f" · archivo {p['fecha_archivo']}")
        except Exception as e:  # noqa: BLE001
            registro["damodaran"] = {**registro.get("damodaran", {}), "estado": "error",
                                     "error": str(e)[:300], "intento": almacen.ahora()}
            aviso(f"  ✗ damodaran          {e}")
        almacen.guardar_registro(registro)
    return registro


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print("Actualizando Observatorio Macro-Financiero de Colombia…")
    reg = actualizar(args or None, con_damodaran="--sin-damodaran" not in sys.argv)
    errores = [k for k, v in reg.items() if v.get("estado") == "error"]
    print(f"Listo. {len(errores)} con error: {', '.join(errores) or 'ninguna'}")
    sys.exit(1 if errores else 0)
