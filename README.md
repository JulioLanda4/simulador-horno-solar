# Mini heliostato impreso

Proyecto para disenar y construir una maqueta experimental de heliostato de aproximadamente 20 cm x 20 cm, impresa en 3D y controlada con electronica compatible con ESP32/Arduino.

El objetivo es que funcione con Sol real y que conserve una arquitectura semejante a los sistemas solares del IER-UNAM: heliostato plano de dos ejes, motorreductores DC, encoders, homing, seguimiento, modo manual, modo target y validacion optica.

## Criterio del proyecto

- HoSIER: referencia de arquitectura de sistema real.
- Mini horno solar del IER-UNAM: referencia geometrica inicial y referencia visual de la maqueta.

## Documentos principales

- [`FUENTES.md`](FUENTES.md): indice de fuentes locales del proyecto.
- [`docs/01_arquitectura_preliminar.md`](docs/01_arquitectura_preliminar.md): arquitectura fisica, geometria inicial, modos de operacion y riesgos.
- [`docs/02_motores_encoders_drivers.md`](docs/02_motores_encoders_drivers.md): seleccion inicial de motores, encoders y drivers.
- [`docs/03_comparativa_motores_opciones_usuario.md`](docs/03_comparativa_motores_opciones_usuario.md): comparativa de motores propuestos.
- [`docs/04_lista_materiales_preliminar.md`](docs/04_lista_materiales_preliminar.md): lista preliminar de materiales.
- [`docs/05_comparativa_componentes_usuario.md`](docs/05_comparativa_componentes_usuario.md): comparativa de puente H, fuente, buck, finales de carrera, rodamientos y coples.
- [`docs/06_reemplazos_componentes_no_recomendados.md`](docs/06_reemplazos_componentes_no_recomendados.md): reemplazos para piezas descartadas o debiles.
- [`docs/07_busqueda_amazon_mercadolibre_reemplazos.md`](docs/07_busqueda_amazon_mercadolibre_reemplazos.md): busqueda de reemplazos en Amazon Mexico y Mercado Libre.
- [`docs/08_viabilidad_impresion3d_y_simplificacion.md`](docs/08_viabilidad_impresion3d_y_simplificacion.md): revision para una version mas barata, ligera y mayormente impresa en 3D.
- [`docs/09_lista_compra_consolidada.md`](docs/09_lista_compra_consolidada.md): lista final de compra para el MVP barato.
- [`docs/10_diseno_mecanico_inicial.md`](docs/10_diseno_mecanico_inicial.md): diseno mecanico conceptual antes de CAD.
- [`docs/11_parametros_cerrados_y_polea_impresa.md`](docs/11_parametros_cerrados_y_polea_impresa.md): parametros cerrados de impresion/espejo y diseno de polea grande impresa.
- [`docs/12_riel_impreso_receptor.md`](docs/12_riel_impreso_receptor.md): comparacion y decision del riel impreso del receptor.
- [`docs/13_especificacion_cad_mvp.md`](docs/13_especificacion_cad_mvp.md): lista de piezas, parametros y tolerancias para iniciar CAD.
- [`docs/14_plan_de_trabajo_mvp.md`](docs/14_plan_de_trabajo_mvp.md): plan por fases para pasar de pruebas impresas al seguimiento con Sol real.
- [`docs/15_electronica_y_firmware_mvp.md`](docs/15_electronica_y_firmware_mvp.md): arquitectura electrica inicial y protocolo de firmware MVP.
- [`docs/16_diagramas_electronica.md`](docs/16_diagramas_electronica.md): diagramas de potencia, cableado, finales de carrera y flujo de firmware.
- [`cad/openscad/`](cad/openscad/): primeras piezas parametricas para pruebas de tolerancia.
- [`cad/freecad/`](cad/freecad/): version FreeCAD de las piezas de prueba, con exportacion a FCStd, STEP y STL.
- [`electronics/kicad/`](electronics/kicad/): proyecto KiCad editable para el cableado MVP.
- [`firmware/`](firmware/): firmware MVP para probar motores, encoders y finales de carrera.

## Fuentes locales

- `fuentes/Resumen_tecnico_HoSIER_IER_UNAM.pdf`
- `fuentes/Resumen_tecnico_mini_horno_solar_IER_UNAM.pdf`
- `fuentes/fotos_mini_horno/`

## Estado actual

- Fuentes tecnicas agregadas.
- Fotografias del mini horno agregadas como referencia visual.
- Arquitectura preliminar documentada.
- Seleccion inicial de motores, encoders y drivers documentada.

## Proxima etapa sugerida

1. Preparar piezas pequenas de tolerancia: 608ZZ, eje 8 mm, riel doble guia, carro y polea GT2 impresa.
2. Imprimir y medir esas pruebas en PETG.
3. Ajustar tolerancias reales de la impresora.
4. Modelar el ensamble mecanico completo.
5. Probar movimiento manual, homing y encoder antes del seguimiento solar.
