"""Actualiza el catálogo de acciones del comparador y del portafolio.

Une: Colombia (BVC y ADR), Latinoamérica (cuaderno de betas), EE. UU. (todo Nasdaq y NYSE, S&P 500, Nasdaq-100)
y los índices principales de Europa, Canadá y Hong Kong. Los símbolos de otros países se validan en Yahoo Finance.

Uso:  python actualizar_universo.py
"""
from nucleo import universo


def actualizar() -> dict:
    try:
        us = universo.descargar()
        universo.guardar(us)
    except Exception as e:  # noqa: BLE001 - si falla una fuente se conserva la lista anterior de EE. UU.
        print(f"No se pudo actualizar la lista de EE. UU. ({e}); se usa la anterior.")
        us = universo.leer()
    glob = universo.indices_globales()
    if not glob.empty:
        glob = glob[glob["ticker"].isin(universo.validar_en_yahoo(glob["ticker"].tolist()))]
    cat = universo.construir_catalogo(us, glob)
    universo.guardar_catalogo(cat)
    return {"total": len(cat), "paises": cat["pais"].nunique(), "globales": len(glob)}


if __name__ == "__main__":
    r = actualizar()
    cat = universo.leer_catalogo()
    print(f"Catálogo: {r['total']} símbolos en {r['paises']} países "
          f"({r['globales']} de índices de otros países validados en Yahoo).")
    print(cat["pais"].value_counts().to_string())
