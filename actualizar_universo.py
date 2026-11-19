"""Actualiza la lista de acciones de EE. UU. (Nasdaq, NYSE, S&P 500, Nasdaq-100) que usan el comparador y el portafolio.

Uso:  python actualizar_universo.py
"""
from nucleo import universo


def actualizar() -> int:
    df = universo.descargar()
    universo.guardar(df)
    return len(df)


if __name__ == "__main__":
    n = actualizar()
    df = universo.leer()
    print(f"Universo guardado: {n} símbolos · {int(df['sp500'].sum())} del S&P 500 · "
          f"{int(df['nasdaq100'].sum())} del Nasdaq-100 · {int((df['tipo'] == 'ETF').sum())} ETF.")
