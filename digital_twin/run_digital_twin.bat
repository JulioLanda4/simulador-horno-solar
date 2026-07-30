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
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo El simulador termino con error ^(codigo %EXIT_CODE%^).
  echo Revisa el mensaje anterior para conocer la causa.
  pause
)

endlocal & exit /b %EXIT_CODE%
