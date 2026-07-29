# Comparativa de motores propuestos

Fecha de revision: 2026-07-02.

Objetivo: evaluar las opciones propuestas para el mini heliostato impreso de 20 cm x 20 cm, considerando uso con ESP32/Arduino, motor DC con reductor, posibilidad de lectura por encoder, torque suficiente, baja velocidad y semejanza con la arquitectura real de los sistemas del IER.

## Criterios de evaluacion

- Debe mover un eje de acimut o elevacion de una maqueta con espejo de 20 cm x 20 cm.
- Se prefiere motor DC con reductor metalico.
- Se prefiere encoder incremental integrado A/B.
- Para elevacion se requiere mas margen de torque que para acimut.
- Para seguimiento solar, una velocidad menor y controlable es preferible a muchas RPM.
- Si no tiene encoder, solo puede servir agregando encoder externo, sensor magnetico absoluto o mecanismo adicional de referencia.

## Tabla comparativa

| Opcion | Enlace de compra | Datos relevantes de ficha | Encoder | Evaluacion para este proyecto | Veredicto |
|---|---|---:|---:|---|---|
| JGB37-520 6V 425/800 RPM | [UNIT Electronics](https://uelectronics.com/producto/jgb37-520-motorreductor-6v-425-rpm-_-800-rpm/) | 6 V; 425 u 800 rpm; torque nominal 0.18 kgf cm en 425 rpm y 0.1 kgf cm en 800 rpm; torque detenido 0.72 y 0.4 kgf cm; corriente detenido 2 A. | No indicado. | Aunque el formato 37 mm parece atractivo, esta version es demasiado rapida y con torque muy bajo. No alcanza para elevacion y tampoco conviene para acimut salvo con reduccion mecanica adicional. | No recomendado. |
| GA12-N20 3V/6V/12V | [UNIT Electronics](https://uelectronics.com/producto/ga12-n20-motorreductor-dc-3v-6v-12v/) | Versiones 12 V de 30, 100, 200, 300 y 500 rpm; la de 30 rpm declara 2.5 kg cm; eje D de 3 mm; cuerpo muy pequeno. | No indicado. | La version 12 V 30 rpm podria mover cargas pequenas si el eje esta muy balanceado, pero el eje de 3 mm y el cuerpo N20 son debiles para una montura experimental. Mejor para pruebas, riel del receptor o mecanismos auxiliares. | Solo auxiliar o prototipo liviano. |
| JGA25-370 12/60/130/620 RPM | [UNIT Electronics](https://uelectronics.com/producto/motorreductores-jga25-370-de-12-60-130-620-rpm/) | 25 mm x 70 mm; eje D de 4 mm; versiones 6 V 12 rpm, 6 V 60 rpm, 12 V 130 rpm y 12 V 620 rpm; torque de parada: >35, 15, 8 y 2.2 kg cm respectivamente; corriente pico hasta 2.2 A. | No indicado. | Mecanicamente es mas serio que N20. La version 12 rpm 6 V o 60 rpm 6 V tendria buen torque, pero sin encoder integrado no cumple la arquitectura base. Podria servir si agregamos encoder externo en el eje final. | Posible con encoder externo. |
| Motorreductor TT engranajes metal 1:90 | [UNIT Electronics](https://uelectronics.com/producto/motorreductor-tt-engranajes-de-metal-190/) | 6 V; reduccion 1:90; velocidad sin carga aprox. 110 rpm; torque nominal 0.3 Nm; peso 39 g. | No indicado. | Es barato y facil de usar, pero la carcasa TT tiene poca rigidez y precision. Puede servir para una maqueta didactica, no para la version experimental que busca parecerse a los sistemas reales. | No recomendado para ejes principales. |
| GM 25-370 con encoder 12V 140/330 RPM | [UNIT Electronics](https://uelectronics.com/producto/gm-25-370-motor-con-encoder-12v-dc-140rpm-330rpm/) | 12 V; engranes metalicos; encoder Hall incremental doble fase 3.3-5 V; 11 PPR base; eje D de 4 mm; 140 rpm: 4.3 kg cm nominal, 8.5 kg cm stall, 493.9 PPR salida; 330 rpm: 5.8 kg cm nominal, 12 kg cm stall, 341.2 PPR salida. | Si. | Es la opcion mas alineada con el proyecto: DC, reductor metalico, encoder A/B compatible con ESP32 y torque razonable. La version 140 rpm es preferible por mayor reduccion y mejor resolucion de salida; aun podria requerir transmision adicional o eje balanceado. | Recomendado, especialmente 140 rpm. |
| Steren motor reductor metalico eje D 12 V | [Steren](https://www.steren.com.mx/motor-reductor-metalico-con-eje-tipo-d-12-vcc.html) | 12 V; 62 rpm; torque 4.9 kgf cm; eje D de 3.9 mm; dimensiones 25 x 25 x 65 mm. | No. | Buen candidato mecanico por velocidad y torque, pero no tiene encoder. Podria servir si se agrega AS5600 u otro encoder externo al eje final. Es practico por disponibilidad, pero no cumple solo con la arquitectura de control por encoder. | Posible con encoder externo. |

## Ranking preliminar

1. GM 25-370 con encoder 12 V 140 rpm.
2. Steren 12 V 62 rpm, solo si se agrega encoder externo.
3. JGA25-370 6 V 60 rpm o 6 V 12 rpm, solo si se agrega encoder externo.
4. GA12-N20 12 V 30 rpm, solo para receptor/riel o prototipo liviano.
5. TT metal 1:90, solo para maqueta didactica sin precision.
6. JGB37-520 425/800 rpm, no recomendado para esta maqueta.

## Recomendacion

Para los ejes principales, la mejor opcion de la lista es el **GM 25-370 con encoder 12 V en version 140 rpm**. Tiene encoder incremental compatible con 3.3 V a 5 V, engranes metalicos, torque nominal razonable y resolucion de salida suficiente para empezar.

Para elevacion, el diseno mecanico debe incluir balanceo o contrapeso. Si el espejo queda desbalanceado, incluso un motor con 4.3 kg cm nominal puede trabajar al limite. El eje de elevacion debe disenarse para que el centro de gravedad quede lo mas cerca posible del eje.

Si se decide usar el motor de Steren o el JGA25-370 sin encoder, hay que agregar medicion angular externa. La opcion mas limpia seria un sensor magnetico absoluto en el eje final, por ejemplo AS5600, mas finales de carrera para seguridad.

## Driver sugerido por opcion

| Opcion | Driver minimo razonable |
|---|---|
| GM 25-370 140 rpm | DRV8871, DRV8876, Cytron MD10C o equivalente. Evitar TB6612FNG si se trabaja cerca de bloqueo. |
| GM 25-370 330 rpm | Driver con margen de al menos 3 A por eje. |
| JGA25-370 60/130 rpm | Driver con margen de 2.5 A o mas. |
| Steren 12 V 62 rpm | Falta corriente de bloqueo real; elegir driver con margen, no asumir 32 mA como corriente de carga. |
| GA12-N20 | DRV8833/TB6612FNG solo si la corriente real lo permite; mejor DRV887x para margen. |
| TT metal | TB6612FNG podria bastar, pero no se recomienda para ejes principales. |
