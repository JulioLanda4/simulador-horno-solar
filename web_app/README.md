# Gemelo digital web 0.1

Edicion web experimental del simulador del mini horno solar. Conserva el
nucleo de calculo en Python y lo ejecuta en el navegador con
Shinylive/Pyodide; GitHub Pages sirve solamente archivos estaticos.

## Alcance de la primera fase

- Tiempo real o fecha simulada con multiplicador.
- Modos Automatico, Manual y Home con movimiento gradual.
- Posicion solar D&B/REDA, normal, reflexion e impacto sobre el target.
- Vistas iniciales de gemelo 3D, spot, trayectoria solar, facetas y diagnostico.
- Acomodo optimo de facetas cuadradas, circulares y hexagonales.
- Historial local y descarga CSV.
- Interfaz responsiva para escritorio y dispositivos angostos.

Esta fase valida la arquitectura web. La paridad completa con la version 2.0
de escritorio se incorporara en etapas posteriores sin eliminarla ni
modificar su etiqueta estable.

## Desarrollo local

```powershell
uv sync --project web_app
uv run --project web_app shiny run web_app/app.py
```

## Exportacion estatica

```powershell
uv run --project web_app shinylive export web_app _site
```
