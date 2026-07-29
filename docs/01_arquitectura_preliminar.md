# Arquitectura preliminar del mini heliostato impreso

## Objetivo

Disenar y construir una maqueta experimental de heliostato de aproximadamente 20 cm x 20 cm, impresa en 3D y controlada con electronica compatible con ESP32/Arduino. El sistema debe funcionar con Sol real y debe conservar, a escala, la logica de operacion de los sistemas solares del IER-UNAM.

## Criterio de referencia

- HoSIER: referencia de arquitectura de sistema real.
- Mini horno solar: referencia geometrica inicial y referencia visual de la montura.

El HoSIER aporta la estructura de modos y subsistemas: heliostato plano, seguimiento en acimut y elevacion, home, modo manual, modo seguimiento, modo target, finales de carrera y correccion optica de deriva.

El mini horno solar aporta una geometria mas compatible con la maqueta: heliostato plano de dos ejes, concentrador o foco fijo, convencion +x oeste, +y sur, +z cenit, y vector preliminar heliostato-foco R = (0, 5.55, -0.35) m.

## Sistema fisico propuesto

La maqueta debe representar:

- Heliostato plano exterior de dos ejes.
- Espejo aproximado de 20 cm x 20 cm.
- Montura azimut-elevacion.
- Base fija con eje vertical de acimut.
- Bastidor posterior reticulado o semi-reticulado, inspirado en las fotografias del mini horno.
- Eje horizontal de elevacion atravesando o soportando el bastidor.
- Motorreductores DC con encoders.
- Finales de carrera o sensores de referencia para homing.
- Receptor sobre riel, usable como foco experimental y como pantalla de validacion.

## Receptor movil

El receptor sobre riel debe poder operar en dos modos fisicos:

1. Foco experimental:
   - El receptor representa el punto objetivo real.
   - El rayo reflejado debe caer sobre ese punto.
   - Puede alojar una placa, sensor de irradiancia, sensor de temperatura o blanco pequeno.

2. Pantalla de validacion:
   - El receptor funciona como pantalla blanca o cuadriculada.
   - Sirve para medir error de apuntamiento.
   - Permite comparar posicion esperada contra posicion real del spot.

La misma pieza puede aceptar insertos intercambiables: pantalla blanca, cuadricula, sensor de cuatro cuadrantes o receptor termico pequeno.

## Control de movimiento

No se adopta PID como requisito base. El control inicial debe parecerse mas a una logica industrial discreta:

- Homing por eje.
- Lectura de encoder.
- Conversion de cuentas a angulo.
- Movimiento hacia consigna angular.
- Reduccion de velocidad cerca del objetivo si el driver lo permite.
- Parada al entrar en una ventana de tolerancia.
- Correccion por backlash mediante aproximacion desde direccion conocida.
- Limites de software.
- Finales de carrera fisicos.
- Modo seguro ante error de encoder o limite.

La consigna angular proviene del calculo geometrico del heliostato:

```text
vector solar -> vector hacia receptor/foco -> normal ideal -> angulos de acimut/elevacion
```

## Modos de operacion

### Home

Busca referencias mecanicas de cada eje y define cero de encoder.

### Manual

Permite mover acimut y elevacion desde interfaz local, botones o comandos seriales. Es necesario para montaje, prueba y calibracion.

### Target

Mueve el heliostato a una orientacion calculada para un receptor/foco definido, sin actualizar continuamente con el Sol.

### Seguimiento

Calcula periodicamente la posicion solar y actualiza la orientacion del espejo para mantener el rayo reflejado sobre el receptor.

### Validacion optica

Usa la pantalla de validacion o un sensor en receptor para medir la deriva del spot y registrar error horizontal/vertical.

## Geometria base

Convencion:

- +x hacia el oeste.
- +y hacia el sur.
- +z hacia el cenit.
- Origen en el centro de rotacion del heliostato.

Para el mini horno real:

```text
R_real = (0, 5.55, -0.35) m
|R_real| = 5.561 m
```

Si el espejo de maqueta es de 0.20 m y se toma como referencia un heliostato real equivalente de 2.37 m por lado:

```text
lambda = 0.20 / 2.37 = 0.0844
R_maqueta = lambda * R_real = (0, 0.468, -0.030) m
```

Esto sugiere un receptor/foco inicial a aproximadamente 47 cm delante del heliostato y 3 cm por debajo del centro de rotacion. Ese valor debe tratarse como punto de partida, no como dimension final.

## Electronica propuesta

- Controlador principal: ESP32.
- Motores: DC con motoreductor metalico y encoder incremental A/B.
- Drivers: puente H con margen de corriente suficiente para arranque y bloqueo momentaneo.
- Sensores de referencia: microswitch, sensor Hall o sensor inductivo miniatura.
- Alimentacion: fuente separada para motores y regulacion limpia para logica.
- Interfaz: web local o serial para configuracion, pruebas y registro.

## Riesgos tecnicos principales

- Backlash de reductores y transmisiones.
- Flexion de piezas impresas en 3D.
- Desbalance del eje de elevacion.
- Resolucion angular real menor que la resolucion teorica del encoder.
- Error de cero mecanico.
- Desalineacion entre eje de acimut, eje de elevacion y plano del espejo.
- Viento y vibracion.
- Saturacion o dano por concentracion solar si se usan superficies muy reflectantes.

## Pendientes antes del CAD

- Definir si la maqueta replica visualmente mas al HoSIER o al mini horno.
- Estimar masa del espejo y bastidor.
- Definir material del espejo.
- Definir si el eje de elevacion tendra contrapesos.
- Elegir motorreductores y drivers.
- Definir rango angular por eje.
- Definir tolerancia de apuntamiento deseada en pantalla.
- Definir dimensiones del riel del receptor.
