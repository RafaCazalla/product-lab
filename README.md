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

## Los datos van dentro del repositorio

`index.html` se publica **con los datos reales incrustados**: 9.754 valoraciones de
Google Play y 710 reviews con su texto literal, del **31 de mayo al 14 de agosto de 2026**
(el grueso cae en junio, julio y agosto; mayo son solo los últimos días).

Conviene saber qué implica, porque es una decisión y no un descuido:

- El texto es de **usuarios reales**. Son reseñas públicas de Google Play, pero aquí van
  agregadas en un volcado, y en un repositorio público eso se clona, se indexa y queda
  archivado. Unas pocas reseñas contienen el nombre que su autor escribió en el propio
  texto; el filtro «Descartar ruido», activo por defecto, las deja fuera de la lista de
  verbatims, pero siguen en el fichero.
- No hay nombres de autor de Play: esa columna no existe en el export. En las respuestas
  del equipo, el saludo con el nombre del usuario se normaliza a `{nombre}`.
- **Ni la pantalla de contraseña ni la restricción por IP protegen esto.** La primera es
  un cierre de cortesía dentro de un fichero estático; la segunda cubre la URL de Vercel,
  no GitHub.

Para regenerar los datos desde un export de la consola de Google Play:

```bash
python3 tools/reviews_build.py mi_export.csv -o data/reviews.json --inline index.html
```

El CSV debe traer estas columnas: `id`, `package_name`, `app_version_code`, `app_version`,
`language`, `device`, `date`, `rating`, `text`, `developer_reply_date`,
`developer_reply_text`, `review_link`, `took_date`.

Y para dejar el `index.html` sin datos (estado vacío, útil si algún día se separan):

```bash
python3 tools/reviews_build.py --empty --inline index.html
```

## Para replicarlo con la base de datos completa

Este panel es un **prototipo con dos meses y medio de datos** (31 may – 14 ago 2026,
9.754 valoraciones). Lo que sigue es lo que hay que saber para llevarlo a los 5 años de
histórico, por orden de lo que rompe antes.

### 1. El formato aguanta; incrustarlo en el HTML, no

Las valoraciones no van como objetos JSON, sino como una cadena de **10 caracteres por
fila** con índices en base 36 a tablas de idioma, día, dispositivo y versión:

```
rating(1) idioma(1) día(2) dispositivo(3) versión(2) respuesta(1)
```

Se descomprime una vez a arrays tipados y a partir de ahí filtrar por cualquier cruce es
un recorrido lineal sin índices ni caché. Eso escala bien:

| | Valoraciones | Con texto | Empaquetado |
|---|---|---|---|
| Hoy | 9.754 | 710 | 445 KB (en el HTML) |
| 5 años, conservador | ~120.000 | ~8.900 | ~2,4 MB |
| 5 años, al ritmo del mejor mes | ~355.000 | ~26.000 | ~6,8 MB |

Lo que no aguanta es meterlo en el `index.html`. A partir de ~1 MB hay que **servirlo
desde un endpoint** y quitar el bloque `const RD`. El cambio es acotado: `metric()`,
`rSel()` y las funciones `*Rows()` son los únicos puntos de entrada, y `renderActive()` es
el único sitio que habría que volver `async` (ya mantiene el render anterior en opacidad
reducida mientras llegan los datos, sin esqueleto ni salto de layout).

### 2. Los agregados deberían bajar al servidor

Con 350.000 filas, recorrerlas en el navegador por cada cambio de filtro empieza a
notarse. Lo natural es que el servidor devuelva ya agregado lo que hoy calculan
`bucketBy()` y `statOf()`: `GROUP BY` de idioma, versión, dispositivo y día, con la
distribución de 1-5★ por grupo. Los verbatims se paginan aparte.

Con eso el navegador solo pinta, y las reglas de honestidad del panel (umbrales, Wilson,
celdas en blanco) se aplican igual sobre los agregados.

### 3. El texto de las reviews merece vivir aparte

Del fichero actual, **solo el 14 % es dato personal**: los 40 KB del texto literal. El
resto —clasificación, filas empaquetadas, agregados— no contiene una palabra escrita por
un usuario. Separarlos permite que el análisis sea accesible sin exponer el texto, y que
el texto se borre en cualquier momento sin tocar nada más.

### 4. La clasificación es un léxico, no un modelo

`tools/reviews_build.py` etiqueta tema y sentimiento con un léxico multiidioma. Es
determinista y auditable: se puede revisar por qué una review lleva un tema. Sus límites
están medidos: identifica tema en el 29 % de los textos, y turco, persa, birmano y
amárico caen en «sin señal». Con 26.000 reviews conviene pasar a un modelo, pero
**guardando la etiqueta junto al texto** para que el panel siga siendo determinista y la
revisión humana siga siendo posible.

### 5. La resolución temporal la marca la muestra, no el gusto

La tarjeta de evolución tiene selector de grano (día · semana · mes) y el mismo umbral en
los tres: un punto necesita **30 valoraciones** para dibujarse, porque por debajo la media
de una nota es ruido (con n=10 el error típico ronda ±0,3 en una escala de 1 a 5). El eje
lleva todos los periodos del rango, también los vacíos, para que un hueco de tres semanas
no se vea como un día.

