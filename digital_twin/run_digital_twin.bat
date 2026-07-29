@echo off
setlocal

set "PROJECT_DIR=%~dp0.."
set "FREECAD_PY=C:\Program Files\FreeCAD 0.21\bin\python.exe"

if not exist "%FREECAD_PY%" (
  echo No se encontro Python de FreeCAD en:
  echo %FREECAD_PY%
  echo.
  echo Instala Python normal con Tcl/Tk o ajusta FREECAD_PY en este archivo.
  pause
  exit /b 1
)

cd /d "%PROJECT_DIR%"
"%FREECAD_PY%" digital_twin\run_digital_twin.py %*

endlocal
