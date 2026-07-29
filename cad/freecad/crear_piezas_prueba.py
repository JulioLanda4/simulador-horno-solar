import math
import os
import sys
from pathlib import Path

import FreeCAD as App
import Part

try:
    import Mesh
    import Import
except Exception:
    Mesh = None
    Import = None


ROOT = Path(__file__).resolve().parent
OUT_FCSTD = ROOT / "fcstd"
OUT_STEP = ROOT / "step"
OUT_STL = ROOT / "stl"

for folder in (OUT_FCSTD, OUT_STEP, OUT_STL):
    folder.mkdir(parents=True, exist_ok=True)


EPS = 0.05


def v(x, y, z):
    return App.Vector(float(x), float(y), float(z))


def cyl_z(d, h, x=0, y=0, z=0):
    return Part.makeCylinder(d / 2, h, v(x, y, z), v(0, 0, 1))


def cyl_x(d, h, x=0, y=0, z=0):
    return Part.makeCylinder(d / 2, h, v(x - h / 2, y, z), v(1, 0, 0))


def cyl_y(d, h, x=0, y=0, z=0):
    return Part.makeCylinder(d / 2, h, v(x, y - h / 2, z), v(0, 1, 0))


def box(dx, dy, dz, x=0, y=0, z=0):
    return Part.makeBox(dx, dy, dz, v(x, y, z))


def teardrop_y(d, length, x=0, y=0, z=0, segments=27):
    """Prisma para un orificio M3 con techo a 55 grados respecto a la horizontal."""
    radius = d / 2
    roof_angle = math.radians(55)
    roof_z = radius / math.sqrt(2) * (1 + math.tan(roof_angle))
    points = [v(x, y - length / 2, z + roof_z)]

    for i in range(segments + 1):
        angle = math.radians(135 + 270 * i / segments)
        points.append(
            v(
                x + radius * math.cos(angle),
                y - length / 2,
                z + radius * math.sin(angle),
            )
        )

    points.append(points[0])
    wire = Part.makePolygon(points)
    return Part.Face(wire).extrude(v(0, length, 0))


def export_shape(name, shape):
    doc = App.newDocument(name)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    doc.recompute()

    fcstd_path = OUT_FCSTD / f"{name}.FCStd"
    step_path = OUT_STEP / f"{name}.step"
    stl_path = OUT_STL / f"{name}.stl"

    doc.saveAs(str(fcstd_path))

    if Import is not None:
        Import.export([obj], str(step_path))

    if Mesh is not None:
        Mesh.export([obj], str(stl_path))

    App.closeDocument(doc.Name)
    return fcstd_path, step_path, stl_path


def make_bearing_fit_plate():
    plate = box(115, 38, 8)
    pocket_ds = [22.1, 22.2, 22.3]

    for i, diameter in enumerate(pocket_ds):
        x = 22 + i * 36
        y = 19
        pocket = cyl_z(diameter, 7.25 + EPS, x, y, 8 - 7.25)
        push_hole = cyl_z(14, 8 + 2 * EPS, x, y, -EPS)
        plate = plate.cut(pocket).cut(push_hole)

    return plate.removeSplitter()


def make_shaft_clamp():
    body = box(34, 22, 18, -17, -11, 0)
    bore = cyl_x(8.2, 38, 0, 0, 9)
    slit = box(36, 1.2, 18 + EPS, -18, -0.6, 0)
    body = body.cut(bore).cut(slit)

    for x in (-9, 9):
        body = body.cut(cyl_y(3.3, 26, x, 0, 12.2))

    relief = cyl_z(12, 4 + EPS, 0, 0, -EPS)
    return body.cut(relief).removeSplitter()


def make_double_guide_rail():
    rail_len = 120
    rail_w = 70
    base_h = 4
    guide_w = 10
    guide_h = 8
    spacing = 50

    shape = box(rail_len, rail_w, base_h)
    for y in (rail_w / 2 - spacing / 2, rail_w / 2 + spacing / 2):
        shape = shape.fuse(box(rail_len, guide_w, guide_h, 0, y - guide_w / 2, base_h))

    shape = shape.fuse(box(rail_len, 8, 4, 0, rail_w / 2 - 4, base_h))
    return shape.removeSplitter()


