# Firmware MVP

Firmware inicial para probar el mini heliostato con ESP32, motores DC con encoder, puente H y finales de carrera.

## Objetivo

Este firmware no implementa seguimiento solar completo. Su funcion es probar:

- movimiento manual por eje,
- lectura de encoders,
- finales de carrera,
- homing,
- movimiento relativo por conteos.

## Archivo principal

- `mini_heliostato_mvp/mini_heliostato_mvp.ino`

## Comandos seriales

Configurar monitor serial a `115200`.

```text
status
stop
home az
home el
jog az + 120
jog az - 120
jog el + 120
jog el - 120
move az 500 100
move el -300 100
```

## Importante

Revisar pines antes de conectar el hardware real. La tabla de pines esta en `docs/15_electronica_y_firmware_mvp.md`.
