# Parametros cerrados y alternativa de polea impresa

Fecha: 2026-07-03.

Este documento actualiza el diseno con tres decisiones nuevas:

- cama de impresion: 210 x 210 x 205 mm,
- espejo probable: 200 x 200 mm, 3 mm de grosor,
- receptor sobre riel impreso,
- buscar transmision con polea grande impresa.

## Cama de impresion

Volumen disponible:

```text
210 x 210 x 205 mm
```

Implicaciones:

- No conviene disenar piezas de 210 mm exactos; dejar margen.
- Dimension maxima practica de pieza plana: 195 a 205 mm.
- La base de 250 x 250 mm debe imprimirse por secciones o reducirse.
- El bastidor posterior no debe depender de una sola pieza de 220 x 220 mm.
- Conviene disenar el bastidor como marco modular: 4 lados + diagonales + nodo central.

## Espejo

Opcion probable:

- Espejo cuadrado de 20 x 20 cm.
- Grosor probable: 3 mm.
- Enlace proporcionado: https://www.homedepot.com.mx/p/reflexion-espejo-cuadrado-20-x-20-cm-2020-232921

No se pudo verificar la ficha desde Codex, asi que se toma como dato de diseno preliminar.

### Masa aproximada

Con vidrio de 3 mm:

```text
volumen = 0.20 * 0.20 * 0.003 = 0.00012 m3
densidad vidrio ~= 2500 kg/m3
masa ~= 0.30 kg
```

Entonces:

```text
masa espejo ~= 300 g
masa espejo + bastidor ~= 350 a 500 g
```

Esto sigue siendo viable para los GM 25-370 si el eje de elevacion queda cerca del centro de gravedad.

## Bastidor compatible con cama 210 x 210

No imprimir el portaespejo completo como una placa maciza. Mejor:

1. Marco perimetral en 4 piezas.
2. Esquinas atornilladas.
3. Diagonales impresas separadas.
4. Nodo central para unir diagonales.
5. Abrazaderas suaves para sujetar el espejo sin forzarlo.

Propuesta:

```text
marco exterior: 205 x 205 mm aprox.
ventana/soporte espejo: 200 x 200 mm
ancho de perfil impreso: 10 a 15 mm
grosor estructural: 6 a 10 mm
```

El espejo no debe quedar presionado directamente por piezas rigidas. Usar pequenas almohadillas, cinta doble cara delgada o apoyos impresos con holgura.

## Base compatible con cama 210 x 210

Opcion simple:

- base central impresa de 190 x 190 mm,
- 4 patas extensibles o atornilladas,
- huecos para colocar lastre,
- orificios para fijar a una tabla si hace falta.

No hace falta imprimir una base de 250 x 250 mm de una sola pieza.

## Receptor con riel impreso

El receptor no ira sobre perfil 2020 ni riel comercial en la primera version.

Propuesta:

- riel impreso recto en secciones,
- longitud inicial: 500 a 600 mm,
- carro deslizante impreso,
- tornillo M3/M4 para bloquear posicion,
- pantalla intercambiable,
- escala impresa o regla pegada.

Como el receptor no carga mucho peso, un riel impreso es viable.

Recomendacion:

- imprimir el riel en tramos de 180 a 200 mm,
- unir tramos con espigas, tornillos o una base plana,
- evitar depender de una sola pieza larga.

## Alternativa de polea grande impresa

La mejor ruta barata es:

```text
polea pequena comercial de 4 mm en motor
correa GT2
polea grande impresa en eje principal de 8 mm
```

### Por que no imprimir la polea pequena

La polea pequena va en el eje del motor de 4 mm. Es una pieza pequena, con prisioneros, donde la precision importa. Conviene comprarla.

### Por que si imprimir la polea grande

La polea grande:

- es mas facil de imprimir,
- puede integrarse con un cubo de fijacion,
- permite relacion de transmision personalizada,
- reduce costo,
- aumenta torque efectivo,
- mejora resolucion angular.

## Tamano recomendado de polea impresa

Usar perfil GT2, paso 2 mm.

| Dientes motor | Dientes polea impresa | Relacion | Diametro primitivo aprox. |
|---:|---:|---:|---:|
| 20 | 40 | 2:1 | 25.5 mm |
| 20 | 60 | 3:1 | 38.2 mm |
| 20 | 80 | 4:1 | 50.9 mm |
| 16 | 64 | 4:1 | 40.7 mm |

Recomendacion inicial:

```text
20 dientes en motor + 60 dientes impresos en eje = 3:1
```

Si se consigue polea comercial de 16 dientes con bore 4 mm:

```text
16 dientes en motor + 64 dientes impresos en eje = 4:1
```

Ambas caben sin problema en la cama de impresion.

## Diseno de la polea impresa

Especificacion inicial:

```text
perfil: GT2
dientes: 60
bore: 8 mm
ancho para banda: 6 mm o 10 mm segun correa comprada
cubo central: 18 a 24 mm de diametro
grosor total: 10 a 14 mm
fijacion: prisionero M3 contra eje o abrazadera partida
material: PETG
```

Preferir fijacion por abrazadera partida antes que depender solo de un prisionero en plastico.

## Fijacion al eje de 8 mm

Opciones:

1. Cubo partido con dos tornillos M3.
2. Inserto metalico o tuerca cautiva.
3. Prisionero M3 contra eje con plano limado.
4. Polea impresa atornillada a un cubo separado.

Para evitar que patine, lo mejor es:

```text
eje 8 mm con una cara plana pequena + polea impresa con abrazadera
```

## Compra necesaria para transmision

Comprar:

- 2 poleas GT2 para eje de motor de 4 mm.
- 1 o 2 correas GT2.
- opcional: 2 poleas de 8 mm si se decide no imprimirlas.

Imprimir:

- 2 poleas grandes de 60 dientes, bore 8 mm, una para acimut y una para elevacion.

## Decision actualizada

La transmision base queda asi:

```text
motor GM 25-370
polea GT2 comercial bore 4 mm
correa GT2
polea GT2 grande impresa en PETG, 60 dientes, bore 8 mm
eje metalico de 8 mm
rodamiento 608ZZ
```

## Pendientes inmediatos

- Correa definida: GT2 de 6 mm de ancho.
- Encontrar polea GT2 de 4 mm para el motor.
- Definir si el eje de 8 mm tendra plano limado para fijacion.
- Riel definido: doble guia impresa en tramos de 180 a 200 mm.
