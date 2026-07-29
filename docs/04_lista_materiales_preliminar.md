# Lista preliminar de materiales

Fecha: 2026-07-02.

Esta lista corresponde a una primera version funcional del mini heliostato impreso de aproximadamente 20 cm x 20 cm. La lista esta separada por prioridad:

- MVP: necesario para construir una version funcional.
- Recomendado: mejora precision, seguridad o facilidad de calibracion.
- Experimental: util para validar deriva, cerrar lazo optico o hacer mediciones.

## Resumen rapido

| Subsistema | Material | Cantidad sugerida | Prioridad | Comentario |
|---|---:|---:|---|---|
| Control | ESP32 DevKit | 1 | MVP | Control principal, WiFi local, lectura de encoders e interfaz. |
| Movimiento | GM 25-370 con encoder 12 V 140 rpm | 2 | MVP | Uno para acimut y uno para elevacion. |
| Movimiento | Driver puente H para motor DC | 2 | MVP | Uno por motor. No usar MX1508 con motores de 12 V; L298N o BTS7960 son opciones baratas. |
| Alimentacion | Fuente 12 V 3 A | 1 | MVP | Suficiente para primera version ligera si se mueve lento y balanceado. 5 A queda como margen opcional. |
| Alimentacion | Convertidor buck 12 V a 5 V | 1 | MVP | Alimentacion de logica, sensores y perifericos. |
| Optica | Espejo de 20 cm x 20 cm | 1 | MVP | Preferible ligero y rigido. |
| Mecanica | Filamento PETG o ASA | 1 kg | MVP | Mejor que PLA para exterior y temperatura. |
| Mecanica | Tornilleria M3/M4 | Surtido | MVP | Ensamble de piezas impresas, motores y soportes. |
| Mecanica | Insertos roscados M3/M4 | Surtido | Recomendado | Mejora resistencia y mantenimiento. |
| Mecanica | Rodamientos | 4 a 8 | MVP | Ejes de acimut/elevacion y receptor si aplica. |
| Mecanica | Ejes metalicos 4 mm, 6 mm u 8 mm | Segun CAD | MVP | Depende del acoplamiento final. |
| Mecanica | Ejes metalicos | 1 a 2 tramos | MVP | No imprimir ejes funcionales. Usar 6 mm u 8 mm. |
| Transmision | Poleas/correas GT2 o polea grande impresa | 2 juegos | Recomendado | Mas barato y tolerante que cople directo. |
| Seguridad | Finales de carrera o sensores Hall | 4 | MVP | Home y limite por eje. |
| Seguridad | Interruptor general | 1 | MVP | Corte de energia del sistema. |
| Seguridad | Paro de emergencia pequeno | 1 | Recomendado | Muy conveniente para pruebas al Sol. |
| Cableado | Cables, terminales, conectores | Surtido | MVP | Motores, encoders, sensores, alimentacion. |
| Receptor | Riel lineal o perfil aluminio | 1 | MVP | Receptor movil/pantalla de validacion. |
| Receptor | Carro o base deslizable | 1 | MVP | Porta pantalla, sensor o receptor. |
| Validacion | Pantalla blanca o cuadriculada | 1 | MVP | Medicion visual del spot. |
| Validacion | Regla milimetrica o cuadricula | 1 | Recomendado | Medicion de error en pantalla. |
| Tiempo | RTC DS3231 | 1 | Recomendado | Hora estable sin depender siempre de WiFi. |
| Medicion | Sensor de luz de 4 cuadrantes | 1 | Experimental | Correccion optica tipo peephole simplificado. |
| Medicion | Sensor absoluto AS5600 | 2 | Experimental | Medicion directa de ejes finales. |

## Electronica principal

### Controlador

- 1 ESP32 DevKit.
- 1 cable USB de datos.
- 1 placa perforada, protoboard de pruebas o PCB simple.

El ESP32 es adecuado porque permite WiFi local, interfaz web simple, lectura de encoders por interrupciones y comunicacion serial para depuracion.

### Motores y drivers

- 2 motorreductores DC con encoder.
- Opcion recomendada actual: GM 25-370 con encoder 12 V, version 140 rpm.
- 2 drivers puente H para motor DC.

Driver sugerido:

- Opcion barata: L298N, si la estructura esta balanceada y se valida que no se caliente.
- Opcion barata con mas margen: BTS7960/IBT-2, uno por motor.
- No usar MX1508 con motores de 12 V: queda limitado por voltaje.

### Sensores de referencia

- 2 sensores de home, uno por eje.
- 2 finales de carrera adicionales, uno por limite critico de cada eje.

Opciones:

- Microswitch mecanico.
- Sensor Hall con iman.
- Sensor optico ranurado.

Para una primera version, microswitch o Hall son suficientes.

### Alimentacion

