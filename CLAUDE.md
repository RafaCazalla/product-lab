# BeSoccer Product Lab

Panel interno de la **voz del usuario en Google Play**, orientado a decisiones de
CPO/CRO: la nota que ponen y lo que escriben.

**Estado: v0.6.** Una sola página autónoma, sin build y sin dependencias. **Todo lo que
muestra es dato real**, incrustado en el propio HTML, y ahora de **dos fuentes**:
9.754 valoraciones de Google Play (710 con texto, 31 may – 14 ago 2026) y 3.454
respuestas de la encuesta de salida (10 jun – 14 sep 2026, España, Android).

**El panel no interpreta por su cuenta.** Todo lo que se lee sin pulsar nada es
aritmética sobre los datos. La interpretación la escribe Claude, y solo cuando se pulsa
«Ejecutar contexto» (ver «Lectura de IA»).

Cuatro pestañas, cada una con un cometido:

| Pestaña | Qué contesta |
|---|---|
| **Resumen** | Portada: las dos secciones resumidas y por dónde empezar. |
| **Rating** | La nota: reparto, idioma, versión, dispositivo y calidad de la muestra. |
| **Reviews** | El texto: embudo de la voz, temas con su signo, sentimiento y los verbatims en crudo. |
| **Survey** | La encuesta de salida: de qué se queja quien ya ha dicho que la app no le gusta, y en qué se parece o no a lo que dice Play. |

En v0.2 convivían estas vistas con seis pestañas de métricas de producto sintéticas
(comportamiento, retención, embudos, segmentos). **Se eliminaron en v0.3**, junto con su
modelo de datos, su barra de filtros y las primitivas que solo ellas usaban
(`lineChart`, `sparkline`, `stackedRows`, `dumbbell`, `meterCell`, `pill`). Están en el
historial de git si hacen falta.

**El tema oscuro es el predeterminado** y **la interfaz está en español e inglés**
(ver «Design system» e «Idioma»).

## Estructura

```
index.html                    toda la aplicación (estilos + datos + gráficas + vistas)
data/reviews.json             valoraciones reales ya clasificadas (copia legible del
                              bloque que va incrustado en index.html)
tools/reviews_build.py        CSV de Google Play -> JSON clasificado. Etiqueta tema y
                              sentimiento con un léxico multiidioma. Sin dependencias.
tools/survey_build.py         CSV de encuesta -> JSON clasificado. Importa el
                              clasificador de reviews_build: misma taxonomía, que es
                              lo único que permite comparar las dos fuentes.
datasurvey/                   CSV de origen de las encuestas (NO se publica: trae
                              tokens de FCM, ver «Privacidad»)
data/survey.json              respuestas clasificadas, sin identificadores
tools/smoke.js                prueba de humo: renderiza las cuatro vistas bajo ~2.900
                              cortes, en los dos idiomas, y caza excepciones, cifras
                              degeneradas y cadenas sin traducir
.claude/skills/               skill de criterio de visualización (data-visualization,
                              de anthropics/knowledge-work-plugins)
tools/validate_palette.py     valida una paleta categórica (banda de luminosidad, croma,
                              separación bajo daltonismo, contraste). Sin dependencias.
tools/oklch.py                genera hex en OKLCH (snap a color válido dentro de gama)
docs/roadmap.md               qué falta, por orden
```

No hay servidor ni build: `open index.html` basta. Para probar en móvil de verdad,
`python3 -m http.server 8000` desde la raíz.

## Orden de los módulos

Cada módulo movible lleva en `data-mod` una **clave estable e independiente del
idioma** (`dist`, `lang-dev`, `evo`, `ctx`…). El orden se guarda por vista en
`localStorage` (`bsp-order-<vista>`) y `layoutModules(view, g)` lo aplica al final de
cada render, así que la disposición sobrevive a recargas, a cambios de filtro y a cambiar
de idioma.

