# Observatorio Macro-Financiero de Colombia

Tablero del grupo de investigación en finanzas para **monitorear la coyuntura macroeconómica
de Colombia** y **estimar el costo de capital** (Ke y WACC) con supuestos trazables y citables.

## Contenido

| Página | Qué ofrece |
|---|---|
| **Coyuntura** | 8 indicadores clave con variación a 12 meses, lectura rápida automática y Ke de referencia |
| **Indicadores** | 20 series en 7 bloques, ficha técnica, descarga en CSV y comparador (tasas o índice base 100) |
| **Costo de capital** | CAPM global + CRP, Fisher y WACC; cascada del Ke, ficha citable, sensibilidad, WACC por industria e historial de supuestos |
| **Beta propio vs Damodaran** | Beta por industria estimado con acciones latinoamericanas de Yahoo Finance frente al de Damodaran, Ke con cada fuente, empresas detrás de cada industria y elección de la fuente que usarán Valoración y Proyectos |
| **Comparador de acciones** | Cualquier ticker de Yahoo Finance: retorno por periodo, riesgo (volatilidad, caída máxima, VaR, beta, alfa), valoración (P/E, P/B, EV/EBITDA, dividendo), solidez (ROE, márgenes, D/E), ficha por acción y conexión con el beta de su industria |
| **Catálogo de acciones** | Explorador con filtros por país, índice, sector y tipo: Colombia (BVC y ADR), Latinoamérica (585 del cuaderno), EE. UU. (todo Nasdaq y NYSE, S&P 500, Nasdaq-100, ETF) y los índices FTSE 100, DAX, CAC 40, Euro Stoxx 50, IBEX 35, FTSE MIB, AEX, SMI, S&P/TSX 60 y Hang Seng (`python actualizar_universo.py`). También acepta cualquier símbolo de Yahoo Finance |
| **Portafolio** | Pesos editables (igual ponderado, mínima varianza, máximo Sharpe), desempeño frente a un índice, aporte al riesgo, correlaciones, VaR y frontera eficiente sin ventas en corto |
| **Evaluación de proyectos** | Flujo de caja del proyecto y del inversionista, deuda, capital de trabajo, pérdidas fiscales; VPN, TIR, TIRM, APV; tornado, escenarios macro y Monte Carlo |
| **Valoración de empresas** | Estados financieros editables o desde Excel, diagnóstico (ROIC, EVA), DCF del FCFF con valor terminal consistente, puente de valor, sensibilidad WACC × g y contraste con múltiplos |
| **Metodología y fuentes** | Estado de cada serie, fórmulas y referencias académicas |

## Fuentes

| Fuente | Series | Acceso |
|---|---|---|
| Banco de la República | TPM, IBR, TES 1/5/10A, COLCAP | API SDMX (`totoro.banrep.gov.co`) |
| DANE (vía OCDE) | PIB, IPC total y básico, desempleo | API SDMX OCDE |
| Superfinanciera | TRM | datos.gov.co (Socrata) |
| Reserva Federal (FRED) | Tesoro 10A, breakeven 10A, CPI EE. UU. | CSV público o API con clave |
| Banco Mundial | Cuenta corriente, IED, deuda y balance fiscal | API WDI |
| Damodaran (NYU Stern) | Betas por industria, ERP, CRP, tasa impositiva, múltiplos EV/EBITDA y P/E | Archivos Excel |
| Yahoo Finance (cuaderno `Beta_Latinoamerica_CAPM.ipynb`) | Betas propios por industria (acciones de Brasil, México, Chile, Argentina, Colombia y otros) | Archivo `resultados_beta_latam.xlsx` importado con `importar_beta_latam.py` o desde la página |
| Superintendencia de Sociedades | Estados financieros NIIF por empresa (2015 en adelante) para la valoración | datos.gov.co (consulta en línea por NIT o nombre) |

## Uso local

```bash
pip install -r requirements.txt
python actualizar_datos.py      # descarga todo (unos 2 minutos)
streamlit run app.py
```

