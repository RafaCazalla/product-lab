# BeSoccer Product Lab

Panel interno de la **voz del usuario en Google Play**: la nota que pone la gente y lo
que escribe. Orientado a decisiones de producto y CRO.

Una sola página autónoma: **sin build, sin dependencias y sin servidor**. `open index.html`
y ya. Las gráficas son SVG escrito a mano.


## Qué trae

| Pestaña | Qué contesta |
|---|---|
| **Resumen** | Portada: las dos secciones resumidas. |
| **Rating** | Reparto de la nota, idioma, versión, familia de dispositivo, evolución mensual y calidad de la muestra. |
| **Reviews** | Embudo de la voz, temas con el signo de la nota, sentimiento del texto y los verbatims en crudo. |

- **Interfaz en español e inglés**, con el español como original.
- **Tema oscuro por defecto**, claro a un clic.
- **Módulos reordenables** por arrastre o con el teclado; la posición se guarda.
- **Lectura de IA bajo demanda**: el panel no interpreta por su cuenta. Todo lo que se ve
  sin pulsar nada es aritmética; la interpretación la escribe Claude solo al pulsar
  «Ejecutar contexto», y siempre sobre el brief de datos del corte activo.

## Este repositorio no lleva datos

`index.html` se publica aquí con el **esqueleto de datos vacío**: el texto de las reviews
es de usuarios reales y no se publica. La página arranca y enseña su estado vacío.

Para hidratarlo con un export de la consola de Google Play:

```bash
python3 tools/reviews_build.py mi_export.csv -o data/reviews.json --inline index.html
```

El CSV debe traer estas columnas: `id`, `package_name`, `app_version_code`, `app_version`,
`language`, `device`, `date`, `rating`, `text`, `developer_reply_date`,
`developer_reply_text`, `review_link`, `took_date`.

Para volver al esqueleto vacío antes de commitear:

```bash
python3 tools/reviews_build.py --empty --inline index.html
```

Y para que no se te olvide, hay un hook que **rechaza** el commit si `index.html` lleva
reviews dentro (no reescribe nada, solo avisa):

```bash
ln -sf ../../tools/pre-commit .git/hooks/pre-commit
```

## Herramientas

```
tools/reviews_build.py     CSV de Play -> JSON clasificado (tema y sentimiento con un
                           léxico multiidioma reproducible, no con un modelo)
tools/smoke.js             prueba de humo: renderiza las vistas bajo ~2.700 cortes en los
                           dos idiomas y caza excepciones, cifras degeneradas y cadenas
                           sin traducir. Requiere macOS (osascript), sin dependencias
tools/validate_palette.py  valida la paleta de series (daltonismo, croma, contraste)
tools/embed_logo.py        recorta, reescala e incrusta el logo como data URI
tools/oklch.py             genera hex en OKLCH dentro de gama
```

Antes de dar por bueno un cambio:

```bash
osascript -l JavaScript tools/smoke.js
python3 tools/validate_palette.py "#57a52e,#2f95cf,#d9515f,#9179e0,#b98d16,#23a9aa" dark "#1b1e1a"
```

## Honestidad de los datos

El panel está construido para no afirmar más de lo que el dato sostiene, y esas reglas
son parte del diseño, no un adorno:

- **No dibuja tendencias semanales.** El export de Play llega en lotes de cobertura muy
  desigual; la única gráfica temporal es mensual y lleva el aviso dentro.
- **Umbrales y guarda estadística.** Un dispositivo se marca «peor que la media» solo si
  su intervalo de Wilson al 95 % queda entero por encima; las celdas sin base suficiente
  van en blanco, no a cero.
- **Volumen y signo siempre juntos.** Una barra de «80 menciones» sin el signo de la nota
  miente por omisión.
- **El sentimiento sale del texto, nunca de la estrella**, para que cruzarlos informe.
- **Corte vacío se dice, no se dibuja.**

## Dos capas de acceso, y lo que cada una protege

**1. Restricción por IP (`middleware.js`).** Edge Middleware de Vercel: quien no venga de
una IP autorizada recibe 403 **antes** de que se sirva una línea del HTML. Esta sí es una
barrera de servidor. Falla cerrado (si no se puede determinar la IP, deniega) y la página
de bloqueo muestra la IP detectada, porque una IP doméstica cambia y una conexión IPv6 no
coincide con la IPv4 esperada. Para cambiar la lista sin commitear: variable de entorno
`ALLOWED_IPS` en Vercel, IP separadas por comas.

```bash
osascript -l JavaScript tools/middleware_test.js
```

**2. Pantalla de contraseña (dentro de `index.html`).** **Es un cierre de cortesía, no
seguridad**: la página es un fichero estático, así que quien lea el código fuente ve lo
que haya sin pasar por ella. La propia pantalla lo advierte.

**Lo que ninguna de las dos protege: este repositorio.** El middleware cubre la URL de
Vercel; si el repositorio es público, cualquiera lee lo que haya en `index.html` desde
GitHub. Por eso el repositorio va sin datos.

## Documentación

- `CLAUDE.md` — arquitectura, design system y las reglas no negociables de gráficas.
- `docs/roadmap.md` — qué falta, por orden, y la deuda conocida.

## Licencia

Sin licencia pública: código interno de BeSoccer.