- La clave **no puede salir del título**: los títulos están traducidos, y el orden se
  perdería al cambiar de idioma. Se pasa a mano: `key: 'dist'` en `plotCard`, o
  `mod(node, 'hero', etiqueta)` para las tarjetas que se construyen a pelo.
- **Las claves que no estén guardadas van al final** en su orden natural. Así, añadir una
  tarjeta nueva no rompe la disposición de quien ya tenía una guardada, y una clave
  guardada que ya no existe se ignora sin perder módulos. La prueba de humo comprueba
  las dos cosas.
- **La cabecera de cada vista no se mueve**: el primer `eyebrow` y la nota de fuente no
  llevan clave, para que el encabezado no acabe por el medio. Todo lo demás sí, incluidos
  los `eyebrow` de sección.
- **Hay vía de teclado**: la pinza es un `<button>` y responde a las flechas. Sin eso el
  reordenado no existiría para quien no usa ratón.
- «Restablecer orden», en la barra de filtros, borra la clave de la vista activa.

## Lectura de IA (bajo demanda)

El panel distingue dos clases de texto y **no las mezcla nunca**:

| | Quién lo escribe | Cuándo aparece |
|---|---|---|
| **Cifras, titulares calculados, umbrales y avisos de muestra** | el propio código, con aritmética | siempre |
| **«Qué significa esto y qué haría»** | Claude | solo al pulsar «Ejecutar contexto» |

Antes de v0.4 la interpretación iba escrita a mano en tarjetas `readCard` y en las notas
al pie. Eso se ha eliminado: una opinión fija bajo unos datos que se filtran deja de ser
cierta en cuanto cambias el corte. Lo que queda en las notas es **método**, no lectura:
por qué el umbral es n ≥ 30, qué mide el signo, por qué no hay serie temporal. Eso tiene
que quedarse; sin esas notas el panel engaña.

`contextCard(view)` es la tarjeta, una por vista. Lo que hace al pulsar:

1. `ctxPrompt(view)` compone el **brief de datos**: texto plano con las cifras que están
   en pantalla en ese corte, más una muestra de hasta 24 verbatims. Nada que no se esté
   mostrando. Se puede leer entero con «Ver prompt» y copiar con «Copiar prompt».
2. Si la página corre publicada como Artifact con la capacidad `sample` declarada,
   pregunta a Claude con la cuenta de quien mira (`sample.json`, `modelTier: 'default'`);
   la primera llamada le pide permiso.
3. Si no (abierta en `file://`, o sin la capacidad), no hay a quién preguntar: ofrece el
   prompt para llevarlo a Claude a mano y **«Pegar respuesta»** para traer el resultado.

Reglas de esta parte:

- **Declarar la capacidad al publicar**: `capabilities: {sample: {}}`. Si se omite en un
  republish se arrastra la declaración guardada; un objeto vacío la borra y el botón deja
  de encenderse.
- **`window.claude` puede no existir** (en `file://` no existe, y framed por un host que
  no contesta `use()` resuelve `null` a los ~10 s). Se comprueba
  `window.claude && typeof window.claude.use === 'function'` y se diseña para la
  ausencia: la página se pinta sin la función y el botón se enciende si llega.
- **Una lectura describe UN corte.** Se guarda en `CTX_CACHE` con la clave del corte
  (`ctxKey`) y solo reaparece si vuelves exactamente a él. Si cambias un filtro, la
  lectura anterior ya no habla de las cifras en pantalla y desaparece: es a propósito.
- **El prompt lleva las reglas dentro** porque `sample` no tiene memoria ni system prompt
  que la página controle: cada llamada ve solo el `input`. Las reglas prohíben inventar
  cifras, exigen citar la que sostiene cada afirmación, prohíben afirmar tendencias
  temporales y obligan a decir cuándo la base es pequeña.
- **Nunca llamar en bucle ni en un temporizador**, y nunca reintentar desde código: cada
  llamada gasta la cuota de quien mira. Solo al pulsar.
