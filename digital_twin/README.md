# Gemelo digital del mini horno / mini heliostato

Subproyecto en Python para simular el panel de control del mini horno solar IER y el mini heliostato impreso.

**Version estable actual: 2.0 (`v2.0.0`).**

## Que incluye

- Interfaz grafica estilo LabVIEW con modo automatico/manual, home, seguimiento, target `RX/RY/RZ`, offsets, contadores y estado de motores.
- Switches ON/OFF en lugar de casillas de seleccion.
- Selector excluyente entre `Tiempo real` y `Fecha simulada` para evaluar una
  posicion solar concreta sin combinar interruptores ambiguos.
- Zona horaria UTC editable e independiente de la longitud. El perfil
  `Minihorno IER` usa `UTC-6`; esta zona se aplica de forma coherente a D&B,
  REDA y SPA/PVLIB.
- El programa abre detenido en `Configuracion`: primero se eligen el origen
  temporal, los parametros y el modo de movimiento; la sesion comienza solo al
  pulsar `INICIAR TIEMPO REAL` o `INICIAR FECHA SIMULADA`.
- En modo Automatico, el heliostato se mueve fluidamente hacia la orientacion calculada para la fecha/hora activa.
- Al cambiar desde Manual o Home hacia Automatico, conserva la posicion actual
  y recorre gradualmente el nuevo objetivo; las actualizaciones periodicas de
  seguimiento tampoco teletransportan los ejes.
- Perillas arrastrables para la velocidad de los motores.
- Selector de modo con estado visible: Automatico, Manual y Home.
- Al abrir, el heliostato aparece en Manual y Home, pero los calculos, el reloj
  simulado y los motores permanecen detenidos hasta iniciar la sesion.
- En modo Manual, controles de direccion por eje para mover acimut y elevacion con la velocidad indicada por cada perilla.
- Home mueve fluidamente el heliostato hacia acimut 0 grados y elevacion 90 grados. Solo el arranque inicia ya colocado en Home.
- `RX`, `RY`, `RZ`, ubicacion y metodo solar estan en la pestana inferior
  `Calibracion y perfiles`.
- Valores iniciales: `RX=0`, `RY=5.55`, `RZ=-0.4`, cercanos a la geometria real documentada `R=(0, 5.55, -0.35) m`.
- Campo `Peralte Helio` usado como conversion entre la lectura mecanica del eje
  de elevacion y la normal optica. No desplaza por si solo el spot ideal.
- Panel izquierdo con scroll y secciones desplegables; cada grupo puede abrirse
  solo cuando el experimento lo necesita sin perder ninguna opcion editable.
- La geometria, activacion, rayos y mapa de intensidad de las facetas se
  manipulan desde una sola seccion desplegable.
- El switch `Seguimiento solar` forma parte de las opciones del modo Automatico.
- Modelo solar aproximado tipo Duffie-Beckman, canal `REDA` de comparacion simulada y opcion `SPA/PVLIB` si ese paquete esta instalado en el Python usado.
- Geometria del heliostato con convencion del proyecto: `+x` oeste, `+y` sur, `+z` cenit.
- Dinamica simulada de motores, PWM, encoders y tolerancia `cdr`.
- El campo de LabVIEW `Consideracion (+/- cdr)` aparece con ese nombre y define la ventana angular de parada.
- Banner de estado operacional: manual/listo, movimiento manual, moviendo, en objetivo, en home y alertas.
- Validaciones visibles para sol bajo horizonte, fecha invalida, limites mecanicos y motores apagados con error angular.
- Alertas separadas por severidad: informativas, advertencias y criticas.
- Pestana inferior `Calibracion y perfiles` para introducir las dimensiones de
  un heliostato y concentrador propios, limites por eje, conteos por grado y
  velocidad maxima de motores.
- Perfil `Minihorno IER` precargado para restaurar de una vez su ubicacion,
  target, dimensiones, movimiento, facetas y parametros del spot. Al editar
  una medida se activa automaticamente `Diseno personalizado`.
- Las dimensiones se introducen en metros fisicos completos. En el perfil IER,
  por ejemplo, el lado del espejo es `2.0 m`; el dibujo 3D ajusta su escala de
  pantalla sin modificar esa medida.
- `RX/RY/RZ` se interpretan desde el centro optico del espejo. El valor
  `RZ=-0.40 m` deja el concentrador 0.40 m debajo del centro del heliostato,
  no debajo del nivel del suelo.
- Selector de vista 3D: isometrica, frontal, lateral, superior y libre.
- En la vista libre, el boton derecho del mouse rota la escena en cualquier
  direccion y el boton izquierdo desplaza el encuadre. `Restablecer vista libre`
  recupera tanto la orientacion como la posicion inicial.
- El heliostato y el concentrador se ordenan por profundidad al rotar, evitando
  superposiciones artificiales desde la parte posterior. El orden conserva la
  secuencia interna de poligonos y usa histeresis cerca de profundidades iguales
  para impedir parpadeos; rejilla y guias permanecen en una capa de suelo.
- Ventana 3D en tiempo real con heliostato, base abierta, soporte central,
  bastidor reticulado, riel, mesa/receptor, concentrador de 18 facetas, vector
  solar, normal y rayo reflejado. La orientacion XYZ se presenta en una tarjeta
  fija con un indicador de ejes que gira junto con la camara, evitando etiquetas
  amontonadas y mostrando la direccion visible de cada eje.
- La base del heliostato se representa como bastidor abierto. Los arcos de
  limites de acimut/elevacion se ocultan por defecto y pueden mostrarse con
  `Guias de limites mecanicos` cuando se requiera diagnosticar el recorrido.
