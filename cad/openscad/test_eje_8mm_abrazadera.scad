include <_common.scad>

// Abrazadera partida para eje de 8 mm.
// Objetivo: comprobar bore, ranura y fuerza de apriete con dos tornillos M3.

body = [34, 22, 18];
bore_d = 8.2;
slit_w = 1.2;
screw_spacing = 18;

difference() {
    translate([-body[0] / 2, -body[1] / 2, 0])
        cube(body);

    // Paso del eje.
    translate([0, 0, body[2] / 2])
        shaft_hole_x(d = bore_d, length = body[0] + 2);

    // Ranura de apriete.
    translate([-body[0] / 2 - eps, -slit_w / 2, 0])
        cube([body[0] + 2 * eps, slit_w, body[2] + eps]);

    // Tornillos de apriete M3, perpendiculares a la ranura.
    for (x = [-screw_spacing / 2, screw_spacing / 2]) {
        translate([x, 0, body[2] * 0.68])
            screw_hole_y(d = m3_clearance, length = body[1] + 2);
    }

    // Aligeramiento inferior.
    translate([0, 0, -eps])
        cylinder(d = 12, h = 4, $fn = 64);
}
