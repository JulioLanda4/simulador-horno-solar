import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "mini_heliostato_mvp"
ROOT.mkdir(parents=True, exist_ok=True)

PROJECT = ROOT / "mini_heliostato_mvp.kicad_pro"
SCHEMATIC = ROOT / "mini_heliostato_mvp.kicad_sch"


def u():
    return str(uuid.uuid4())


def connector_symbol(name, pin_count):
    pins = []
    half = (pin_count - 1) * 2.54 / 2
    for i in range(pin_count):
        y = half - i * 2.54
        pins.append(
            f'''
			(pin passive line
				(at 0 {y:.2f} 180)
				(length 2.54)
				(name "Pin_{i + 1}"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "{i + 1}"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)'''
        )

    box_h = pin_count * 2.54 + 2.54
    top = box_h / 2
    bottom = -box_h / 2
    return f'''
		(symbol "MiniHeliostato:{name}"
			(pin_names
				(offset 1.016)
				(hide yes)
			)
			(exclude_from_sim no)
			(in_bom yes)
			(on_board yes)
			(property "Reference" "J"
				(at 3.81 {top + 1.27:.2f} 0)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "Value" "{name}"
				(at 3.81 {bottom - 1.27:.2f} 0)
				(effects
					(font
						(size 1.27 1.27)
					)
				)
			)
			(property "Footprint" ""
				(at 0 0 0)
				(effects
					(font
						(size 1.27 1.27)
					)
					(hide yes)
				)
			)
			(property "Datasheet" "~"
				(at 0 0 0)
				(effects
					(font
						(size 1.27 1.27)
					)
					(hide yes)
				)
			)
			(symbol "{name}_0_1"
				(rectangle
					(start 2.54 {top:.2f})
					(end 15.24 {bottom:.2f})
					(stroke
						(width 0.254)
						(type default)
					)
					(fill
						(type background)
					)
				)
			)
			(symbol "{name}_1_1"
				{''.join(pins)}
			)
		)'''


def symbol_instance(lib_id, ref, value, x, y, pin_count):
    sym_uuid = u()
    pin_uuids = "\n".join([f'\t\t(pin "{i}" (uuid "{u()}"))' for i in range(1, pin_count + 1)])
    return f'''
	(symbol
		(lib_id "{lib_id}")
		(at {x:.2f} {y:.2f} 0)
		(unit 1)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(dnp no)
		(uuid "{sym_uuid}")
		(property "Reference" "{ref}"
			(at {x + 3.81:.2f} {y - 8.0:.2f} 0)
			(effects
				(font
					(size 1.27 1.27)
				)
			)
		)
		(property "Value" "{value}"
			(at {x + 3.81:.2f} {y + 8.0:.2f} 0)
			(effects
				(font
					(size 1.27 1.27)
				)
			)
		)
{pin_uuids}
	)''', sym_uuid


def text(label, x, y, size=1.5):
    return f'''
	(text "{label}"
		(at {x:.2f} {y:.2f} 0)
		(effects
			(font
				(size {size:.2f} {size:.2f})
			)
		)
		(uuid "{u()}")
	)'''


def label(name, x, y):
    return f'''
	(label "{name}"
		(at {x:.2f} {y:.2f} 0)
		(effects
			(font
				(size 1.27 1.27)
			)
		)
		(uuid "{u()}")
	)'''


def wire(x1, y1, x2, y2):
    return f'''
	(wire
		(pts
			(xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})
		)
		(stroke
			(width 0)
			(type default)
		)
		(uuid "{u()}")
	)'''


def route(points):
    segments = []
    for a, b in zip(points, points[1:]):
        segments.append(wire(a[0], a[1], b[0], b[1]))
    return "".join(segments)


def pin_y(center_y, pin_count, pin_number):
    half = (pin_count - 1) * 2.54 / 2
    return center_y + half - (pin_number - 1) * 2.54


def net_stub(x, y, name):
    return wire(x, y, x - 12.0, y) + label(name, x - 12.0, y)


def pin_point(cx, cy, pin_count, pin_number):
    return (cx, pin_y(cy, pin_count, pin_number))


def labeled_pin(cx, cy, pin_count, pin_number, name, side="left"):
    px, py = pin_point(cx, cy, pin_count, pin_number)
    if side == "left":
        return wire(px, py, px - 7.0, py) + label(name, px - 7.0, py)
    return wire(px, py, px + 7.0, py) + label(name, px + 7.0, py)


