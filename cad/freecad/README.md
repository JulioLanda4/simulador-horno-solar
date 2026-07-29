# Piezas de prueba en FreeCAD

Esta carpeta contiene la version FreeCAD de las primeras piezas de tolerancia del mini heliostato.

## Archivos generados

El script `crear_piezas_prueba.py` genera:

- archivos `.FCStd` editables en FreeCAD,
- archivos `.STEP` para SolidWorks, Onshape, Fusion 360 y otros CAD,
- archivos `.STL` para impresion 3D.

## Piezas

| Pieza | Archivo base | Objetivo |
|---|---|---|
| Placa alojamientos 608ZZ | `test_608zz_bearing_fit` | Elegir diametro real de alojamiento: 22.1, 22.2 o 22.3 mm. |
| Abrazadera eje 8 mm | `test_eje_8mm_abrazadera` | Probar bore 8.2 mm y apriete con tornillos M3. |
| Riel doble guia | `test_riel_doble_guia` | Probar perfil del riel impreso. |
| Carro receptor | `test_carro_doble_guia` | Probar deslizamiento y bloqueo del carro. |
| Polea GT2 60 dientes | `polea_gt2_60d_aproximada` | Probar diametro, bore, abrazadera y agarre preliminar. |

## Como regenerar

Desde PowerShell, usando la instalacion local de FreeCAD:

```powershell
& "C:\Program Files\FreeCAD 0.21\bin\FreeCADCmd.exe" "cad\freecad\crear_piezas_prueba.py"
```

Para regenerar solamente la polea:

```powershell
$env:MINI_HELIOSTATO_PIECES = "polea_gt2_60d_aproximada"
& "C:\Program Files\FreeCAD 0.21\bin\FreeCADCmd.exe" "cad\freecad\crear_piezas_prueba.py"
Remove-Item Env:MINI_HELIOSTATO_PIECES
```

## Nota sobre la polea

La polea es una aproximacion mecanica, no un perfil GT2 certificado. Sirve para comprobar si la correa asienta, si el diametro funciona y si la abrazadera sujeta el eje. Si la transmision se ve viable, luego conviene refinar el perfil de diente.

La revision actual se imprime con la brida plana sobre la cama y el eje vertical. La cara inferior, la rampa conservadora de 35 grados de la brida superior y los pasos M3 tipo lagrima permiten desactivar los soportes. La abrazadera usa dos tornillos M3 pasantes con tuerca.

## Orden recomendado de impresion

1. `test_608zz_bearing_fit.stl`
2. `test_eje_8mm_abrazadera.stl`
3. `test_riel_doble_guia.stl`
4. `test_carro_doble_guia.stl`
5. `polea_gt2_60d_aproximada.stl`
