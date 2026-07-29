include <_common.scad>

// Placa de prueba para encontrar el diametro correcto del alojamiento 608ZZ.
// Imprimir plana. Probar que alojamiento queda firme sin fracturar PETG.

pocket_ds = [22.1, 22.2, 22.3];
plate = [115, 38, 8];
pocket_depth = 7.2;
push_hole_d = 14;

difference() {
    cube(plate);

    for (i = [0:2]) {
        x = 22 + i * 36;
        y = plate[1] / 2;

        // Alojamiento casi completo del rodamiento.
        translate([x, y, plate[2] - pocket_depth])
            cylinder(d = pocket_ds[i], h = pocket_depth + eps, $fn = 128);

        // Orificio inferior para empujar el rodamiento si queda apretado.
        translate([x, y, -eps])
            cylinder(d = push_hole_d, h = plate[2] + 2 * eps, $fn = 96);
    }
}

// Etiquetas en relieve bajo.
for (i = [0:2]) {
    x = 22 + i * 36;
    translate([x - 8, 3, plate[2]])
        linear_extrude(height = 0.45)
            text(str(pocket_ds[i]), size = 5, font = "Liberation Sans");
}
