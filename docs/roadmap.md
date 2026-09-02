# Roadmap

Por orden de valor, no de esfuerzo.

## 1. Datos reales
Sustituir la capa de datos sintéticos (ver "Para enchufar datos reales" en `CLAUDE.md`).
Solo hay tres puntos de entrada: `metric()`, `series()` y las funciones `*Rows()`.

Decisiones pendientes antes de empezar:
- **Fuente**: BigQuery (export de Firebase/GA4), Amplitude/Mixpanel, o el almacén propio.
- **Quién sirve los datos**: un endpoint JSON propio o consultas directas.
- **Rating de tienda**: App Store Connect y Google Play Developer API no dan lo mismo ni
  con la misma granularidad; hay que decidir la unidad común (rating por idioma de la
  reseña, no por país de la cuenta).

## 2. Rating por versión de app
El desglose que falta y donde se esconden las caídas de rating: cruzar rating × versión ×
idioma para separar "el mercado nos valora peor" de "la build 8.4.2 rompió algo".

## 3. Significancia real en experimentos
Hoy la confianza es un dato de entrada. Calcularla desde expuestos y conversiones, y
marcar el efecto mínimo detectable con el tamaño de muestra disponible.

## 4. Cohortes por origen de instalación
La matriz de cohortes por semana ya está; abrirla por canal de adquisición es lo que
convierte retención en decisión de inversión.

## 5. Alertas
Un umbral por métrica y corte (por ejemplo, rating de un mercado cayendo dos periodos
seguidos) es más útil que otra pestaña.

## Deuda conocida
- Las etiquetas directas se ocultan cuando colisionan; con 4+ series convergentes lo
  correcto serían pequeños múltiplos o líneas guía.
- La barra de filtros es `sticky` a 44 px; si el encabezado envuelve en pantallas muy
  estrechas, ese desplazamiento se queda corto.
- `heatmap` dibuja 168 celdas con su propia zona de hover; si crece mucho, conviene
  delegar el hover en el contenedor.