- La lectura sale marcada como escrita por Claude, con la advertencia de que **si una
  cifra no cuadra, manda la tarjeta**.

## La única gráfica temporal

`Rating por idioma, mes a mes` es la única tarjeta que dibuja el tiempo, y existe porque
se pidió explícitamente. Lo que la hace defendible:

- **Grano seleccionable (día · semana · mes), por defecto semana**, con el mismo umbral
  en los tres: un punto necesita `MIN_POINT` (30) valoraciones o no se dibuja. La
  recolección llegó en 9 lotes y se concentra en la primera quincena de cada mes (julio:
  4.152 valoraciones en la primera, 6 en la segunda), así que dos periodos contiguos no
  son muestras comparables y la nota lo dice.
- **El eje lleva TODOS los periodos del rango**, también los vacíos. Colocar los puntos
  por posición hacía que un hueco de tres semanas se viera igual que un día: el eje
  mentía sobre el tiempo. `lineChart` acepta `null` y parte la línea.
- **La tarjeta declara cuántos puntos dibuja de cuántos posibles.** Con grano diario son
  64 de 304: la limitación se ve en vez de disimularse con puntos que no sostiene nadie.
- **`lineChart` acepta huecos**: un `null` parte la línea en vez de inventar el tramo.
  Un mes que no llega a 60 valoraciones para un idioma no se dibuja.
- **Punto hueco cuando la base es menor de 300**, y la base va en el tooltip y en la
  tabla, columna a columna.
- **El titular calculado avisa del riesgo**: busca el mayor salto entre meses
  consecutivos y lo enseña **junto al cambio de base** que lo acompaña. Con estos datos
  sale que el español pasa de 3,69 a 4,75 entre junio y julio mientras su base pasa de 90
  a 4.158 valoraciones: casi con seguridad es la muestra, no el producto.

Si algún día la ingesta es diaria, esta tarjeta puede bajar a semanas y quitar los
huecos. Hasta entonces, **no añadas más gráficas de tiempo**.

## Criterio de visualización

En `.claude/skills/data-visualization` está instalada la skill de
`anthropics/knowledge-work-plugins` (commit `77961df`). **No es una librería**: es un
documento de criterio orientado a Python (matplotlib/seaborn/plotly). Sus patrones de
código no se usan aquí y no deben usarse: meterían un build, un runtime de Python o un
bundle de plotly, y este panel se abre con `open index.html`. Lo que sí se aplica es su
criterio, y de ahí salieron tres cosas que faltaban:

- **Titular calculado** (`insight` en `plotCard`): la skill pide que el título diga el
  hallazgo, no la categoría. Aquí el hallazgo se **calcula del corte** y se rehace con
  cada filtro, así que sigue siendo aritmética y no opinión.
- **Incertidumbre a la vista** (`ci: [lo, hi]` en `barsH`): bigotes del intervalo de
  Wilson. Antes el intervalo solo estaba en el tooltip y en la tabla, y una barra sola
  invita a conclusiones que el intervalo desmiente.
- **Texto alternativo por gráfica** (`alt` en las primitivas): un `role="img"` sin nombre
  accesible era un hueco silencioso. Ahora la gráfica entera se describe con su hallazgo.

## Idioma

La interfaz va en **español (original) e inglés**, con el botón `ES/EN` de la barra. El
español hace de clave: `t('Rating medio')` devuelve la traducción si existe y, si no, el
propio español. Así una cadena sin traducir se ve legible en vez de mostrar una clave
cruda o un hueco.

- **Nunca concatenes alrededor de una cifra.** `nf(n) + ' valoraciones'` se rompe al
  traducir porque el orden cambia. Va así: `t('{n} valoraciones', { n: nf(n) })`. Los
  huecos tienen que aparecer en los dos idiomas, y eso se comprueba al generar el bloque.