- Cono visual de incertidumbre basado en `cdr`.
- Vista combinada de pantalla/spot y comparacion ideal, con error y corregida.
- En esa vista, la cruz gris identifica el centro nominal y los puntos de color
  representan realmente los casos Ideal, Con error y Corregido. Los avisos de
  fuera de escala se mantienen dentro del area de la grafica.
- Vista de trayectoria solar diaria con marca de hora activa.
- Vista combinada `Deriva y correccion` con errores u/v/radial, tiempo desde la
  ultima actualizacion, comparacion sin/con correccion y compensacion AZ/EL.
- Cada una de sus seis graficas puede ampliarse con un clic y regresar con el
  boton `VOLVER A 6 GRAFICAS`.
- Vista unica `Facetas / rayos / intensidad`; el mapa termico aparece como
  fondo del plano receptor/foco y conserva encima los impactos individuales.
- Tanto el esquema de rayos como el plano receptor/intensidad pueden ampliarse
  con un clic y regresar con `VOLVER A VISTA GENERAL`.
- Vista de diagnostico con barras de error angular, error total del spot, tabla de vectores `S/R/N` y target crudo.
- Captura interna de muestras de la sesion para replay.
- Exportacion CSV con tiempo, modo, estado, angulos, targets, error angular, spot, vector solar y parametros principales.
- Pestanas inferiores compactas para status, eventos/validaciones y calibracion.
- Panel de operacion fijo con estado `Configuracion`, `En ejecucion`, `Pausado`
  o `Replay`; accion principal contextual para iniciar/pausar/reanudar, retorno
  a configuracion, Home, CSV, reproduccion, regreso a simulacion y manual.
- Los controles se habilitan segun el contexto: la fecha simulada solo se edita
  antes de iniciar, los motores manuales requieren una sesion activa y Replay
  requiere que la simulacion este pausada y existan muestras.
- Recuadro permanente de fecha y hora activa, origen temporal, estado del reloj
  y multiplicador de tiempo, junto a los controles globales.
- Manual de usuario integrado con indice lateral: inicio rapido, mapa de la
  interfaz, modos y reloj, seguimiento, errores, correccion, facetas, cada
  vista grafica, panel inferior, calibracion, CSV/replay, experimentos guiados
  y solucion de problemas. Incluye ademas la referencia tecnica sobre flujo,
  geometria optica, metodos solares, motores, formulas, unidades, rendimiento
  y limitaciones reales del programa.
- Las ecuaciones se muestran en tarjetas matematicas compactas, con simbolos,
  subindices, superindices, productos punto y fracciones apiladas legibles.
- Los campos numericos invalidos se resaltan sin descartar el ultimo estado valido.

## Como ejecutar

Desde la raiz del proyecto:

```cmd
digital_twin\run_digital_twin.bat
```

Tambien puedes abrir con doble clic:

```text
digital_twin\run_digital_twin.bat
```

Puedes comprobar el lanzador sin abrir la interfaz:

```cmd
digital_twin\run_digital_twin.bat --self-test
```

En PowerShell:

```powershell
python digital_twin\run_digital_twin.py
```

En esta maquina tambien funciona el Python incluido con FreeCAD:

```powershell
& 'C:\Program Files\FreeCAD 0.21\bin\python.exe' digital_twin\run_digital_twin.py
```

En `cmd.exe` el comando equivalente es:

```cmd
"C:\Program Files\FreeCAD 0.21\bin\python.exe" digital_twin\run_digital_twin.py
```

Si `python` da problemas en esta maquina, el Python incluido con Codex sirve para pruebas de modelo, pero su Tcl/Tk puede no abrir ventanas:

```powershell
& 'C:\Users\landa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' digital_twin\run_digital_twin.py
```

Prueba sin abrir interfaz:

```powershell
& 'C:\Users\landa\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' digital_twin\run_digital_twin.py --self-test
```

## Rendimiento de la interfaz

El selector `Calidad grafica` modifica solamente la frecuencia de dibujo; no
cambia el paso temporal ni las ecuaciones del simulador:

- `Rapida`: limita el dibujo hasta aproximadamente 5 FPS.
- `Equilibrada`: limita el dibujo hasta aproximadamente 12.5 FPS.
- `Alta`: dibuja en cada ciclo del modelo.

La interfaz redibuja unicamente la pestana visible. La geometria de facetas y
el mapa de intensidad se reutilizan mientras sus parametros no cambien. El
panel de status muestra FPS, tiempo de ciclo y tiempo de dibujo para comparar
los perfiles sin herramientas externas.

La resolucion del mapa acepta cualquier impar entre 21 y 121; los valores
pares se ajustan al siguiente impar al terminar la edicion. La informacion
conceptual del flujo se abre con `ACERCA DEL MODELO`, fuera de las vistas de
trabajo, para que posteriormente pueda integrarse al manual de usuario.

## Notas importantes

- No controla hardware fisico.
- No abre puerto serial.
- No usa GPIO.
- El canal `REDA` no es una implementacion astronomica completa; queda como modo de comparacion para el gemelo.
- La opcion `SPA/PVLIB` usa `pvlib.solarposition.spa_python` si esta disponible. Si no esta instalado, la interfaz lo indica y usa `REDA` aproximado como respaldo.
- El modelo de motor es discreto y emula la logica vista en el VI: comparar angulo real contra objetivo con tolerancia `cdr`, activar direccion y detener dentro de la ventana.
- Las exportaciones CSV se proponen en `digital_twin/logs/`.
- En el gemelo, los conteos de encoder son una escala interna de simulacion. No representan todavia un encoder fisico medido.
