# Reemplazos para componentes no recomendados

Fecha de revision: 2026-07-02.

Objetivo: proponer reemplazos para las piezas que no convencen en la lista de compra, priorizando UNIT Electronics cuando sea viable.

## Componentes a reemplazar

| Pieza descartada o debil | Motivo | Reemplazo preferido | Enlace | Comentario |
|---|---|---|---|---|
| Doble Puente H MX1508 | No soporta bien motores de 12 V; limitado a 2-9 V para motores y 0.8 A nominal por canal. | Cytron MD10C, 1 por motor | [Cytron MD10C](https://www.cytron.io/p-10amp-5v-30v-dc-motor-driver) | Mejor opcion practica: 5-30 V, compatible con logica 3.3/5 V, hasta 10 A continuos segun ficha. No es de UNIT. |
| Doble Puente H MX1508 | Mismo motivo. | Pololu VNH5019, 1 por motor | [Pololu VNH5019](https://www.pololu.com/product/1451) | Muy buen margen: 5.5-24 V y 12 A continuos segun ficha. Mas caro, pero robusto. |
| Doble Puente H MX1508 | Mismo motivo. | Pololu DRV8874 o DRV8876, 1 por motor | [Pololu DRV8876](https://www.pololu.com/product/4036) | DRV8876 puede quedar justo; mejor DRV8874 si se compra de esta familia. Sirve si se limita corriente y el eje esta balanceado. |
| Fuente 12 V 2 A | Corriente baja para dos motores con picos de arranque. | Fuente 12 V 5 A o mas | Buscar en proveedor disponible | No se encontro una opcion clara en UNIT dentro de las fichas revisadas. Si se usa UNIT, la fuente 12 V 3 A solo debe considerarse para pruebas. |
| Fuente 12 V 3 A | Puede quedar justa; ademas en la ficha revisada aparecia sin existencias. | Fuente 12 V 5 A o 10 A | Buscar en proveedor disponible | Objetivo: alimentar dos motores y logica con margen. |
| Cople rigido UNIT 5x5/5x8/8x8 | No coincide con el eje D de 4 mm del GM 25-370. | Cople 4x8 mm, preferible flexible | Buscar cople 4x8 mm | Si se usan rodamientos 608ZZ, el eje principal sera de 8 mm; el motor tiene eje de 4 mm. |
| Cople rigido UNIT 5x5/5x8/8x8 | Exige alineacion perfecta y transmite vibracion. | Polea GT2 con bore 4 mm + eje/polea 8 mm | Buscar en UNIT o proveedor de impresoras 3D | Mejor que cople directo si queremos reduccion adicional y montaje menos critico. |

## Reemplazo recomendado para driver

La mejor ruta para este proyecto es usar **un driver por motor**.

Orden recomendado:

1. Cytron MD10C: opcion mas practica y con margen amplio.
2. Pololu VNH5019: opcion robusta con corriente suficiente.
3. Pololu DRV8874: opcion compacta si se consigue.
4. Pololu DRV8876: posible, pero mas justo para picos.

No usar MX1508 para los ejes principales.

## Reemplazo recomendado para fuente

Buscar fuente:

```text
12 V DC
5 A minimo
60 W minimo
preferible 8 A a 10 A si el costo no sube demasiado
```

La fuente de 12 V 3 A puede servir solo si:

- Se mueve un eje a la vez.
- La estructura esta bien balanceada.
- Se limita la corriente.
- Se acepta que es fuente de banco/prototipo, no final.

## Reemplazo recomendado para coples

Si se confirma:

- Motor GM 25-370: eje D de 4 mm.
- Rodamientos 608ZZ: eje principal de 8 mm.

Entonces buscar:

```text
cople flexible 4mm a 8mm
cople rigido 4mm a 8mm
polea GT2 bore 4mm
polea GT2 bore 8mm
```

Preferencia:

1. Correa GT2 con poleas: permite reduccion extra y tolera mejor la ubicacion del motor.
2. Cople flexible 4x8 mm: util si se quiere acoplamiento directo.
3. Cople rigido 4x8 mm: solo si la alineacion es muy buena.

## Nota sobre UNIT Electronics

De las opciones revisadas de UNIT, si sirven:

- XL4015 como buck 12 V a 5 V.
- Finales de carrera.
- Rodamientos 608ZZ si se disenan ejes de 8 mm.

No conviene usar de UNIT, para esta version:

- MX1508 como driver principal.
- Cople rigido 5x5/5x8/8x8 para el GM 25-370.
- Fuente 12 V 2 A como fuente principal.

La fuente 12 V 3 A de UNIT queda como opcion de prueba, no como fuente final.
