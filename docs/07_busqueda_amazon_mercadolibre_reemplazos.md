# Busqueda en Amazon y Mercado Libre de reemplazos

Fecha de revision: 2026-07-02.

Objetivo: buscar reemplazos para las piezas no recomendadas cuando UNIT Electronics no tiene una opcion adecuada.

## Limitaciones de busqueda

- Amazon Mexico permitio consultar algunas paginas de busqueda y extraer resultados para BTS7960 y fuente 12 V 5 A.
- Mercado Libre respondio con paginas publicas, pero no expuso resultados de producto en el HTML accesible desde Codex. Por eso se dejan enlaces de busqueda, no listings verificados.
- Los precios y existencia pueden cambiar; verificar antes de comprar.

## Reemplazos buscados

| Necesidad | Opcion encontrada o busqueda | Enlace | Evaluacion |
|---|---|---|---|
| Driver para motor DC 12 V, reemplazo de MX1508 | BTS7960 43A en Amazon Mexico | [HiLetgo BTS7960 43A](https://www.amazon.com.mx/HiLetgo-BTS7960-43A-Potencia-Arduino/dp/B00WSN98DC) | Aceptable y barato para prototipo. Usar 1 modulo por motor. La corriente de 43 A es nominal comercial; no disenar cerca de ese limite. |
| Driver para motor DC 12 V, reemplazo de MX1508 | Paquete de 2 BTS7960 en Amazon Mexico | [Teyleten Robot BTS7960 2 piezas](https://www.amazon.com.mx/Teyleten-Robot-controlador-inteligente-corriente/dp/B099N8XS5P) | Practico porque necesitamos dos ejes. Revisar vendedor, entrega y comentarios antes de comprar. |
| Driver para motor DC 12 V | Busqueda Mercado Libre BTS7960 | [Mercado Libre: BTS7960 driver motor 43A](https://listado.mercadolibre.com.mx/bts7960-driver-motor-43a) | Buscar modulo IBT-2/BTS7960. Confirmar que opere con 12 V y logica compatible con ESP32/Arduino. |
| Driver mas robusto/oficial | Cytron MD10C | [Cytron MD10C](https://www.cytron.io/p-10amp-5v-30v-dc-motor-driver) | Mejor tecnicamente que BTS7960 generico, pero no necesariamente disponible en Amazon/Mercado Libre Mexico. |
| Driver robusto/oficial | Pololu VNH5019 | [Pololu VNH5019](https://www.pololu.com/product/1451) | Muy buen margen y protecciones. Mas caro y puede requerir compra/importacion. |
| Fuente 12 V con margen | Busqueda Amazon 12 V 5 A | [Amazon Mexico: fuente 12V 5A](https://www.amazon.com.mx/s?k=fuente+12v+5a) | Buscar fuente 12 V 5 A o mas. Preferir fuente conmutada cerrada o adaptador certificado. |
| Fuente 12 V con mas margen | Busqueda Amazon 12 V 10 A | [Amazon Mexico: fuente 12V 10A](https://www.amazon.com.mx/s?k=fuente+12v+10a) | Mejor margen para pruebas con dos motores. Usar fusible y caja protegida si es fuente abierta. |
| Fuente 12 V con margen | Busqueda Mercado Libre 12 V 5 A | [Mercado Libre: fuente 12V 5A](https://listado.mercadolibre.com.mx/fuente-12v-5a) | Verificar que entregue 5 A reales y que tenga protecciones. |
| Acople motor 4 mm a eje 8 mm | Busqueda Amazon cople 4x8 mm | [Amazon Mexico: cople flexible 4mm 8mm](https://www.amazon.com.mx/s?k=cople+flexible+4mm+8mm) | Buscar cople flexible 4x8 mm. Mejor que rigido si hay desalineacion. |
| Acople motor 4 mm a eje 8 mm | Busqueda Mercado Libre cople 4x8 mm | [Mercado Libre: cople flexible 4mm 8mm](https://listado.mercadolibre.com.mx/cople-flexible-4mm-8mm) | Confirmar diametros internos exactos: 4 mm y 8 mm. |
| Transmision por correa | Busqueda Amazon polea GT2 4 mm | [Amazon Mexico: polea GT2 4mm](https://www.amazon.com.mx/s?k=polea+gt2+4mm) | Para eje del motor GM 25-370. Verificar bore 4 mm. |
| Transmision por correa | Busqueda Amazon polea GT2 8 mm | [Amazon Mexico: polea GT2 8mm](https://www.amazon.com.mx/s?k=polea+gt2+8mm) | Para eje principal de 8 mm si se usan rodamientos 608ZZ. |
| Transmision por correa | Busqueda Mercado Libre polea GT2 4 mm | [Mercado Libre: polea GT2 4mm](https://listado.mercadolibre.com.mx/polea-gt2-4mm) | Alternativa a cople directo; permite reduccion adicional. |

## Decision recomendada

### Driver

Si se compra en Amazon/Mercado Libre, la opcion mas realista y facil de encontrar es:

```text
2 modulos BTS7960 / IBT-2
1 modulo por motor
```

Ventajas:

- Mucho mas margen que MX1508.
- Compatible con motores DC de 12 V.
- Comun en proyectos Arduino.
- Barato y facil de encontrar.

Precauciones:

- Las especificaciones de 43 A en modulos genericos suelen ser optimistas.
- Usar fusible en la alimentacion de motores.
- No encerrar sin ventilacion.
- Probar primero con corriente limitada o fuente de laboratorio.
- No asumir que todos los vendedores entregan la misma calidad.

### Fuente

Buscar:

```text
12 V
5 A minimo
10 A preferible si el costo es razonable
60 W minimo
120 W si es 12 V 10 A
```

Para prototipo de banco:

- 12 V 5 A es suficiente si el sistema esta balanceado.
- 12 V 10 A da mejor margen para arranque y bloqueo momentaneo.

### Acople/transmision

Si el eje principal sera de 8 mm:

1. Preferir poleas GT2 de 4 mm y 8 mm con correa.
2. Si se quiere directo, usar cople flexible 4x8 mm.
3. Evitar cople rigido salvo que la alineacion sea muy buena.

## Lista de compra ajustada

| Material | Cantidad | Fuente sugerida |
|---|---:|---|
| GM 25-370 con encoder 12 V 140 rpm | 2 | UNIT Electronics |
| BTS7960 / IBT-2 | 2 | Amazon Mexico o Mercado Libre |
| XL4015 buck | 1 | UNIT Electronics |
| Fuente 12 V 5 A o 10 A | 1 | Amazon Mexico o Mercado Libre |
| Finales de carrera | 4 | UNIT Electronics |
| Rodamientos 608ZZ | 4 a 8 | UNIT Electronics |
| Cople flexible 4x8 mm o poleas GT2 4/8 mm | 2 juegos | Amazon Mexico o Mercado Libre |
| PETG | Segun inventario | Material propio; comprar mas si no alcanza |
| PLA | Segun inventario | Solo prototipos |
