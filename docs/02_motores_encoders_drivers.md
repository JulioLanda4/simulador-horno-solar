# Seleccion inicial de motores, encoders y drivers

## Criterio de seleccion

La maqueta debe parecerse a los sistemas reales del IER: motores DC con motoreductor, encoders y control por posicion. Por eso no se recomienda usar servos de hobby como solucion principal, aunque podrian servir para pruebas didacticas muy tempranas.

Para el primer prototipo funcional se busca:

- Compatibilidad con ESP32/Arduino.
- Motor DC con reductor metalico.
- Encoder incremental A/B.
- Velocidad baja o media, no alta.
- Suficiente torque para mover un espejo de 20 cm x 20 cm con bastidor impreso.
- Driver con margen de corriente para arranque y bloqueo momentaneo.
- Piezas faciles de conseguir o sustituir.

## Estimacion rapida de torque

El eje critico es elevacion. Si el espejo y el bastidor no quedan balanceados, el torque requerido puede crecer mucho.

Modelo simple:

```text
T = m * g * d
```

donde:

- T es torque en N m.
- m es masa del conjunto espejo + bastidor.
- g = 9.81 m/s2.
- d es distancia entre el centro de gravedad y el eje de elevacion.

Ejemplo:

```text
m = 0.40 kg
d = 0.05 m
T = 0.40 * 9.81 * 0.05 = 0.196 N m
```

En unidades comunes:

```text
1 kg cm = 0.098 N m
0.196 N m = 2.0 kg cm
```

Con margen por friccion, viento, holgura y aceleracion, conviene buscar al menos 3 a 5 veces ese torque. Para el eje de elevacion, el objetivo inicial razonable es un motorreductor capaz de entregar aproximadamente 6 a 10 kg cm o mas a baja velocidad, o balancear mecanicamente el eje para reducir la carga.

## Opcion recomendada para prototipo serio

### Motorreductor DC metalico tipo 37D / 37 mm con encoder

Uso recomendado:

- Eje de elevacion.
- Eje de acimut, si se quiere usar el mismo tipo de motor en ambos ejes.

Ventajas:

- Mas robusto que motores N20 o TT.
- Mejor margen de torque.
- Eje de salida mas util para acoplamientos, poleas o engranes.
- Existen versiones con encoder incremental de cuadratura.
- Hay variantes de 12 V y distintas relaciones de reduccion.

Criterio de busqueda:

```text
37D metal gearmotor encoder 12V 50RPM
37D metal gearmotor encoder 12V 100RPM
JGB37-520 encoder gear motor 12V
GB37-520 encoder motor 12V
```

Seleccion tentativa:

- 12 V.
- 30 a 100 RPM nominales en eje de salida.
- Encoder incremental A/B.
- Relacion de reduccion alta.
- Eje de salida de 6 mm o similar.

Comentario:

Para seguimiento solar, la velocidad no es el problema. Es preferible torque, repetibilidad y baja velocidad controlable. Una version de 30 a 60 RPM puede ser mas comoda que una de 200 RPM.

## Opcion intermedia

### Motorreductor DC metalico tipo 25D / 25 mm con encoder

Uso recomendado:

- Eje de acimut si la friccion es baja.
- Prototipo compacto.
- Pruebas iniciales de control con encoder.

Ventajas:

- Mas pequeno y ligero que 37D.
- Disponible con encoder.
- Suficiente si la montura esta bien balanceada y con baja friccion.

Riesgos:

- Puede quedarse corto en elevacion si el espejo queda desbalanceado.
- Menor margen ante viento o friccion.

Criterio de busqueda:

```text
25D metal gearmotor encoder 12V
25GA370 encoder motor 12V
```

## Opciones que no se recomiendan como base

### Motor TT con encoder

No se recomienda para este proyecto como solucion principal. Es barato y compatible con Arduino, pero tiene poca rigidez, baja precision mecanica y mucha holgura para una maqueta experimental de seguimiento solar.

### Servo de hobby

