# Especificacion CAD del MVP

Fecha: 2026-07-03.

Objetivo: convertir las decisiones mecanicas del proyecto en una lista clara de piezas y parametros para modelar el primer prototipo CAD del mini heliostato.

## Parametros globales

| Parametro | Valor |
|---|---:|
| Cama de impresion | 210 x 210 x 205 mm |
| Material final principal | PETG |
| Material de prototipo | PLA |
| Espejo | 200 x 200 x 3 mm |
| Masa estimada del espejo | 300 g |
| Ejes principales | 8 mm metalicos |
| Rodamientos | 608ZZ, 8 x 22 x 7 mm |
| Correa | GT2, 6 mm de ancho |
| Polea motor | GT2, bore 4 mm |
| Polea eje | GT2 impresa, 60 dientes, bore 8 mm |
| Relacion inicial | 3:1 si el motor usa polea de 20 dientes |
| Receptor | riel impreso de doble guia |

## Reglas de diseno para impresion

- Evitar piezas de mas de 200 mm en cualquier dimension plana.
- Dejar holgura de 0.2 a 0.4 mm en ensambles impresos.
- Dejar 0.2 mm extra en alojamientos ajustados que luego puedan lijarse.
- Usar insertos, tuercas cautivas o tornillos pasantes en uniones estructurales.
- Evitar roscas impresas pequenas en piezas sometidas a ajuste frecuente.
- Usar nervaduras en lugar de piezas macizas.
- Preferir piezas modulares atornilladas.

## Lista de piezas CAD

### Grupo A: espejo y eje de elevacion

| Pieza | Cantidad | Material | Notas |
|---|---:|---|---|
| Modelo de referencia del espejo | 1 | No imprimible | 200 x 200 x 3 mm. |
| Marco superior del bastidor | 1 | PETG | Largo menor a 205 mm. |
| Marco inferior del bastidor | 1 | PETG | Igual al superior. |
| Marco lateral izquierdo | 1 | PETG | Con punto de union al eje. |
| Marco lateral derecho | 1 | PETG | Con punto de union al eje. |
| Diagonales del bastidor | 2 a 4 | PETG | Inspiradas en estructura reticulada del mini horno. |
| Nodo central | 1 | PETG | Une diagonales y ayuda a rigidizar. |
| Abrazaderas suaves del espejo | 4 | PETG/TPU si existe | No deben forzar el vidrio. |
| Soporte de eje de elevacion | 2 | PETG | Integra alojamiento o union al eje de 8 mm. |
| Polea grande elevacion | 1 | PETG | GT2 60 dientes, bore 8 mm. |

### Grupo B: horquilla

| Pieza | Cantidad | Material | Notas |
|---|---:|---|---|
| Lateral izquierdo de horquilla | 1 | PETG | Alojamiento para 608ZZ. |
| Lateral derecho de horquilla | 1 | PETG | Alojamiento para 608ZZ. |
| Travesano frontal | 1 | PETG | Une laterales, evita torsion. |
| Travesano posterior | 1 | PETG | Une laterales, deja paso a correa. |
| Soporte motor elevacion | 1 | PETG | Con ranuras para tensionar correa. |
| Tope elevacion home | 1 | PETG | Ajustable. |
| Tope elevacion limite | 1 | PETG | Ajustable. |

### Grupo C: base y acimut

| Pieza | Cantidad | Material | Notas |
|---|---:|---|---|
| Base central | 1 | PETG | Maximo 190 x 190 mm. |
| Patas extensibles | 4 | PETG | Atornilladas a base. |
| Columna/pedestal | 1 | PETG | Baja y ancha. |
| Alojamiento inferior de rodamiento acimut | 1 | PETG | Para 608ZZ. |
| Alojamiento superior de rodamiento acimut | 1 | PETG | Para 608ZZ. |
| Plato giratorio/soporte horquilla | 1 | PETG | Une acimut con horquilla. |
| Polea grande acimut | 1 | PETG | GT2 60 dientes, bore 8 mm. |
| Soporte motor acimut | 1 | PETG | Con ranuras para tensionar correa. |
| Tope acimut home | 1 | PETG | Ajustable. |
| Tope acimut limite | 1 | PETG | Ajustable. |

