# Encargo v0.6 — Reenfocar el panel: de "quién puntúa peor" a "qué le está pasando al usuario"

> Pegar como prompt en una sesión sobre este repositorio. Es autocontenido.
> Usa la skill `cro-ux-producto` para esto.

## Estado a 17 sept 2026

El bloqueo de fondo —9 lotes de exportación manual— desapareció en v0.8 con la ingesta
continua desde el bucket de Play Console (ver `CLAUDE.md`, «Arquitectura de datos»).

| Punto | Estado |
|---|---|
| 1.1 Quitar `reply`, `sent-star`, `fam-fric` | **Hecho** |
| 1.2 Fusionar `lang-dev` y `lang-vol` | **Descartado** tras inspección — ver nota abajo |
| 1.3 Arreglar `ver` | **Hecho**, con una corrección: el intervalo es de la t, no de Wilson |
| 1.4 `evo` por versión | **Hecho en v0.8** como `st-rating`: nota semanal total y por versión, desde los informes diarios de Play |
| 1.5 `topic-month` → tema × versión | **Hecho en v0.8** como `topic-ver`: mapa tema × las 8 versiones con más texto, umbral por celda |
| 1.6 Flujo por versión en ventana equivalente | **Desbloqueado en v0.8**: `ST.versions[].active_devices` da el despliegue real de cada versión, día a día. Pendiente de construir |
| 1.7 Temas nuevos por versión | **Hecho en v0.8** como `topic-new`: temas cuyo intervalo de Wilson en la última versión queda entero por encima de las anteriores |

### Por qué 1.4 a 1.7 están bloqueados

Todos fallan por la misma causa: **la dimensión versión no tiene base en este volcado.**

- **6.4.0 concentra 7.231 de las 9.754 valoraciones (74 %).** El resto son fragmentos: 6.3.0 (453),
  6.5.0 (248), 6.1.1 (148), 6.2.0 (117), 5.6.3 (86).
- Con el umbral de 30 por punto, la serie versión × semana da **10 puntos dibujables en total**, y
  versión × mes solo tiene 3 periodos en todo el rango. Menos puntos que la actual por idioma, no
  más.
- **La aproximación «primera valoración = fecha de publicación» es falsa para 5 de 6 versiones.**
  6.3.0, 6.1.1, 6.2.0 y 5.6.3 tienen su primera valoración el 31 de mayo, que es el primer día de
  la recolección, no el día que salieron. Solo 6.5.0 (27 de julio) aparece de verdad dentro de la
  ventana. Una tarjeta de «días desde el lanzamiento» estaría midiendo días desde que empezamos a
  mirar.
- Y los huecos de 6.4.0 en las semanas 1, 2, 3, 6 y 7 no son comportamiento de la app: son los
  **9 lotes** de recolección.
- En texto es peor: de 710 reviews, 441 son de 6.4.0, 135 no traen versión y el resto se reparte en
  fragmentos. «Temas nuevos en 6.5.0» se apoyaría en 33 textos, con temas de n = 2.

**Qué lo desbloquea**, por orden de valor:

1. **Fechas reales de publicación** de cada versión, de Play Console. Convierte 1.6 de aproximación
   en atribución.
2. **Ingesta continua** en vez de 9 lotes. Sin esto, cualquier eje temporal mide el calendario del
   volcado.
3. **Más rango**, para que convivan varias versiones con base suficiente.

Con 1 y 2, los cuatro puntos se vuelven construibles y el diseño de este encargo sirve tal cual.

### Por qué 1.2 se descarta

`lang-dev` y `lang-vol` no son redundantes: son el par tasa/volumen que exige la propia regla de
honestidad del panel, cada uno con la forma correcta para su magnitud —divergente para la
desviación, barras para el recuento— y ya se citan mutuamente en las notas. Fusionarlos obligaría a
meter dos escalas en una gráfica, que es justo lo que las reglas prohíben, o a juntar dos SVG bajo
un título, que no simplifica nada. La redundancia que yo creí ver con `heat-lang-fam` no existe: el
mapa de calor contesta otra pregunta —si es idioma o hardware— y vive en su propia sección.

## Diagnóstico de partida (no hace falta rederivarlo, pero se puede discutir)

El panel corta casi todo por **atributos de la persona** —idioma, familia de dispositivo— y casi
nada por **causa** —versión, momento—. Idioma y dispositivo dicen a quién le duele; no dicen qué
se lo hizo. Además el idioma está confundido con el hardware, cosa que este mismo `CLAUDE.md`
documenta.

Regla que ordena el trabajo: **la fecha sirve para detectar, la versión para atribuir.** Un
despliegue es escalonado y cada usuario actualiza cuando quiere, así que un corte por fecha mezcla
usuarios de dos versiones y diluye el efecto justo cuando se quiere medir.

## Fase 1 — Todo esto sale del dato que ya está en `RD`, sin fuentes nuevas

### 1.1 Quitar tres tarjetas

- **`reply`** (Cobertura de respuesta del equipo, Rating) — mide al equipo de soporte, no al
  usuario. Ninguna decisión de producto cambia con esa cifra y se sube contestando con plantilla.
- **`sent-star`** (Qué dice el texto y qué dice la estrella, Reviews) — es una tarjeta sobre el
  clasificador, no sobre el usuario. Su valor fue demostrar una vez que el sentimiento no es
  tautología de la estrella; eso es apéndice de método, no tarjeta permanente.
- **`fam-fric`** (Tasa de fricción por familia, Reviews) — misma pregunta que `fam-rating` y
  `heat-lang-fam` con peor instrumento (710 textos frente a 9.754 notas) y con otra definición de
  "malo" (`w` frente a 1-2★), que es justo la mezcla que `CLAUDE.md` prohíbe.