Con este dataset, puntos dibujables por idioma:

| Idioma | Día | Semana | Mes |
|---|---|---|---|
| Español | 24 | 6 | 3 |
| Francés | 32 | 7 | 4 |
| Portugués | 6 | 5 | 3 |
| Inglés | **2** | 6 | 3 |

**El grano por defecto es la semana**, que con esta muestra es el punto dulce: 24 de 48
puntos posibles dibujan, hay 12 periodos en lugar de 4 y aparecen los cuatro idiomas
(6 semanas de 10 en español, 7 de 11 en francés, 5 de 9 en portugués, 6 de 11 en inglés).
El diario solo sostiene español y francés; en inglés dibuja 2 puntos y no es una línea. El
mensual aplana la forma. Con la base de 5 años y una ingesta diaria, el grano diario pasa
a tener sentido para los cuatro idiomas.

### 6. Lo que este dataset no permite afirmar, y con la base completa sí

La recolección llegó en 9 lotes de cobertura muy desigual y concentrada en la primera
quincena de cada mes (julio: 4.152 valoraciones en la primera, 6 en la segunda). Por eso
el panel **se niega a dibujar tendencias semanales** y la única gráfica temporal es
mensual, con huecos y el aviso dentro. Con ingesta continua eso desaparece: se puede
bajar a semanas, quitar los huecos y activar alertas por umbral.

### Lo que el prototipo ya deja ver

Hallazgos reales de estos dos meses y medio, con las cifras que los sostienen:

- **El cuello de botella es el texto, no la nota.** Solo el 7,4 % de las valoraciones
  trae texto y apenas el 2,1 % deja algo accionable. Las 1-2★ sin texto no son
  respondibles ni diagnosticables.
- **El rating por idioma está confundido con el hardware.** El francés puntúa 4,41 frente
  al 4,71 del español, y el 46 % del volumen en francés viene de dispositivos Transsion
  de gama de entrada, frente al 7,4 % en español.
- **Cada mercado se queja de otra cosa.** El español de publicidad (52 quejas), el francés
  de que la app se cierra (11, sobre una base seis veces menor). Son dos hojas de ruta.
- **El volumen sin signo engaña.** «Datos, cobertura y estadísticas» es el segundo tema
  más mencionado (77), pero 59 de esas menciones son de 4-5★: es lo que más se elogia, no
  el segundo problema.

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

**1. Restricción por IP (`middleware.js`) — ESCRITA Y PROBADA, PERO HOY INACTIVA.**
Edge Middleware que devuelve 403 a quien no venga de una IP autorizada, antes de servir
una línea de HTML. Falla cerrado (si no se puede determinar la IP, deniega) y la página de
bloqueo muestra la IP detectada, porque una IP doméstica cambia y una conexión IPv6 no
coincide con la IPv4 esperada. La lista se cambia sin commitear con la variable de entorno
`ALLOWED_IPS` (entradas separadas por comas) y acepta IP exacta o rango CIDR, en IPv4 y
en IPv6:

```
90.161.49.230        una IPv4 concreta
90.161.49.0/24       todo el rango: una IP doméstica cambia dentro del suyo
2a0c:5a80::/32       un rango IPv6
```

La lista por defecto, en `middleware.js`, son tres IPv4 exactas. Si alguna es dinámica
—las domésticas casi siempre lo son— conviene cambiarla por su rango (`/24`) antes de que
un cambio de IP deje a alguien fuera. Y para no tener que commitear cada vez que cambia
una, mejor gestionarlas desde `ALLOWED_IPS` en las variables de entorno de Vercel: manda
sobre esta constante y no requiere despliegue.

**No confíes en ella tal como está el despliegue.** Este proyecto de Vercel sirve el
repositorio como estático puro, así que `middleware.js` se entrega como un fichero más en
lugar de ejecutarse en el borde: se comprueba porque una ruta inexistente devuelve 404 y
no 403. Para activarla hay que configurar el proyecto de forma que Vercel empaquete el
middleware, o usar el firewall de Vercel (Settings → Firewall), que hace lo mismo sin
código. Añadir un `package.json` para forzar el paso de build **no funciona**: convierte
el proyecto en uno con build y el despliegue falla por no encontrar directorio de salida.

```bash
osascript -l JavaScript tools/middleware_test.js
```

**2. Pantalla de contraseña (dentro de `index.html`).** **Es un cierre de cortesía, no
seguridad**: la página es un fichero estático, así que quien lea el código fuente ve lo
que haya sin pasar por ella. La propia pantalla lo advierte.

**Lo que ninguna de las dos protege: este repositorio.** El middleware cubre la URL de
Vercel; siendo el repositorio público, cualquiera lee los datos de `index.html` desde
GitHub sin pasar por ninguna de las dos capas. Es una decisión tomada a sabiendas.

## Documentación

- `CLAUDE.md` — arquitectura, design system y las reglas no negociables de gráficas.
- `docs/roadmap.md` — qué falta, por orden, y la deuda conocida.

## Licencia

Sin licencia pública: código interno de BeSoccer.
