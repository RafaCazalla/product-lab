# BeSoccer Product Lab

Panel interno de analítica de producto de BeSoccer, orientado a decisiones de CPO/CRO:
cómo se usa la app, rating por idioma, retención, embudos y segmentos.

**Estado: v0.1.** Una sola página autónoma, sin build y sin dependencias. Los datos son
sintéticos y deterministas: la plataforma está lista para enchufar datos reales.

## Estructura

```
index.html                    toda la aplicación (estilos + datos + gráficas + vistas)
tools/validate_palette.py     valida una paleta categórica (banda de luminosidad, croma,
                              separación bajo daltonismo, contraste). Sin dependencias.
tools/oklch.py                genera hex en OKLCH (snap a color válido dentro de gama)
docs/roadmap.md               qué falta, por orden
```

No hay servidor ni build: `open index.html` basta. Para probar en móvil de verdad,
`python3 -m http.server 8000` desde la raíz.

## Design system de BeSoccer

Los tokens **no son inventados**: salen del CSS de producción de `besoccer.com`
(`/media/css/style.css`), que usa hex literales, no custom properties.

| Rol | Valor |
|---|---|
| Verde marca | `#3B811F` (el color dominante del sitio) · variantes `#33701B`, `#569F33`, `#51A331` |
| Verde "en directo" | `#01D77F` |
| Tinta / secundario / apagado | `#383838` · `#6A6A6A` · `#A7A7A7` |
| Hairline / plano / hueco | `#E1E1E1` · `#ECECEC` · `#F9F9F9` |
| Rojo · azul · ámbar | `#BD2F42` · `#01B1FC`, `#75B8E5` · `#E9B12C`, `#FFB80C` |
| Tipografía | **Asap Condensed** (400/600) para títulos, cifras y etiquetas; **Asap** para texto |

BeSoccer no tiene tema oscuro real (`.dark` es un modificador de componente). El tema
oscuro de este panel es propio: se define **solo con tokens**, en tres ámbitos
(`:root`, `@media (prefers-color-scheme: dark)` con guarda `:not([data-theme="light"])`,
y `:root[data-theme="dark"]`). Nunca pongas un color únicamente dentro de un bloque
`@media` o `[data-theme]`: el usuario que no ha elegido tema no lo recibiría.

## Reglas de gráficas (no negociables)

La paleta de series está **validada**, y el orden de los slots es el mecanismo de
seguridad para daltonismo. No la reordenes ni añadas un séptimo color sin revalidar:

```bash
python3 tools/validate_palette.py "#3b811f,#0479b2,#bd2f42,#7756d0,#d8a10c,#18a0a1" light "#ffffff"
python3 tools/validate_palette.py "#57a52e,#2f95cf,#d9515f,#9179e0,#b98d16,#23a9aa" dark  "#1b1e1a"
```

Ambas pasan hoy: ΔE CVD adyacente 16,4 (claro) / 16,2 (oscuro); suelo de visión normal
21,2 / 19,7. El ámbar claro `#d8a10c` queda por debajo de 3:1 sobre blanco, así que
**siempre lleva etiqueta directa o vista de tabla** (ya la lleva).

- **Un solo eje.** Nunca dos escalas Y en la misma gráfica. Dos magnitudes distintas →
  dos gráficas, o indexadas a una base común (=100).
- **Secuencial = un tono** (rampa verde `--q1`…`--q6`, claro→oscuro). **Ordinal** para
  pasos ordenados (embudos): `--o1`…`--o5`. **Divergente** = azul ↔ rojo con gris neutro
  al centro (nunca verde↔rojo: es el fallo clásico de daltonismo).
- **El color sigue a la entidad, no a su posición.** Filtrar no debe repintar las series
  supervivientes.
- Marcas finas (barras ≤ 24 px, líneas 2 px), rejilla hairline **sólida**, hueco de 2 px
  en color de superficie entre marcas contiguas, anillo de 2 px en los puntos.
- **Etiquetas directas selectivas**: el extremo, el máximo o la serie que cuenta. Nunca
  un número en cada punto. El texto usa tokens de tinta, jamás el color de la serie.
- Leyenda siempre que haya ≥ 2 series; una sola serie no lleva leyenda.
- Las formas de "todos los pares" (dispersión, burbujas) **no** pasan la validación con
  esta paleta: usa barras, líneas, apilados, mapa de calor, dumbbell o divergente.