- **Los identificadores no se traducen.** `FAMS`, los ids de tema, `SENTS[].id` y
  `SIGNS[].id` viajan en `rstate` y hacen de clave de `Map`. Se traducen **al pintar**,
  con `famLabel()`, `topicLabel()`, `sentLabel()`, `signLabel()`.
- **Los números también cambian de idioma**: `es-ES` usa coma decimal, `en-GB` punto.
  `setLocale()` rehace los formateadores; no crees `Intl.NumberFormat` a mano.
- El texto de las reviews **jamás se traduce**: es contenido del usuario.
- Las etiquetas de tema las genera `tools/reviews_build.py` en español y se traducen
  como cualquier otra cadena. Si cambias una ahí, la traducción cae al español y la
  prueba de humo lo dice.
- La elección se recuerda en `localStorage` (`bsp-lang`); el tema, no.

Al añadir una cadena no hace falta buscar dónde va en el diccionario: **la prueba de humo
recorre las tres vistas en inglés y lista lo que falte**, listo para pegar.

### Antes de dar por bueno un cambio

```bash
osascript -l JavaScript tools/smoke.js      # macOS, sin dependencias: ~2.900 renders
```

Ejecuta cada vista contra un DOM simulado, **en los dos idiomas**, y falla si aparece una
excepción, si el DOM resultante contiene `NaN`, `Infinity`, `undefined` o `null`, o si
queda alguna cadena sin traducir. Además comprueba:

- **El arranque**, no solo las vistas por separado: que la pestaña inicial se pinte de
  verdad y que el sello, el pie y los filtros tengan contenido. Esto existe porque un
  fallo en `applyStaticI18n()` dejaba la primera pantalla en blanco mientras cambiar de
  pestaña funcionaba, y llamar a las vistas a mano no lo veía.
- **El orden de los módulos**: claves únicas, pinza en todos, que un orden guardado se
  aplique y que una clave desconocida no pierda módulos.

**`smoke.js` va casi entero dentro de dos literales de plantilla** (`SHIM` y `DRIVER`).
Dentro de ellos **no puede haber un backtick ni un `${`**, ni siquiera en un comentario:
un backtick cierra el literal antes de tiempo y el fichero deja de parsear con un error
que apunta a una línea que no tiene nada que ver. Ha pasado dos veces.

**Y el orden importa:** el barrido en inglés de una vista nueva tiene que ir **antes** de
`var miss = Array.from(I18N_MISS)`. Detrás de esa foto, sus cadenas sin traducir no
entran en el recuento y la prueba pasa en falso.

El shim imita al navegador en lo que importa para cazar estos fallos: `querySelector`
devuelve **`null`** para lo que no está o se ha desprendido del documento, `textContent`
desprende a los hijos, `appendChild`/`insertBefore` **mueven** en vez de duplicar, los
nodos con `data-i18n` se construyen con los `id` que llevan dentro, y `localStorage`
funciona de verdad. Si tocas el shim, no lo hagas más permisivo. Lo segundo es lo que se
cuela sin que nadie lo vea: un divisor a cero en una primitiva no lanza, solo pinta
`d="M0 4LNaN…"` y la barra desaparece. Así se encontraron los ceros de `barsH`, `funnel`,
`diverging`, `heatmap` y `groupedCols`, hoy todos protegidos.

**Toda primitiva de gráfica tiene que sobrevivir a un corte vacío**: `max === min`,
`total === 0` o `rows === []` son estados normales cuando el usuario cruza tres filtros
sobre datos reales, no casos imposibles.

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
oscuro de este panel es propio, y desde v0.3 **es el predeterminado**: se define solo con
tokens, en dos ámbitos que declaran los **45 tokens completos** cada uno:

- `:root` → **oscuro**. Es lo que recibe quien no ha elegido nada.
- `:root[data-theme="light"]` → claro. Lo pone el botón «Tema», y es la única forma de
  salir del oscuro.