- `python actualizar_datos.py tpm trm` actualiza solo esas series.
- Opcional: define la variable de entorno `FRED_API_KEY` (clave gratuita en
  https://fredaccount.stlouisfed.org) para usar la API oficial de FRED.
- `python importar_beta_latam.py resultados_beta_latam.xlsx` carga la corrida del cuaderno de betas propios
  (también se puede subir el archivo desde la página «Beta propio vs Damodaran»).
- Pruebas del motor financiero: `python -m pytest tests`.

## Publicar para el grupo (Streamlit Community Cloud, gratis)

1. Sube la carpeta `observatorio_macro/` a un repositorio de GitHub, incluida la carpeta `datos/`.
2. En https://share.streamlit.io crea una app que apunte a `app.py`.
3. La acción `.github/workflows/actualizar_datos.yml` descarga los datos cada día hábil y
   los guarda en el repositorio. Streamlit redespliega la app automáticamente con cada cambio.
   Si quieres usar la API de FRED, agrega `FRED_API_KEY` en *Settings → Secrets* del repositorio.

## Modo público (para estudiantes)

Si el tablero se publica abierto, cualquier visitante comparte el mismo servidor. Para que nadie pueda
volver a descargar todas las fuentes ni reemplazar el beta propio con un archivo subido, activa el modo
público en *Settings → Secrets* de Streamlit Community Cloud:

```toml
publico = true
admin_clave = "una-clave-larga"   # opcional: habilita un campo «Administración» en la barra lateral
```

### Claves opcionales (Secrets)

- `FRED_API_KEY`: clave gratuita de https://fredaccount.stlouisfed.org. FRED rechaza o demora las conexiones desde servidores
  compartidos (GitHub Actions, Streamlit Cloud); con la clave la descarga del Tesoro, el breakeven y el CPI de EE. UU. es estable.
  Agrégala en *Settings → Secrets and variables → Actions* de GitHub (para la actualización diaria).
- `SOCRATA_APP_TOKEN`: token gratuito de datos.gov.co. Sin él, las consultas a la Supersociedades pueden ser limitadas por uso
  compartido. Agrégalo en los Secrets de Streamlit Cloud.

En modo público se ocultan «Actualizar datos ahora» y la importación del cuaderno; las demás páginas
funcionan igual. En uso local (sin estas variables) todo sigue disponible. Los datos se siguen actualizando
con la acción programada de GitHub. La identidad visual (logo, colores) está en `assets/` y `.streamlit/config.toml`.

## Estructura

```
app.py                  navegación y barra lateral
actualizar_datos.py     descarga de todas las fuentes
nucleo/
  catalogo.py           ficha técnica de cada serie (agregar indicadores aquí)
  fuentes.py            conectores a BanRep, OCDE, datos.gov.co, FRED y Banco Mundial
  yahoo.py              precios, perfil e indicadores de acciones y tipo de cambio (Yahoo Finance)
  portafolio.py         retorno, riesgo, beta, VaR, contribución al riesgo y frontera eficiente
  lecturas.py           interpretaciones automáticas de tablas y gráficos
  tema.py               identidad visual (estilos, plantilla de gráficos, tarjetas de lectura)
  seleccion.py          selector de acciones compartido por Comparador y Portafolio
  acceso.py             modo público: oculta las acciones que modifican datos
  beta_propio.py        beta propio de LatAm (Yahoo Finance) y combinación con Damodaran
  damodaran.py          lectura de betas, ERP, CRP e impuestos
  costo_capital.py      motor de costo de capital (funciones puras, con pruebas)
  finmat.py             VPN, TIR, TIRM, recuperación descontada
  escenarios.py         trayectorias macro (PIB, inflación, TRM por PPA)
  proyectos.py          motor de evaluación de proyectos, tornado y Monte Carlo
  valoracion.py         motor de valoración DCF, EVA y sensibilidad
  supersociedades.py    búsqueda de empresas y mapeo de cuentas NIIF a los rubros del modelo
  carga_archivos.py     lectura flexible de Excel/CSV con asignación de cuentas
  componentes.py        selector sector → WACC automático y editor del escenario macro
  mercado.py            supuestos de mercado por defecto
  almacen.py            lectura y escritura de datos locales (CSV/JSON)
  ui.py                 tarjetas, gráficos y formato colombiano
paginas/                una página del tablero por archivo
datos/                  series descargadas, registro e historial de supuestos
tests/                  pruebas del costo de capital
```

### Agregar un indicador
Añade una entrada `Serie(...)` en `nucleo/catalogo.py` con su proveedor y parámetros, y luego
ejecuta `python actualizar_datos.py <id>`. Aparece automáticamente en su bloque.

## Hoja de ruta

- **Fase 1 (lista):** indicadores clave, calculadora Ke/WACC con CAPM + CRP, sensibilidad,
  WACC por industria y fichas citables.
- **Fase 2 (lista):** evaluación de proyectos y valoración de empresas, con WACC automático por sector
  y escenarios macro interactivos.
- **Fase 2b:** opciones reales (árbol binomial), comparación de modelos (Godfrey-Espinosa, D-CAPM de Estrada, Lessard), curva TES
  completa, serie histórica del WACC por sector, beta local con datos de la BVC.
- **Fase 3:** escenarios y proyecciones (encuesta de expectativas del BanRep y MFMP), alertas
  y boletín mensual automático.

## Limitaciones

- El PIB, el IPC y el desempleo llegan vía OCDE, con algunos días de rezago frente al DANE.
- Las series fiscales del Banco Mundial tienen rezago anual. Para cifras oficiales recientes,
  usa el Marco Fiscal de Mediano Plazo.
- Las betas de Damodaran son de empresas de mercados emergentes o globales, no exclusivamente
  colombianas.
- El diferencial TES − Tesoro no equivale a un CRP en dólares.