- Toda gráfica tiene hover + foco por teclado y **gemela en tabla** (botón "Tabla"):
  ningún valor vive solo en el color o en el tooltip.

## Arquitectura de `index.html`

El fichero va en bloques `<script>` en este orden, y conviene mantenerlo así:

1. **Utilidades** — `nf/compact/pct/dur/signed` (formato es-ES), `rng()` (PRNG sembrado),
   `S()` (SVG), `E()`, tooltip compartido, `mount()/unmount()` + `ResizeObserver`.
2. **Modelo de datos** — `PLATS`, `SEGS`, `MARKETS`, `BASE`, `state`, `key()`,
   `metric(name)`, `series(name, {offset})`, `activeBase()`, `deltaOf(name)`.
3. **Primitivas de gráfica** — `lineChart`, `sparkline`, `barsH`, `stackedRows`,
   `heatmap`, `funnel`, `dumbbell`, `diverging`, `groupedCols`, `legend`, `table`, `meterCell`.
4. **Componentes de tarjeta** — `card`, `head`, `plotCard` (incluye la vista de tabla),
   `kpiTile`, `readCard`, `eyebrow`.
5. **Derivadas por corte** — `sectionMix`, `screenRows`, `featureRows`, `cohorts`,
   `retentionCurves`, `funnelActivation`, `funnelPremium`, `reach`, `segmentIndex`,
   y las constantes de contenido (`SECTIONS`, `SCREENS`, `EXPERIMENTS`, `CRO`, `THEMES`).
6. **Vistas** — `renderResumen`, `renderUso`, `renderIdiomas`, `renderRetencion`,
   `renderCro`, `renderSegmentos`.
7. **Enrutado y filtros** — `renderActive()`, `selectTab()`, listeners, tema.

### Para enchufar datos reales

Sustituye **solo la capa 2 y las derivadas de la capa 5**. Las primitivas y las vistas no
cambian. Los tres puntos de entrada son:

- `metric(name)` → un escalar bajo el corte activo (`dau`, `spu`, `len`, `d7`, `prem`, `notif`, `rating`, `stick`).
- `series(name, {offset})` → `{x, v, bands, dates, step}`; `offset` en días sirve para el
  periodo anterior. Agrega a semanas cuando el rango pasa de 60 días.
- las funciones `*Rows()` / `cohorts()` / `funnel*()` → filas ya agregadas.

Todas leen `state` (`range`, `plat`, `market`, `seg`, `compare`) y `key()` como clave de
caché/semilla. Si las llamadas pasan a ser asíncronas, `renderActive()` es el único sitio
que hay que volver `async`: mantiene el render anterior a opacidad reducida (`.stale`)
mientras llegan los datos, sin esqueleto ni salto de layout.

### Reglas de coherencia de cifras (mantener)

Son la razón de que las tarjetas no se contradigan entre sí:

- Todo lo que **cuenta usuarios** parte de `activeBase()` (media del periodo), no de
  `metric('dau')`. Así ninguna tarjeta discute con la cifra del héroe.
- Los KPI de embudo se **derivan del embudo** (`fp[3]/fp[0]`, mayor caída calculada), no
  se escriben a mano.
- La tabla de segmentos divide por el multiplicador del segmento filtrado para no
  contarlo dos veces.
- Exactamente **una cifra-héroe por vista** (hoy, DAU en Resumen).

## Convenciones

- **Todo en español**, formato `es-ES` vía `Intl` (coma decimal, punto de millar).
- Sin librerías. Si algún día hace falta una, se carga UMD desde cdnjs con versión fijada.
- `textContent` para insertar cualquier etiqueta en el DOM (nunca `innerHTML` con datos).
- `font-variant-numeric: tabular-nums` solo en columnas de números; las cifras grandes
  van con figuras proporcionales.
- Respeta `prefers-reduced-motion` y deja foco visible.

## Publicación

Está publicado como Artifact privado:
`https://claude.ai/code/artifact/0c86327e-8e32-4740-bdd7-6633ebe37da6`

El fichero se movió de sitio desde la sesión que lo publicó, así que para actualizar ese
mismo enlace hay que **pasar la URL explícitamente** al publicar (`url: <la de arriba>`);
publicar sin ella crearía un artifact nuevo y distinto.