Ya **no se consulta `prefers-color-scheme`**: «por defecto» significa oscuro para todo el
mundo, con luz u oscuridad en el sistema operativo. Si algún día se quiere volver a
respetar el sistema, el sitio es un `@media (prefers-color-scheme: light)` con guarda
`:root:not([data-theme="dark"])`, nunca un bloque que defina colores a medias.

La regla de fondo no cambia: **ningún color vive solo en un ámbito**. Si añades un token,
añádelo a los dos, o quien no haya tocado el botón se quedará sin él. La comprobación es
de una línea:

```bash
python3 - <<'EOF'
import re; css=open('index.html',encoding='utf-8').read()
g=lambda p: set(re.findall(r'(--[\w-]+):', re.search(p, css, re.S|re.M).group(1)))
d, l = g(r'^:root \{(.*?)^\}'), g(r'^:root\[data-theme="light"\] \{(.*?)^\}')
print('solo oscuro:', d-l or 'ninguno', '| solo claro:', l-d or 'ninguno')
EOF
```

`color-scheme` se declara en los dos ámbitos: es lo que hace que los `input[type="date"]`
de la barra de filtros salgan con los colores nativos correctos.

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
6. **Vistas sintéticas** — `renderResumen`, `renderUso`, `renderIdiomas`,
   `renderRetencion`, `renderCro`, `renderSegmentos`.
7. **Datos reales** — `const RD = {…}` (el bloque que genera `reviews_build.py --inline`).
8. **Capa real y sus vistas** — descompresión a arrays tipados, `rstate`, `rSel()`,
   `bucketBy()`, `wilson()`, `emptyCut()`, `renderRating`, `renderReviews`.
9. **Enrutado y filtros** — `renderActive()`, `selectTab()`, las dos barras, tema.

## Capa de datos (Google Play)

Es el único origen de datos del panel. Su estado es `rstate`, y la barra de filtros
`#f-real` lo maneja: fechas absolutas, idioma, familia de dispositivo, nota, sentimiento
y tema. Los dos últimos solo filtran texto, así que `selectTab()` oculta esos controles
(`.rev-only`) fuera de Reviews. `state` guarda **solo** la pestaña abierta.

## La encuesta (pestaña Survey)

Segunda fuente. Dos formatos previstos:

1. **De salida** (`meta.kind = 'exit'`): se dispara tras que el usuario diga que la app
   no le gusta. Es la que hay cargada.
2. **Personalizada**, con varias preguntas: `meta.questions` y el campo `Pregunta` por
   fila ya lo soportan, pero **no hay datos todavía** y la vista no pinta selector de
   pregunta mientras solo haya una.

**Las tres diferencias con Play, y ninguna se disimula:**

- **No hay nota.** Una encuesta no tiene estrella, así que aquí **no existe el reparto
  por signo** de Reviews. La muestra entera *es* el lado negativo. No inventes un
  equivalente de `SIGNS` para esta vista.
- **No hay denominador.** Se sabe quién contestó; no a cuánta gente se le enseñó. Por eso
  la vista habla siempre de **composición** («de quien contesta, el 71,6 % menciona
  publicidad») y **jamás de tasa** sobre la base de usuarios. La primera tarjeta dibuja
  la cadena con las tres cajas que no se miden, en vez de esconderlo en una nota al pie.
  **Si algún día llega el recuento de impresiones de la encuesta, esa es la tarjeta que
  cambia**, y entonces sí hay tasa de respuesta.
- **La muestra está seleccionada por el disparador.** Comparar su composición con la de
  Play mide el instrumento tanto como el producto, y la tarjeta de comparación lo dice
  en su nota. No se lee como un cambio en el tiempo.

Además, **la versión de app está confundida con el tiempo** (6.4.0 concentra el 90 % de
las respuestas porque era la vigente cuando más se disparó la encuesta) y **junio
concentra el 73 %**, así que esta pestaña tampoco dibuja series temporales.

