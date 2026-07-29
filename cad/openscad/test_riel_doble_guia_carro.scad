include <_common.scad>

// Cambiar a "rail" o "carriage" y exportar cada pieza por separado.
part = "rail";

rail_len = 120;
rail_w = 70;
rail_base_h = 4;
guide_w = 10;
guide_h = 8;
guide_spacing = 50;

carriage_len = 70;
carriage_w = 70;
carriage_h = 14;
clearance = 0.45;
lock_screw_d = m4_clearance;

module rail_profile(len = rail_len) {
    union() {
        cube([len, rail_w, rail_base_h]);

        for (y = [rail_w / 2 - guide_spacing / 2, rail_w / 2 + guide_spacing / 2]) {
            translate([0, y - guide_w / 2, rail_base_h])
                cube([len, guide_w, guide_h]);
        }

        // Nervadura central baja.
        translate([0, rail_w / 2 - 4, rail_base_h])
            cube([len, 8, 4]);
    }
}

module carriage() {
    difference() {
        cube([carriage_len, carriage_w, carriage_h]);

        // Canal inferior para que el carro abrace las dos guias.
        for (y = [carriage_w / 2 - guide_spacing / 2, carriage_w / 2 + guide_spacing / 2]) {
            translate([-eps, y - guide_w / 2 - clearance, -eps])
                cube([
                    carriage_len + 2 * eps,
                    guide_w + 2 * clearance,
                    guide_h + rail_base_h + clearance
                ]);
        }

        // Rebaje central para reducir friccion contra la base del riel.
        translate([-eps, carriage_w / 2 - 11, -eps])
            cube([carriage_len + 2 * eps, 22, rail_base_h + clearance]);

        // Tornillo de bloqueo lateral M4.
        translate([carriage_len / 2, carriage_w / 2 + guide_spacing / 2, rail_base_h + guide_h / 2])
            rotate([90, 0, 0])
                cylinder(d = lock_screw_d, h = 24, center = true, $fn = 48);

        // Perforaciones para montar pantalla o soporte.
        for (x = [carriage_len / 2 - 15, carriage_len / 2 + 15]) {
            translate([x, carriage_w / 2, carriage_h - 6])
                cylinder(d = m3_clearance, h = 8, $fn = 48);
        }
    }
}

if (part == "rail") {
    rail_profile();
} else if (part == "carriage") {
    carriage();
}
