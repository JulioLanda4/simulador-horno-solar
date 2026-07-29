# Riel impreso para receptor

Fecha: 2026-07-03.

Objetivo: comparar opciones de riel impreso para el receptor/pantalla del mini heliostato y elegir una arquitectura inicial.

## Requisitos del receptor

El receptor:

- no estara motorizado en la primera version,
- debe moverse manualmente,
- debe poder bloquearse en una posicion,
- debe sostener una pantalla blanca/cuadriculada o un sensor pequeno,
- debe colocarse inicialmente a unos 470 mm del heliostato,
- debe imprimirse en tramos por la cama de 210 x 210 mm.

La carga sera baja, asi que no necesitamos un riel lineal comercial.

## Opciones

### 1. Riel tipo V

Concepto:

```text
carro con perfil en V que desliza sobre una guia en V
```

Ventajas:

- Autocentra mejor que una ranura plana.
- Reduce juego lateral si se imprime bien.
- Permite un movimiento relativamente suave.
- Es visualmente limpio.

Desventajas:

- Requiere buena impresion de las caras inclinadas.
- Puede atascarse si hay rebabas o si el PETG deja hilos.
- Se desgasta con el tiempo si se aprieta demasiado.
- Es mas sensible a deformaciones de impresion.

Uso recomendado:

- Bueno si se quiere mejor guiado y se acepta ajustar con lija/holgura.

### 2. Riel tipo ranura rectangular

Concepto:

```text
carro con patin rectangular que corre dentro de una ranura
```

Ventajas:

- Muy facil de disenar e imprimir.
- Robusto.
- Barato.
- Facil de dividir en tramos.
- Facil de bloquear con tornillo.

Desventajas:

- Tiene mas friccion.
- Puede tener mas juego lateral.
- Si se aprieta mucho, se atora.
- Menor precision que un perfil tipo V.

Uso recomendado:

- Mejor opcion para el primer prototipo si priorizamos simplicidad.

### 3. Doble guia impresa

Concepto:

```text
dos rieles paralelos impresos + carro que abraza ambos lados
```

Ventajas:

- Mejor estabilidad contra giro del carro.
- Facil de hacer modular.
- Permite poner escala en medio.
- Tolera mejor una pantalla vertical.
- Se puede ajustar con tornillos laterales.

Desventajas:

- Necesita mejor alineacion entre las dos guias.
- Si los tramos quedan desalineados, el carro se traba.
- Ocupa mas ancho.

Uso recomendado:

- Mejor equilibrio para receptor/pantalla, especialmente si la pantalla tiene altura.

### 4. Riel impreso + varillas metalicas

Concepto:

```text
estructura impresa + una o dos varillas lisas metalicas
```

Ventajas:

- Movimiento mas suave.
- Menor desgaste.
- Mas recto que un riel completamente impreso.

Desventajas:

- Agrega compra de varillas.
- Mas piezas.
- Se aleja un poco de "todo impreso".

Uso recomendado:

- Buena segunda version si el riel impreso tiene demasiada friccion.

## Comparativa

| Tipo de riel | Facilidad de impresion | Suavidad | Rigidez | Costo | Recomendacion |
|---|---:|---:|---:|---:|---|
| Tipo V | Media | Media-alta | Media | Bajo | Bueno, pero requiere ajuste. |
| Ranura rectangular | Alta | Media-baja | Media | Muy bajo | Mas simple para primer prototipo. |
| Doble guia impresa | Media | Media | Alta | Bajo | Mejor equilibrio para pantalla. |
| Impreso + varillas | Media | Alta | Alta | Medio | Mejor si el impreso no basta. |

## Recomendacion para el proyecto

Usar **doble guia impresa** para la primera version.

Motivo:

- El receptor/pantalla puede tender a girarse si solo va en una ranura central.
- La doble guia da mejor estabilidad.
- Se puede imprimir por tramos de 180 a 200 mm.
- Permite colocar una escala o regla al centro.
- Sigue siendo barato y mayormente impreso.

## Diseno sugerido

Riel:

```text
longitud por tramo: 180 a 200 mm
numero de tramos: 3
longitud total: 540 a 600 mm
separacion entre guias: 40 a 60 mm
alto de guia: 6 a 10 mm
ancho de guia: 8 a 12 mm
material: PETG o PLA para pruebas
```

Carro:

```text
base: 70 x 70 mm aprox.
contacto con doble guia en forma de U invertida
tornillo M3/M4 para bloqueo
soporte vertical intercambiable para pantalla/sensor
```

Bloqueo:

```text
tornillo lateral o superior que presiona suavemente contra una guia
```

No usar bloqueo que deforme permanentemente el riel.

## Decision

Para CAD inicial:

```text
riel impreso de doble guia
3 tramos de 180-200 mm
carro impreso con bloqueo por tornillo
pantalla intercambiable
```