def make_double_guide_carriage():
    length = 70
    width = 70
    height = 14
    guide_w = 10
    guide_h = 8
    base_h = 4
    spacing = 50
    clearance = 0.45

    shape = box(length, width, height)

    for y in (width / 2 - spacing / 2, width / 2 + spacing / 2):
        channel = box(
            length + 2 * EPS,
            guide_w + 2 * clearance,
            guide_h + base_h + clearance + EPS,
            -EPS,
            y - guide_w / 2 - clearance,
            -EPS,
        )
        shape = shape.cut(channel)

    center_relief = box(length + 2 * EPS, 22, base_h + clearance, -EPS, width / 2 - 11, -EPS)
    shape = shape.cut(center_relief)

    lock_screw = cyl_y(4.3, 24, length / 2, width / 2 + spacing / 2, base_h + guide_h / 2)
    shape = shape.cut(lock_screw)

    for x in (length / 2 - 15, length / 2 + 15):
        shape = shape.cut(cyl_z(3.3, 8, x, width / 2, height - 6))

    return shape.removeSplitter()


def make_approx_gt2_pulley():
    teeth = 60
    pitch = 2
    bore_d = 8.2
    pulley_h = 9
    flange_h = 1.2
    flange_extra_d = 4
    hub_d = 22
    hub_h = 16.5
    clamp_gap = 1.2
    clamp_screw_x = 7.5
    clamp_screw_z = (4, 10)
    clamp_pad_x = 7
    clamp_pad_y = 23
    top_flange_cap_h = 0.8
    top_flange_angle = 35

    pitch_d = teeth * pitch / math.pi
    root_d = pitch_d - 1.2
    outer_d = pitch_d + 1.0
    tooth_depth = (outer_d - root_d) / 2
    tooth_w = 1.05
    flange_d = outer_d + flange_extra_d
    top_flange_chamfer_h = ((flange_d - root_d) / 2) / math.tan(
        math.radians(top_flange_angle)
    )
    track_z = flange_h
    top_flange_z = track_z + pulley_h
    top_flange_top = top_flange_z + top_flange_chamfer_h + top_flange_cap_h
    total_h = max(hub_h, top_flange_top)

    # Cara inferior plana: toda la brida descansa directamente en la cama.
    shape = cyl_z(flange_d, flange_h)
    shape = shape.fuse(cyl_z(root_d, pulley_h, 0, 0, track_z))

    for i in range(teeth):
        angle = math.radians(i * 360 / teeth)
        radial = root_d / 2 + tooth_depth / 2
        cx = math.cos(angle) * radial
        cy = math.sin(angle) * radial
        tooth = box(
            tooth_depth + 0.7,
            tooth_w,
            pulley_h,
            -0.35,
            -tooth_w / 2,
            track_z,
        )
        tooth.rotate(v(0, 0, 0), v(0, 0, 1), math.degrees(angle))
        tooth.translate(v(cx, cy, 0))
        shape = shape.fuse(tooth)

    # Brida superior con transicion conservadora a 35 grados y un remate corto.
    top_flange = Part.makeCone(
        root_d / 2,
        flange_d / 2,
        top_flange_chamfer_h,
        v(0, 0, top_flange_z),
        v(0, 0, 1),
    )
    shape = shape.fuse(top_flange)
    shape = shape.fuse(
        cyl_z(
            flange_d,
            top_flange_cap_h,
            0,
            0,
            top_flange_z + top_flange_chamfer_h,
        )
    )

    shape = shape.fuse(cyl_z(hub_d, hub_h))
    shape = shape.fuse(
        box(
            clamp_pad_x,
            clamp_pad_y,
            hub_h,
            clamp_screw_x - clamp_pad_x / 2,
            -clamp_pad_y / 2,
            0,
        )
    )

    shape = shape.cut(cyl_z(bore_d, total_h + 2 * EPS, 0, 0, -EPS))
    shape = shape.cut(
        box(
            flange_d / 2 + 2,
            clamp_gap,
            total_h + 2 * EPS,
            0,
            -clamp_gap / 2,
            -EPS,
        )
    )

    for z in clamp_screw_z:
        shape = shape.cut(teardrop_y(3.3, clamp_pad_y + 2, clamp_screw_x, 0, z))

    return shape.removeSplitter()


def main():
    pieces = {
        "test_608zz_bearing_fit": make_bearing_fit_plate(),
        "test_eje_8mm_abrazadera": make_shaft_clamp(),
        "test_riel_doble_guia": make_double_guide_rail(),
        "test_carro_doble_guia": make_double_guide_carriage(),
        "polea_gt2_60d_aproximada": make_approx_gt2_pulley(),
    }

    requested = {arg for arg in sys.argv[1:] if arg in pieces}
    requested.update(
        name.strip()
        for name in os.environ.get("MINI_HELIOSTATO_PIECES", "").split(",")
        if name.strip() in pieces
    )
    if requested:
        pieces = {name: shape for name, shape in pieces.items() if name in requested}

    for name, shape in pieces.items():
        fcstd, step, stl = export_shape(name, shape)
        print(f"generated: {fcstd}")
        print(f"generated: {step}")
        print(f"generated: {stl}")


if __name__ == "__main__":
    main()
