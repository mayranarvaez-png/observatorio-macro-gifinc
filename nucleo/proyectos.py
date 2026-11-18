"""Evaluación financiera de proyectos de inversión.

Valores monetarios en millones de COP nominales; precio y costo unitario en COP.

Estructura del flujo (convención de fin de año; t = 0 es hoy):
    Ingresos − Costos variables − Costos fijos = EBITDA
    EBITDA − Depreciación = EBIT (utilidad operativa)
    Flujo de caja libre del proyecto (FCLP):
        EBIT − impuesto operativo + depreciación − inversión fija − inversión en KTNO + salvamento neto
    Flujo de caja del inversionista (FCI):
        FCLP − intereses − abonos + escudo fiscal + desembolso de deuda

El capital de trabajo que necesita el año t se invierte al final del año t−1 y se
recupera al final del horizonte. Las pérdidas fiscales se compensan con utilidades
futuras (Art. 147 E.T.).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd

from . import finmat

INDEXACIONES = ["Inflación", "TRM", "Fijo"]
SISTEMAS_DEUDA = ["Cuota fija", "Abono constante", "Pago al final (bullet)"]


@dataclass
class Proyecto:
    nombre: str = "Planta de transformación de café especial"
    horizonte: int = 8
    # Inversión
    inversion_inicial: float = 4500.0         # millones COP
    vida_util: int = 10                        # años, depreciación en línea recta
    salvamento_pct: float = 0.30               # valor de mercado al final, % de la inversión
    # Demanda y precios
    cantidad_inicial: float = 400_000          # unidades en el año 1
    elasticidad_pib: float = 1.2               # crecimiento de cantidades = ε · PIB real + adicional
    crecimiento_adicional: float = 0.02
    precio_inicial: float = 18_000             # COP por unidad, año 1
    indexacion_precio: str = "Inflación"
    ajuste_real_precio: float = 0.0            # crecimiento real del precio por encima del índice
    # Costos
    costo_variable_unitario: float = 11_200    # COP por unidad, año 1
    indexacion_costos: str = "Inflación"
    costos_fijos: float = 1_350.0              # millones COP, año 1 (indexados a inflación)
    # Capital de trabajo
    dias_cartera: float = 45
    dias_inventario: float = 30
    dias_proveedores: float = 30
    # Financiación
    pct_deuda: float = 0.40
    tasa_deuda: float = 0.152                  # E.A.
    plazo_deuda: int = 5
    sistema_deuda: str = "Cuota fija"
    # Impuestos
    tasa_impuesto: float = 0.35
    compensar_perdidas: bool = True

    @classmethod
    def desde_dict(cls, datos: dict) -> "Proyecto":
        validos = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in datos.items() if k in validos})

    def a_dict(self) -> dict:
        return asdict(self)


# --- Piezas del modelo -------------------------------------------------------------
def _indice(tipo: str, inflacion: np.ndarray, trm: np.ndarray, ajuste_real: float) -> np.ndarray:
    """Factor multiplicativo por año (año 1 = 1)."""
    n = len(inflacion)
    if tipo == "Inflación":
        base = np.cumprod(np.r_[1.0, 1 + inflacion[1:]])
    elif tipo == "TRM":
        base = trm / trm[0]
    else:
        base = np.ones(n)
    return base * (1 + ajuste_real) ** np.arange(n)


def impuestos_con_perdidas(base: np.ndarray, tasa: float, compensar: bool) -> np.ndarray:
    """Impuesto de renta por año; las pérdidas se acumulan y se compensan después."""
    imp = np.zeros_like(base)
    perdidas = 0.0
    for i, b in enumerate(base):
        if b < 0:
            perdidas += -b if compensar else 0.0
            continue
        usable = min(perdidas, b)
        perdidas -= usable
        imp[i] = (b - usable) * tasa
    return imp


def tabla_deuda(monto: float, tasa: float, plazo: int, sistema: str, n: int) -> pd.DataFrame:
    saldo = monto
    filas = []
    cuota_fija = finmat.anualidad(monto, tasa, plazo) if monto > 0 else 0.0
    for t in range(1, n + 1):
        interes = saldo * tasa
        if t > plazo or saldo <= 1e-9:
            abono = 0.0
        elif sistema == "Cuota fija":
            abono = cuota_fija - interes
        elif sistema == "Abono constante":
            abono = monto / plazo
        else:
            abono = saldo if t == plazo else 0.0
        filas.append({"t": t, "Saldo inicial": saldo, "Intereses": interes, "Abono a capital": abono,
                      "Cuota": interes + abono, "Saldo final": saldo - abono})
        saldo -= abono
    return pd.DataFrame(filas)


def calcular(p: Proyecto, escenario: pd.DataFrame) -> dict:
    """Devuelve el estado de resultados, los flujos y la tabla de deuda."""
    n = p.horizonte
    esc = escenario.iloc[:n]
    pib = esc["PIB real (%)"].to_numpy() / 100
    infl = esc["Inflación Colombia (%)"].to_numpy() / 100
    trm = esc["TRM fin de año"].to_numpy()

    # Operación (años 1..n)
    crec_q = p.elasticidad_pib * pib + p.crecimiento_adicional
    cantidad = p.cantidad_inicial * np.cumprod(np.r_[1.0, 1 + crec_q[1:]])
    precio = p.precio_inicial * _indice(p.indexacion_precio, infl, trm, p.ajuste_real_precio)
    cvu = p.costo_variable_unitario * _indice(p.indexacion_costos, infl, trm, 0.0)
    ingresos = cantidad * precio / 1e6
    costo_var = cantidad * cvu / 1e6
    fijos = p.costos_fijos * _indice("Inflación", infl, trm, 0.0)
    ebitda = ingresos - costo_var - fijos
    dep_anual = p.inversion_inicial / p.vida_util
    depreciacion = np.array([dep_anual if t <= p.vida_util else 0.0 for t in range(1, n + 1)])
    ebit = ebitda - depreciacion

    # Deuda
    monto_deuda = p.inversion_inicial * p.pct_deuda
    deuda = tabla_deuda(monto_deuda, p.tasa_deuda, min(p.plazo_deuda, n), p.sistema_deuda, n)
    intereses = deuda["Intereses"].to_numpy()
    abonos = deuda["Abono a capital"].to_numpy()

    # Impuestos: operativo (sin deuda) y real (con intereses)
    imp_operativo = impuestos_con_perdidas(ebit, p.tasa_impuesto, p.compensar_perdidas)
    uai = ebit - intereses
    imp_real = impuestos_con_perdidas(uai, p.tasa_impuesto, p.compensar_perdidas)
    escudo = imp_operativo - imp_real
    utilidad_neta = uai - imp_real

    # Capital de trabajo neto operativo
    ktno = (ingresos * p.dias_cartera + costo_var * p.dias_inventario
            - costo_var * p.dias_proveedores) / 365
    ktno_ext = np.r_[0.0, ktno, 0.0]                     # t = 0..n+1
    inv_kt = np.diff(ktno_ext)                           # t = 0..n; en t = n queda −KTNO (recuperación)

    # Salvamento
    libro_final = p.inversion_inicial - depreciacion.sum()
    valor_mercado = p.inversion_inicial * p.salvamento_pct
    imp_salvamento = (valor_mercado - libro_final) * p.tasa_impuesto
    salvamento_neto = valor_mercado - imp_salvamento

    def con_t0(x, t0=0.0):
        return np.r_[t0, x]

    capex = con_t0(np.zeros(n), p.inversion_inicial)
    salv = np.zeros(n + 1)
    salv[-1] = salvamento_neto
    fclp = (con_t0(ebit) - con_t0(imp_operativo) + con_t0(depreciacion) - capex - inv_kt + salv)
    fci = (fclp - con_t0(intereses) - con_t0(abonos) + con_t0(escudo) + con_t0(np.zeros(n), monto_deuda))

    columnas = list(range(n + 1))
    resultados = pd.DataFrame({
        "Cantidad (unidades)": con_t0(cantidad, np.nan),
        "Precio unitario (COP)": con_t0(precio, np.nan),
        "Ingresos": con_t0(ingresos),
        "Costos variables": -con_t0(costo_var),
        "Costos fijos": -con_t0(fijos),
        "EBITDA": con_t0(ebitda),
        "Depreciación": -con_t0(depreciacion),
        "EBIT (utilidad operativa)": con_t0(ebit),
        "Intereses": -con_t0(intereses),
        "Utilidad antes de impuestos": con_t0(uai),
        "Impuesto de renta": -con_t0(imp_real),
        "Utilidad neta": con_t0(utilidad_neta),
    }, index=columnas).T
    flujos = pd.DataFrame({
        "EBIT": con_t0(ebit),
        "(−) Impuesto operativo": -con_t0(imp_operativo),
        "(+) Depreciación": con_t0(depreciacion),
        "(−) Inversión fija": -capex,
        "(−) Inversión en capital de trabajo": -inv_kt,
        "(+) Salvamento neto de impuestos": salv,
        "Flujo de caja libre del proyecto": fclp,
        "(−) Intereses": -con_t0(intereses),
        "(+) Escudo fiscal de intereses": con_t0(escudo),
        "(−) Abonos a capital": -con_t0(abonos),
        "(+) Desembolso del crédito": con_t0(np.zeros(n), monto_deuda),
        "Flujo de caja del inversionista": fci,
    }, index=columnas).T
    return {
        "resultados": resultados,
        "flujos": flujos,
        "deuda": deuda,
        "fclp": fclp,
        "fci": fci,
        "escudo": con_t0(escudo),
        "ktno": con_t0(ktno),
        "margen_ebitda": ebitda / np.where(ingresos == 0, np.nan, ingresos),
    }


def indicadores(m: dict, wacc: float, ke: float, ku: float, kd: float) -> dict:
    fclp, fci = m["fclp"], m["fci"]
    vp_escudos = finmat.vpn(kd, m["escudo"])
    vpn_base = finmat.vpn(ku, fclp)
    return {
        "vpn": finmat.vpn(wacc, fclp),
        "tir": finmat.tir(fclp),
        "tirm": finmat.tirm(fclp, wacc, wacc),
        "recuperacion": finmat.recuperacion_descontada(wacc, fclp),
        "ir": finmat.indice_rentabilidad(wacc, fclp),
        "cambios_signo": finmat.cambios_de_signo(fclp),
        "vpn_inversionista": finmat.vpn(ke, fci),
        "tir_inversionista": finmat.tir(fci),
        "vpn_base_ku": vpn_base,
        "vp_escudos": vp_escudos,
        "apv": vpn_base + vp_escudos,
    }


# --- Riesgo ------------------------------------------------------------------------
VARIABLES_SENSIBILIDAD = {
    "precio_inicial": "Precio de venta",
    "cantidad_inicial": "Cantidad vendida",
    "costo_variable_unitario": "Costo variable unitario",
    "costos_fijos": "Costos fijos",
    "inversion_inicial": "Inversión inicial",
    "dias_cartera": "Días de cartera",
}


def tornado(p: Proyecto, escenario: pd.DataFrame, wacc: float, variacion: float = 0.10) -> pd.DataFrame:
    base = finmat.vpn(wacc, calcular(p, escenario)["fclp"])
    filas = []
    for campo, etiqueta in VARIABLES_SENSIBILIDAD.items():
        valor = getattr(p, campo)
        bajo = finmat.vpn(wacc, calcular(Proyecto(**{**asdict(p), campo: valor * (1 - variacion)}), escenario)["fclp"])
        alto = finmat.vpn(wacc, calcular(Proyecto(**{**asdict(p), campo: valor * (1 + variacion)}), escenario)["fclp"])
        filas.append({"Variable": etiqueta, "VPN con −": bajo, "VPN con +": alto,
                      "Rango": abs(alto - bajo)})
    for etiqueta, d in [("Tasa de descuento (WACC)", variacion)]:
        bajo = finmat.vpn(wacc * (1 - d), calcular(p, escenario)["fclp"])
        alto = finmat.vpn(wacc * (1 + d), calcular(p, escenario)["fclp"])
        filas.append({"Variable": etiqueta, "VPN con −": bajo, "VPN con +": alto, "Rango": abs(alto - bajo)})
    df = pd.DataFrame(filas).sort_values("Rango")
    df.attrs["vpn_base"] = base
    return df


def punto_equilibrio_precio(p: Proyecto, escenario: pd.DataFrame, wacc: float) -> float | None:
    """Precio inicial que hace VPN = 0 (bisección)."""
    def f(precio):
        return finmat.vpn(wacc, calcular(Proyecto(**{**asdict(p), "precio_inicial": precio}), escenario)["fclp"])
    a, b = 0.0, p.precio_inicial * 5
    if np.sign(f(a)) == np.sign(f(b)):
        return None
    for _ in range(60):
        m = (a + b) / 2
        if np.sign(f(m)) == np.sign(f(a)):
            a = m
        else:
            b = m
    return (a + b) / 2


def _triangular_inv(u: np.ndarray, minimo: float, moda: float, maximo: float) -> np.ndarray:
    if maximo <= minimo:
        return np.full_like(u, moda)
    c = (moda - minimo) / (maximo - minimo)
    return np.where(u < c,
                    minimo + np.sqrt(u * (maximo - minimo) * (moda - minimo)),
                    maximo - np.sqrt((1 - u) * (maximo - minimo) * (maximo - moda)))


_phi = np.vectorize(lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2))))


def montecarlo(p: Proyecto, escenario: pd.DataFrame, wacc: float, rangos: dict[str, tuple[float, float]],
               correlacion_precio_cantidad: float = 0.0, n_sim: int = 1000, semilla: int = 7) -> pd.DataFrame:
    """Simula el VPN variando los campos de `rangos` con distribuciones triangulares.

    rangos[campo] = (mínimo, máximo) como desviación relativa al valor base (p. ej. (-0.2, 0.1)).
    La moda es el valor base. Precio y cantidad pueden estar correlacionados (cópula gaussiana).
    """
    rng = np.random.default_rng(semilla)
    campos = list(rangos)
    z = rng.standard_normal((n_sim, len(campos)))
    if "precio_inicial" in campos and "cantidad_inicial" in campos and correlacion_precio_cantidad:
        i, j = campos.index("precio_inicial"), campos.index("cantidad_inicial")
        rho = correlacion_precio_cantidad
        z[:, j] = rho * z[:, i] + math.sqrt(1 - rho ** 2) * z[:, j]
    u = _phi(z)
    base = asdict(p)
    muestras = {c: _triangular_inv(u[:, k], base[c] * (1 + rangos[c][0]), base[c], base[c] * (1 + rangos[c][1]))
                for k, c in enumerate(campos)}
    vpns = []
    for s in range(n_sim):
        q = Proyecto(**{**base, **{c: muestras[c][s] for c in campos}})
        vpns.append(finmat.vpn(wacc, calcular(q, escenario)["fclp"]))
    df = pd.DataFrame(muestras)
    df["VPN"] = vpns
    return df