No se recomienda como arquitectura principal porque no representa bien los sistemas reales del IER y oculta el problema de lectura de encoder, homing y conversion de cuentas a angulo.

### Motor paso a paso

Puede funcionar tecnicamente, pero se aleja de la arquitectura real descrita: motores DC con motoreductores y encoders.

## Encoders

### Encoder integrado en motor

Es la opcion mas directa para el primer prototipo.

Ventajas:

- Facil de comprar junto con el motor.
- Salidas A/B compatibles con interrupciones del ESP32.
- Permite contar posicion relativa.

Limitaciones:

- Si el encoder esta en el eje del motor, mide antes del reductor.
- No mide directamente holgura o backlash en el eje final.
- Requiere homing para conocer posicion absoluta.

Conversion general:

```text
theta = theta_home + s * 360 * (C - C_home) / (4 * PPR * G)
```

donde:

- C es la cuenta actual.
- C_home es la cuenta en home.
- PPR son pulsos por revolucion del encoder.
- G es la relacion total de transmision.
- s es el signo de montaje.

### Sensor magnetico absoluto AS5600 en eje final

Puede ser una mejora importante para medir directamente el eje de acimut o elevacion.

Ventajas:

- Mide angulo absoluto.
- Puede colocarse en el eje final.
- Reduce dependencia del homing para conocer posicion angular.

Limitaciones:

- Rango de 0 a 360 grados.
- Requiere montaje mecanico cuidadoso del iman.
- No sustituye finales de carrera de seguridad.

Uso recomendado:

- Segunda version o version experimental de comparacion.
- Medicion directa del eje final para cuantificar backlash.

## Drivers de motor

### Para motores 37D

Se recomienda usar drivers con margen de corriente mayor que los drivers pequenos tipicos.

Opciones a evaluar:

- DRV8871 / DRV8876.
- VNH5019.
- BTS7960, si el motor elegido tiene corriente de bloqueo alta.
- Cytron MD10C o equivalente si se quiere margen y simplicidad.

No se recomienda elegir el driver solo por corriente nominal. Hay que revisar corriente de arranque y corriente de bloqueo del motor elegido.

### Para motores 25D

Opciones posibles:

- DRV8833 solo si el motor es pequeno y la corriente de bloqueo entra en margen.
- TB6612FNG solo para motores pequenos.
- DRV8871 / DRV8876 como opcion con mejor margen.

Para este proyecto, TB6612FNG puede quedar corto si se usan motores 37D o si hay carga mecanica significativa.

## Recomendacion inicial

Para evitar redisenos tempranos:

- Usar dos motorreductores DC metalicos 37D con encoder, 12 V, baja velocidad.
- Usar un driver por eje con margen de corriente real.
- Incluir finales de carrera o sensores Hall para home y seguridad.
- Disenar el eje de elevacion balanceado o con contrapeso ajustable.
- Dejar espacio mecanico para agregar un AS5600 o sensor absoluto en el eje final.

## Fuentes web consultadas

- Pololu, categoria 37D Metal Gearmotors: https://www.pololu.com/category/116/37d-metal-gearmotors
- Pololu, categoria 25D Metal Gearmotors: https://www.pololu.com/category/115/25d-metal-gearmotors
- Pololu, VNH5019 Motor Driver Carrier: https://www.pololu.com/product/1451
- Pololu, DRV8876 Motor Driver Carrier: https://www.pololu.com/product/4036
- DFRobot, Metal DC Geared Motor with Encoder: https://www.dfrobot.com/product-1617.html
- ams OSRAM, AS5600 position sensor: https://ams-osram.com/products/sensor-solutions/position-sensors/ams-as5600-position-sensor

## Pendientes de compra

- Buscar disponibilidad en Mexico: Mercado Libre, Amazon Mexico, tiendas de robotica locales y proveedores educativos.
- Confirmar torque nominal, torque de paro, RPM, corriente sin carga y corriente de bloqueo.
- Confirmar PPR real y si el encoder opera a 3.3 V o 5 V.
- Confirmar dimensiones para CAD.
- Confirmar tipo de eje de salida y acoplamiento.
