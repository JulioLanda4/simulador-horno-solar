# Diseno mecanico inicial

Fecha: 2026-07-03.

Objetivo: fijar el primer diseno mecanico conceptual del mini heliostato impreso antes de pasar a CAD. La version inicial debe ser barata, ligera, mayormente impresa en PETG, con piezas metalicas solo donde hagan falta.

## Filosofia del primer prototipo

```text
ligero + balanceado + lento + barato + facil de modificar
```

No se busca todavia una maquina final. Se busca una plataforma que permita:

- mover dos ejes,
- leer encoders,
- hacer home,
- apuntar manualmente,
- validar la geometria solar,
- medir error sobre una pantalla/receptor.

## Dimensiones iniciales

| Elemento | Dimension inicial | Comentario |
|---|---:|---|
| Espejo | 200 x 200 mm | Mantener como referencia central del proyecto. |
| Bastidor posterior | modular, aprox. 205 x 205 mm | La cama es 210 x 210 mm; conviene imprimir marco en piezas. |
| Altura del centro del espejo | 180 a 220 mm | Suficiente para dejar espacio a base, motor y eje de acimut. |
| Distancia inicial al receptor | 470 mm | Escalamiento preliminar del mini horno. Ajustable. |
| Base | centro 190 x 190 mm + patas | Compatible con cama 210 x 210 mm y ampliable con patas atornilladas. |
| Eje de elevacion | 8 mm recomendado | Compatible con rodamientos 608ZZ. |
| Eje de acimut | 8 mm recomendado | Simplifica compra y diseno si se reutilizan 608ZZ. |

Estas dimensiones son de partida. Deben ajustarse al volumen real de impresion, al espejo elegido y al espacio de prueba.

## Arquitectura de ejes

### Eje de acimut

El eje de acimut es vertical y gira toda la horquilla del heliostato.

Componentes:

- base fija impresa,
- columna central corta,
- eje metalico vertical de 8 mm,
- dos rodamientos 608ZZ o soporte equivalente,
- polea grande impresa en PETG, preferentemente 60 dientes,
- motor GM 25-370 montado en la base,
- correa GT2 entre motor y eje de acimut.

No se recomienda acoplar el motor directamente al eje de acimut en la primera version, porque exigiria buena alineacion y no daria reduccion adicional.

### Eje de elevacion

El eje de elevacion es horizontal y atraviesa la horquilla o el bastidor del espejo.

Componentes:

- dos soportes laterales impresos,
- eje metalico horizontal de 8 mm,
- dos rodamientos 608ZZ,
- bastidor/portaespejo montado sobre el eje,
- polea grande impresa en PETG, preferentemente 60 dientes,
- motor GM 25-370 montado en un costado de la horquilla,
- correa GT2 entre motor y eje de elevacion.

La prioridad es que el centro de gravedad del espejo+bastidor quede lo mas cerca posible del eje de elevacion.

## Balance del eje de elevacion

El eje de elevacion debe quedar casi balanceado. Si no, el motor trabajara para sostener peso y no solo para mover.

Estrategias:

- ubicar el eje de elevacion cerca del centro geometrico del espejo,
- montar el espejo sobre un bastidor ligero,
- agregar pequenas ranuras para mover el espejo unos milimetros arriba/abajo,
- dejar espacio posterior para un contrapeso pequeno si hace falta,
- evitar que el motor cargue directamente el peso por acoplamiento rigido.

Modelo simple:

```text
T = m * g * d
```

Ejemplo con 0.35 kg y centro de gravedad a 20 mm:

```text
T = 0.35 * 9.81 * 0.02 = 0.069 N m = 0.70 kg cm
```

Con el GM 25-370, esto es manejable. El problema real sera friccion, holgura y flexion.

## Transmision recomendada

### Configuracion base

Para cada eje:

```text
motor GM 25-370 -> polea pequena GT2 4 mm -> correa -> polea grande impresa/eje 8 mm
```

La polea pequena debe tener bore de 4 mm para el eje del motor.

La polea grande puede ser:

- comercial de 8 mm si se consigue,
- impresa en PETG,
- integrada al bastidor o al eje mediante prisionero/abrazadera.

### Relacion de transmision sugerida

Buscar relacion adicional de 2:1 a 4:1.

Ejemplos:

| Polea motor | Polea eje | Relacion |
|---:|---:|---:|
| 20 dientes | 40 dientes | 2:1 |
| 20 dientes | 60 dientes | 3:1 |
| 16 dientes | 64 dientes | 4:1 |

Para el primer prototipo, 3:1 es buen punto medio. La configuracion preferida es:

```text
20 dientes en motor + 60 dientes impresos en eje = 3:1
```

Ventajas:

- reduce velocidad,
- aumenta torque efectivo,
- mejora resolucion angular,
- no hace la polea demasiado grande.

## Piezas impresas en PETG