def main():
    project = {
        "board": {"design_settings": {}},
        "boards": [],
        "cvpcb": {},
        "erc": {},
        "libraries": {},
        "meta": {"filename": "mini_heliostato_mvp.kicad_pro", "version": 1},
        "net_settings": {},
        "pcbnew": {},
        "schematic": {},
        "sheets": [["root", ""]],
        "text_variables": {},
    }
    PROJECT.write_text(json.dumps(project, indent=2), encoding="utf-8")

    symbols = [
        connector_symbol("Conn_ESP32_24", 24),
        connector_symbol("Conn_L298N_10", 10),
        connector_symbol("Conn_MotorEncoder_6", 6),
        connector_symbol("Conn_LimitSwitches_4", 4),
        connector_symbol("Conn_Power_4", 4),
        connector_symbol("Conn_Buck_4", 4),
    ]

    placements = []
    instances = []

    for args in [
        ("MiniHeliostato:Conn_ESP32_24", "U1", "ESP32 DevKit - conexiones MVP", 82, 105, 24),
        ("MiniHeliostato:Conn_L298N_10", "U2", "Driver L298N acimut", 158, 65, 10),
        ("MiniHeliostato:Conn_L298N_10", "U3", "Driver L298N elevacion", 158, 125, 10),
        ("MiniHeliostato:Conn_MotorEncoder_6", "M1", "Motor acimut con encoder", 230, 65, 6),
        ("MiniHeliostato:Conn_MotorEncoder_6", "M2", "Motor elevacion con encoder", 230, 125, 6),
        ("MiniHeliostato:Conn_LimitSwitches_4", "J1", "Finales acimut", 158, 180, 4),
        ("MiniHeliostato:Conn_LimitSwitches_4", "J2", "Finales elevacion", 230, 180, 4),
        ("MiniHeliostato:Conn_Power_4", "J3", "Entrada fuente 12 V", 35, 40, 4),
        ("MiniHeliostato:Conn_Buck_4", "U4", "Buck XL4015", 35, 80, 4),
    ]:
        sym, sym_uuid = symbol_instance(*args)
        placements.append(sym)
        instances.append((sym_uuid, args[1], args[2], args[0]))

    nets = []

    # Visible point-to-point wiring. These wires are intentionally drawn even
    # when labels would be enough electrically, because this file is meant for
    # bench wiring.
    esp_x = 82
    esp_y = 105
    az_drv_x, az_drv_y = 158, 65
    el_drv_x, el_drv_y = 158, 125
    az_motor_x, az_motor_y = 230, 65
    el_motor_x, el_motor_y = 230, 125
    az_lim_x, az_lim_y = 158, 180
    el_lim_x, el_lim_y = 230, 180
    pwr_x, pwr_y = 35, 40
    buck_x, buck_y = 35, 80

    def connect(a, b, mid_x):
        nets.append(route([a, (mid_x, a[1]), (mid_x, b[1]), b]))

    # ESP32 to L298N control lines.
    for esp_pin, driver_pin in [(1, 1), (2, 2), (3, 3)]:
        connect(pin_point(esp_x, esp_y, 24, esp_pin), pin_point(az_drv_x, az_drv_y, 10, driver_pin), 120)
    for esp_pin, driver_pin in [(4, 1), (5, 2), (6, 3)]:
        connect(pin_point(esp_x, esp_y, 24, esp_pin), pin_point(el_drv_x, el_drv_y, 10, driver_pin), 128)

    # L298N outputs to motors.
    for drv_pin, motor_pin in [(6, 1), (7, 2)]:
        connect(pin_point(az_drv_x, az_drv_y, 10, drv_pin), pin_point(az_motor_x, az_motor_y, 6, motor_pin), 196)
        connect(pin_point(el_drv_x, el_drv_y, 10, drv_pin), pin_point(el_motor_x, el_motor_y, 6, motor_pin), 196)

    # Encoder signals back to ESP32.
    for motor_pin, esp_pin in [(5, 7), (6, 8)]:
        connect(pin_point(az_motor_x, az_motor_y, 6, motor_pin), pin_point(esp_x, esp_y, 24, esp_pin), 205)
    for motor_pin, esp_pin in [(5, 9), (6, 10)]:
        connect(pin_point(el_motor_x, el_motor_y, 6, motor_pin), pin_point(esp_x, esp_y, 24, esp_pin), 214)

    # Limit switches to ESP32.
    connect(pin_point(az_lim_x, az_lim_y, 4, 1), pin_point(esp_x, esp_y, 24, 11), 136)
    connect(pin_point(az_lim_x, az_lim_y, 4, 3), pin_point(esp_x, esp_y, 24, 12), 142)
    connect(pin_point(el_lim_x, el_lim_y, 4, 1), pin_point(esp_x, esp_y, 24, 13), 204)
    connect(pin_point(el_lim_x, el_lim_y, 4, 3), pin_point(esp_x, esp_y, 24, 14), 210)

    # 12 V motor bus.
    p12 = pin_point(pwr_x, pwr_y, 4, 1)
    for target in [
        pin_point(az_drv_x, az_drv_y, 10, 4),
        pin_point(el_drv_x, el_drv_y, 10, 4),
        pin_point(buck_x, buck_y, 4, 1),
    ]:
        connect(p12, target, 56)

    # 5 V optional logic bus from buck.
    v5 = pin_point(buck_x, buck_y, 4, 3)
    for target in [
        pin_point(esp_x, esp_y, 24, 17),
        pin_point(az_drv_x, az_drv_y, 10, 8),
        pin_point(el_drv_x, el_drv_y, 10, 8),
        pin_point(az_motor_x, az_motor_y, 6, 3),
        pin_point(el_motor_x, el_motor_y, 6, 3),
    ]:
        connect(v5, target, 62)

    # Common GND bus.
    gnd = pin_point(pwr_x, pwr_y, 4, 2)
    for target in [
        pin_point(buck_x, buck_y, 4, 2),
        pin_point(buck_x, buck_y, 4, 4),
        pin_point(esp_x, esp_y, 24, 15),
        pin_point(esp_x, esp_y, 24, 16),
        pin_point(az_drv_x, az_drv_y, 10, 5),
        pin_point(az_drv_x, az_drv_y, 10, 9),
        pin_point(el_drv_x, el_drv_y, 10, 5),
        pin_point(el_drv_x, el_drv_y, 10, 9),
        pin_point(az_motor_x, az_motor_y, 6, 4),
        pin_point(el_motor_x, el_motor_y, 6, 4),
        pin_point(az_lim_x, az_lim_y, 4, 2),
        pin_point(az_lim_x, az_lim_y, 4, 4),
        pin_point(el_lim_x, el_lim_y, 4, 2),
        pin_point(el_lim_x, el_lim_y, 4, 4),
    ]:
        connect(gnd, target, 48)

    # Net labels remain on the important pins so the schematic is readable.
    visible_labels = [
        (esp_x, esp_y, 24, 1, "PWM_AZ"), (esp_x, esp_y, 24, 2, "IN1_AZ"),
        (esp_x, esp_y, 24, 3, "IN2_AZ"), (esp_x, esp_y, 24, 4, "PWM_EL"),
        (esp_x, esp_y, 24, 5, "IN1_EL"), (esp_x, esp_y, 24, 6, "IN2_EL"),
        (esp_x, esp_y, 24, 7, "ENC_A_AZ"), (esp_x, esp_y, 24, 8, "ENC_B_AZ"),
        (esp_x, esp_y, 24, 9, "ENC_A_EL"), (esp_x, esp_y, 24, 10, "ENC_B_EL"),
        (esp_x, esp_y, 24, 11, "HOME_AZ"), (esp_x, esp_y, 24, 12, "LIMIT_AZ"),
        (esp_x, esp_y, 24, 13, "HOME_EL"), (esp_x, esp_y, 24, 14, "LIMIT_EL"),
        (pwr_x, pwr_y, 4, 1, "+12V"), (pwr_x, pwr_y, 4, 2, "GND"),
        (buck_x, buck_y, 4, 3, "+5V_OPT"),
    ]
    for cx, cy, count, pin, name in visible_labels:
        nets.append(labeled_pin(cx, cy, count, pin, name, "left"))

    notes = [
        text("Mini heliostato MVP - esquema de interconexion", 25, 18, 2.2),
        text("No es PCB final: usar para cableado, revision de pines y pruebas de banco.", 25, 24, 1.3),
        text("GND comun obligatorio entre fuente, ESP32, drivers, buck y encoders.", 25, 200, 1.3),
        text("L298N: iniciar barato; cambiar a BTS7960 si hay calentamiento o falta de torque.", 25, 207, 1.3),
    ]

    symbol_instances = "\n".join(
        [
            f'		(path "/{sym_uuid}"\n			(reference "{ref}")\n			(unit 1)\n			(value "{value}")\n			(footprint "")\n		)'
            for sym_uuid, ref, value, lib_id in instances
        ]
    )

    sch = f'''(kicad_sch
	(version 20250114)
	(generator "codex")
	(generator_version "1.0")
	(uuid "{u()}")
	(paper "A3")
	(title_block
		(title "Mini heliostato MVP - cableado")
		(date "2026-07-03")
		(company "Proyecto mini heliostato impreso")
	)
	(lib_symbols
{''.join(symbols)}
	)
{''.join(notes)}
{''.join(placements)}
{''.join(nets)}
	(sheet_instances
		(path "/"
			(page "1")
		)
	)
	(symbol_instances
{symbol_instances}
	)
)'''
    SCHEMATIC.write_text(sch, encoding="utf-8")
    print(PROJECT)
    print(SCHEMATIC)


if __name__ == "__main__":
    main()
