# Gemelo digital del mini horno / mini heliostato

Subproyecto en Python para simular el panel de control del mini horno solar IER y el mini heliostato impreso.

## Que incluye

- Interfaz grafica estilo LabVIEW con modo automatico/manual, home, seguimiento, target `RX/RY/RZ`, offsets, contadores y estado de motores.
- Switches ON/OFF en lugar de casillas de seleccion.
- Fecha y hora especificas para evaluar una posicion solar concreta.
- `Fecha especifica` ON usa la fecha/hora escrita; OFF usa la fecha y hora actuales.
- En modo Automatico, el heliostato se mueve fluidamente hacia la orientacion calculada para la fecha/hora activa.
- Perillas arrastrables para la velocidad de los motores.
- Selector de modo con estado visible: Automatico, Manual y Home.
- Al iniciar, el programa arranca siempre en Manual y en Home.
- En modo Manual, controles de direccion por eje para mover acimut y elevacion con la velocidad indicada por cada perilla.
- Home mueve fluidamente el heliostato hacia acimut 0 grados y elevacion 90 grados. Solo el arranque inicia ya colocado en Home.
- `RX`, `RY` y `RZ` estan en el bloque `Concentrador / Target`.
- Valores iniciales: `RX=0`, `RY=5.55`, `RZ=-0.4`, cercanos a la geometria real documentada `R=(0, 5.55, -0.35) m`.
- Campo `Peralte Helio` aplicado a la elevacion/normal del heliostato.
- Panel izquierdo con scroll para acceder a todo el control.
- Modelo solar aproximado tipo Duffie-Beckman, canal `REDA` de comparacion simulada y opcion `SPA/PVLIB` si ese paquete esta instalado en el Python usado.
- Geometria del heliostato con convencion del proyecto: `+x` oeste, `+y` sur, `+z` cenit.
- Dinamica simulada de motores, PWM, encoders y tolerancia `cdr`.
- El campo de LabVIEW `Consideracion (+/- cdr)` aparece con ese nombre y define la ventana angular de parada.
- Banner de estado operacional: manual/listo, movimiento manual, moviendo, en objetivo, en home y alertas.
- Validaciones visibles para sol bajo horizonte, fecha invalida, limites mecanicos y motores apagados con error angular.
- Alertas separadas por severidad: informativas, advertencias y criticas.
- Panel de calibracion para geometria visual, limites por eje, conteos por grado y velocidad maxima de motores.
- El bloque de calibracion muestra valores en metros, grados y grados/segundo; no son comandos fisicos, solo parametros del gemelo.
- Selector de vista 3D: isometrica, frontal, lateral y superior.
- Ventana 3D en tiempo real con heliostato, base inspirada en las fotos, horquilla, bastidor reticulado, arcos de limite, riel, mesa/receptor, concentrador de 18 facetas, vector solar, normal y rayo reflejado.
- Cono visual de incertidumbre basado en `cdr`.
- Vista de pantalla/concentrador para ver directamente donde cae el spot.
- Vista de trayectoria solar diaria con marca de hora activa.
- Vista de diagnostico con barras de error angular, error total del spot, tabla de vectores `S/R/N` y target crudo.
- Captura interna de muestras de la sesion para replay.
- Exportacion CSV con tiempo, modo, estado, angulos, targets, error angular, spot, vector solar y parametros principales.
- Bitacora de eventos recientes para cambios de modo, jog manual, pausa, home y alertas.

## Como ejecutar

Desde la raiz del proyecto:

```cmd
digital_twin\run_digital_twin.bat
```

Tambien puedes abrir con doble clic:

```text
digital_twin\run_digital_twin.bat
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

## Notas importantes

- No controla hardware fisico.
- No abre puerto serial.
- No usa GPIO.
- El canal `REDA` no es una implementacion astronomica completa; queda como modo de comparacion para el gemelo.
- La opcion `SPA/PVLIB` usa `pvlib.solarposition.spa_python` si esta disponible. Si no esta instalado, la interfaz lo indica y usa `REDA` aproximado como respaldo.
- El modelo de motor es discreto y emula la logica vista en el VI: comparar angulo real contra objetivo con tolerancia `cdr`, activar direccion y detener dentro de la ventana.
- Las exportaciones CSV se proponen en `digital_twin/logs/`.
- En el gemelo, los conteos de encoder son una escala interna de simulacion. No representan todavia un encoder fisico medido.
