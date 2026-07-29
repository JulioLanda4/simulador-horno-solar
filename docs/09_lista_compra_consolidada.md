# Lista de compra consolidada

Fecha: 2026-07-02.

Objetivo: lista practica de compra para una primera version simple, barata y mayormente impresa en 3D del mini heliostato de 20 cm x 20 cm.

## Criterio

- Preferir UNIT Electronics cuando el componente sea adecuado.
- Usar Amazon/Mercado Libre solo cuando UNIT no tenga una opcion clara o cuando el componente de UNIT no convenga.
- Mantener la primera version ligera, balanceada, lenta y barata.
- No comprar fuente de 10 A ni drivers caros al inicio.
- Imprimir todo lo posible, excepto ejes, rodamientos, tornilleria y algunos elementos de transmision.

## Compra principal

| Subsistema | Componente | Cantidad | Enlace preferente | Decision |
|---|---:|---:|---|---|
| Control | ESP32 DevKit | 1 | [Buscar ESP32 en UNIT](https://uelectronics.com/?s=ESP32&post_type=product) | Puede ser cualquier ESP32 DevKit compatible con Arduino IDE. |
| Movimiento | GM 25-370 con encoder 12 V 140 rpm | 2 | [UNIT Electronics](https://uelectronics.com/producto/gm-25-370-motor-con-encoder-12v-dc-140rpm-330rpm/) | Motor recomendado para acimut y elevacion. Elegir version 140 rpm. |
| Driver | L298N doble puente H | 2 | [Buscar L298N en UNIT](https://uelectronics.com/?s=L298N&post_type=product) | Sirve si es modulo L298N de doble puente H. Aunque lo anuncien para motores a pasos, tambien maneja motores DC. Validar temperatura en pruebas. |
| Driver | BTS7960 / IBT-2 | 2 | [Amazon Mexico](https://www.amazon.com.mx/s?k=BTS7960+driver+motor+43A) | Alternativa con mas margen si no se consigue L298N o si este se calienta. |
| Alimentacion | Fuente 12 V 3 A | 1 | [UNIT Electronics](https://uelectronics.com/producto/fuente-conmutada-12v-3a/) | Suficiente para primera version si se mueve lento y balanceado. Revisar existencia. |
| Alimentacion | Fuente 12 V 5 A | 1 | [Amazon Mexico](https://www.amazon.com.mx/s?k=fuente+12v+5a) | Comprar solo si la de 3 A no esta disponible o si se quiere margen. |
| Alimentacion | XL4015 buck 12 V a 5 V | 1 | [UNIT Electronics](https://uelectronics.com/producto/xl4015-convertidor-dc-dc-buck-reductor/) | Para alimentar ESP32/sensores desde 12 V. Ajustar con multimetro antes de conectar. |
| Seguridad | Final de carrera mecanico | 4 | [UNIT Electronics](https://uelectronics.com/producto/interruptor-fin-de-carrera-125v-1a-limit-switch/) | Home y limite por eje. |
| Mecanica | Rodamiento 608ZZ, 8 x 22 x 7 mm | 4 a 8 | [UNIT Electronics](https://uelectronics.com/producto/608zz-7-rodamiento-tipo-balero-de-8-x-22-x-7-mm/) | Usar si los ejes principales son de 8 mm. |
| Mecanica | Varilla/eje metalico 8 mm | 1 a 2 tramos | [Buscar varilla 8 mm en UNIT](https://uelectronics.com/?s=varilla+8mm&post_type=product) | No imprimir ejes funcionales. |
| Transmision | Correa GT2 | 1 | [Buscar GT2 en UNIT](https://uelectronics.com/?s=GT2&post_type=product) | Para transmision barata con polea grande impresa. |
| Transmision | Polea GT2 bore 4 mm | 2 | [Amazon Mexico](https://www.amazon.com.mx/s?k=polea+gt2+4mm) | Para eje del motor GM 25-370. Las poleas de UNIT visibles en la captura no parecen incluir 4 mm. |
| Transmision | Polea GT2 bore 8 mm o polea grande impresa | 2 | [Amazon Mexico](https://www.amazon.com.mx/s?k=polea+gt2+8mm) | Las opciones de 8 mm de UNIT si pueden servir para el eje principal si usamos 608ZZ. Tambien puede sustituirse por polea grande impresa. |
| Cableado | Cables Dupont / jumpers | 1 set | [Buscar Dupont en UNIT](https://uelectronics.com/?s=dupont&post_type=product) | Para pruebas de encoder, limites y control. |
| Cableado | Cable para motores | Surtido | [Buscar cable en UNIT](https://uelectronics.com/?s=cable&post_type=product) | Usar calibre mayor que jumpers para alimentacion de motores. |
| Prototipo | Placa perforada o protoboard | 1 | [Buscar protoboard en UNIT](https://uelectronics.com/?s=protoboard&post_type=product) | Para pruebas iniciales. |
| Mecanica | Tornilleria M3/M4 | Surtido | Ferreteria local / [Buscar tornilleria en UNIT](https://uelectronics.com/?s=tornillo+M3&post_type=product) | Tornillos, tuercas y rondanas. |
| Optica | Espejo 20 cm x 20 cm | 1 | Vidrieria/local | Preferir ligero. Puede ser acrilico espejado para primera version. |

## Materiales que podemos imprimir o usar del inventario

| Elemento | Fuente | Comentario |
|---|---|---|
| Base | Impresion 3D | PLA para prototipo; PETG para version final. |
| Pedestal corto | Impresion 3D | Debe ser ancho y nervado. |
| Bastidor posterior del espejo | Impresion 3D | Buen candidato para PETG. |
| Portamotor | Impresion 3D | PETG recomendado. Usar tornillos reales. |
| Soportes de finales de carrera | Impresion 3D | Faciles de iterar. |
| Polea grande | Impresion 3D | Reduce costo y permite relacion de transmision personalizada. |
| Receptor/pantalla | Impresion 3D | Con insertos para pantalla, cuadricula o sensor. |
| PLA disponible | Inventario | Prototipos, pruebas de encaje, piezas no expuestas al Sol. |
| PETG disponible | Inventario | Piezas estructurales y expuestas al Sol. Comprar mas si no alcanza. |

## Opcionales para despues

| Componente | Cantidad | Enlace | Cuando comprar |
|---|---:|---|---|
| RTC DS3231 | 1 | [Buscar DS3231 en UNIT](https://uelectronics.com/?s=DS3231&post_type=product) | Si se quiere hora precisa sin depender de WiFi. |
| AS5600 | 2 | [Buscar AS5600 en UNIT](https://uelectronics.com/?s=AS5600&post_type=product) | Si se quiere medir angulo absoluto en ejes finales. |
| Sensor de corriente | 1 a 2 | [Buscar sensor de corriente en UNIT](https://uelectronics.com/?s=sensor+corriente&post_type=product) | Si se quieren detectar bloqueos o sobrecarga. |
| Paro de emergencia pequeno | 1 | [Buscar paro de emergencia en UNIT](https://uelectronics.com/?s=paro+emergencia&post_type=product) | Recomendado si se hacen pruebas prolongadas al Sol. |
| Sensor optico de cuatro cuadrantes | 1 | Por definir | Para version tipo peephole simplificado. |
| ESP32-CAM | 1 | [Buscar ESP32-CAM en UNIT](https://uelectronics.com/?s=ESP32-CAM&post_type=product) | Para registrar deriva del spot en pantalla. |

## Compra minima recomendada

Para empezar de forma barata:

1. 1 ESP32 DevKit.
2. 2 GM 25-370 con encoder 12 V 140 rpm.
3. 2 L298N o 2 BTS7960/IBT-2.
4. 1 fuente 12 V 3 A.
5. 1 XL4015.
6. 4 finales de carrera.
7. 4 rodamientos 608ZZ si se usan ejes de 8 mm.
8. 1 eje metalico de 8 mm.
9. Correa GT2 y 2 poleas pequenas de 4 mm, o pinones equivalentes.
10. Tornilleria M3/M4.
11. Espejo 20 cm x 20 cm.

## No comprar por ahora

| Componente | Motivo |
|---|---|
| Fuente 12 V 10 A | Sobredimensionada para primera version. |
| Drivers Cytron/Pololu | Excelentes, pero caros para el MVP. |
| Cople rigido UNIT 5x5/5x8/8x8 | No coincide con el eje de 4 mm del GM 25-370. |
| MX1508 | No conviene con motores de 12 V. |
| Driver de pasos A4988/DRV8825/TMC | No sirve para motores DC con escobillas; solo para motores a pasos. |
| Sensor optico avanzado | Mejor despues de validar movimiento y geometria. |
