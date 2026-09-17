# Roadmap

Por orden de valor, no de esfuerzo.

## Hecho en v0.2 y v0.3

**v0.2** — Las pestañas **Rating** y **Reviews** sobre datos reales de Google Play
(9.764 valoraciones, 720 con texto, 31 may – 14 ago 2026). Cierra el punto 2 del roadmap
anterior (rating × versión × idioma) y buena parte del 1 para el lado de tienda.

**v0.3** — Fuera las seis pestañas de métricas sintéticas y su modelo de datos: el panel
es solo dato real, en tres pestañas (Resumen · Rating · Reviews). Tema oscuro por
defecto. Y tres cosas más que salieron de usarlo:

- **Los temas se muestran con su signo.** La barra de volumen sola engañaba: «Datos,
  cobertura y estadísticas · 80» parecía el segundo problema del panel cuando 59 de esas
  80 menciones son de 4-5★. Ahora van partidas en 1-2★ / 3★ / 4-5★, hay una tarjeta de
  acidez (% de 1-2★ por tema) y el filtro «Nota» agrupa por signo.
- **Interfaz en español e inglés**, con el español como original y clave de traducción.
- **La prueba de humo comprueba los dos idiomas** y falla si queda una cadena sin
  traducir, así que el diccionario no se queda atrás sin que nadie lo note.

Consecuencia para el roadmap: los puntos que hablaban de *comportamiento* del usuario
(cohortes por canal, significancia de experimentos) ya no tienen vista donde vivir. Se
mantienen abajo porque siguen siendo válidos, pero ahora implican **volver a crear** esa
pestaña, no rellenarla.

Lo que dejó ver el dato real, y que no se veía con datos sintéticos:

- **El cuello de botella es el texto, no la nota.** Solo el 7,4 % de las valoraciones
  trae texto, y apenas el 2,1 % del total deja algo accionable. El embudo de la voz
  (pestaña Reviews) es la tarjeta que enmarca todo lo demás.
- **El rating por idioma está confundido con el hardware.** El francés puntúa 4,41
  frente al 4,71 del español, y el 46 % del volumen en francés viene de dispositivos
  Transsion (Tecno/Infinix/itel) frente al 7,4 % en español. Tratarlo como problema
  de traducción sería atacar la correlación, no la causa.
- **Cada mercado pide cosas distintas.** El español se queja de publicidad (52 de sus
  quejas) y el francés de que la app se cierra (11, sobre una base seis veces menor).
- **No hay serie temporal.** La recolección llegó en 9 lotes con cobertura muy
  desigual (de 6 a 4.500 valoraciones por semana), así que el panel se niega a dibujar
  tendencias semanales y lo dice en la tarjeta de calidad de muestra.

**v0.4** — La interpretación deja de estar escrita a mano y pasa a generarse solo cuando
se pide, con «Ejecutar contexto» (capacidad `sample` del Artifact, o el prompt copiado a
mano si la página se abre en local). Se instala la skill `data-visualization` y de su
criterio salen tres arreglos: titulares calculados, bigotes de intervalo de confianza y
texto alternativo por gráfica.

Y un defecto de datos encontrado al revisar el brief: **10 reviews venían reingeridas**
—la misma review devuelta en un lote posterior con id nuevo—, así que una queja se
contaba hasta tres veces. `tools/reviews_build.py` las descarta ahora con una huella
conservadora (texto ≥ 20 caracteres idéntico + dispositivo + fecha + nota, y en lotes
distintos). En las valoraciones **sin** texto esa reingesta no es detectable, así que
puede quedar una inflación pequeña del mismo tipo: está dicho en el pie de cada vista.

**v0.5** — Tres cosas:

- **Arreglado el fallo de la primera pantalla en blanco.** `applyStaticI18n()` hacía
  `textContent` sobre los botones de pestaña, que **contienen** el `<span id="ratcount">`;
  eso destruía el span, el `$('#ratcount')` siguiente daba `null` y la excepción abortaba
  antes del `selectTab('resumen')` final. Los listeners de pestaña ya estaban puestos, así
  que cambiar de pestaña funcionaba y la primera pantalla no. Ahora la etiqueta traducible
  va en su propio `<span>`, el arranque no depende de que un id siga ahí, y un fallo al
  pintar muestra una tarjeta con el error en vez de dejar la vista muda.
- **Módulos movibles con posición persistente** (ver «Orden de los módulos» en CLAUDE.md).
- **Gráfica de rating por idioma mes a mes**, con huecos y el aviso de muestra dentro
  (ver «La única gráfica temporal»).

**v0.6** — Cuarta pestaña: **Survey**, la encuesta de salida. 3.454 respuestas del
mercado español en Android (10 jun – 14 sep 2026), clasificadas con **el mismo léxico**
que las reseñas, que es lo único que permite comparar las dos fuentes.

