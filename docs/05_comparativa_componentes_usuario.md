# Comparativa de componentes propuestos

Fecha de revision: 2026-07-02.

Objetivo: evaluar las opciones propuestas para completar la lista de materiales del mini heliostato impreso.

## Tabla comparativa

| Componente | Enlace | Datos relevantes | Evaluacion para el proyecto | Veredicto |
|---|---|---|---|---|
| Doble Puente H MX1508 | [UNIT Electronics](https://uelectronics.com/producto/doble-puente-h/) | 2 canales; motores 2 a 9 V; logica 1.8 a 7 V; corriente nominal 0.8 A por canal; pico 1.5 A. | No es adecuado para los GM 25-370 de 12 V. El voltaje maximo de motor es bajo para nuestra arquitectura y la corriente de pico es limitada. | No usar en ejes principales. |
| XL4015 convertidor DC-DC buck | [UNIT Electronics](https://uelectronics.com/producto/xl4015-convertidor-dc-dc-buck-reductor/) | Entrada 8 a 34 V; salida 1.25 a 32 V; hasta 5 A max; 75 W; eficiencia reportada 96%; sin proteccion contra polaridad inversa. | Si sirve para bajar de 12 V a 5 V para ESP32, sensores y logica. Debe ajustarse con multimetro antes de conectar la electronica. | Recomendado. |
| Fuente AC-DC 5 V / 12 V / 24 V | [UNIT Electronics](https://uelectronics.com/producto/fuente-de-alimentacion-ac-dc-de-5v-12v-24v/) | Versiones: 5 V 700 mA, 12 V 2 A, 24 V 4 A. | La version 12 V 2 A queda corta para dos motores con picos de arranque. Puede servir para pruebas ligeras o solo logica, no como fuente principal de motores. | No como fuente principal. |
| Fuente conmutada 12 V 3 A | [UNIT Electronics](https://uelectronics.com/producto/fuente-conmutada-12v-3a/) | 12 V; 3 A; 36 W; proteccion contra cortocircuito, sobrecarga y sobretension. | Mejor que la de 12 V 2 A, pero sigue siendo una opcion justa. Puede servir si se mueve un eje a la vez y se evita bloqueo. Idealmente buscar 12 V 5 A o mas. En la ficha revisada aparecia sin existencias. | Aceptable para pruebas, preferir 5 A. |
| Interruptor fin de carrera 125 V 1 A | [UNIT Electronics](https://uelectronics.com/producto/interruptor-fin-de-carrera-125v-1a-limit-switch/) | Microswitch mecanico tipo fin de carrera. | Sirve para home y limites de seguridad de baja tension. Debe cablearse como senal al ESP32, no como corte principal de potencia. Usar 4: home y limite por eje, o mas si se desean limites dobles. | Recomendado. |
| Filamento PETG disponible | Material existente | PETG disponible en poca cantidad. | Usarlo para piezas estructurales, soportes de motor, soportes de rodamiento, base expuesta al Sol y receptor. | Recomendado para piezas finales. |
| Filamento PLA disponible | Material existente | PLA disponible en buena cantidad. | Usarlo para prototipos, plantillas, cubiertas, pruebas de encaje y piezas sin carga ni exposicion al Sol. No usar como material final estructural al exterior. | Solo prototipos o piezas no criticas. |
| Rodamiento 608ZZ-7 | [UNIT Electronics](https://uelectronics.com/producto/608zz-7-rodamiento-tipo-balero-de-8-x-22-x-7-mm/) | ID 8 mm; OD 22 mm; ancho 7 mm; doble blindaje metalico ZZ. | Si sirve para ejes de 8 mm. Es robusto y facil de alojar en piezas impresas, pero obliga a disenar los ejes principales de 8 mm. | Recomendado si usamos ejes de 8 mm. |
| Cople rigido de aluminio | [UNIT Electronics](https://uelectronics.com/producto/cople-rigido-de-aluminio/) | Modelos 5x5 mm, 5x8 mm y 8x8 mm; longitud 25 mm; diametro exterior 14 mm; 4 prisioneros M4. | No coincide directamente con el eje D de 4 mm del GM 25-370. Serviria para ejes 5/8 mm, pero no para motor 4 mm sin adaptador. Ademas, al ser rigido exige buena alineacion. | No comprar para GM 25-370 salvo que se cambie el eje/acople. |

## Conclusiones

1. El **MX1508 no debe usarse para los ejes principales**. Es barato, pero esta dimensionado para motores pequenos de bajo voltaje. Para los GM 25-370 de 12 V conviene un driver con margen mayor: DRV8871, DRV8876, BTS7960 pequeno, VNH5019, Cytron MD10C o equivalente.
2. El **XL4015 si sirve** como buck 12 V a 5 V, siempre que se ajuste antes de conectar el ESP32.
3. La **fuente de 12 V 3 A puede servir para pruebas**, pero la compra principal deberia apuntar a 12 V 5 A o mas si se moveran dos ejes o si habra picos de arranque.
4. Los **finales de carrera mecanicos sirven** para home y limites. No sustituyen un paro de emergencia ni un corte de potencia.
5. Los **608ZZ son buena eleccion** si se decide que los ejes principales seran de 8 mm.
6. El **cople rigido listado no coincide con el motor GM 25-370**, porque las opciones publicadas son 5x5, 5x8 y 8x8 mm. Para el GM 25-370 se debe buscar cople 4x8 mm, cople flexible 4x8 mm, polea con bore de 4 mm o un adaptador impreso/maquinado.

## Lista ajustada de compra inmediata

| Material | Cantidad | Decision |
|---|---:|---|
| GM 25-370 con encoder 12 V 140 rpm | 2 | Comprar para ejes principales. |
| Driver puente H alternativo al MX1508 | 2 | Buscar DRV887x, VNH5019, BTS7960 o Cytron MD10C. |
| XL4015 buck | 1 | Comprar. |
| Fuente 12 V 5 A o mas | 1 | Buscar alternativa; 12 V 3 A solo para pruebas. |
| Finales de carrera | 4 | Comprar. |
| Rodamientos 608ZZ | 4 a 8 | Comprar si se disenan ejes de 8 mm. |
| Coples 4x8 mm o poleas de 4 mm | 2 | Buscar otra opcion; no comprar el cople listado para los GM 25-370. |
| PETG | Segun inventario | Usar para piezas estructurales; comprar mas si no alcanza. |
| PLA | Ya disponible | Usar solo para prototipos y piezas no criticas. |
