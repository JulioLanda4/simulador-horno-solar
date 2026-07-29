# Plan de trabajo del MVP

Fecha: 2026-07-03.

Objetivo: construir un primer mini heliostato funcional, barato y mayormente impreso en 3D, usando un espejo de aproximadamente 200 x 200 mm, dos ejes motorizados, encoders, finales de carrera y un receptor sobre riel impreso de doble guia.

## Criterio general

El proyecto debe avanzar de menor a mayor riesgo:

1. Validar tolerancias impresas.
2. Validar transmision mecanica.
3. Validar movimiento de cada eje por separado.
4. Integrar los dos ejes.
5. Integrar electronica y lectura de encoders.
6. Ejecutar apuntamiento con Sol real.
7. Medir error sobre pantalla/receptor.

Esto evita imprimir una estructura grande antes de saber si los alojamientos, poleas, ejes y guias funcionan bien con la impresora real.

## Fase 1: Pruebas impresas pequenas

### Piezas

| Pieza | Cantidad | Objetivo |
|---|---:|---|
| Alojamiento de rodamiento 608ZZ | 2 a 3 variantes | Ajustar tolerancia del diametro de 22 mm. |
| Abrazadera de eje 8 mm | 2 variantes | Probar sujecion sin deformar el eje. |
| Seccion corta de riel doble guia | 1 | Probar friccion y rigidez del perfil. |
| Mini carro del receptor | 1 | Probar deslizamiento y bloqueo. |
| Polea GT2 impresa de 60 dientes | 1 a 2 variantes | Probar engrane con correa GT2 de 6 mm. |
| Soporte de motor con ranuras | 1 | Probar montaje y tensionado de correa. |

### Criterio de exito

- El rodamiento 608ZZ entra firme, sin fracturar la pieza.
- El eje de 8 mm gira libremente donde debe girar.
- La abrazadera bloquea el eje sin juego visible.
- La polea impresa no salta dientes con tension moderada.
- El carro del receptor se desliza sin atascarse y puede bloquearse con tornillo.

## Fase 2: Compra minima para pruebas

Comprar solo lo necesario para validar el concepto mecanico y electronico:

| Componente | Cantidad inicial | Nota |
|---|---:|---|
| Motorreductor GM 25-370 con encoder, 12 V, 140 rpm | 2 | Uno por eje. |
| Driver L298N o BTS7960/IBT-2 | 2 | L298N si se prioriza costo; BTS7960 si se quiere mas margen. |
| Fuente 12 V 3 A | 1 | Suficiente para el MVP si el sistema esta balanceado. |
| Buck XL4015 | 1 | Para alimentar 5 V/3.3 V si hace falta. |
| Finales de carrera | 4 | Home y limite por eje. |
| Rodamientos 608ZZ | 6 a 8 | Ejes y pruebas. |
| Correa GT2 de 6 mm | 1 a 2 m | Para acimut y elevacion. |
| Polea GT2 20 dientes bore 4 mm | 2 | Una por motor. |
| Eje metalico 8 mm | 1 a 2 tramos | Para acimut/elevacion. |
| Tornilleria M3/M4 | Surtida | Ensamble, ranuras y bloqueos. |

No conviene comprar todavia componentes caros de control, fuentes grandes ni sensores opticos avanzados. Primero hay que demostrar que la mecanica barata mueve el espejo con holgura aceptable.

## Fase 3: CAD del primer ensamble mecanico

Orden recomendado:

1. Modelos de referencia: espejo, motor, rodamiento, eje, polea motor y correa.
2. Bastidor modular del espejo.
3. Eje de elevacion y horquilla.
4. Base y eje de acimut.
5. Soportes de motores con ranuras de tension.
6. Topes y soportes para finales de carrera.
7. Receptor con riel doble guia.
8. Soportes para electronica y gestion de cableado.

El CAD debe mantenerse parametrico donde sea practico: diametro de eje, diametro de rodamiento, ancho de correa, distancia entre guias y dimensiones del espejo.

## Fase 4: Movimiento manual y homing

Antes de implementar seguimiento solar:

1. Mover acimut en ambos sentidos.
2. Mover elevacion en ambos sentidos.
3. Leer encoder de cada motor.
4. Detectar finales de carrera.
5. Ejecutar homing por eje.
6. Guardar posicion cero.
7. Mover a posiciones angulares por conteo de encoder.

No se requiere PID para esta fase. El control puede ser por movimiento incremental: avanzar, contar pulsos, detener y corregir con movimientos pequenos si hace falta.

## Fase 5: Apuntamiento solar

El seguimiento debe calcular:

1. Vector solar local.
2. Vector desde heliostato hacia receptor.
3. Normal requerida del espejo.
4. Angulos objetivo de acimut y elevacion.
5. Movimiento discreto hacia esos angulos.

El primer objetivo experimental no debe ser concentrar potencia. Debe ser mantener la mancha solar centrada en una pantalla blanca o cuadriculada del receptor. Cuando eso funcione, se puede cambiar a receptor de prueba.

## Fase 6: Validacion experimental

Mediciones iniciales:

| Medicion | Metodo simple |
|---|---|
| Error de apuntamiento | Distancia de la mancha al centro de la pantalla. |
| Repetibilidad de home | Volver a home y medir si regresa al mismo punto. |
| Juego mecanico | Mover ida/vuelta y observar cambio en mancha. |
| Deriva | Registrar posicion de mancha cada cierto tiempo. |
| Rigidez | Observar vibracion o caida con viento ligero. |

La pantalla de validacion es solo una forma barata y segura de medir si el heliostato apunta correctamente. No es el receptor final; es el instrumento de calibracion inicial.

## Siguiente accion inmediata

La siguiente accion del proyecto debe ser preparar el paquete de pruebas de tolerancia:

1. Definir en CAD cinco piezas pequenas:
   - alojamiento 608ZZ,
   - abrazadera de eje 8 mm,
   - tramo corto de doble guia,
   - mini carro,
   - polea GT2 60 dientes.
2. Imprimirlas en PETG.
3. Medir ajustes reales.
4. Corregir tolerancias.
5. Solo despues modelar piezas grandes.

## Decision

Seguimos con una ruta MVP mecanica primero. La prioridad no es comprar mas electronica ni cerrar el algoritmo completo todavia; la prioridad es comprobar que una estructura impresa, con ejes metalicos, rodamientos 608ZZ, correa GT2 y poleas impresas puede mover de forma repetible un espejo de 20 x 20 cm.
