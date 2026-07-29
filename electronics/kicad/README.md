# KiCad

Esta carpeta contiene el proyecto KiCad del cableado MVP.

## Proyecto principal

- `mini_heliostato_mvp/mini_heliostato_mvp.kicad_pro`
- `mini_heliostato_mvp/mini_heliostato_mvp.kicad_sch`

## Que representa

El esquema es de interconexion, no una PCB final. Sirve para:

- revisar pines del ESP32,
- revisar senales hacia drivers L298N,
- revisar encoders,
- revisar finales de carrera,
- mantener una referencia editable en CAD electrico.

## Regenerar

```powershell
python electronics\kicad\generate_kicad_mvp.py
```

## Abrir

Abrir en KiCad:

```powershell
& "C:\Program Files\KiCad\9.0\bin\kicad.exe" "electronics\kicad\mini_heliostato_mvp\mini_heliostato_mvp.kicad_pro"
```

## Fritzing

Fritzing esta instalado, pero no es la mejor fuente maestra del proyecto porque sus archivos dependen de piezas especificas y son menos amigables para versionar. Para un diagrama tipo protoboard puede hacerse despues, cuando se confirme el modulo ESP32 exacto, el driver exacto y si se usara protoboard o terminal block.
