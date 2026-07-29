# Fuentes del proyecto

Este archivo registra las fuentes base del proyecto **Mini heliostato impreso**. Antes de tomar decisiones de geometria, control, escalamiento o seleccion de componentes, se deben consultar estos documentos.

## Documentos locales

### HoSIER del IER-UNAM

- Archivo: [`fuentes/Resumen_tecnico_HoSIER_IER_UNAM.pdf`](fuentes/Resumen_tecnico_HoSIER_IER_UNAM.pdf)
- Uso principal: referencia de arquitectura real de horno solar de alto flujo radiativo.
- Contenido relevante:
  - Heliostato plano de 81 m2.
  - Seguimiento en acimut y elevacion.
  - Concentrador fijo de 36 m2 con 409 facetas.
  - Separacion heliostato-concentrador de aproximadamente 14 m.
  - Distancia focal efectiva de 3.68 m.
  - Encoders multivuelta, finales de carrera y modos manual, seguimiento, target y home.
  - Correccion de deriva mediante dispositivo optico tipo peephole.
  - Criterios de error optico en mrad y guia de escalamiento.

### Mini horno solar del IER-UNAM

- Archivo: [`fuentes/Resumen_tecnico_mini_horno_solar_IER_UNAM.pdf`](fuentes/Resumen_tecnico_mini_horno_solar_IER_UNAM.pdf)
- Uso principal: referencia geometrica y de control mas cercana a una maqueta experimental.
- Contenido relevante:
  - Heliostato plano de dos ejes.
  - Superficie reflectante documentada de 5.6 m2.
  - Concentrador fijo tipo DEFRAC con 18 espejos.
  - Distancia focal equivalente aproximada de 2.00 m.
  - Potencia nominal cercana a 1.3 kWth.
  - Encoders incrementales de 5 V con senales A y B.
  - Convencion geometrica: +x oeste, +y sur, +z cenit.
  - Origen en el centro de rotacion del heliostato.
  - Vector preliminar heliostato-foco: R = (0, 5.55, -0.35) m.
  - Ley vectorial de reflexion: la normal del heliostato es la bisectriz entre el vector solar y el vector hacia el foco.
  - Conversion general de cuentas de encoder a angulo.

### Fotografias del mini horno solar

- Carpeta: [`fuentes/fotos_mini_horno/`](fuentes/fotos_mini_horno/)
- Uso principal: referencia visual para la arquitectura fisica, la disposicion heliostato-concentrador y la maqueta mecanica.
- Archivos:
  - `mini_horno_vista_general_01.jpg`
  - `mini_horno_vista_general_02.jpg`
  - `heliostato_vista_lateral_01.jpg`
  - `mini_horno_vista_general_03.jpg`
  - `heliostato_espejo_frontal_01.jpg`
  - `mecanismo_ejes_motores_01.jpg`
  - `mecanismo_transmision_azimut_01.jpg`
  - `mecanismo_ejes_motores_02.jpg`
  - `mecanismo_elevacion_01.jpg`
  - `estructura_posterior_heliostato_01.jpg`
- Observaciones visibles:
  - Heliostato plano exterior con estructura posterior reticulada.
  - Concentrador fijo dentro de caseta o recinto protegido.
  - Montura de dos ejes con base azimutal y eje de elevacion horizontal.
  - Uso de motorreductores, transmision mecanica y cableado externo.
  - Estructura robusta con contrapesos o elementos de balanceo.
  - La maqueta debe conservar visualmente la separacion entre heliostato movil y zona de foco/concentrador fijo.

## Criterio de uso

Para este proyecto, el HoSIER debe usarse como referencia de arquitectura de sistema real. El mini horno solar debe usarse como referencia geometrica inicial, porque sus dimensiones y datos medidos son mas compatibles con una maqueta de espejo aproximado de 20 cm x 20 cm.

Si una decision de diseno depende de datos no presentes en estos documentos, debe marcarse como pendiente de levantamiento experimental o validacion en campo.
