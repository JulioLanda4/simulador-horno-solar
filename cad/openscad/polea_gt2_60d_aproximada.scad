include <_common.scad>

// Polea GT2 aproximada para prueba mecanica inicial.
// No es un perfil GT2 certificado. Usarla para validar espacio, bore,
// montaje, tension y agarre preliminar con la correa real.

teeth = 60;
pitch = gt2_pitch;
belt_width = gt2_belt_width;
bore_d = 8.2;
pulley_h = 9;
flange_h = 1.2;
flange_extra_d = 4;
hub_d = 22;
hub_h = 16.5;
clamp_gap = 1.2;
clamp_screw_x = 7.5;
clamp_screw_z = [4, 10];
clamp_pad_x = 7;
clamp_pad_y = 23;
top_flange_cap_h = 0.8;
top_flange_angle = 35;

pitch_d = teeth * pitch / PI;
root_d = pitch_d - 1.2;
outer_d = pitch_d + 1.0;
tooth_depth = (outer_d - root_d) / 2;
tooth_w = 1.05;
flange_d = outer_d + flange_extra_d;
top_flange_chamfer_h = ((flange_d - root_d) / 2) / tan(top_flange_angle);
track_z = flange_h;
top_flange_z = track_z + pulley_h;
top_flange_top = top_flange_z + top_flange_chamfer_h + top_flange_cap_h;
total_h = max(hub_h, top_flange_top);

module tooth() {
    translate([root_d / 2, -tooth_w / 2, track_z])
        cube([tooth_depth + 0.7, tooth_w, pulley_h]);
}

// Orificio horizontal con techo a 45 grados. Conserva el paso libre para M3
// sin crear el pequeno techo circular que algunos laminadores soportan.
module teardrop_hole_y(d = m3_clearance, length = 20) {
    r = d / 2;
    roof_angle = 55;
    roof_z = r / sqrt(2) * (1 + tan(roof_angle));
    rotate([90, 0, 0])
        linear_extrude(height = length, center = true, convexity = 4)
            polygon(concat(
                [[0, roof_z]],
                [for (a = [135:10:405]) [r * cos(a), r * sin(a)]]
            ));
}

module printable_body() {
    union() {
        // La brida inferior es ahora la cara de apoyo completa (z = 0).
        cylinder(d = flange_d, h = flange_h, $fn = 180);

        translate([0, 0, track_z])
            cylinder(d = root_d, h = pulley_h, $fn = 180);

        for (i = [0:teeth - 1]) {
            rotate([0, 0, i * 360 / teeth])
                tooth();
        }

        // Brida superior autosoportada: cono conservador a 35 grados y remate corto.
        translate([0, 0, top_flange_z])
            cylinder(
                d1 = root_d,
                d2 = flange_d,
                h = top_flange_chamfer_h,
                $fn = 180
            );
        translate([0, 0, top_flange_z + top_flange_chamfer_h])
            cylinder(d = flange_d, h = top_flange_cap_h, $fn = 180);

        // Cubo y caras planas para las cabezas/tuercas de los M3.
        cylinder(d = hub_d, h = hub_h, $fn = 96);
        translate([
            clamp_screw_x - clamp_pad_x / 2,
            -clamp_pad_y / 2,
            0
        ])
            cube([clamp_pad_x, clamp_pad_y, hub_h]);
    }
}

difference() {
    printable_body();

    // Bore del eje.
    translate([0, 0, -eps])
        cylinder(d = bore_d, h = total_h + 2 * eps, $fn = 96);

    // Una sola ranura radial: abre la abrazadera sin separar la polea en dos.
    translate([0, -clamp_gap / 2, -eps])
        cube([flange_d / 2 + 2, clamp_gap, total_h + 2 * eps]);

    // Dos tornillos M3 de apriete, imprimibles horizontalmente sin soporte.
    for (z = clamp_screw_z) {
        translate([clamp_screw_x, 0, z])
            teardrop_hole_y(d = m3_clearance, length = clamp_pad_y + 2);
    }
}