Lo que enseña, y por qué está montado así:

- **La publicidad es el 71,6 %** [IC95 69,8–73,3] de las 2.580 respuestas con contenido,
  7,2 veces el segundo motivo. Es la señal más concentrada de todo el panel.
- **La tarjeta de comparación entre fuentes** es la que justifica tener dos: publicidad
  pesa 71,6 % en la encuesta y 20,9 % en las reseñas en español, y «sin queja» va del
  4,0 % al 44,6 %. Esa diferencia **es del instrumento**, no del producto —Play recoge
  también a quien está contento—, y la nota de la tarjeta lo dice.
- **La primera tarjeta es el límite, no el hallazgo.** Dibuja la cadena
  «vieron el aviso → dijeron que no les gusta → vieron la encuesta → contestaron» con
  las tres primeras cajas en blanco, porque solo se mide la última. Sin denominador no
  hay tasa, así que la vista habla de composición y nunca de «el X % de los usuarios».

Y dos cosas que aparecieron al montarla:

- **El CSV traía tokens de registro de FCM** en la columna `Usuario`. Es una credencial
  viva. `survey_build.py` los usa para contar personas y los tira; no llegan al JSON.
- **Había datos personales en el texto libre**: un correo y tres móviles. Se tachan en el
  constructor —no a mano en el HTML— y quedan marcados como «[dato personal retirado]»,
  para que al leer el verbatim se vea que falta algo en vez de parecer una frase cortada.
  Las reseñas de Play se revisaron por lo mismo y están limpias: los correos que salen
  son el `soporte@besoccer.com` de las plantillas del propio equipo.

Pendiente de esta pestaña: **la tasa de respuesta**. Es su contra-métrica obligatoria —sin
ella se puede «mejorar» el resultado enseñando la encuesta menos veces y nadie lo vería—
y es la cifra que convierte esas tres cajas vacías en un embudo de verdad. También falta
el **formato 2** (encuestas personalizadas con varias preguntas): el constructor y el JSON
ya lo soportan, no hay datos.


**v0.7** — Limpieza con criterio: fuera `pairs` (ordenaba pares de motivos por recuento
bruto y presentaba como hallazgo el par MENOS asociado), `topic-month` y `evo` (medían el
calendario del volcado). Umbral por celda en «Qué duele en cada idioma»: sobreviven 5 de 32
celdas y los huecos son el mensaje. Las gráficas de tema filtran la lista de texto al
pulsarlas. La portada gana el módulo de la encuesta.

**v0.8** — **La capa de datos a escala.** El panel deja de generarse desde un CSV exportado a
mano y pasa a una cadena `bucket de Play Console → data/play/*.csv → data/play.db (SQLite)
→ index.html`. La base es el archivo (reseñas desde 2013, series diarias desde 2025-02) y el
panel una ventana generada (2024-01 → hoy): **158.014 valoraciones, 28.916 con texto**, ×16
y ×42 lo que había. Formato empaquetado ensanchado a 12 caracteres. Y por primera vez el
panel dibuja el tiempo con datos que lo sostienen: bloque `ST` con nota semanal por versión,
cierres y ANR por 1.000 dispositivos activos, ANR por versión y por día de la semana, altas
y bajas de usuario. Lo que salió al mirar: un incidente de cierres entre octubre de 2025 y
febrero de 2026 (×14, resuelto) y ANR que casi se duplican los sábados. Las tarjetas por
versión, idioma y modelo dibujan las 12 con más volumen y mandan el resto a la tabla.

## 1. Pipeline de ingesta continua

Hoy `tools/reviews_build.py` parte de un CSV volcado a mano. Lo que falta:

- Tirar de la **Google Play Developer API** (`reviews.list`) en un cron, no de un export.
  Ojo: la API solo devuelve reseñas de los últimos 7 días, así que el histórico hay que
  acumularlo; los lotes irregulares de este dataset son exactamente ese problema.
- **App Store Connect** no da el texto por idioma de la reseña, sino por territorio.
  Antes de mezclarlo con Play hay que decidir la unidad común y documentar que no es
  la misma dimensión.
- Con ingesta diaria, la tarjeta de cobertura de muestra pasa a ser una serie temporal
  de verdad y se puede activar el `lineChart` que hoy no se dibuja a propósito.

## 2. Etiquetado: del léxico al modelo

El clasificador actual es un léxico multiidioma (es/fr/pt/en + árabe básico) y eso es
una virtud mientras el volumen sea bajo: es determinista, auditable y explica por qué
etiquetó cada review. Sus límites conocidos, medidos sobre estos 720 textos:

- **Cobertura**: identifica tema en el 29 % de los textos. El resto es elogio genérico,
  ruido o texto demasiado vago; la clasificación en «sin contenido» acierta bien, pero
  se le escapan nombres propios en idiomas no cubiertos.
