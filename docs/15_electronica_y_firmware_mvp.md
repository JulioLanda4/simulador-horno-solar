# Electronica y firmware del MVP

Fecha: 2026-07-03.

Objetivo: definir una primera arquitectura electrica y un firmware minimo para probar el mini heliostato antes de integrar seguimiento solar completo.

## Criterio

El firmware inicial no debe intentar resolver todo el seguimiento. Primero debe demostrar:

1. mover cada motor en ambos sentidos,
2. leer encoders,
3. detectar finales de carrera,
4. ejecutar homing por eje,
5. mover por conteos relativos,
6. reportar estado por puerto serial.

No se usa PID en esta etapa. El control es discreto: encender motor, contar pulsos, detener y corregir con movimientos pequenos si hace falta.

## Arquitectura electrica inicial

```text
Fuente 12 V 3 A
  |
  +-- Driver motor acimut
  |     +-- Motor DC acimut con encoder
  |
  +-- Driver motor elevacion
  |     +-- Motor DC elevacion con encoder
  |
  +-- Buck XL4015
        +-- 5 V para logica auxiliar si se necesita
        +-- ESP32 por pin 5V/VIN o USB durante pruebas
```

Durante pruebas de banco conviene alimentar el ESP32 por USB y compartir GND con la fuente de motores.

## Senales por eje

Cada eje necesita:

| Senal | Funcion |
|---|---|
| PWM | Velocidad del motor. |
| IN1 | Direccion puente H. |
| IN2 | Direccion puente H. |
| ENC_A | Canal A del encoder. |
| ENC_B | Canal B del encoder. |
| HOME | Final de carrera de referencia. |
| LIMIT | Final de carrera de seguridad. |

Para una primera prueba se puede usar solo `HOME` por eje y dejar `LIMIT` preparado.

## Pines propuestos ESP32

Estos pines son una propuesta inicial; se deben ajustar segun la placa ESP32 exacta.

| Eje | PWM | IN1 | IN2 | ENC_A | ENC_B | HOME | LIMIT |
|---|---:|---:|---:|---:|---:|---:|---:|
| Acimut | 25 | 26 | 27 | 34 | 35 | 32 | 33 |
| Elevacion | 14 | 12 | 13 | 36 | 39 | 18 | 19 |

Notas:

- GPIO 34, 35, 36 y 39 son solo entrada; sirven para encoder.
- Los finales de carrera se conectan con `INPUT_PULLUP`, cerrando a GND.
- Todos los GND deben estar comunes: ESP32, driver, fuente y buck.

## Comandos seriales del firmware MVP

El firmware inicial debe aceptar comandos simples:

| Comando | Funcion |
|---|---|
| `status` | Reporta conteos, finales y estado. |
| `stop` | Detiene ambos motores. |
| `home az` | Homing del eje de acimut. |
| `home el` | Homing del eje de elevacion. |
| `jog az + 120` | Mueve acimut en sentido positivo a PWM 120. |
| `jog az - 120` | Mueve acimut en sentido negativo a PWM 120. |
| `jog el + 120` | Mueve elevacion en sentido positivo a PWM 120. |
| `jog el - 120` | Mueve elevacion en sentido negativo a PWM 120. |
| `move az 500 100` | Mueve acimut 500 conteos a PWM 100. |
| `move el -300 100` | Mueve elevacion -300 conteos a PWM 100. |

## Secuencia de pruebas de banco

1. Probar ESP32 por USB con `status`.
2. Leer finales de carrera con multimetro y luego con `status`.
3. Mover motor acimut sin correa con `jog az + 100`.
4. Confirmar que encoder cambia al mover el motor.
5. Repetir con elevacion.
6. Probar `stop`.
7. Probar `move` por conteos pequenos.
8. Probar `home` con el final de carrera en la mano, antes de montarlo.
9. Montar motores en estructura.
10. Repetir pruebas con correa y espejo aun sin Sol.

## Homing sin PID

Secuencia recomendada por eje:

1. Mover lento hacia el final de carrera HOME.
2. Detener al detectar HOME.
3. Retroceder una distancia pequena por conteos.
4. Acercarse otra vez mas lento.
5. Poner contador del encoder en cero.

Esto da una referencia repetible sin necesidad de control PID.

## Siguiente etapa despues del firmware MVP

Cuando el movimiento por conteos sea confiable:

1. medir conteos por vuelta del eje real,
2. calcular grados por conteo,
3. definir limites seguros en conteos,
4. agregar conversion `angulo -> conteos`,
5. integrar calculo solar y vector de receptor.

## Decision

Mientras se imprimen piezas, el trabajo paralelo debe ser firmware de banco y protocolo de pruebas. El seguimiento solar debe esperar hasta que la mecanica tenga referencia de home, movimiento repetible y conversion aproximada entre conteos y angulo.
