# Viabilidad de impresion 3D y simplificacion del sistema

Fecha: 2026-07-02.

Objetivo: revisar el proyecto bajo una premisa mas austera: espejo pequeno de 20 cm x 20 cm, estructura ligera, mayoria de piezas impresas en 3D, bajo costo y control simple.

## Conclusion principal

El planteamiento anterior era conservador. Para una maqueta pequena, bien balanceada y de movimiento lento, **no hace falta empezar con una fuente de 10 A ni drivers grandes**. Esa recomendacion daba margen ante bloqueo, desbalance y errores mecanicos, pero puede simplificarse.

La estrategia mas barata y razonable es:

- Imprimir casi toda la estructura.
- Usar piezas metalicas solo donde realmente importan: ejes, tornillos, rodamientos y quiza resortes/contrapesos.
- Balancear el eje de elevacion para que el motor no cargue el peso del espejo.
- Mover un eje a la vez durante las primeras pruebas.
- Usar fuente 12 V 2 A o 3 A al inicio, y subir a 5 A solo si aparecen caidas de voltaje o bloqueos.

## Que si conviene imprimir en 3D

| Pieza | Viabilidad | Comentario |
|---|---|---|
| Base fija | Alta | Imprimir con buena area de apoyo, nervaduras y espacio para peso/lastre. |
| Columna o pedestal | Media-alta | Sirve si es corta y ancha. Evitar columnas delgadas. |
| Bastidor posterior del espejo | Alta | Ideal para replicar visualmente la estructura reticulada del mini horno. |
| Portaespejo | Alta | Conviene imprimir con respaldo plano y puntos de fijacion. |
| Soportes de motor | Alta | Usar PETG y tornillos/insertos. |
| Soportes de finales de carrera | Alta | Facil de ajustar e iterar. |
| Topes mecanicos | Alta | Pueden ser impresos y reemplazables. |
| Carro del receptor | Alta | Buen candidato para impresion 3D. |
| Pantalla/receptor intercambiable | Alta | Insertos impresos para pantalla, cuadricula o sensor. |
| Poleas grandes o sector dentado | Media | Viable si se imprimen grandes, con dientes robustos y baja carga. |
| Engranes | Media-baja | Funcionan, pero introducen holgura y desgaste. Mejor para pruebas que para precision final. |
| Cople rigido | Baja | No conviene imprimir como pieza final si transmite torque directo. Puede patinar, deformarse o quedar descentrado. |
| Eje principal | Baja | Debe ser metalico. Un eje impreso tendra flexion, desgaste y mala concentricidad. |

## Que no conviene imprimir como pieza funcional principal

### Ejes

Los ejes de acimut y elevacion deben ser metalicos. La impresion 3D no da buena concentricidad ni resistencia al desgaste.

Recomendacion:

- Eje de elevacion: varilla metalica de 6 mm u 8 mm.
- Eje de acimut: tornillo, varilla o perno metalico; si se usa 608ZZ, entonces 8 mm.

### Rodamientos

No imprimir rodamientos como solucion principal. Se pueden imprimir bujes para pruebas, pero para repetibilidad convienen rodamientos reales o bujes de baja friccion.

### Coples pequenos

Un cople impreso de 4 mm a 8 mm puede servir para pruebas lentas, pero no como solucion final confiable si va directo al eje. Mejor usar:

- cople flexible 4x8 mm comprado,
- polea GT2 de 4 mm en motor,
- engrane/polea impresa grande fijada al eje de salida.

## Transmision barata recomendada

Para abaratar, la mejor ruta no es necesariamente cople directo. Es mejor usar una transmision impresa o semimpresa con reduccion.

### Opcion A: polea pequena comercial + polea grande impresa

- Motor GM 25-370 con polea pequena en eje de 4 mm.
- Polea grande impresa en el eje de elevacion/acimut.
- Correa GT2 o banda dentada.

Ventajas:

- Baja costo.
- Permite reduccion adicional.
- Tolera mejor desalineacion que cople rigido.
- Reduce exigencia de torque del motor.

Riesgos:

- Hay que imprimir bien la polea grande.
- La tension de correa no debe flexionar la estructura.

### Opcion B: pinon comercial o impreso + sector dentado impreso

- Pinon pequeno en el motor.
- Sector dentado grande impreso unido al eje.

Ventajas:

- Se parece visualmente a un mecanismo real.
- Permite mucho torque.
- Puede ser compacto.

Riesgos:

- Backlash entre dientes.
- Desgaste si se imprime en PLA.
- Requiere buen ajuste.

### Opcion C: cople directo

- Motor acoplado directamente al eje.

Ventajas:

- Simple.
- Menos piezas.

Riesgos:

- Exige alineacion.
- Transmite vibracion.
- Puede cargar radialmente el eje del motor.
- Sin reduccion adicional, la resolucion y el control fino dependen solo del motorreductor.

