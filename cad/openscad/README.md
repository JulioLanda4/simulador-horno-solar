# Piezas de prueba en OpenSCAD

Estas piezas son el primer paquete de tolerancias del mini heliostato. La idea es imprimir piezas pequenas antes de modelar el ensamble completo.

## Flujo recomendado

1. Abrir cada archivo `.scad` en OpenSCAD.
2. Ajustar parametros al inicio del archivo si hace falta.
3. Renderizar con F6.
4. Exportar STL.
5. Imprimir en PETG con la misma configuracion que se usara en piezas finales.
6. Medir el ajuste real y registrar cambios.

## Archivos

| Archivo | Uso |
|---|---|
| `_common.scad` | Parametros comunes del proyecto. |
| `test_608zz_bearing_fit.scad` | Placa con tres alojamientos para probar ajuste de rodamientos 608ZZ. |
| `test_eje_8mm_abrazadera.scad` | Abrazadera partida para eje metalico de 8 mm. |
| `test_riel_doble_guia_carro.scad` | Tramo corto de riel doble guia y carro de prueba. |
| `polea_gt2_60d_aproximada.scad` | Polea GT2 aproximada de 60 dientes para prueba inicial de correa. |

## Nota sobre la polea GT2

La polea incluida es una aproximacion imprimible para verificar diametro, montaje, tension y espacio. Para transmision final conviene usar un generador GT2 con perfil correcto o ajustar esta geometria despues de probarla con la correa real.

La revision actual esta preparada para imprimirse sin soportes con el eje de la polea vertical:

- colocar la brida circular plana directamente sobre la cama;
- no invertir ni imprimir la polea de canto;
- la brida superior tiene una transicion conservadora de 35 grados;
- los dos pasos M3 tienen techo tipo lagrima y la ranura de apriete es radial.

## Primer orden de impresion

1. `test_608zz_bearing_fit.scad`
2. `test_eje_8mm_abrazadera.scad`
3. `test_riel_doble_guia_carro.scad`, primero `part = "rail"`
4. `test_riel_doble_guia_carro.scad`, luego `part = "carriage"`
5. `polea_gt2_60d_aproximada.scad`

## Registro minimo de resultados

Para cada pieza conviene anotar:

- filamento,
- temperatura de boquilla,
- temperatura de cama,
- altura de capa,
- porcentaje de relleno,
- diametro o holgura probada,
- resultado: flojo, correcto o apretado.
