"""Estados financieros NIIF reportados a la Superintendencia de Sociedades (datos.gov.co).

Conjuntos de datos (formato largo: un concepto por fila):
    6hqw-m3dm  Carátula (razón social, CIIU, unidad de reporte…)
    pfdp-zks5  Estado de situación financiera
    prwj-nzxa  Estado de resultado integral
    ctcp-462n  Estado de flujo de efectivo

Cobertura: sociedades vigiladas por Supersociedades. No incluye emisores de valores
ni entidades financieras (vigiladas por la Superintendencia Financiera).

Los nombres de los conceptos vienen con tildes dañadas en la fuente ("administraci�n"),
por eso se comparan normalizados: minúsculas, solo letras ASCII y números.
"""
from __future__ import annotations

import os
import re

import pandas as pd
import requests

from .valoracion import RUBROS

BASE = "https://www.datos.gov.co/resource/"
DATASETS = {"caratula": "6hqw-m3dm", "balance": "pfdp-zks5", "resultados": "prwj-nzxa", "flujo": "ctcp-462n"}
URL_FUENTE = "https://www.datos.gov.co/browse?q=Estados%20Financieros%20NIIF"
_TIMEOUT = 120


def _get(dataset: str, params: dict) -> list[dict]:
    headers = {}
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    r = requests.get(BASE + DATASETS[dataset] + ".json", params=params, headers=headers, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def norm(texto: str) -> str:
    """Quita todo lo que no sea letra ASCII o número: hace iguales 'operación' y 'operaci�n'."""
    # Se eliminan (no se transliteran) las letras con tilde, igual que el carácter dañado de la fuente.
    texto = re.sub(r"[^a-z0-9 ]", "", str(texto).lower())
    return re.sub(r"\s+", " ", texto).strip()


_REPARACIONES = [
    ("ci�n", "ción"), ("si�n", "sión"), ("Raz�n", "Razón"), ("p�rdida", "pérdida"),
    ("l�cteos", "lácteos"), ("Compa��a", "Compañía"), ("compa��a", "compañía"),
    ("econ�mic", "económic"), ("pl�stic", "plástic"), ("qu�mic", "químic"),
    ("veh�cul", "vehícul"), ("energ�a", "energía"), ("log�a", "logía"), ("a�o", "año"),
    ("M�ximo", "Máximo"), ("Direcci�n", "Dirección"), ("plusval�a", "plusvalía"),
    ("inversi�n", "inversión"), ("financiaci�n", "financiación"), ("operaci�n", "operación"),
    ("art�culo", "artículo"), ("Tel�fono", "Teléfono"), ("n�mero", "número"),
    ("PA�IA", "PAÑIA"), ("Pa�ia", "Pañia"), ("A�O", "AÑO"), ("CI�N", "CIÓN"),
    ("ESPA�A", "ESPAÑA"), ("Espa�a", "España"),
]


def reparar(texto) -> str:
    """Repara las tildes dañadas más comunes de la fuente; el resto se deja sin el carácter dañado."""
    if not isinstance(texto, str):
        return texto
    for malo, bueno in _REPARACIONES:
        texto = texto.replace(malo, bueno)
    return texto.replace("�", "")


# --- Búsqueda --------------------------------------------------------------------------
def buscar(texto: str) -> pd.DataFrame:
    """Busca por razón social (fragmento) o por NIT (solo dígitos)."""
    texto = texto.strip()
    if not texto:
        return pd.DataFrame()
    if texto.replace(".", "").replace("-", "").isdigit():
        nit = texto.replace(".", "").split("-")[0]
        where = f"concepto like 'Raz%social%' AND nit = '{nit}'"
    else:
        # Las letras con tilde o ñ se vuelven comodín: la fuente guarda "EXITO", "ÉXITO" o "�XITO".
        seguro = re.sub(r"[^\x00-\x7f]", "%", texto.upper()).replace("'", "''")
        seguro = re.sub(r"\s+", "%", seguro)
        where = f"concepto like 'Raz%social%' AND upper(valor) like '%{seguro}%'"
    filas = _get("caratula", {"$select": "nit, valor, max(fecha_corte) as ultimo", "$where": where,
                              "$group": "nit, valor", "$limit": 200})
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    df["ultimo"] = pd.to_datetime(df["ultimo"])
    df = df.sort_values("ultimo").groupby("nit").tail(1)          # nombre más reciente por NIT
    df["valor"] = df["valor"].map(reparar)
    df = df.rename(columns={"nit": "NIT", "valor": "Razón social", "ultimo": "Último corte"})
    df["Último corte"] = df["Último corte"].dt.year
    return df.sort_values(["Último corte", "Razón social"], ascending=[False, True]).reset_index(drop=True)


def caratula(nit: str) -> dict:
    filas = _get("caratula", {"nit": nit, "$limit": 5000, "$order": "fecha_corte DESC"})
    datos = {}
    for f in filas:
        clave = norm(f["concepto"])
        datos.setdefault(clave, f.get("valor"))
    def buscar_clave(fragmento):
        return next((v for k, v in datos.items() if fragmento in k), None)
    return {
        "razon_social": reparar(buscar_clave("razn social") or buscar_clave("razon social")),
        "ciiu": reparar(buscar_clave("ciiu")),
        "unidad": buscar_clave("unidad de diligenciamiento"),
        "ciudad": buscar_clave("ciudad de la direccin del domicilio"),
        "estado": buscar_clave("estado actual"),
    }


# --- Descarga ---------------------------------------------------------------------------
def _anio(periodo: str, fecha_corte: str) -> int | None:
    anio_corte = int(fecha_corte[:4])
    p = norm(periodo)
    if p == "periodo actual":
        return anio_corte
    if p == "periodo anterior":
        return anio_corte - 1
    if "ene01" in p.replace(" ", ""):
        return None                       # saldo de apertura de la transición a NIIF
    m = re.match(r"(\d{4})", str(periodo))
    return int(m.group(1)) if m else None


def descargar(nit: str) -> pd.DataFrame:
    """Todos los conceptos de cierre anual (31 de diciembre) de los tres estados, en formato largo."""
    partes = []
    for estado in ("balance", "resultados", "flujo"):
        filas = _get(estado, {"nit": nit, "$limit": 50000, "$where": "date_extract_m(fecha_corte) = 12 "
                                                                     "AND date_extract_d(fecha_corte) = 31"})
        if filas:
            df = pd.DataFrame(filas)
            df["estado"] = estado
            partes.append(df)
    if not partes:
        return pd.DataFrame()
    df = pd.concat(partes, ignore_index=True)
    df["anio"] = [_anio(p, f) for p, f in zip(df["periodo"], df["fecha_corte"])]
    df = df.dropna(subset=["anio"])
    df["anio"] = df["anio"].astype(int)
    df = df[df["anio"].between(2000, pd.Timestamp.today().year)]   # la fuente trae algunos periodos inválidos
    df["categoria"] = df["punto_entrada"].map(categoria)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["clave"] = df["concepto"].map(norm)
    # Prioridad: el dato del informe de ese año (periodo actual) sobre la cifra comparativa del año siguiente;
    # entre reenvíos del mismo informe, el radicado más reciente.
    df["prioridad"] = (df["anio"] == df["fecha_corte"].str[:4].astype(int)).astype(int)
    df = df.sort_values(["prioridad", "numero_radicado"])
    return df


def categoria(punto_entrada: str) -> str:
    """Agrupa los nombres del tipo de reporte, que Supersociedades ha cambiado con los años
    ("Individuales", "Individual Grupo 1", "Separado Grupo 1"…)."""
    return "Consolidado" if "consolidad" in str(punto_entrada).lower() else "Individual o separado"


def puntos_de_entrada(df: pd.DataFrame) -> list[str]:
    """Categorías de reporte disponibles, primero individual o separado."""
    return sorted(df["categoria"].dropna().unique().tolist(), key=lambda c: c == "Consolidado")


# --- Mapeo a los rubros del modelo de valoración ------------------------------------------
def _es(clave: str, *opciones: str) -> bool:
    return any(clave == norm(o) for o in opciones)


def _contiene(clave: str, *fragmentos: str, excluir: tuple[str, ...] = ()) -> bool:
    return all(norm(f) in clave for f in fragmentos) and not any(norm(e) in clave for e in excluir)


REGLAS = {
    # rubro: (estado, función de selección de conceptos, descripción para el estudiante)
    "ventas": ("resultados", lambda c: _es(c, "Ingresos de actividades ordinarias"),
               "Ingresos de actividades ordinarias"),
    "costo": ("resultados", lambda c: _es(c, "Costo de ventas"), "Costo de ventas"),
    "ebit": ("resultados", lambda c: _es(c, "Ganancia (pérdida) por actividades de operación"),
             "Ganancia (pérdida) por actividades de operación"),
    "gastos_op": ("resultados", lambda c: (_es(c, "Gastos de administración", "Costos de distribución",
                                                "Gastos de ventas", "Otros gastos")),
                  "Gastos de administración + distribución/ventas + otros gastos"),
    "otros_ingresos": ("resultados", lambda c: _es(c, "Otros ingresos"), "Otros ingresos"),
    "dya": ("flujo", lambda c: _contiene(c, "ajustes por", "depreciaci") or _contiene(c, "ajustes por", "amortizaci"),
            "Ajustes por depreciación y amortización (flujo de efectivo)"),
    "capex": ("flujo", lambda c: _contiene(c, "compras de propiedades planta y equipo")
              or _contiene(c, "compras de activos intangibles"),
              "Compras de propiedades, planta y equipo + intangibles (flujo de efectivo)"),
    "cxc": ("balance", lambda c: _es(c, "Cuentas comerciales por cobrar y otras cuentas por cobrar corrientes"),
            "Cuentas comerciales por cobrar corrientes"),
    "inventarios": ("balance", lambda c: _es(c, "Inventarios corrientes", "Inventarios"), "Inventarios corrientes"),
    "cxp": ("balance", lambda c: _contiene(c, "por pagar", "comercial", "corriente", excluir=("no corriente",)),
            "Cuentas comerciales por pagar corrientes"),
    "ppe": ("balance", lambda c: _es(c, "Propiedades, planta y equipo"), "Propiedades, planta y equipo"),
    "intangibles": ("balance", lambda c: _es(c, "Activos intangibles distintos de la plusvalía"),
                    "Activos intangibles distintos de la plusvalía"),
    "deuda": ("balance", lambda c: _es(c, "Otros pasivos financieros corrientes", "Otros pasivos financieros no corrientes",
                                          "Obligaciones financieras corrientes", "Obligaciones financieras no corrientes"),
              "Otros pasivos financieros (corrientes + no corrientes)"),
    "caja": ("balance", lambda c: _es(c, "Efectivo y equivalentes al efectivo"), "Efectivo y equivalentes al efectivo"),
}


def _sumar(df: pd.DataFrame, regla: str) -> tuple[pd.Series, pd.DataFrame]:
    estado, selector, _ = REGLAS[regla]
    sub = df[(df["estado"] == estado) & df["clave"].map(selector)]
    if regla == "dya":
        # Si hay una línea combinada "depreciación y amortización", se usa solo esa para no duplicar.
        combinada = sub[sub["clave"].str.contains("depreciaci") & sub["clave"].str.contains("amortizaci")]
        if not combinada.empty:
            sub = combinada
        sub = sub[~sub["clave"].str.contains("deterioro")]
    # Un valor por concepto y año (el de mayor prioridad, que quedó al final al ordenar).
    sub = sub.groupby(["anio", "clave"]).tail(1)
    return sub.groupby("anio")["valor"].sum(), sub[["anio", "concepto", "valor"]]


def a_rubros(df: pd.DataFrame, punto: str, divisor: float = 1000.0) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Convierte el reporte NIIF en la tabla de rubros del modelo (millones de COP si la fuente
    está en miles: divisor = 1000). Devuelve (tabla, trazabilidad, advertencias)."""
    df = df[df["categoria"] == punto]
    s, traza, avisos = {}, [], []
    for regla in REGLAS:
        serie, detalle = _sumar(df, regla)
        s[regla] = serie
        detalle = detalle.assign(rubro=regla)
        traza.append(detalle)

    anios = sorted(set(s["ventas"].index) & (set(s["cxc"].index) | set(s["caja"].index)))
    if not anios:
        return pd.DataFrame(), pd.DataFrame(), ["No se encontraron ingresos y balance para un mismo año."]
    con_flujo = set(df.loc[df["estado"] == "flujo", "anio"])
    sin_flujo = [a for a in anios if a not in con_flujo]
    if sin_flujo and len(sin_flujo) < len(anios):
        anios = [a for a in anios if a in con_flujo]
        avisos.append(f"Se excluyen {', '.join(map(str, sin_flujo))}: solo aparecen como cifras comparativas, "
                      "sin estado de flujo de efectivo (faltan D&A y CAPEX).")

    def v(regla, anio):
        return float(s[regla].get(anio, 0.0) or 0.0)

    tabla = {}
    for a in anios:
        ventas, costo, dya = v("ventas", a), v("costo", a), abs(v("dya", a))
        if a in s["ebit"].index:
            ebit = v("ebit", a)
        else:
            ebit = ventas - costo - v("gastos_op", a) + v("otros_ingresos", a)
            avisos.append(f"{a}: EBIT calculado con los componentes (no se reportó la utilidad operativa).")
        if a not in s["dya"].index:
            avisos.append(f"{a}: sin depreciación en el flujo de efectivo; se usa 0.")
        if a not in s["capex"].index:
            avisos.append(f"{a}: sin CAPEX en el flujo de efectivo; se usa 0.")
        tabla[a] = {
            "Ventas": ventas,
            "Costo de ventas": costo,
            # EBITDA = EBIT + D&A  ⇒  gastos operacionales sin D&A = ventas − costo − EBIT − D&A
            "Gastos operacionales (sin D&A)": ventas - costo - ebit - dya,
            "Depreciación y amortización": dya,
            "CAPEX": abs(v("capex", a)),
            "Capital de trabajo neto operativo (KTNO)": v("cxc", a) + v("inventarios", a) - v("cxp", a),
            "Activo fijo neto": v("ppe", a) + v("intangibles", a),
            "Deuda financiera": v("deuda", a),
            "Caja e inversiones temporales": v("caja", a),
        }
    resultado = (pd.DataFrame(tabla).loc[RUBROS] / divisor).round(1)
    trazabilidad = pd.concat(traza, ignore_index=True)
    trazabilidad = trazabilidad[trazabilidad["anio"].isin(anios)]
    trazabilidad["rubro"] = trazabilidad["rubro"].map(lambda r: REGLAS[r][2])
    trazabilidad["valor"] = trazabilidad["valor"] / divisor
    trazabilidad["concepto"] = trazabilidad["concepto"].map(reparar)
    trazabilidad = trazabilidad.rename(columns={"anio": "Año", "concepto": "Concepto NIIF reportado",
                                                "valor": "Valor (millones COP)", "rubro": "Usado en"})
    return resultado, trazabilidad, avisos
