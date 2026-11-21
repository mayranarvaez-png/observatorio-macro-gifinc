"""Identidad visual de GIFINC: estilos de la página, plantilla de gráficos y componentes de presentación.

Colores medidos del logo: rojo #E91D26 y gris #585858. La paleta categórica de los gráficos mantiene el
orden de `ui.PALETA`: las parejas adyacentes superan 22 de ΔE en visión normal y 9 simulando daltonismo
(comprobado con una reimplementación propia de OKLab + Machado 2009, no con el validador de la skill).
Tres colores quedan por debajo de 3:1 de contraste sobre blanco (verde, ámbar y rosa): por eso todo gráfico
de varias series lleva leyenda y las series se rotulan en la tabla.
"""
from __future__ import annotations

import html
import re

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from . import ui

ROJO, GRIS, TINTA = ui.ROJO, ui.GRIS, "#2B2B2E"

_CSS = f"""
<style>
:root {{ --gif-rojo:{ROJO}; --gif-gris:{GRIS}; --gif-tinta:{TINTA}; }}
.block-container {{ padding-top: 2.2rem; max-width: 100%; padding-left: clamp(1rem, 3vw, 3rem); padding-right: clamp(1rem, 3vw, 3rem); }}

/* Encabezado de página */
.gif-banner {{
  background: linear-gradient(105deg, #2B2B2E 0%, #585858 58%, {ROJO} 150%);
  color: #fff; border-radius: 16px; padding: 26px 32px 24px 32px; margin: 0 0 18px 0;
  box-shadow: 0 6px 18px rgba(43,43,46,.18); position: relative; overflow: hidden;
}}
.gif-banner:after {{
  content: ""; position: absolute; right: -40px; top: -40px; width: 220px; height: 220px; border-radius: 50%;
  background: rgba(233,29,38,.22);
}}
.gif-banner .gif-kicker {{ letter-spacing: .16em; font-size: .72rem; font-weight: 700; color: #FFB3B6; text-transform: uppercase; }}
.gif-banner h1 {{ color: #fff !important; margin: 4px 0 6px 0 !important; padding: 0 !important; font-size: 2.05rem !important; line-height: 1.15 !important; }}
.gif-banner p {{ color: #E9E9EC; margin: 0; max-width: 62rem; font-size: .98rem; }}
.gif-chips {{ margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; position: relative; z-index: 1; }}
.gif-chip {{ background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); color: #fff;
  border-radius: 999px; padding: 2px 12px; font-size: .78rem; }}

/* Títulos de sección */
h2, h3 {{ border-left: 5px solid {ROJO}; padding-left: 12px !important; margin-top: 1.4rem !important; }}

/* Tarjetas de indicadores */
[data-testid="stMetric"] {{
  background: linear-gradient(180deg, #FFFFFF 0%, #F6F6F8 100%); border-left: 5px solid {ROJO};
  border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 4px rgba(0,0,0,.07);
}}
[data-testid="stMetricLabel"] p {{ color: {GRIS}; font-weight: 600; letter-spacing: .01em; }}
[data-testid="stMetricValue"] {{ color: {TINTA}; font-weight: 750; font-size: clamp(1.3rem, 1.9vw, 1.95rem) !important;
  line-height: 1.15; }}
/* Nada se corta con «…»: etiquetas, valores y variaciones pasan a la línea siguiente si no caben. */
[data-testid="stMetricValue"], [data-testid="stMetricValue"] *,
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] *,
[data-testid="stMetricDelta"], [data-testid="stMetricDelta"] * {{
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important; overflow-wrap: anywhere;
}}

/* Pestañas */
button[data-baseweb="tab"] {{ font-weight: 600; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color: {ROJO}; }}
[data-baseweb="tab-highlight"] {{ background-color: {ROJO} !important; height: 3px !important; }}

/* Tarjeta de análisis */
.gif-lectura {{ border-radius: 12px; padding: 14px 18px 10px 18px; margin: 10px 0 16px 0;
  background: rgba(128,128,128,.08); border: 1px solid rgba(128,128,128,.22); border-left-width: 6px; }}
.gif-lectura .gif-lt {{ font-weight: 750; letter-spacing: .02em; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }}
.gif-lectura ul {{ margin: 4px 0 4px 0; padding-left: 1.2rem; }}
.gif-lectura li {{ margin: 3px 0; line-height: 1.45; }}
.gif-lectura .gif-nota {{ font-size: .8rem; opacity: .7; margin-top: 4px; }}
.gif-tono-neutro {{ border-left-color: {GRIS}; }}
.gif-tono-ok {{ border-left-color: #1BAF7A; }}
.gif-tono-alerta {{ border-left-color: #EDA100; }}
.gif-tono-riesgo {{ border-left-color: {ROJO}; }}

/* Etiquetas de estado (semáforo con texto: nunca solo color) */
.gif-tag {{ display:inline-block; border-radius:6px; padding:1px 8px; font-size:.78rem; font-weight:650; }}
.gif-tag.ok {{ background:#DDF3EA; color:#0B6B47; }}
.gif-tag.alerta {{ background:#FDF0CC; color:#7A5600; }}
.gif-tag.riesgo {{ background:#FBDADB; color:#9B1017; }}
.gif-tag.neutro {{ background:#E8E8EB; color:#444; }}
</style>
"""