Al quitarlas, comprobar que el orden guardado en `localStorage` sigue funcionando: las claves
desconocidas deben ignorarse sin perder módulos (la prueba de humo ya lo cubre).

### 1.2 Fusionar las dos tarjetas de idioma

`lang-dev` y `lang-vol` responden a la misma decisión que `heat-lang-fam`, y solo el mapa de calor
resuelve el confusor idioma/hardware. Fusionar `lang-dev` y `lang-vol` en **una** tarjeta de dos
columnas —tasa con su intervalo | volumen absoluto— manteniendo la regla de no mezclar tasa y
volumen en la misma escala. El mapa de calor queda como la tarjeta principal de esa sección.

### 1.3 Arreglar `ver` (Rating medio por versión) — hacer esto primero

Hoy dibuja solo la media. **Una versión con n=61 y otra con n=4.000 se ven exactamente igual**, lo
que invita a la atribución falsa que el resto del panel se esfuerza en evitar. Añadir:

- **Bigotes de intervalo de confianza** (la primitiva `ci` de `barsH` y `wilson()` ya existen; en
  `dev-worse` ya se usa esa guarda).
- **El volumen a la vista**, no solo en la tabla.

### 1.4 Cambiar el eje de `evo`: de idioma a versión

Mismo componente, misma primitiva `lineChart` con huecos, otra clave de agrupación. El idioma es
la dimensión confundida; la versión es la causal. Mantener el selector de grano y todas las
guardas actuales (`MIN_POINT`, punto hueco por base, "n puntos de N posibles").

### 1.5 `topic-month` → tema × versión

Por lo mismo del punto anterior: el mes no atribuye, la versión sí.

### 1.6 Nueva tarjeta: flujo de valoraciones por versión, en días desde el lanzamiento

La que hoy no existe y es la que contesta "¿esta release rompió algo?". No la nota acumulada: las
valoraciones **recibidas** cada día, comparando cada versión en su **ventana equivalente** (días
1-14 de la v8.4 contra días 1-14 de la v8.3), no contra el histórico.

Aviso que debe ir en la nota al pie de la tarjeta: **no tenemos la fecha real de publicación de
cada versión**. Se aproxima con la primera valoración recibida con esa versión, que llega con
retraso desconocido. Es una aproximación utilizable y hay que decir que lo es.

### 1.7 Nueva tarjeta: temas nuevos en esta versión

Qué queja aparece **por primera vez** en la versión reciente, frente al fondo recurrente que ya
muestran `topics-sign` y `acid`. Es la tarjeta que contesta literalmente "qué problemas le están
surgiendo al usuario ahora". Sale de cruzar tema (en `rev`) con `R_ver` por número de fila.

Cuidado con la base: con 710 textos repartidos por versión, muchas celdas no llegarán al umbral.
Aplicar la regla de siempre —celda sin base suficiente va en blanco, no a cero— y si el corte se
agota, `emptyCut()`.

## Fase 2 — Requiere fuentes que hoy no están en el panel

No empezarla sin hablarlo. Queda escrita para que el diseño de la fase 1 no la impida:

- **Cierres y ANR por versión**, con los umbrales oficiales de Android vitals dibujados como línea
  de referencia: 1,09 % de cierres percibidos, 0,47 % de ANR, 8 % en un modelo concreto. Es lo que
  convierte la correlación en mecanismo. Requiere datos de Play Console.
- **App Store como control de dirección**: si baja en Play y no en App Store es de Android; si baja
  en las dos es producto o backend. **Dirección, nunca nivel** — las dos tiendas ponderan lo
  reciente con fórmulas que no publican.

## Reglas del repo que no se negocian

- **El panel no interpreta por su cuenta.** Todo lo que se lee sin pulsar nada es aritmética. La
  interpretación solo aparece con «Ejecutar contexto». No añadir texto de opinión bajo ninguna
  tarjeta nueva; lo que sí va en las notas es **método** (por qué ese umbral, qué mide el signo,
  por qué la fecha de release es una aproximación).
- **Ningún volumen sin su signo**, celdas sin base suficiente en blanco y no a cero, tasa y volumen
  por separado.
- Cada módulo movible necesita su **clave estable e independiente del idioma** en `data-mod`,
  pasada a mano (`key: '...'`), nunca derivada del título.
- **Toda primitiva tiene que sobrevivir a un corte vacío**: `max === min`, `total === 0`,
  `rows === []`.
- Cadenas nuevas: nada de concatenar alrededor de una cifra, usar `t('{n} …', { n })`. La prueba de
  humo lista lo que falte traducir, listo para pegar.

## Criterio de aceptación

```bash
osascript -l JavaScript tools/smoke.js
```

Tiene que pasar limpio: sin excepciones, sin `NaN`/`Infinity`/`undefined`/`null` en el DOM, sin
cadenas sin traducir, y con las comprobaciones de arranque y de orden de módulos en verde.

Empezar por 1.3 (arreglar `ver`), que es el defecto real; lo demás son mejoras. Ir una por una, y
antes de escribir código, decir si alguna de estas decisiones parece equivocada.

## Dos notas de contexto

**El orden importa.** Empezar por 1.3 no es arbitrario: `ver` sin intervalos ni volumen es el único
punto del panel donde hoy se puede sacar una conclusión falsa con los datos que ya hay.

**1.6 lleva una concesión.** Si se pueden sacar las fechas reales de release de Play Console —un
CSV de diez líneas— esa tarjeta pasa de aproximación a atribución limpia. Es probablemente el dato
con mejor relación valor/esfuerzo de toda la lista.