Para este proyecto, la opcion A parece la mas equilibrada.

## Recalculo simple de torque

El eje critico es elevacion.

```text
T = m * g * d
```

Si el espejo + bastidor pesan 0.35 kg y el centro de gravedad queda a 2 cm del eje:

```text
T = 0.35 * 9.81 * 0.02 = 0.069 N m
T = 0.70 kg cm
```

El GM 25-370 de 140 rpm declara 4.3 kg cm nominal y 8.5 kg cm de paro, asi que estaria sobrado si el eje esta balanceado.

Si el centro de gravedad queda a 5 cm:

```text
T = 0.35 * 9.81 * 0.05 = 0.172 N m
T = 1.75 kg cm
```

Sigue siendo viable, pero ya conviene reducir friccion y evitar acelerar brusco.

La conclusion es clara: **el problema no es tanto el torque del motor, sino el balanceo, la friccion y la holgura**.

## Fuente de alimentacion revisada

Para primera version:

| Fuente | Uso recomendado |
|---|---|
| 12 V 2 A | Posible si se mueve un eje a la vez, sin bloqueo y con estructura balanceada. |
| 12 V 3 A | Buena opcion inicial barata. |
| 12 V 5 A | Margen comodo, recomendable si el costo sigue bajo. |
| 12 V 10 A | No necesaria para la primera maqueta. |

Decision revisada:

- No comprar 10 A al inicio.
- Usar 12 V 3 A como base barata si ya esta disponible o es facil de conseguir.
- Subir a 5 A solo si en pruebas hay reinicios, caidas de voltaje o arranques pesados.

## Driver revisado

El MX1508 no sirve para motores de 12 V porque su rango de motor es 2 a 9 V.

Pero tampoco necesitamos forzosamente un driver caro. Para esta version simple:

| Driver | Evaluacion |
|---|---|
| MX1508 | No, por voltaje insuficiente para motor 12 V. |
| L298N | Barato y suficiente para pruebas lentas si la corriente real del motor no supera su margen. Ineficiente, pero simple. |
| BTS7960 / IBT-2 | Buena opcion barata con mucho margen. Puede parecer sobrado, pero suele ser economico. |
| DRV887x | Buena opcion compacta, pero menos facil de conseguir barato. |
| Cytron/Pololu | Muy buenos, pero pueden ser demasiado caros para la primera etapa. |

Decision revisada:

- Buscar primero **L298N** o **BTS7960/IBT-2** barato.
- Si el L298N se calienta o no mueve bien, pasar a BTS7960.
- Para mantener robustez sin gastar mucho, BTS7960 sigue siendo buena opcion aunque este sobrado.

## Version barata recomendada

### Electronica

- 1 ESP32.
- 2 GM 25-370 con encoder 12 V 140 rpm.
- 1 fuente 12 V 3 A.
- 1 buck XL4015 o similar.
- 2 drivers baratos:
  - opcion economica: L298N,
  - opcion con margen: BTS7960/IBT-2.
- 4 finales de carrera.

### Mecanica

- Estructura impresa en 3D.
- Bastidor impreso en PETG si alcanza; PLA solo para prototipos.
- Ejes metalicos de 6 mm u 8 mm.
- Rodamientos 608ZZ si se usan ejes de 8 mm.
- Transmision por correa:
  - polea pequena en motor,
  - polea grande impresa,
  - correa GT2 o similar.

### Optica

- Espejo ligero de 20 cm x 20 cm.
- Respaldo impreso o placa ligera.
- Receptor/pantalla impresa con cuadricula.

## Compra minima revisada

| Material | Cantidad | Prioridad |
|---|---:|---|
| ESP32 | 1 | MVP |
| GM 25-370 con encoder 12 V 140 rpm | 2 | MVP |
| Driver L298N o BTS7960 | 2 | MVP |
| Fuente 12 V 3 A | 1 | MVP |
| XL4015 buck | 1 | MVP |
| Finales de carrera | 4 | MVP |
| Rodamientos 608ZZ | 4 | MVP si se usan ejes de 8 mm |
| Eje metalico 8 mm | 1 o 2 tramos | MVP si se usan 608ZZ |
| Tornilleria M3/M4 | Surtido | MVP |
| PETG | Lo disponible | Estructural |
| PLA | Lo disponible | Prototipos |
| Correa GT2 o banda similar | 1 | Recomendado |
| Poleas pequenas 4 mm o pinones | 2 | Recomendado |

## Cambio de filosofia

La primera version debe ser:

```text
ligera + balanceada + lenta + barata + facil de modificar
```

No:

```text
sobredimensionada + cara + pesada + dificil de iterar
```

La precision experimental se construye despues con calibracion, medicion de error y mejor mecanica, no comprando desde el inicio fuentes y drivers grandes.