# --- Plantilla de gráficos --------------------------------------------------------------
_FUENTE = "Segoe UI, Inter, Roboto, Helvetica, Arial, sans-serif"


def _registrar_plantilla() -> None:
    if "gifinc" in pio.templates:
        return
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=_FUENTE, color=TINTA),
        colorway=ui.PALETA,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#ECECEF", linecolor="#C9C9CF", zeroline=False, ticks="outside", tickcolor="#C9C9CF",
                   automargin=True, title=dict(standoff=12), exponentformat="none", separatethousands=True),
        yaxis=dict(gridcolor="#ECECEF", linecolor="#C9C9CF", zeroline=False, automargin=True, title=dict(standoff=12),
                   exponentformat="none", separatethousands=True),
        hoverlabel=dict(bgcolor="white", bordercolor="#C9C9CF", font=dict(family=_FUENTE, size=13, color=TINTA)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=13)),
        title=dict(font=dict(size=16, color=TINTA), x=0),
        separators=",.",
    )
    pio.templates["gifinc"] = t
    pio.templates.default = "gifinc"


def aplicar() -> None:
    """Inyecta los estilos y la plantilla de gráficos. Se llama una vez desde app.py."""
    _registrar_plantilla()
    st.markdown(_CSS, unsafe_allow_html=True)


# --- Componentes -----------------------------------------------------------------------
def _negritas(texto: str) -> str:
    """Escapa HTML y convierte **negrita** de Markdown, para poder usar texto con formato dentro de las tarjetas."""
    seguro = html.escape(texto)
    seguro = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", seguro)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", seguro)


def encabezado(titulo: str, subtitulo: str = "", seccion: str = "", chips: list[str] | None = None) -> None:
    """Banda de título de página (sustituye a st.title + st.caption)."""
    chips_html = "".join(f'<span class="gif-chip">{html.escape(c)}</span>' for c in (chips or []))
    st.markdown(
        f'<div class="gif-banner">'
        f'{f"<div class=gif-kicker>{html.escape(seccion)}</div>" if seccion else ""}'
        f'<h1>{html.escape(titulo)}</h1>'
        f'{f"<p>{_negritas(subtitulo)}</p>" if subtitulo else ""}'
        f'{f"<div class=gif-chips>{chips_html}</div>" if chips_html else ""}'
        f'</div>', unsafe_allow_html=True)


ICONOS = {"neutro": "◆", "ok": "✔", "alerta": "▲", "riesgo": "●"}


def lectura(puntos: list[str], titulo: str = "Análisis", tono: str = "neutro", nota: str = "") -> None:
    """Tarjeta con una interpretación en viñetas. El tono cambia el color del borde y el símbolo (no solo el color)."""
    if not puntos:
        return
    lis = "".join(f"<li>{_negritas(p)}</li>" for p in puntos)
    st.markdown(
        f'<div class="gif-lectura gif-tono-{tono}"><div class="gif-lt">'
        f'<span>{ICONOS.get(tono, "◆")}</span><span>{html.escape(titulo)}</span></div>'
        f'<ul>{lis}</ul>{f"<div class=gif-nota>{_negritas(nota)}</div>" if nota else ""}</div>',
        unsafe_allow_html=True)


def etiqueta(texto: str, tono: str = "neutro") -> str:
    """HTML de una etiqueta de estado, para usar dentro de st.markdown(unsafe_allow_html=True)."""
    return f'<span class="gif-tag {tono}">{html.escape(texto)}</span>'