| Pieza | Material | Notas de diseno |
|---|---|---|
| Base fija | PETG | Nervaduras inferiores; espacio para tornillos o lastre. |
| Columna/pedestal | PETG | Corta y ancha; evitar columna delgada. |
| Horquilla lateral | PETG | Dos placas laterales unidas por travesanos. |
| Bastidor del espejo | PETG | Modular en 4 lados + diagonales; no una sola pieza mayor que la cama. |
| Portaespejo | PETG | Superficie de apoyo plana; no forzar el espejo. |
| Soporte motor acimut | PETG | Ranuras para tensar correa. |
| Soporte motor elevacion | PETG | Ranuras para tensar correa. |
| Poleas grandes | PETG | 60 dientes GT2, bore 8 mm, fijacion por abrazadera o prisionero. |
| Soportes de finales de carrera | PETG o PLA | Ajustables. |
| Receptor movil | PETG o PLA | PETG si estara al Sol. |

PLA puede usarse para prototipos y piezas de prueba, pero PETG debe usarse en piezas que queden expuestas al Sol o que carguen el espejo.

## Piezas no impresas

| Pieza | Cantidad | Motivo |
|---|---:|---|
| Motores GM 25-370 con encoder | 2 | Movimiento de acimut/elevacion. |
| Ejes metalicos 8 mm | 1 a 2 tramos | Rigidez y concentricidad. |
| Rodamientos 608ZZ | 4 a 8 | Giro suave y repetible. |
| Tornilleria M3/M4 | Surtido | Ensamble y ajuste. |
| Poleas pequenas GT2 4 mm | 2 | Eje del motor. Aun falta localizar compra. |
| Correa GT2 | 1 a 2 | Transmision. |
| Finales de carrera | 4 | Home y limites. |
| Espejo 200 x 200 mm | 1 | Superficie reflectante. |

## Finales de carrera

Usar 4 finales de carrera:

- home acimut,
- limite acimut,
- home elevacion,
- limite elevacion.

Para el primer prototipo, home y limite pueden compartir lado si el rango mecanico es pequeno, pero conviene dejar espacio para dos sensores por eje.

## Rango angular inicial

| Eje | Rango inicial recomendado | Comentario |
|---|---:|---|
| Acimut | +/- 90 grados | Suficiente para primeras pruebas. |
| Elevacion | 0 a 80 grados aprox. | Evitar choques del bastidor con base. |

No hace falta cubrir todo el cielo en la primera version. Es mejor limitar rango y ganar seguridad.

## Receptor sobre riel

La primera version del receptor debe ser simple:

- riel impreso recto en secciones,
- carro impreso,
- pantalla blanca/cuadriculada intercambiable,
- posicion inicial a 470 mm del centro del heliostato,
- ajuste manual de posicion,
- tornillo de bloqueo.

El riel puede imprimirse en tramos de 180 a 200 mm y unirse con tornillos o espigas.

No hace falta motorizar el receptor al inicio.

## Orden de CAD recomendado

1. Modelo simplificado del espejo 200 x 200 mm.
2. Bastidor posterior y eje de elevacion.
3. Horquilla lateral con rodamientos.
4. Base y eje de acimut.
5. Soportes de motores.
6. Poleas grandes impresas.
7. Soportes de finales de carrera.
8. Receptor/pantalla.

No modelar detalles esteticos antes de validar:

- giro libre,
- balance,
- espacio para correas,
- acceso a tornillos,
- carrera de finales de carrera.

## Pruebas mecanicas antes de electronica completa

1. Montar espejo falso de carton o acrilico ligero.
2. Verificar giro manual de elevacion.
3. Verificar balance del eje de elevacion.
4. Verificar giro manual de acimut.
5. Montar poleas/correas sin motores energizados.
6. Comprobar que no haya interferencias.
7. Ajustar tension de correas.
8. Solo despues conectar motores.

## Decision para la primera version

La primera version queda definida asi:

```text
Material principal: PETG
Espejo: 200 x 200 mm
Ejes: metalicos de 8 mm
Rodamientos: 608ZZ
Motores: GM 25-370 con encoder 12 V 140 rpm
Transmision: correa GT2 + polea pequena 4 mm + polea grande impresa de 60 dientes
Fuente: 12 V 3 A
Driver: L298N si funciona frio; BTS7960 si se requiere margen
Receptor: riel impreso de doble guia con pantalla intercambiable
```

## Pendientes concretos

- Cama confirmada: 210 x 210 x 205 mm.
- Espejo probable: 200 x 200 mm, 3 mm de grosor.
- Confirmar compra de poleas GT2 de 4 mm para el motor.
- Relacion inicial elegida: 3:1 con polea impresa de 60 dientes si la polea del motor es de 20 dientes.
- Elegir si el eje de acimut usara 1 o 2 rodamientos 608ZZ.
- Receptor definido: riel impreso manual de doble guia.
