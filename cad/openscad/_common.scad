// Parametros comunes del mini heliostato.

$fn = 96;

eps = 0.02;

bearing_608_od = 22;
bearing_608_id = 8;
bearing_608_width = 7;

shaft_d = 8;
shaft_clearance = 0.2;

m3_clearance = 3.3;
m4_clearance = 4.3;

gt2_pitch = 2;
gt2_belt_width = 6;

module rounded_box(size = [10, 10, 10], r = 2) {
    hull() {
        for (x = [r, size[0] - r])
        for (y = [r, size[1] - r])
        for (z = [r, size[2] - r])
            translate([x, y, z]) sphere(r = r, $fn = 24);
    }
}

module screw_hole_x(d = m3_clearance, length = 20) {
    rotate([0, 90, 0])
        cylinder(d = d, h = length, center = true, $fn = 48);
}

module screw_hole_y(d = m3_clearance, length = 20) {
    rotate([90, 0, 0])
        cylinder(d = d, h = length, center = true, $fn = 48);
}

module shaft_hole_x(d = shaft_d + shaft_clearance, length = 40) {
    rotate([0, 90, 0])
        cylinder(d = d, h = length, center = true, $fn = 96);
}