### Grupo D: receptor de doble guia

| Pieza | Cantidad | Material | Notas |
|---|---:|---|---|
| Tramo de riel doble guia | 3 | PETG o PLA | 180 a 200 mm por tramo. |
| Union de riel | 2 | PETG | Espigas o placas de union. |
| Carro deslizante | 1 | PETG | Abraza doble guia. |
| Tornillo de bloqueo | 1 | Metalico | M3/M4. |
| Soporte vertical de pantalla | 1 | PETG | Intercambiable. |
| Pantalla blanca/cuadriculada | 1 | Impresa o lamina | Insertable. |

### Grupo E: soportes electronicos

| Pieza | Cantidad | Material | Notas |
|---|---:|---|---|
| Soporte ESP32 | 1 | PLA/PETG | Puede ir en base o caja separada. |
| Soporte driver | 1 a 2 | PLA/PETG | Dejar ventilacion. |
| Soporte XL4015 | 1 | PLA/PETG | Acceso a ajuste de voltaje. |
| Guia de cables | Varias | PLA/PETG | Evitar que cables entren en correas. |

## Dimensiones sugeridas de piezas clave

### Polea grande impresa

```text
perfil: GT2
dientes: 60
ancho de correa: 6 mm
ancho de polea: 8 a 10 mm
bore: 8.2 mm inicial, ajustar segun impresion
cubo: 22 mm de diametro
fijacion: abrazadera partida con 2 tornillos M3
material: PETG
```

### Riel de doble guia

```text
tramo: 190 mm
ancho total: 70 mm
separacion entre guias: 50 mm
guia: 10 mm ancho x 8 mm alto
base del riel: 3 a 5 mm espesor
uniones: espigas o placas atornilladas
```

### Carro del receptor

```text
base: 70 x 70 mm
holgura lateral por guia: 0.3 a 0.5 mm
bloqueo: tornillo M3/M4 presionando una guia
pantalla: soporte vertical desmontable
```

### Base

```text
base central: 190 x 190 mm
espesor: 6 a 10 mm con nervaduras
patas: 4 piezas atornilladas
espacio para lastre: opcional
```

## Tolerancias iniciales

| Ensamble | Tolerancia inicial |
|---|---:|
| Alojamiento 608ZZ | 22.1 a 22.3 mm |
| Paso eje 8 mm | 8.2 mm |
| Polea impresa en eje 8 mm | 8.2 mm + abrazadera |
| Ranuras de motor | 0.5 a 1.0 mm de margen |
| Carro sobre doble guia | 0.3 a 0.5 mm por lado |
| Encaje de rieles | 0.2 a 0.4 mm |

Estas tolerancias deben ajustarse con una pieza de prueba antes de imprimir piezas grandes.

## Orden de modelado

1. Crear modelos de referencia: espejo, motor, rodamiento 608ZZ, eje 8 mm, polea motor 20 dientes.
2. Modelar polea grande impresa y probar ajuste en eje.
3. Modelar riel doble guia y carro corto como prueba.
4. Modelar bastidor del espejo modular.
5. Modelar horquilla y eje de elevacion.
6. Modelar base y eje de acimut.
7. Modelar soportes de motor y finales de carrera.
8. Integrar ensamble completo.

## Primeras piezas de prueba

Antes de imprimir piezas grandes:

1. Alojamiento de rodamiento 608ZZ.
2. Abrazadera de eje 8 mm.
3. Seccion pequena de riel doble guia + mini carro.
4. Polea impresa de 60 dientes.
5. Soporte motor con ranuras.

## Decision

El CAD del MVP debe iniciar por pruebas de tolerancia, no por el ensamble completo. Si las pruebas de rodamiento, eje, riel y polea funcionan, el resto del diseno tendra menos retrabajo.
