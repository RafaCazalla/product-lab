# BeSoccer Product Lab

Panel de analítica de producto de BeSoccer: uso de la app, rating por idioma, retención,
embudos y CRO, y segmentos. Una sola página, sin build ni dependencias.

- **Ver el panel:** `open index.html`
- **Probar en móvil:** `python3 -m http.server 8000` y abre `http://localhost:8000`
- **Versión publicada (privada):** https://claude.ai/code/artifact/0c86327e-8e32-4740-bdd7-6633ebe37da6

Los datos de esta versión son **sintéticos y deterministas**: cada combinación de filtros
devuelve siempre las mismas cifras y las tarjetas cuadran entre sí. Sirven para validar el
diseño del panel, no para tomar decisiones.

## Continuar en Claude Code

```bash
cd ~/Claude/besoccer-product-lab
claude
```

`CLAUDE.md` se carga solo al arrancar: contiene el design system, las reglas de gráficas y
el mapa del código. No hace falta `/init`.

Si quieres historial de cambios (recomendado antes de tocar nada):

```bash
git add -A && git commit -m "BeSoccer Product Lab v0.1"
```

## Estructura

| Ruta | Qué es |
|---|---|
| `index.html` | La aplicación completa: tokens, modelo de datos, primitivas SVG, vistas |
| `tools/validate_palette.py` | Valida la paleta de series (daltonismo, contraste, luminosidad) |
| `tools/oklch.py` | Genera colores en OKLCH dentro de gama sRGB |
| `docs/roadmap.md` | Lo siguiente, por orden de valor |
| `CLAUDE.md` | Instrucciones del proyecto para Claude Code |