- Fuente 12 V 3 A para primera version.
- Fuente 12 V 5 A solo si las pruebas muestran caidas de voltaje, arranques pesados o movimiento simultaneo de ejes.
- Convertidor buck 12 V a 5 V.
- Fusible o portafusible.
- Interruptor general.
- Paro de emergencia pequeno.
- Capacitores cerca de drivers si hay ruido electrico.

## Mecanica e impresion 3D

### Material de impresion

Preferido:

- PETG.
- ASA si se imprimira bien y se requiere mejor resistencia exterior.

Evitar como material final:

- PLA comun para piezas estructurales expuestas al Sol, porque puede deformarse con temperatura.

### Tornilleria y fijacion

- Tornillos M3: 8, 10, 12, 16 y 20 mm.
- Tornillos M4: 10, 16, 20 y 25 mm.
- Tuercas M3/M4.
- Rondanas planas.
- Rondanas de presion.
- Insertos roscados M3/M4.

### Ejes, rodamientos y acoples

Pendiente de cerrar con CAD, pero conviene prever:

- Eje de acimut de 6 mm u 8 mm.
- Eje de elevacion de 6 mm u 8 mm.
- Coples del eje del motor de 4 mm hacia eje mecanico.
- Rodamientos 608ZZ, 625ZZ o similares segun escala.
- Rodamiento axial o base giratoria para el eje de acimut si la carga lo requiere.

### Transmision

Opciones viables:

- Acoplamiento directo: simple, pero exige buena alineacion.
- Correa GT2: permite reduccion adicional y acomoda mejor el motor.
- Engranes impresos: faciles de fabricar, pero pueden introducir backlash.
- Tornillo sin fin: puede ayudar a sostener posicion, pero complica impresion y eficiencia.

Para una primera version experimental, una reduccion por correa GT2 entre motor y eje puede ser una buena solucion.

## Espejo y receptor

### Espejo

- 1 espejo aproximado de 20 cm x 20 cm.
- Preferible que sea ligero.
- Debe montarse sobre respaldo rigido para evitar flexion.

Opciones:

- Espejo acrilico ligero.
- Espejo de vidrio delgado.
- Lamina reflectante sobre placa rigida.

Para precision optica, el espejo de primera superficie seria mejor, pero es mas delicado y costoso. Para el primer prototipo puede usarse espejo ligero y luego mejorar.

### Receptor movil

- Riel lineal, varilla lisa o perfil de aluminio.
- Carro deslizable.
- Soporte para pantalla.
- Soporte intercambiable para sensor.
- Regla o escala milimetrica.
- Tornillo de bloqueo para fijar posicion.

El receptor debe aceptar al menos dos insertos:

- Pantalla blanca/cuadriculada.
- Foco experimental o sensor.

## Validacion y medicion

### Minimo

- Pantalla blanca.
- Cuadricula impresa.
- Regla.
- Nivel de burbuja.
- Brujula o referencia de norte/sur.

### Recomendado

- RTC DS3231.
- Sensor de temperatura para registrar condiciones.
- Sensor de corriente en motores.
- Sensor absoluto AS5600 en ejes finales para comparar contra encoder del motor.

### Experimental

- Sensor de cuatro cuadrantes para detectar desplazamiento del spot.
- Camara ESP32-CAM o camara externa para registrar posicion del punto reflejado.
- Fotodiodos o LDRs con filtros/atenuacion para medicion de luz.

## Herramientas y consumibles

- Impresora 3D.
- Cautin.
- Estano.
- Termofit.
- Pinzas.
- Multimetro.
- Fuente de laboratorio, si esta disponible.
- Calibrador/vernier.
- Taladro o minitaladro.
- Limas o herramienta de acabado.
- Cinta doble cara o adhesivo estructural para fijacion temporal.
- Loctite o fijador de roscas de baja resistencia.

## Compra minima sugerida

Para empezar sin sobredimensionar:

- 1 ESP32 DevKit.
- 2 GM 25-370 con encoder 12 V 140 rpm.
- 2 drivers L298N o BTS7960/IBT-2.
- 1 fuente 12 V 3 A.
- 1 buck 12 V a 5 V.
- 4 sensores de limite/home.
- 1 espejo 20 cm x 20 cm.
- 1 kg PETG.
- Surtido de tornilleria M3/M4.
- 4 a 8 rodamientos.
- correa GT2/poleas o coples compatibles con motor de 4 mm y eje mecanico elegido.
- Material para riel del receptor.
- Pantalla blanca/cuadriculada.

## Pendientes para cerrar cantidades exactas

- Peso real del espejo.
- Peso estimado del bastidor impreso.
- Diametro elegido para los ejes.
- Tipo final de transmision.
- Rango angular de acimut y elevacion.
- Si el receptor usara riel impreso, varilla lisa o perfil de aluminio.
- Si se agregara sensor optico desde la primera version o hasta una segunda etapa.