**El clasificador se reutiliza, pero una etiqueta se renombra.** `praise` se escribió
para reseñas, donde «mejor» es elogio; contestando a «qué podríamos mejorar» casi siempre
es una petición. Se renombra a «Sin queja identificable» en `SURVEY_LABEL`, sin tocar el
léxico: el límite es de encuadre de la pregunta, no de vocabulario, y parchear el léxico
lo haría invisible.

### Privacidad (no negociable)

El CSV de origen trae una columna `Usuario` que **no es un id: es un token de registro de
FCM**. Es una credencial viva —con ella se puede enviar una notificación a ese teléfono—
y este panel se publica.

- `survey_build.py` lo usa solo para contar personas únicas y repetidores, y **lo tira**:
  no llega al JSON ni al HTML.
- `datasurvey/` **no se publica**.
- Comprobación de una línea antes de publicar: `grep -c APA91b index.html` tiene que dar
  **0**.

### Regenerar los datos

```bash
python3 tools/reviews_build.py <csv de Play> -o data/reviews.json --inline index.html
python3 tools/reviews_build.py <csv de Play> --audit    # revisar el etiquetado a mano

python3 tools/survey_build.py <csv de encuesta> -o data/survey.json --inline index.html
python3 tools/survey_build.py <csv de encuesta> --audit
```

`--inline` sustituye el bloque `const RD = …;` (o `const SD = …;`) dentro de
`index.html`, escapando `<` como `\u003c`: sin eso, una sola review que contenga
`</script` tumba la página. **No pegues el JSON a mano.**

**El reemplazo va por corte de cadenas, nunca con `re.sub`.** En la cadena de reemplazo
de `re.sub` las barras invertidas son escapes, y el JSON va lleno de `\u003c`: el bloque
sale corrupto y la página no arranca. Se perdió un rato con esto; está así a propósito.

### Formato: columnar empaquetado

Las 9.764 valoraciones no van como objetos, sino como una cadena de **10 caracteres por
fila** (`rows`), con índices en base 36 a las tablas `langs`, `days`, `devs`, `vers`:

```
rating(1) idioma(1) día(2) dispositivo(3) versión(2) respuesta(1)
```

`respuesta` es `-` si nadie contestó, o la latencia en días en base 36. La capa lo
descomprime una vez a arrays tipados (`R_rat`, `R_lang`, `R_day`, `R_dev`, `R_ver`,
`R_lat`, `R_fam`, `R_dayn`, `R_text`), y a partir de ahí **filtrar las 9.764 filas por
cualquier cruce es instantáneo**, sin índices ni caché. Solo las 720 con texto llevan
objeto completo en `rev`, enlazado por número de fila.

Las respuestas del equipo se guardan deduplicadas en `tpl` (335 plantillas para 585
respuestas): el saludo con el nombre del usuario se normaliza a `{nombre}`. Sirve para
ver **qué plantilla recibió cada queja**, que es una revisión de CRO por sí sola.

### Puntos de entrada

- `rSel(ignore)` → índices de fila que pasan el corte. `ignore` permite pedir el corte
  **sin una de sus propias dimensiones**: así el desglose por idioma no se queda con un
  solo idioma cuando hay filtro de idioma puesto. Úsalo en todo desglose.
- `rSelText(ignore)` → índices en `RD.rev`, aplicando además ruido, fricción, sentimiento
  y tema.
- `bucketBy(ids, keyFn)` → `Map` de clave a `[n1,n2,n3,n4,n5]`; `statOf(a)` lo convierte
  en `{n, avg, bad, top, dist}`.
- `wilson(k, n)` → intervalo de confianza al 95 %.

### Reglas de honestidad de esta capa (no negociables)

Son la razón de que el panel no afirme más de lo que el dato sostiene:

- **Nada de tendencias semanales.** La recolección llegó en 9 lotes con cobertura
  desigual (de 6 a 4.500 valoraciones por semana). La tarjeta de calidad de muestra
  marca en gris las semanas con `n < 100` y lo dice en su nota. Los temas se comparan
  **por mes**, nunca por semana.
- **Umbral y guarda estadística en dispositivos.** Solo modelos con `n ≥ 30`, y se marca
  «peor que la media» únicamente si el intervalo de Wilson al 95 % **queda entero por
  encima** de la base global. Sin eso se persiguen modelos que solo parecen malos por
  tener pocas valoraciones.
- **Celdas sin base suficiente van en blanco**, no a cero (`n ≥ 25` en los mapas de
  calor, `n ≥ 30` en columnas de idioma, `n ≥ 40` en familias y meses).
- **El sentimiento se calcula del texto, nunca de la nota.** Por eso el cruce
  sentimiento × nota informa: si se derivara de la estrella, sería una tautología.
- **Ningún volumen se muestra sin su signo.** Una barra que dice «Datos, cobertura y
  estadísticas · 80» miente por omisión: 59 de esas 80 menciones son de 4-5★, o sea que
  es lo que más se elogia, no el segundo problema. Los temas van en `stackedBarsH`
  partidos por `SIGNS` (1-2★ / 3★ / 4-5★), y el filtro «Nota» permite quedarse con un
  lado. Si añades un recuento por categoría, parte por signo o explica por qué no.
- **«Criticar» significa una sola cosa: 1-2★.** Hay dos nociones parecidas y no se
  mezclan. `SIGNS`/`signOf()` es la estrella, inequívoca, y es lo que usan los temas por
  idioma y por mes. `w` (fricción) es más amplio —nota ≤ 3 **o** sentimiento del texto
  negativo/mixto— y solo aparece donde la etiqueta dice «fricción». No uses una para
  rotular la otra.
- **Tasa y volumen se muestran por separado.** El español da el mayor número absoluto de
  1-2★ y a la vez la mejor tasa; confundirlos invierte la prioridad.
- **Corte vacío se dice, no se dibuja.** `emptyCut()` explica por qué se agotó el dato
  y ofrece restablecer. Un gráfico de ceros miente.
- Los codenames de dispositivo son literales de Play. Los prefijos `TECNO-`, `Infinix-`,
  `itel-` y `HN` son ciertos; **la gama Samsung A se infiere** de `^a\d{2}` y se etiqueta
  «(inf.)» en la interfaz.

### El clasificador de texto

`tools/reviews_build.py` etiqueta con un léxico multiidioma, no con un modelo: es
determinista, auditable y reproducible. Lo importante al tocarlo:

- Un tema es **materia de la que habla**, no valencia. `data` incluye tanto «faltan
  ligas» como «variedad de ligas»; el cruce con `w` (fricción) separa una cosa de otra.
  Por eso la tarjeta de balance es divergente y no una barra más.
- `praise` es **excluyente**: solo se pone si no hay ningún tema de problema.
- Hay negación en los dos sentidos: positivos negados (`NEGATED`: «no muy bien») y
  negativos negados (`UNNEG`: «no molesta», «sin publicidad»). Si añades vocabulario,
  añade también su forma negada.
- `has_content()` separa review de ruido con presencia de *stopwords*. Es lo que descarta
  nombres propios y aporreos de teclado sin descartar «good» o «bien».
- Tras cualquier cambio: `--audit` vuelca el etiquetado agrupado por tema para revisarlo
  a mano. Hazlo, con 720 textos se lee en cinco minutos.

### Para enchufar el resto de datos reales

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
- Exactamente **una cifra-héroe por vista**: rating medio en Rating, reviews accionables
  en Reviews. La portada no tiene héroe: son dos módulos de igual peso.
- Los KPI se derivan del mismo `rSel()` que las gráficas de esa vista, y la portada usa
  ese mismo corte, para que ninguna tarjeta discuta con otra.

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
