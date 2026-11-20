"""Componentes visuales compartidos por las páginas del tablero."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from . import almacen
from .catalogo import POR_ID, Serie

# Paleta categórica de GIFINC (orden fijo; el color sigue a la serie, no a su posición).
# Rojo y gris vienen del logo. Parejas adyacentes: ΔE ≥ 22 en visión normal y ≥ 9 con daltonismo.
PALETA = ["#E91D26", "#2A78D6", "#1BAF7A", "#EDA100", "#585858", "#E87BA4", "#6250D6", "#00A3A3"]
ROJO, AZUL, VERDE, AMBAR, GRIS = PALETA[0], PALETA[1], PALETA[2], PALETA[3], PALETA[4]
POS, NEG = AZUL, ROJO      # signo en barras: positivo azul, negativo rojo (el signo también se ve en el eje)
# Rampa secuencial de un solo tono (claro → oscuro) para mapas de calor y magnitudes.
RAMPA = ["#FBD9DA", "#F6B0B3", "#F1878B", "#EC5A60", "#C9161F", "#9B1017", "#6E0B10"]
RAMPA_AZUL = RAMPA         # nombre antiguo, se conserva por compatibilidad
GRIS_REF = "#8a8984"

RANGOS = {"1 año": 1, "3 años": 3, "5 años": 5, "10 años": 10, "Todo": None}


# --- Formato colombiano ---------------------------------------------------------
def num(x: float, dec: int = 2) -> str:
    if x is None or pd.isna(x):
        return "—"
    x = round(float(x), dec) + 0.0   # evita "-0,0"
    return f"{x:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x: float, dec: int = 2, fraccion: bool = True) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{num(x * 100 if fraccion else x, dec)} %"


def en_palabras(millones: float) -> str:
    """Lee una cifra en millones de COP: 2.212.594 → '2,21 billones de pesos'."""
    if millones is None or pd.isna(millones):
        return "—"
    m = abs(millones)
    signo = "−" if millones < 0 else ""
    if m >= 1_000_000:
        return f"{signo}{num(m / 1_000_000, 2)} billones de pesos"
    if m >= 1_000:
        return f"{signo}{num(m / 1_000, 1)} mil millones de pesos"
    return f"{signo}{num(m, 0)} millones de pesos"


def fecha_txt(f) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    f = pd.Timestamp(f)
    return f"{f.day} {meses[f.month - 1]} {f.year}"


def periodo_txt(f, frecuencia: str) -> str:
    f = pd.Timestamp(f)
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    if frecuencia == "Trimestral":
        return f"T{(f.month - 1) // 3 + 1} {f.year}"
    if frecuencia == "Mensual":
        return f"{meses[f.month - 1]} {f.year}"
    if frecuencia == "Anual":
        return str(f.year)
    return fecha_txt(f)


def tarjetas(n: int, ancho: int = 200) -> list:
    """n contenedores para métricas que pasan a la fila siguiente cuando no caben."""
    fila = st.container(horizontal=True, gap="small")
    return [fila.container(width=ancho) for _ in range(n)]


# --- Datos -------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def serie(id_serie: str) -> pd.DataFrame:
    df = almacen.leer_serie(id_serie)
    return df if df is not None else pd.DataFrame(columns=["fecha", "valor"])


def ultimo(id_serie: str) -> tuple[pd.Timestamp | None, float | None]:
    df = serie(id_serie)
    if df.empty:
        return None, None
    fila = df.iloc[-1]
    return fila["fecha"], float(fila["valor"])


def valor_hace(id_serie: str, meses: int = 12) -> float | None:
    df = serie(id_serie)
    if df.empty:
        return None
    objetivo = df["fecha"].iloc[-1] - pd.DateOffset(months=meses)
    previo = df[df["fecha"] <= objetivo]
    return float(previo["valor"].iloc[-1]) if not previo.empty else None


def recortar(df: pd.DataFrame, anios: int | None) -> pd.DataFrame:
    if anios is None or df.empty:
        return df
    return df[df["fecha"] >= df["fecha"].max() - pd.DateOffset(years=anios)]


# --- Gráficos ----------------------------------------------------------------------
def _estilo(fig: go.Figure, altura: int, unidad: str = "") -> go.Figure:
    fig.update_layout(
        height=altura,
        margin=dict(l=8, r=8, t=28, b=8),
        separators=",.",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title=None),
        yaxis=dict(title=unidad or None, zeroline=False),
        xaxis=dict(title=None),
    )
    return fig


def lineas(series: dict[str, pd.DataFrame], unidad: str, colores: list[str] | None = None,
           altura: int = 320, referencias: list[tuple[float, str]] | None = None,
           decimales: int = 2) -> go.Figure:
    colores = colores or PALETA
    fig = go.Figure()
    for i, (nombre, df) in enumerate(series.items()):
        fig.add_scatter(
            x=df["fecha"], y=df["valor"], mode="lines", name=nombre,
            line=dict(width=2, color=colores[i % len(colores)]),
            hovertemplate=f"%{{y:,.{decimales}f}} {unidad}<extra>{nombre}</extra>",
        )
    for valor, etiqueta in referencias or []:
        fig.add_hline(y=valor, line=dict(color=GRIS_REF, width=1, dash="dot"),
                      annotation_text=etiqueta, annotation_position="top left",
                      annotation_font_color=GRIS_REF)
    fig.update_layout(showlegend=len(series) > 1)
    return _estilo(fig, altura, unidad)


TAMANO_LETRA_GRAFICOS = 14


def mostrar(fig: go.Figure) -> None:
    """Muestra un gráfico con márgenes que se ajustan a las etiquetas de los ejes (nunca se cortan)."""
    m = fig.layout.margin
    fig.update_layout(
        font=dict(size=TAMANO_LETRA_GRAFICOS),
        margin=dict(l=max(m.l or 0, 12), r=max(m.r or 0, 20), t=max(m.t or 0, 36), b=max(m.b or 0, 12)),
    )
    fig.update_xaxes(automargin=True, title_standoff=12, exponentformat="none", separatethousands=True)
    fig.update_yaxes(automargin=True, title_standoff=12, exponentformat="none", separatethousands=True)
    st.plotly_chart(fig, width="stretch", theme=None,
                    config={"displaylogo": False, "locale": "es"})


def ficha(s: Serie) -> None:
    """Metadatos citables de una serie."""
    reg = almacen.leer_registro().get(s.id, {})
    df = serie(s.id)
    filas = {
        "Fuente": s.fuente,
        "Frecuencia": s.frecuencia,
        "Unidad": s.unidad,
        "Cobertura": (f"{periodo_txt(df['fecha'].min(), s.frecuencia)} – "
                      f"{periodo_txt(df['fecha'].max(), s.frecuencia)}") if not df.empty else "—",
        "Última descarga": reg.get("actualizado", "—"),
        "Identificador interno": f"`{s.id}`",
    }
    st.markdown("\n".join(f"- **{k}:** {v}" for k, v in filas.items()))
    if s.nota:
        st.caption(s.nota)
    if s.url_consulta:
        st.caption(f"Consulta oficial: {s.url_consulta}")
    if reg.get("estado") == "error":
        st.warning(f"La última actualización falló ({reg.get('intento')}). Se muestra el dato previo.")


def boton_descarga(df: pd.DataFrame, nombre_archivo: str, etiqueta: str = "Descargar CSV",
                   clave: str | None = None) -> None:
    st.download_button(etiqueta, df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=nombre_archivo, mime="text/csv", key=clave,
                       icon=":material/download:")


def tarjeta(id_serie: str, etiqueta: str | None = None, decimales: int = 2,
            color_delta: str = "off", meses_spark: int = 36) -> None:
    """KPI con variación frente a hace 12 meses y minigráfico."""
    s = POR_ID[id_serie]
    fecha, valor = ultimo(id_serie)
    if valor is None:
        st.metric(etiqueta or s.nombre, "Sin datos")
        return
    previo = valor_hace(id_serie, 12)
    sufijo = "" if s.unidad in ("puntos", "COP por USD") else (" p.p." if s.es_tasa else "")
    if previo is None:
        delta = None
    elif s.es_tasa:
        d = valor - previo
        delta = f"{'+' if d > 0 else ''}{num(d, decimales)}{sufijo} vs. hace 12 m"
    else:
        d = valor / previo - 1
        delta = f"{'+' if d > 0 else ''}{pct(d, 1)} vs. hace 12 m"
    df = serie(id_serie)
    df = df[df["fecha"] >= df["fecha"].max() - pd.DateOffset(months=meses_spark)]
    if s.frecuencia == "Diaria":
        df = df.set_index("fecha")["valor"].resample("W").last().dropna().reset_index()
    unidad = "%" if s.unidad.startswith("%") else ""
    st.metric(
        etiqueta or s.nombre,
        f"{num(valor, decimales)}{' ' + unidad if unidad else ''}",
        delta=delta,
        delta_color=color_delta,
        help=f"{s.fuente} · dato de {periodo_txt(fecha, s.frecuencia)}",
        chart_data=df["valor"].tolist(),
        chart_type="line",
        border=True,
    )
    st.caption(f"{periodo_txt(fecha, s.frecuencia)} · {s.unidad}")