- **Idiomas sin léxico**: turco, persa, birmano y amárico caen a «sin señal». Son 117
  valoraciones (1,2 %), pero incluyen una queja grave de suscripción en turco.
- **Sarcasmo y negación compuesta**: se cubre la negación simple («no muy bien», «no
  molesta»), no la ironía.

El salto natural es clasificar con un modelo y **guardar la etiqueta junto al texto**,
para que el panel siga siendo determinista y la revisión humana sea posible. Lo que no
hay que perder al hacerlo: la trazabilidad de por qué una review lleva un tema.

## 3. Cruzar la voz con el comportamiento

Ahora mismo Rating y Reviews viven en su propia capa, con sus propios filtros, separadas
de las métricas de producto. El paso que da valor real es unirlas por versión y mercado:
qué le pasa a la retención D7 de quien pone 1★, y si los modelos marcados en la tarjeta
de dispositivos tienen peor arranque medido.

Requiere un identificador común, que las reviews de Play no traen: hay que ir por
versión × mercado × modelo, no por usuario.

## 4. Significancia real en experimentos
Requiere recrear una vista de CRO (se eliminó en v0.3). Cuando se haga: calcular la
confianza desde expuestos y conversiones en lugar de recibirla como dato, y marcar el
efecto mínimo detectable con el tamaño de muestra disponible. El intervalo de Wilson ya
está implementado (`wilson()`) y sirve tal cual.

## 5. Cohortes por origen de instalación
También requiere recrear la vista de retención. Abrir la matriz de cohortes por canal de
adquisición es lo que convierte retención en decisión de inversión.

## 6. Alertas
Un umbral por métrica y corte (por ejemplo, un modelo cuyo intervalo de 1-2★ se separa
de la media dos volcados seguidos) es más útil que otra pestaña.

## Deuda conocida por la parte del orden

- **El arrastre es HTML5 drag and drop, así que no funciona con el dedo.** En móvil queda
  la vía de teclado y el botón de restablecer. Para táctil habría que pasar a eventos de
  puntero.
- **El orden es una lista plana por vista.** No hay concepto de columna ni de tamaño: un
  módulo `c6` sigue siendo `c6` donde lo dejes. Cambiar el ancho de un módulo sería otra
  cosa y no está.
- **No se sincroniza entre navegadores** al vivir en `localStorage`.

## Deuda conocida por la parte de IA

- **La lectura no se guarda entre visitas.** Vive en memoria (`CTX_CACHE`) y se pierde al
  recargar. Guardarla en `localStorage` con la clave del corte son unas líneas, pero hay
  que decidir cuándo caduca: una lectura de hace un mes sobre datos nuevos miente.
- **No hay forma de comparar dos lecturas** del mismo corte generadas en momentos
  distintos, ni de ver qué prompt produjo una lectura guardada.
- **El camino de «Pegar respuesta» acepta texto libre** y lo parte por párrafos si no
  encuentra JSON. Funciona, pero no valida que la respuesta hable de este corte.

## Deuda conocida

- **La atribución de marca por codename es parcial.** Los prefijos `TECNO-`, `Infinix-`,
  `itel-` y `HN` son literales; la gama Samsung A se infiere de `^a\d{2}` y va marcada
  como inferida. El 73,7 % de los dispositivos no lleva prefijo de fabricante, así que
  «Sin identificar» es el grupo mayor. Con una tabla codename → modelo comercial (la
  publica Google en el device catalog) esto se resuelve del todo.
- **El JSON va incrustado en `index.html`** (259 KB de 354 KB). Mantiene la promesa de
  «abrir el fichero y ya», pero si el histórico crece hay que pasar a `fetch()` y
  entonces deja de funcionar sobre `file://`. El umbral razonable está en ~1 MB.
- La barra de filtros es `sticky` a 44 px; si el encabezado envuelve en pantallas muy
  estrechas, ese desplazamiento se queda corto.
- **El tema elegido no se recuerda.** El botón «Tema» cambia al claro, pero al recargar
  se vuelve al oscuro. El idioma sí se recuerda (`localStorage`, clave `bsp-lang`); al
  tema le faltan las mismas cuatro líneas, y se dejó así a propósito para no contradecir
  el «oscuro por defecto».
- **El inglés está traducido a mano, no revisado por un nativo.** Son 305 entradas y
  varias son párrafos de análisis; conviene que las lea alguien antes de enseñárselo a
  un tercero.
- **Solo hay dos idiomas de interfaz.** Añadir un tercero es añadir una clave a `LANGS`
  y un objeto a `I18N`; el resto del código no cambia.
- `heatmap` dibuja cada celda con su propia zona de hover; si crece mucho, conviene
  delegar el hover en el contenedor.
