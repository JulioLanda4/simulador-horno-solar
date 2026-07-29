"""
Gemelo digital del mini horno solar / mini heliostato.

Este archivo contiene todo el programa:

1. Utilidades matematicas para vectores 3D y angulos.
2. Calculo solar aproximado tipo Duffie-Beckman, REDA aproximado y, si existe,
   SPA mediante pvlib.
3. Modelo del estado fisico simulado: ejes, motores, encoders, geometria del
   target/concentrador, rayo reflejado y error del spot.
4. Interfaz grafica en Tkinter inspirada en el panel de LabVIEW.
5. Vistas del gemelo 3D, pantalla del concentrador, trayectoria solar,
   diagnostico, flujo logico, eventos, replay y exportacion CSV.

Importante: el programa NO controla hardware. No abre puerto serial, no usa
GPIO y no manda senales a motores reales. Solo simula el comportamiento para
entender, validar y visualizar la logica del sistema.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import math
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable


TAU = 2.0 * math.pi
DEG = math.pi / 180.0
RAD = 180.0 / math.pi
PVLIB_STATUS: bool | None = None

# Convencion geometrica usada en todo el gemelo:
#   +x = oeste
#   -x = este
#   +y = sur
#   -y = norte
#   +z = cenit
#
# El acimut interno sigue esa convencion:
#   0 deg   -> sur
#   +90 deg -> oeste
#   -90 deg -> este
#   +/-180  -> norte


def clamp(value: float, low: float, high: float) -> float:
    """Limita un valor numerico al intervalo cerrado [low, high]."""
    return max(low, min(high, value))


def wrap_deg(angle: float) -> float:
    """Normaliza un angulo en grados al rango (-180, 180]."""
    while angle <= -180.0:
        angle += 360.0
    while angle > 180.0:
        angle -= 360.0
    return angle


def v_add(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    """Suma dos vectores 3D componente a componente."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    """Resta dos vectores 3D componente a componente."""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a: tuple[float, float, float], s: float) -> tuple[float, float, float]:
    """Multiplica un vector 3D por un escalar."""
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """Producto punto entre dos vectores 3D."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    """Producto cruz entre dos vectores 3D."""
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_norm(a: tuple[float, float, float]) -> float:
    """Magnitud euclidiana de un vector 3D."""
    return math.sqrt(v_dot(a, a))


def v_unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    """Devuelve el vector unitario; si la norma es casi cero, devuelve cero."""
    n = v_norm(a)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def normal_from_angles(acim_deg: float, elev_deg: float) -> tuple[float, float, float]:
    """Convierte acimut/elevacion del heliostato en un vector normal 3D."""
    acim = acim_deg * DEG
    elev = elev_deg * DEG
    return (
        math.cos(elev) * math.sin(acim),
        math.cos(elev) * math.cos(acim),
        math.sin(elev),
    )


def angles_from_normal(n: tuple[float, float, float]) -> tuple[float, float]:
    """Convierte una normal 3D en los angulos acimut/elevacion equivalentes."""
    n = v_unit(n)
    acim = math.atan2(n[0], n[1]) * RAD
    elev = math.asin(clamp(n[2], -1.0, 1.0)) * RAD
    return wrap_deg(acim), elev


def solar_position_db(
    when: _dt.datetime,
    lat_deg: float,
    lon_deg: float,
    method: str,
) -> tuple[float, float, float]:
    """Calcula una posicion solar aproximada tipo Duffie-Beckman.

    Devuelve:
        (zenit_deg, altura_deg, acimut_labview_deg)

    El acimut devuelto ya esta en la convencion del proyecto:
        Sx = cos(altura) * sin(acimut)
        Sy = cos(altura) * cos(acimut)
        Sz = sin(altura)

    con +x oeste, +y sur, +z cenit. Por eso:
        acimut negativo -> sol hacia el este
        acimut positivo -> sol hacia el oeste

    Si method == "REDA" se agrega una perturbacion pequena para tener un canal
    comparativo dentro del simulador. No es una implementacion REDA completa.
    """

    # Dia del ano y hora decimal civil. Se usan para ecuacion del tiempo,
    # declinacion solar y angulo horario.
    day = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0

    b = TAU * (day - 81) / 364.0
    eot_min = 9.87 * math.sin(2.0 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    if method.upper() == "REDA":
        # REDA/SPA no se reimplementa completo aqui; esta rama solo permite
        # comparar visualmente un canal ligeramente distinto dentro del gemelo.
        eot_min += 0.2 * math.sin(TAU * day / 365.0)
    standard_meridian = round(lon_deg / 15.0) * 15.0
    solar_time = hour + (4.0 * (lon_deg - standard_meridian) + eot_min) / 60.0
    omega = 15.0 * (solar_time - 12.0) * DEG

    decl = 23.45 * DEG * math.sin(TAU * (284 + day) / 365.0)
    if method.upper() == "REDA":
        decl += 0.05 * DEG * math.cos(TAU * day / 365.0)

    lat = lat_deg * DEG
    sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(omega)
    alt = math.asin(clamp(sin_alt, -1.0, 1.0))
    zen = 90.0 - alt * RAD

    cos_alt = max(1e-9, math.cos(alt))
    # Primero se calculan componentes este/norte/arriba. Luego se transforman
    # a la convencion del proyecto: oeste/sur/cenit.
    east = -math.cos(decl) * math.sin(omega)
    north = math.cos(lat) * math.sin(decl) - math.sin(lat) * math.cos(decl) * math.cos(omega)
    south = -north
    west = -east
    az_labview = math.atan2(west / cos_alt, south / cos_alt) * RAD
    return zen, alt * RAD, wrap_deg(az_labview)


def solar_position(
    when: _dt.datetime,
    lat_deg: float,
    lon_deg: float,
    method: str,
) -> tuple[float, float, float, str]:
    """Selecciona el metodo solar activo y devuelve tambien su etiqueta.

    - "D&B": usa la aproximacion Duffie-Beckman local.
    - "REDA": usa el canal aproximado de comparacion.
    - "SPA/PVLIB": intenta usar pvlib.solarposition.spa_python.

    Si pvlib no esta instalado en el Python que ejecuta la interfaz, el gemelo
    no falla: registra que SPA/PVLIB no esta disponible y usa REDA aproximado
    como respaldo.
    """
    global PVLIB_STATUS
    method_key = method.upper()
    if "SPA" in method_key or "PVLIB" in method_key:
        if PVLIB_STATUS is False:
            zen, alt, az = solar_position_db(when, lat_deg, lon_deg, "REDA")
            return zen, alt, az, "SPA/PVLIB no disponible; usando REDA aprox."
        try:
            import pandas as pd  # type: ignore
            from pvlib import solarposition  # type: ignore

            PVLIB_STATUS = True
            timestamp = pd.DatetimeIndex([pd.Timestamp(when)])
            pos = solarposition.spa_python(timestamp, latitude=lat_deg, longitude=lon_deg)
            apparent_zenith = float(pos["apparent_zenith"].iloc[0])
            apparent_elevation = float(pos["apparent_elevation"].iloc[0])
            pvlib_az = float(pos["azimuth"].iloc[0])
            # pvlib mide acimut horario desde el norte: 90 este, 180 sur,
            # 270 oeste. La convencion del gemelo es atan2(oeste, sur):
            # -90 este, 0 sur, +90 oeste.
            az_labview = wrap_deg(pvlib_az - 180.0)
            return apparent_zenith, apparent_elevation, az_labview, "SPA/PVLIB"
        except Exception:
            PVLIB_STATUS = False
            zen, alt, az = solar_position_db(when, lat_deg, lon_deg, "REDA")
            return zen, alt, az, "SPA/PVLIB no disponible; usando REDA aprox."
    zen, alt, az = solar_position_db(when, lat_deg, lon_deg, method)
    source = "REDA aprox." if method_key == "REDA" else "Duffie-Beckman aprox."
    return zen, alt, az, source


@dataclass
class AxisState:
    """Estado de un eje motorizado simulado.

    Representa un eje del heliostato, ya sea acimut o elevacion. Guarda el
    angulo actual, angulo objetivo, conteos de encoder, PWM, estado del motor,
    direccion de puente H simulada (INA/INB), limites mecanicos y velocidad
    maxima.

    No controla un driver real. Los campos INA/INB solo sirven para visualizar
    que direccion estaria activada si existiera hardware conectado.
    """

    name: str
    angle_deg: float = 0.0
    target_deg: float = 0.0
    counts: int = 0
    pwm: float = 0.55
    motor_on: bool = True
    ina: int = 0
    inb: int = 0
    limit_min: float = -95.0
    limit_max: float = 95.0
    counts_per_degree: float = 1000.0
    deg_per_second_at_full_pwm: float = 9.0

    def reset(self) -> None:
        """Reinicia el eje a cero de simulacion y apaga salidas de direccion."""
        self.angle_deg = 0.0
        self.counts = 0
        self.ina = 0
        self.inb = 0

    def update_closed_loop(self, dt: float, tolerance_deg: float, reverse: bool = False) -> None:
        """Mueve el eje hacia su objetivo con una logica discreta tipo LabVIEW.

        La logica es deliberadamente simple:
        1. Calcula error angular = objetivo - angulo actual.
        2. Si el motor esta apagado o el error esta dentro de cdr, se detiene.
        3. Si hay error, activa una direccion y avanza con velocidad proporcional
           al PWM.
        4. Evita sobrepasar el objetivo y respeta los limites mecanicos.

        reverse queda disponible por si se requiere invertir el sentido de un
        eje sin tocar el resto del modelo.
        """
        error = wrap_deg(self.target_deg - self.angle_deg)
        if not self.motor_on or abs(error) <= tolerance_deg:
            self.ina = 0
            self.inb = 0
            return
        direction = 1 if error > 0.0 else -1
        if reverse:
            direction *= -1
        speed = self.deg_per_second_at_full_pwm * clamp(self.pwm, 0.0, 1.0)
        step = direction * speed * dt
        if abs(step) > abs(error):
            step = error
        if reverse:
            step *= -1
        self.angle_deg = clamp(self.angle_deg + step, self.limit_min, self.limit_max)
        self.counts = int(round(self.angle_deg * self.counts_per_degree))
        self.ina = 1 if direction > 0 else 0
        self.inb = 1 if direction < 0 else 0

    def jog(self, direction: int, dt: float) -> None:
        """Mueve manualmente el eje en una direccion mientras se sostiene el jog."""
        if not self.motor_on:
            self.ina = 0
            self.inb = 0
            return
        speed = self.deg_per_second_at_full_pwm * clamp(self.pwm, 0.0, 1.0)
        self.angle_deg = clamp(self.angle_deg + direction * speed * dt, self.limit_min, self.limit_max)
        self.counts = int(round(self.angle_deg * self.counts_per_degree))
        self.ina = 1 if direction > 0 else 0
        self.inb = 1 if direction < 0 else 0


@dataclass
class TwinState:
    """Estado completo del gemelo digital.

    Aqui vive todo lo que describe al sistema en un instante:
    - ubicacion geografica y fecha/hora usada;
    - target del concentrador RX/RY/RZ;
    - peralte, offsets, tolerancia cdr y parametros visuales;
    - estados de los ejes de acimut y elevacion;
    - posicion solar, vector solar, normal ideal, normal real;
    - error del spot y historial reciente.

    La interfaz grafica lee y modifica este estado. La simulacion avanza con
    update(), que recalcula geometria y mueve los ejes si corresponde.
    """

    lat_deg: float = 18.85
    lon_deg: float = -99.233333
    method: str = "D&B"
    use_live_time: bool = True
    simulated_time: _dt.datetime = field(default_factory=_dt.datetime.now)
    rx: float = 0.0
    ry: float = 5.55
    rz: float = -0.40
    peralte: float = 0.40
    scale_to_model: bool = True
    offset_ele: float = 0.0
    offset_acim: float = 0.0
    camera_offset_ele: float = 0.0
    camera_offset_acim: float = 0.0
    cdr: float = 0.07
    delay_s: float = 0.05
    mirror_size_m: float = 0.20
    base_width_m: float = 0.19
    fork_height_m: float = 0.22
    rail_length_m: float = 0.55
    receiver_screen_m: float = 0.16
    uncertainty_gain: float = 1.0
    tracking: bool = True
    automatic: bool = True
    free_mode: bool = False
    running: bool = True
    iterations: int = 0
    az: AxisState = field(default_factory=lambda: AxisState("acim", limit_min=-95.0, limit_max=95.0))
    el: AxisState = field(default_factory=lambda: AxisState("elev", limit_min=0.0, limit_max=90.0))
    zenith: float = 0.0
    altitude: float = 0.0
    solar_azimuth: float = 0.0
    solar_source: str = "Duffie-Beckman aprox."
    target_acim: float = 0.0
    target_elev: float = 0.0
    raw_target_acim: float = 0.0
    raw_target_elev: float = 0.0
    target_saturated: bool = False
    spot_error_x: float = 0.0
    spot_error_z: float = 0.0
    spot_point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    sun_vector: tuple[float, float, float] = (0.0, 1.0, 0.0)
    target_vector: tuple[float, float, float] = (0.0, 1.0, 0.0)
    ideal_normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    actual_normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    history: deque = field(default_factory=lambda: deque(maxlen=720))

    def target_vector_scaled(self) -> tuple[float, float, float]:
        """Devuelve el vector R hacia el concentrador en escala real o maqueta."""
        if self.scale_to_model:
            # La documentacion del proyecto escala el target real de 5.55 m a
            # aproximadamente 0.47 m para la maqueta impresa.
            return (self.rx * 0.0844, self.ry * 0.0844, self.rz * 0.0844)
        return (self.rx, self.ry, self.rz)

    def compute_geometry(self) -> None:
        """Recalcula Sol, normal ideal, angulos objetivo y spot.

        La normal ideal se obtiene como bisectriz entre:
        - S: vector del heliostato hacia el Sol;
        - unit(R): vector unitario desde heliostato hacia concentrador/target.

        Esa normal se convierte a acimut/elevacion. Despues se aplican peralte
        y offsets. El peralte pertenece al heliostato, no a las facetas.
        """
        when = _dt.datetime.now() if self.use_live_time else self.simulated_time
        self.zenith, self.altitude, self.solar_azimuth, self.solar_source = solar_position(
            when, self.lat_deg, self.lon_deg, self.method
        )
        alt = self.altitude * DEG
        az = self.solar_azimuth * DEG
        self.sun_vector = (
            math.cos(alt) * math.sin(az),
            math.cos(alt) * math.cos(az),
            math.sin(alt),
        )
        self.target_vector = self.target_vector_scaled()
        t_unit = v_unit(self.target_vector)
        self.ideal_normal = v_unit(v_add(self.sun_vector, t_unit))
        acim, elev = angles_from_normal(self.ideal_normal)
        self.raw_target_acim = wrap_deg(acim + self.offset_acim + self.camera_offset_acim)
        self.raw_target_elev = elev + self.peralte + self.offset_ele + self.camera_offset_ele
        self.target_acim = self.raw_target_acim
        self.target_elev = clamp(self.raw_target_elev, 0.0, 90.0)
        self.target_saturated = abs(self.raw_target_elev - self.target_elev) > 1e-6
        self.actual_normal = normal_from_angles(self.az.angle_deg, self.el.angle_deg + self.peralte)
        self.compute_spot_error()

    def compute_spot_error(self) -> None:
        """Calcula donde cae el rayo reflejado sobre el plano del target.

        Usa la ley de reflexion:
            reflejado = incidente - 2 * dot(incidente, normal) * normal

        Luego intersecta ese rayo con el eje hacia el target y proyecta el error
        en una pantalla local. Los errores X/Z se guardan en metros.
        """
        t_unit = v_unit(self.target_vector)
        incoming = v_mul(self.sun_vector, -1.0)
        reflected = v_sub(incoming, v_mul(self.actual_normal, 2.0 * v_dot(incoming, self.actual_normal)))
        denom = v_dot(reflected, t_unit)
        if abs(denom) < 1e-9:
            self.spot_point = (float("nan"), float("nan"), float("nan"))
            self.spot_error_x = 0.0
            self.spot_error_z = 0.0
            return
        distance = v_dot(self.target_vector, t_unit) / denom
        self.spot_point = v_mul(reflected, distance)
        error_vec = v_sub(self.spot_point, self.target_vector)
        screen_x = v_unit(v_cross((0.0, 0.0, 1.0), t_unit))
        if v_norm(screen_x) < 1e-9:
            screen_x = (1.0, 0.0, 0.0)
        screen_z = v_unit(v_cross(t_unit, screen_x))
        self.spot_error_x = v_dot(error_vec, screen_x)
        self.spot_error_z = v_dot(error_vec, screen_z)

    def update(self, dt: float, target_override: tuple[float, float] | None = None) -> None:
        """Avanza un paso temporal de la simulacion.

        Si target_override existe, por ejemplo en modo Home, se usa ese objetivo
        angular en lugar del calculado por Sol/target. Si el modo automatico y
        seguimiento estan activos, mueve los ejes suavemente hacia el objetivo.
        """
        if not self.running:
            return
        self.compute_geometry()
        if target_override:
            self.az.target_deg = target_override[0]
            self.el.target_deg = target_override[1]
        else:
            self.az.target_deg = self.target_acim
            self.el.target_deg = self.target_elev
        if self.automatic and (self.tracking or target_override is not None) and not self.free_mode:
            self.az.update_closed_loop(dt, self.cdr)
            self.el.update_closed_loop(dt, self.cdr)
        else:
            self.az.ina = self.az.inb = self.el.ina = self.el.inb = 0
        self.iterations += 1
        self.history.append(
            {
                "t": self.iterations,
                "az": self.az.angle_deg,
                "el": self.el.angle_deg,
                "az_target": self.az.target_deg,
                "el_target": self.el.target_deg,
                "err_x": self.spot_error_x,
                "err_z": self.spot_error_z,
                "spot": self.spot_point,
            }
        )


class Gauge(tk.Canvas):
    """Perilla grafica para seleccionar PWM/velocidad entre 0 y 1.

    Se implementa con Canvas para parecerse mas a una perilla de panel de
    control. El usuario puede arrastrar directamente sobre la perilla; no se
    necesitan botones + y - para cambiar la velocidad.
    """

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        variable: tk.DoubleVar,
        command: Callable[[], None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(master, width=150, height=130, bg="#d8d8d8", highlightthickness=1, **kwargs)
        self.label = label
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self.set_from_pointer)
        self.bind("<B1-Motion>", self.set_from_pointer)

    def set_from_pointer(self, event: tk.Event) -> None:
        """Convierte la posicion del mouse dentro de la perilla a un valor 0..1."""
        cx, cy = 75, 72
        angle = math.degrees(math.atan2(cy - event.y, event.x - cx))
        value = (220.0 - angle) / 260.0
        if value < 0.0:
            value += 360.0 / 260.0
        self.variable.set(clamp(value, 0.0, 1.0))
        self.redraw()
        if self.command:
            self.command()

    def redraw(self) -> None:
        """Redibuja escala, marcas, aguja y porcentaje actual."""
        self.delete("all")
        self.create_text(75, 12, text=self.label, fill="#001a70", font=("Segoe UI", 10, "bold"))
        cx, cy, r = 75, 72, 48
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#eeeeee", outline="#888888", width=2)
        for i in range(11):
            value = i / 10.0
            ang = math.radians(220.0 - 260.0 * value)
            x1 = cx + math.cos(ang) * (r + 2)
            y1 = cy - math.sin(ang) * (r + 2)
            x2 = cx + math.cos(ang) * (r + 12)
            y2 = cy - math.sin(ang) * (r + 12)
            self.create_line(x1, y1, x2, y2, fill="#111111", width=1)
            tx = cx + math.cos(ang) * (r + 24)
            ty = cy - math.sin(ang) * (r + 24)
            self.create_text(tx, ty, text=f"{value:.1g}", font=("Segoe UI", 7))
        val = clamp(self.variable.get(), 0.0, 1.0)
        ang = math.radians(220.0 - 260.0 * val)
        nx = cx + math.cos(ang) * (r - 8)
        ny = cy - math.sin(ang) * (r - 8)
        self.create_line(cx, cy, nx, ny, fill="#d38a00", width=4)
        self.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#ffcc33", outline="#777777")
        self.create_text(75, 121, text=f"{val * 100:4.0f} %", fill="#111111", font=("Consolas", 9, "bold"))


class Switch(tk.Canvas):
    """Switch ON/OFF dibujado en Canvas.

    Reemplaza las casillas con X para que el panel sea mas claro visualmente.
    El valor real vive en una BooleanVar de Tkinter.
    """

    def __init__(self, master: tk.Misc, text: str, variable: tk.BooleanVar, command: Callable[[], None] | None = None) -> None:
        super().__init__(master, width=178, height=34, bg="#d6d6d6", highlightthickness=0)
        self.text = text
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self.toggle)
        self.redraw()

    def toggle(self, _event: tk.Event | None = None) -> None:
        """Invierte el valor booleano y notifica a la aplicacion."""
        self.variable.set(not bool(self.variable.get()))
        self.redraw()
        if self.command:
            self.command()

    def redraw(self) -> None:
        """Dibuja el switch en verde si esta ON o gris si esta OFF."""
        self.delete("all")
        on = bool(self.variable.get())
        self.create_text(0, 17, anchor="w", text=self.text, fill="#111111", font=("Segoe UI", 9))
        x0, y0, x1, y1 = 112, 6, 170, 28
        fill = "#29c463" if on else "#9aa0a6"
        self.create_oval(x0, y0, x0 + 22, y1, fill=fill, outline=fill)
        self.create_oval(x1 - 22, y0, x1, y1, fill=fill, outline=fill)
        self.create_rectangle(x0 + 11, y0, x1 - 11, y1, fill=fill, outline=fill)
        knob_x = x1 - 20 if on else x0 + 2
        self.create_oval(knob_x, y0 + 2, knob_x + 18, y1 - 2, fill="#ffffff", outline="#d0d0d0")
        self.create_text((x0 + x1) / 2, 17, text="ON" if on else "OFF", fill="#ffffff", font=("Segoe UI", 7, "bold"))


class DigitalTwinApp:
    """Aplicacion Tkinter completa del gemelo digital.

    Esta clase conecta tres capas:
    - TwinState: el modelo fisico/matematico simulado.
    - Variables Tkinter: valores editables desde la interfaz.
    - Canvas/ttk: panel de control y vistas graficas.

    El metodo loop() es el ciclo principal: lee controles, avanza la simulacion,
    actualiza lecturas y redibuja todas las vistas.
    """

    def __init__(self, root: tk.Tk) -> None:
        """Crea estado inicial, ventana, estilos, controles y arranca el ciclo."""
        self.root = root
        self.state = TwinState()
        self.last_tick = _dt.datetime.now()
        self.jog_command: tuple[str, int] | None = None
        self.vars: dict[str, tk.Variable] = {}
        self.gauges: list[Gauge] = []
        self.switches: list[Switch] = []
        self.mode_buttons: dict[str, ttk.Button] = {}
        self.manual_controls: list[ttk.Button] = []
        self.current_mode = "manual"
        self.event_log: deque[str] = deque(maxlen=80)
        self.samples: deque[dict[str, object]] = deque(maxlen=20000)
        self.replay_active = False
        self.replay_index = 0
        self.last_status_label = ""
        self.invalid_time_text = ""
        self.state.automatic = False
        self.state.free_mode = True
        self.set_home_pose_instant()
        self.root.title("Gemelo digital - Mini horno solar / Mini heliostato IER")
        self.root.geometry("1580x930")
        self.root.minsize(1280, 780)
        self.root.configure(bg="#242424")
        self.configure_style()
        self.build_ui()
        self.log_event("Inicio en manual y home: acimut 0 deg, elevacion 90 deg")
        self.sync_from_state()
        self.loop()

    def configure_style(self) -> None:
        """Define colores, tipografias y estilos ttk usados en toda la interfaz."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Panel.TFrame", background="#d6d6d6")
        style.configure("Inset.TFrame", background="#e8e8e8", relief="ridge", borderwidth=1)
        style.configure("Dark.TFrame", background="#242424")
        style.configure("Block.TLabelframe", background="#d6d6d6", bordercolor="#888888", relief="ridge")
        style.configure("Block.TLabelframe.Label", background="#d6d6d6", foreground="#1b1b1b", font=("Segoe UI", 10, "bold"))
        style.configure("Gold.TButton", background="#caa23a", foreground="#111111", borderwidth=2, focusthickness=0)
        style.map("Gold.TButton", background=[("active", "#e1bd54")])
        style.configure("Mode.TButton", background="#d3b044", foreground="#111111", borderwidth=1, padding=7, font=("Segoe UI", 9, "bold"))
        style.map("Mode.TButton", background=[("active", "#e4c45a")])
        style.configure("ActiveMode.TButton", background="#1f7a4d", foreground="#ffffff", borderwidth=2, padding=7, font=("Segoe UI", 9, "bold"))
        style.map("ActiveMode.TButton", background=[("active", "#24945d")])
        style.configure("Manual.TButton", background="#46566a", foreground="#ffffff", borderwidth=1, padding=5, font=("Segoe UI", 9, "bold"))
        style.map("Manual.TButton", background=[("active", "#5a708b")])
        style.configure("Green.TButton", background="#31c95b", foreground="#061906", borderwidth=2)
        style.map("Green.TButton", background=[("active", "#5ee67a")])
        style.configure("Red.TButton", background="#b80d0d", foreground="#ffffff", borderwidth=2)
        style.map("Red.TButton", background=[("active", "#d42121")])
        style.configure("Readout.TLabel", background="#e9e9e9", foreground="#cc0000", relief="sunken", padding=4, font=("Consolas", 10, "bold"))
        style.configure("Small.TLabel", background="#d6d6d6", foreground="#111111", font=("Segoe UI", 9))
        style.configure("ModeStatus.TLabel", background="#172432", foreground="#ffffff", padding=7, font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background="#c8a73a", foreground="#00185e", relief="raised", padding=7, font=("Segoe UI", 15, "bold"))

    def var(self, name: str, value: object) -> tk.Variable:
        """Crea y registra una variable Tkinter segun el tipo de valor inicial."""
        if isinstance(value, bool):
            v: tk.Variable = tk.BooleanVar(value=value)
        elif isinstance(value, int):
            v = tk.IntVar(value=value)
        elif isinstance(value, float):
            v = tk.DoubleVar(value=value)
        else:
            v = tk.StringVar(value=str(value))
        self.vars[name] = v
        return v

    def build_ui(self) -> None:
        """Construye la distribucion principal: panel izquierdo y pestanas derechas."""
        self.var("az_pwm", self.state.az.pwm)
        self.var("el_pwm", self.state.el.pwm)
        self.var("tracking", self.state.tracking)
        self.var("automatic", self.state.automatic)
        self.var("free_mode", self.state.free_mode)
        self.var("specific_time", not self.state.use_live_time)
        self.var("scale_to_model", self.state.scale_to_model)
        self.var("method", self.state.method)
        self.var("view_mode", "Isometrica")
        self.var("mode_status", "MODO ACTIVO: MANUAL / MOVIMIENTO LIBRE")
        self.var("date_text", self.state.simulated_time.strftime("%Y-%m-%d"))
        self.var("time_text", self.state.simulated_time.strftime("%H:%M:%S"))
        for name in (
            "lat_deg",
            "lon_deg",
            "rx",
            "ry",
            "rz",
            "peralte",
            "offset_ele",
            "offset_acim",
            "camera_offset_ele",
            "camera_offset_acim",
            "cdr",
            "delay_s",
            "mirror_size_m",
            "base_width_m",
            "fork_height_m",
            "rail_length_m",
            "receiver_screen_m",
            "uncertainty_gain",
        ):
            self.var(name, getattr(self.state, name))
        self.var("az_limit_min", self.state.az.limit_min)
        self.var("az_limit_max", self.state.az.limit_max)
        self.var("el_limit_min", self.state.el.limit_min)
        self.var("el_limit_max", self.state.el.limit_max)
        self.var("az_counts_per_degree", self.state.az.counts_per_degree)
        self.var("el_counts_per_degree", self.state.el.counts_per_degree)
        self.var("az_deg_per_second", self.state.az.deg_per_second_at_full_pwm)
        self.var("el_deg_per_second", self.state.el.deg_per_second_at_full_pwm)

        main = ttk.Frame(self.root, style="Dark.TFrame")
        main.pack(fill="both", expand=True, padx=8, pady=8)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # El panel izquierdo puede crecer mas que la ventana; por eso se coloca
        # dentro de un Canvas con scrollbar vertical.
        left_outer = ttk.Frame(main, style="Panel.TFrame", width=530)
        left_outer.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        left_outer.grid_propagate(False)
        left_outer.rowconfigure(0, weight=1)
        left_outer.columnconfigure(0, weight=1)
        left_canvas = tk.Canvas(left_outer, bg="#d6d6d6", highlightthickness=0, width=510)
        left_scroll = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll.grid(row=0, column=1, sticky="ns")
        left = ttk.Frame(left_canvas, style="Panel.TFrame")
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda _event: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.bind("<Configure>", lambda event: left_canvas.itemconfigure(left_window, width=event.width))
        left_canvas.bind_all("<MouseWheel>", lambda event: left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        right = ttk.Frame(main, style="Dark.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Label(left, text="Sistema de Control Horno Solar IER - Gemelo Digital", style="Title.TLabel").pack(fill="x", padx=10, pady=(10, 8))
        self.build_mode_block(left)
        self.build_motor_block(left)
        self.build_geometry_block(left)
        self.build_auto_block(left)
        self.build_calibration_block(left)
        self.build_status_block(left)

        # Las vistas graficas del gemelo se organizan como pestanas para que el
        # usuario pueda cambiar entre 3D, spot, trayectoria solar y diagnostico.
        notebook = ttk.Notebook(right)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.scene_canvas = tk.Canvas(notebook, bg="#101821", highlightthickness=0)
        self.receiver_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.solar_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.diagnostic_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.logic_canvas = tk.Canvas(notebook, bg="#f7f7f7", highlightthickness=0)
        self.log_canvas = tk.Canvas(notebook, bg="#f7f7f7", highlightthickness=0)
        notebook.add(self.scene_canvas, text="Gemelo 3D")
        notebook.add(self.receiver_canvas, text="Pantalla / spot")
        notebook.add(self.solar_canvas, text="Trayectoria solar")
        notebook.add(self.diagnostic_canvas, text="Diagnostico")
        notebook.add(self.logic_canvas, text="Flujo del gemelo")
        notebook.add(self.log_canvas, text="Eventos")

    def build_mode_block(self, parent: ttk.Frame) -> None:
        """Construye el bloque de modo: Automatico, Manual, Home y fecha activa."""
        frame = ttk.LabelFrame(parent, text="Modo", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=(6, 8))
        self.mode_label = ttk.Label(frame, textvariable=self.vars["mode_status"], style="ModeStatus.TLabel")
        self.mode_label.pack(fill="x", padx=10, pady=(8, 6))
        row = ttk.Frame(frame, style="Inset.TFrame")
        row.pack(fill="x", padx=10, pady=(0, 8))
        for col, (key, text) in enumerate((("auto", "Automatico"), ("manual", "Manual"), ("home", "Home"))):
            button = ttk.Button(row, text=text, style="Mode.TButton", command=lambda k=key: self.set_mode(k))
            button.grid(row=0, column=col, sticky="ew", padx=4, pady=5)
            self.mode_buttons[key] = button
            row.columnconfigure(col, weight=1)
        switches = ttk.Frame(frame, style="Panel.TFrame")
        switches.pack(fill="x", padx=2, pady=(0, 4))
        self.add_switch(switches, "Fecha especifica", "specific_time")
        date_row = ttk.Frame(frame, style="Inset.TFrame")
        date_row.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(date_row, text="Fecha", style="Small.TLabel").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)
        ttk.Entry(date_row, textvariable=self.vars["date_text"], width=12).grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        ttk.Label(date_row, text="Hora", style="Small.TLabel").grid(row=0, column=2, sticky="w", padx=(12, 4), pady=6)
        ttk.Entry(date_row, textvariable=self.vars["time_text"], width=12).grid(row=0, column=3, sticky="ew", padx=(4, 8), pady=6)
        date_row.columnconfigure(1, weight=1)
        date_row.columnconfigure(3, weight=1)
        ttk.Label(
            frame,
            text="Fecha especifica ON usa estos campos; OFF usa fecha y hora actuales.",
            style="Small.TLabel",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        for i in range(3):
            row.columnconfigure(i, weight=1)
        self.update_mode_visuals()

    def build_motor_block(self, parent: ttk.Frame) -> None:
        """Construye controles manuales de motores y perillas de velocidad."""
        frame = ttk.LabelFrame(parent, text="Control Motor Acimut / Elevacion", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(frame, text="Movimiento manual", style="Small.TLabel").pack(anchor="w", padx=12, pady=(6, 0))
        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x", padx=8, pady=6)
        for col, (axis, title, varname, motor_var, minus, plus) in enumerate(
            (
                ("az", "Acimut", "az_pwm", "az_motor_on", "Oeste", "Este"),
                ("el", "Elevacion", "el_pwm", "el_motor_on", "Bajar", "Subir"),
            )
        ):
            card = ttk.Frame(row, style="Inset.TFrame")
            card.grid(row=0, column=col, sticky="nsew", padx=5)
            row.columnconfigure(col, weight=1)
            gauge = Gauge(card, f"Velocidad {title}", self.vars[varname], command=self.apply_controls)
            gauge.pack(padx=4, pady=(6, 0))
            self.gauges.append(gauge)
            self.add_switch(card, f"Motor {title}", motor_var, create_if_missing=True)
            controls = ttk.Frame(card, style="Inset.TFrame")
            controls.pack(fill="x", padx=8, pady=(4, 8))
            b_minus = ttk.Button(controls, text=f"< {minus}", style="Manual.TButton", command=lambda a=axis: self.start_jog(a, -1))
            b_stop = ttk.Button(controls, text="Detener", style="Manual.TButton", command=self.stop_jog)
            b_plus = ttk.Button(controls, text=f"{plus} >", style="Manual.TButton", command=lambda a=axis: self.start_jog(a, 1))
            for idx, button in enumerate((b_minus, b_stop, b_plus)):
                button.grid(row=0, column=idx, sticky="ew", padx=2, pady=2)
                controls.columnconfigure(idx, weight=1)
                self.manual_controls.append(button)

    def build_geometry_block(self, parent: ttk.Frame) -> None:
        """Construye entradas de ubicacion, metodo solar y target RX/RY/RZ."""
        frame = ttk.LabelFrame(parent, text="Ubicacion, vector solar y concentrador", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.readouts = {}
        location = ttk.Frame(grid, style="Inset.TFrame")
        target = ttk.Frame(grid, style="Inset.TFrame")
        location.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        target.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        ttk.Label(location, text="Ubicacion / vector solar", style="Small.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=6, pady=(5, 2))
        ttk.Label(location, text="TEMIXCO, MOR. MX", style="Small.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=2)
        self.add_entry(location, "Latitud", "lat_deg", 2, 0)
        self.add_entry(location, "Longitud", "lon_deg", 3, 0)
        ttk.Label(location, text="Metodo solar", style="Small.TLabel").grid(row=4, column=0, sticky="w", pady=2, padx=2)
        ttk.OptionMenu(location, self.vars["method"], self.state.method, "D&B", "REDA", "SPA/PVLIB", command=lambda _=None: self.apply_controls()).grid(row=4, column=1, sticky="ew", pady=2)
        for idx, key in enumerate(("zenith", "altitude", "solar_azimuth")):
            label = ("Angulo Zenit", "Altura Solar", "Angulo Acimut")[idx]
            ttk.Label(location, text=label, style="Small.TLabel").grid(row=5 + idx, column=0, sticky="w", pady=2, padx=2)
            out = ttk.Label(location, text="0.000", style="Readout.TLabel")
            out.grid(row=5 + idx, column=1, sticky="ew", pady=2, padx=2)
            self.readouts[key] = out
        location.columnconfigure(1, weight=1)

        ttk.Label(target, text="Concentrador / Target", style="Small.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(5, 2))
        self.add_entry(target, "RX", "rx", 1, 0)
        self.add_entry(target, "RY", "ry", 2, 0)
        self.add_entry(target, "RZ", "rz", 3, 0)
        self.add_entry(target, "Peralte Helio", "peralte", 4, 0)
        self.add_entry(target, "Offset Elev", "offset_ele", 5, 0)
        self.add_entry(target, "Offset Acim", "offset_acim", 6, 0)
        target.columnconfigure(1, weight=1)

    def build_auto_block(self, parent: ttk.Frame) -> None:
        """Construye controles de seguimiento, cdr, refresco y vista 3D."""
        frame = ttk.LabelFrame(parent, text="Seguimiento y objetivo", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.add_switch(grid, "Seguimiento", "tracking", row=0, col=0)
        self.add_switch(grid, "Escalar R a maqueta", "scale_to_model", row=0, col=2)
        self.add_entry(grid, "Consideracion (+/- cdr)", "cdr", 1, 0)
        self.add_entry(grid, "Refresco (s)", "delay_s", 1, 2)
        ttk.Label(grid, text="Vista 3D", style="Small.TLabel").grid(row=2, column=0, sticky="w", pady=2, padx=2)
        ttk.OptionMenu(
            grid,
            self.vars["view_mode"],
            self.vars["view_mode"].get(),
            "Isometrica",
            "Frontal",
            "Lateral",
            "Superior",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=2, column=1, sticky="ew", pady=2, padx=2)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

    def build_calibration_block(self, parent: ttk.Frame) -> None:
        """Construye parametros de calibracion visual y de movimiento simulado.

        Los valores de geometria solo cambian la representacion 3D. Los limites
        y velocidades si afectan la dinamica de los ejes simulados.
        """
        frame = ttk.LabelFrame(parent, text="Calibracion del gemelo", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        ttk.Label(grid, text="Dimensiones para dibujar el gemelo 3D", style="Small.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", padx=2, pady=(2, 4))
        self.add_entry(grid, "Espejo lado (m)", "mirror_size_m", 1, 0)
        self.add_entry(grid, "Base ancho (m)", "base_width_m", 1, 2)
        self.add_entry(grid, "Horquilla alto (m)", "fork_height_m", 2, 0)
        self.add_entry(grid, "Riel largo (m)", "rail_length_m", 2, 2)
        self.add_entry(grid, "Pantalla diam. (m)", "receiver_screen_m", 3, 0)
        self.add_entry(grid, "Zona cdr x", "uncertainty_gain", 3, 2)
        ttk.Label(
            grid,
            text="Estos valores solo ajustan la apariencia y la zona de tolerancia visual.",
            style="Small.TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=4, column=0, columnspan=4, sticky="ew", padx=2, pady=(2, 8))
        ttk.Label(grid, text="Limites y velocidad del movimiento simulado", style="Small.TLabel").grid(row=5, column=0, columnspan=4, sticky="w", padx=2, pady=(2, 4))
        self.add_entry(grid, "Acimut min (deg)", "az_limit_min", 6, 0)
        self.add_entry(grid, "Acimut max (deg)", "az_limit_max", 6, 2)
        self.add_entry(grid, "Elev min (deg)", "el_limit_min", 7, 0)
        self.add_entry(grid, "Elev max (deg)", "el_limit_max", 7, 2)
        self.add_entry(grid, "Vel acimut (deg/s)", "az_deg_per_second", 8, 0)
        self.add_entry(grid, "Vel elev (deg/s)", "el_deg_per_second", 8, 2)
        ttk.Label(
            grid,
            text="Los conteos de encoder se mantienen internos porque vienen de la escala del VI/LabVIEW y no suelen requerir ajuste manual.",
            style="Small.TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=9, column=0, columnspan=4, sticky="ew", padx=2, pady=(4, 2))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)

    def build_status_block(self, parent: ttk.Frame) -> None:
        """Construye lecturas de estado, errores, contadores y botones globales."""
        frame = ttk.LabelFrame(parent, text="Status Heliostato", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.state_banner = tk.Label(
            grid,
            text="Estado: inicializando",
            bg="#172432",
            fg="#ffffff",
            padx=8,
            pady=6,
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        )
        self.state_banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        self.state_detail = ttk.Label(grid, text="", style="Small.TLabel", wraplength=420, justify="left")
        self.state_detail.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        labels = [
            ("Grados Elevacion", "el_angle"),
            ("Grados Acimut", "az_angle"),
            ("Altura Target + Offset", "target_elev"),
            ("Acimut Target + Offset", "target_acim"),
            ("Counter Ele", "el_counts"),
            ("Counter Acim", "az_counts"),
            ("Spot X/Z mm", "spot"),
            ("Error angular", "angular_error"),
            ("Limites", "limit_status"),
            ("Estado motores", "motor_status"),
            ("Iteraciones", "iterations"),
        ]
        for row, (label, key) in enumerate(labels):
            ui_row = row + 2
            ttk.Label(grid, text=label, style="Small.TLabel").grid(row=ui_row, column=0, sticky="w", pady=2)
            out = ttk.Label(grid, text="0", style="Readout.TLabel")
            out.grid(row=ui_row, column=1, sticky="ew", pady=2)
            self.readouts[key] = out
        grid.columnconfigure(1, weight=1)
        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="RESET", style="Gold.TButton", command=self.reset_axes).pack(side="left", padx=3)
        ttk.Button(buttons, text="STOP PROGRAM", style="Red.TButton", command=self.toggle_run).pack(side="left", padx=3)
        ttk.Button(buttons, text="EXPORT CSV", style="Gold.TButton", command=self.export_csv).pack(side="left", padx=3)
        ttk.Button(buttons, text="REPLAY", style="Gold.TButton", command=self.start_replay).pack(side="left", padx=3)
        ttk.Button(buttons, text="LIVE", style="Manual.TButton", command=self.stop_replay).pack(side="left", padx=3)

    def add_switch(
        self,
        parent: tk.Misc,
        label: str,
        varname: str,
        row: int | None = None,
        col: int = 0,
        create_if_missing: bool = False,
    ) -> Switch:
        """Agrega un switch ON/OFF y lo enlaza a una variable Tkinter."""
        if create_if_missing and varname not in self.vars:
            self.var(varname, True)
        switch = Switch(parent, label, self.vars[varname], command=self.apply_controls)
        self.switches.append(switch)
        if row is None:
            switch.pack(anchor="w", padx=12, pady=2)
        else:
            switch.grid(row=row, column=col, columnspan=2, sticky="w", padx=4, pady=2)
        return switch

    def add_entry(self, parent: ttk.Frame, label: str, varname: str, row: int, col: int) -> None:
        """Agrega etiqueta + caja de texto y aplica cambios con Enter o foco fuera."""
        ttk.Label(parent, text=label, style="Small.TLabel").grid(row=row, column=col, sticky="w", pady=2, padx=2)
        entry = ttk.Entry(parent, textvariable=self.vars[varname], width=9)
        entry.grid(row=row, column=col + 1, sticky="ew", pady=2, padx=2)
        entry.bind("<Return>", lambda _event: self.apply_controls())
        entry.bind("<FocusOut>", lambda _event: self.apply_controls())

    def log_event(self, message: str) -> None:
        """Agrega un mensaje a la bitacora evitando duplicados consecutivos."""
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        if self.event_log and self.event_log[-1].endswith(message):
            return
        self.event_log.append(f"{stamp}  {message}")

    def axis_errors(self) -> tuple[float, float]:
        """Devuelve error angular de acimut y elevacion en grados."""
        return (
            wrap_deg(self.state.az.target_deg - self.state.az.angle_deg),
            self.state.el.target_deg - self.state.el.angle_deg,
        )

    def limit_messages(self) -> list[str]:
        """Detecta condiciones relacionadas con limites mecanicos simulados."""
        s = self.state
        messages: list[str] = []
        if not (s.az.limit_min <= s.az.target_deg <= s.az.limit_max):
            messages.append("Acimut objetivo fuera de limite mecanico")
        if s.target_saturated:
            messages.append("Elevacion objetivo recortada a 0-90 deg")
        if abs(s.az.angle_deg - s.az.limit_min) <= 0.05 or abs(s.az.angle_deg - s.az.limit_max) <= 0.05:
            messages.append("Acimut en tope")
        if abs(s.el.angle_deg - s.el.limit_min) <= 0.05 or abs(s.el.angle_deg - s.el.limit_max) <= 0.05:
            messages.append("Elevacion en tope")
        return messages

    def validation_messages(self) -> list[str]:
        """Devuelve solo el texto de alertas/validaciones activas."""
        return [message for _severity, message in self.alert_items()]

    def alert_items(self) -> list[tuple[str, str]]:
        """Clasifica alertas como critica, advertencia o info.

        Las criticas indican que la geometria o el movimiento no son confiables
        (por ejemplo Sol bajo horizonte o fecha invalida). Las advertencias
        indican que algo impide llegar al objetivo. Las informativas describen
        estados normales como modo manual o seguimiento apagado.
        """
        s = self.state
        messages: list[tuple[str, str]] = []
        for message in self.limit_messages():
            messages.append(("critica", message))
        if self.invalid_time_text:
            messages.append(("critica", self.invalid_time_text))
        if s.altitude <= 0.0:
            messages.append(("critica", "Sol bajo horizonte: geometria no operativa"))
        az_err, el_err = self.axis_errors()
        if self.current_mode in ("auto", "home") and (abs(az_err) > s.cdr or abs(el_err) > s.cdr):
            if not s.az.motor_on or not s.el.motor_on:
                messages.append(("advertencia", "Hay error angular y algun motor esta apagado"))
        if self.current_mode == "manual" and self.jog_command is None:
            messages.append(("info", "Manual activo: espera comando libre"))
        if not s.tracking and self.current_mode == "auto":
            messages.append(("info", "Seguimiento apagado"))
        if "no disponible" in s.solar_source:
            messages.append(("info", s.solar_source))
        return messages

    def system_status(self) -> tuple[str, str, str]:
        """Resume el estado operacional para el banner principal."""
        s = self.state
        az_err, el_err = self.axis_errors()
        moving = bool(s.az.ina or s.az.inb or s.el.ina or s.el.inb or self.jog_command)
        near_target = abs(az_err) <= s.cdr and abs(el_err) <= s.cdr
        at_home = abs(wrap_deg(s.az.angle_deg)) <= s.cdr and abs(s.el.angle_deg - 90.0) <= s.cdr
        alerts = [item for item in self.alert_items() if item[0] != "info"]
        has_critical = any(severity == "critica" for severity, _message in alerts)
        if has_critical:
            label, color = "ALERTA", "#9f1239"
        elif alerts:
            label, color = "ADVERTENCIA", "#b7791f"
        elif self.current_mode == "home" and at_home:
            label, color = "EN HOME", "#1f7a4d"
        elif self.current_mode == "manual" and moving:
            label, color = "MOVIMIENTO MANUAL", "#2563eb"
        elif self.current_mode == "manual":
            label, color = "MANUAL / LISTO", "#172432"
        elif moving:
            label, color = "MOVIENDO", "#b7791f"
        elif near_target:
            label, color = "EN OBJETIVO", "#1f7a4d"
        else:
            label, color = "ESPERANDO ACTUACION", "#6b4e16"
        detail_parts = [
            f"Modo {self.current_mode.upper()}",
            f"Err AZ {az_err:+.2f} deg",
            f"Err EL {el_err:+.2f} deg",
        ]
        if alerts:
            detail_parts.append("; ".join(message for _severity, message in alerts[:2]))
        return label, color, " | ".join(detail_parts)

    def set_mode(self, mode: str) -> None:
        """Cambia entre automatico, manual y home.

        - Automatico: calcula objetivo solar y mueve ejes si seguimiento esta ON.
        - Manual: habilita jog libre por botones.
        - Home: mueve suavemente a acimut 0 deg y elevacion 90 deg.
        """
        self.current_mode = mode
        self.jog_command = None
        if mode == "auto":
            self.vars["automatic"].set(True)
            self.vars["free_mode"].set(False)
            self.vars["mode_status"].set("MODO ACTIVO: AUTOMATICO")
            self.log_event("Modo automatico")
        elif mode == "manual":
            self.vars["automatic"].set(False)
            self.vars["free_mode"].set(True)
            self.vars["mode_status"].set("MODO ACTIVO: MANUAL / MOVIMIENTO LIBRE")
            self.log_event("Modo manual libre")
        else:
            self.vars["automatic"].set(True)
            self.vars["free_mode"].set(False)
            self.vars["mode_status"].set("MODO ACTIVO: HOME POSITION")
            self.state.az.target_deg = 0.0
            self.state.el.target_deg = 90.0
            self.log_event("Home solicitado: objetivo 0/90 deg")
        self.apply_controls()
        self.update_mode_visuals()

    def set_home_pose_instant(self) -> None:
        """Coloca instantaneamente el heliostato en home al iniciar el programa."""
        self.state.az.angle_deg = 0.0
        self.state.el.angle_deg = 90.0
        self.state.az.counts = int(round(self.state.az.angle_deg * self.state.az.counts_per_degree))
        self.state.el.counts = int(round(self.state.el.angle_deg * self.state.el.counts_per_degree))
        self.state.az.ina = self.state.az.inb = self.state.el.ina = self.state.el.inb = 0
        self.state.history.clear()

    def home_position(self) -> None:
        """Solicita home como objetivo; el movimiento posterior es fluido."""
        self.current_mode = "home"
        self.jog_command = None
        self.vars["automatic"].set(True)
        self.vars["free_mode"].set(False)
        self.vars["mode_status"].set("MODO ACTIVO: HOME POSITION")
        self.state.az.target_deg = 0.0
        self.state.el.target_deg = 90.0
        self.log_event("Home solicitado: objetivo 0/90 deg")
        self.update_mode_visuals()

    def reset_axes(self) -> None:
        """Reinicia iteraciones y solicita retorno a home."""
        self.home_position()
        self.state.iterations = 0
        self.log_event("Reset de iteraciones y retorno a home")

    def toggle_run(self) -> None:
        """Pausa o reanuda la simulacion sin cerrar la interfaz."""
        self.state.running = not self.state.running
        self.log_event("Programa en marcha" if self.state.running else "Programa pausado")

    def start_jog(self, axis: str, direction: int) -> None:
        """Inicia movimiento manual continuo en un eje."""
        if self.current_mode != "manual":
            self.set_mode("manual")
        self.jog_command = (axis, direction)
        axis_name = "acimut" if axis == "az" else "elevacion"
        self.log_event(f"Jog {axis_name} {'+' if direction > 0 else '-'}")

    def stop_jog(self) -> None:
        """Detiene cualquier movimiento manual y apaga direcciones simuladas."""
        self.jog_command = None
        self.state.az.ina = self.state.az.inb = self.state.el.ina = self.state.el.inb = 0
        self.log_event("Jog detenido")

    def align_to_current_target(self) -> None:
        """Actualiza el objetivo angular con la geometria actual sin mover ejes."""
        self.state.compute_geometry()
        self.state.az.target_deg = self.state.target_acim
        self.state.el.target_deg = self.state.target_elev
        self.state.az.ina = self.state.az.inb = self.state.el.ina = self.state.el.inb = 0

    def apply_controls(self) -> None:
        """Copia valores de la interfaz hacia TwinState.

        Esta funcion es el puente entre Tkinter y el modelo. Convierte texto a
        float/bool cuando corresponde, valida fecha especifica, actualiza PWM,
        limites, velocidades y parametros visuales.
        """
        # Primero se copian variables cuyo nombre coincide directamente con un
        # atributo de TwinState, por ejemplo lat_deg, rx, peralte o delay_s.
        for name, var in self.vars.items():
            try:
                value = var.get()
            except tk.TclError:
                continue
            if hasattr(self.state, name):
                try:
                    current = getattr(self.state, name)
                    if isinstance(current, bool):
                        setattr(self.state, name, bool(value))
                    elif isinstance(current, float):
                        setattr(self.state, name, float(value))
                    else:
                        setattr(self.state, name, value)
                except (TypeError, ValueError):
                    pass

        # Metodo solar y fecha/hora activa. Si "Fecha especifica" esta OFF,
        # siempre se usa la hora real del sistema.
        self.state.method = str(self.vars["method"].get())
        self.state.use_live_time = not bool(self.vars["specific_time"].get())
        if not self.state.use_live_time:
            try:
                date_text = str(self.vars["date_text"].get()).strip()
                time_text = str(self.vars["time_text"].get()).strip()
                self.state.simulated_time = _dt.datetime.fromisoformat(f"{date_text}T{time_text}")
                if self.invalid_time_text:
                    self.log_event("Fecha especifica valida restaurada")
                self.invalid_time_text = ""
            except ValueError:
                if not self.invalid_time_text:
                    self.log_event("Fecha/hora especifica invalida")
                self.invalid_time_text = "Fecha/hora especifica invalida"
        else:
            self.invalid_time_text = ""

        # Variables propias de cada eje: velocidad por PWM, motor ON/OFF,
        # limites, escala de conteo y velocidad maxima.
        self.state.az.pwm = float(self.vars["az_pwm"].get())
        self.state.el.pwm = float(self.vars["el_pwm"].get())
        self.state.az.motor_on = bool(self.vars["az_motor_on"].get())
        self.state.el.motor_on = bool(self.vars["el_motor_on"].get())
        self.state.az.limit_min = float(self.vars["az_limit_min"].get())
        self.state.az.limit_max = float(self.vars["az_limit_max"].get())
        self.state.el.limit_min = float(self.vars["el_limit_min"].get())
        self.state.el.limit_max = float(self.vars["el_limit_max"].get())
        self.state.az.counts_per_degree = max(1.0, float(self.vars["az_counts_per_degree"].get()))
        self.state.el.counts_per_degree = max(1.0, float(self.vars["el_counts_per_degree"].get()))
        self.state.az.deg_per_second_at_full_pwm = max(0.1, float(self.vars["az_deg_per_second"].get()))
        self.state.el.deg_per_second_at_full_pwm = max(0.1, float(self.vars["el_deg_per_second"].get()))
        self.state.az.angle_deg = clamp(self.state.az.angle_deg, self.state.az.limit_min, self.state.az.limit_max)
        self.state.el.angle_deg = clamp(self.state.el.angle_deg, self.state.el.limit_min, self.state.el.limit_max)
        self.state.az.counts = int(round(self.state.az.angle_deg * self.state.az.counts_per_degree))
        self.state.el.counts = int(round(self.state.el.angle_deg * self.state.el.counts_per_degree))

        # Saneamiento de parametros para evitar valores negativos o imposibles.
        self.state.cdr = max(0.0, float(self.state.cdr))
        self.state.delay_s = max(0.01, float(self.state.delay_s))
        self.state.mirror_size_m = max(0.05, float(self.state.mirror_size_m))
        self.state.base_width_m = max(0.05, float(self.state.base_width_m))
        self.state.fork_height_m = max(0.05, float(self.state.fork_height_m))
        self.state.rail_length_m = max(0.10, float(self.state.rail_length_m))
        self.state.receiver_screen_m = max(0.03, float(self.state.receiver_screen_m))
        self.state.uncertainty_gain = max(0.0, float(self.state.uncertainty_gain))

    def snapshot(self) -> dict[str, object]:
        """Crea una muestra exportable del estado actual del gemelo."""
        s = self.state
        return {
            "timestamp": (_dt.datetime.now() if s.use_live_time else s.simulated_time).isoformat(timespec="seconds"),
            "iteration": s.iterations,
            "mode": self.current_mode,
            "state": self.last_status_label,
            "az_deg": s.az.angle_deg,
            "el_deg": s.el.angle_deg,
            "az_target_deg": s.az.target_deg,
            "el_target_deg": s.el.target_deg,
            "az_error_deg": wrap_deg(s.az.target_deg - s.az.angle_deg),
            "el_error_deg": s.el.target_deg - s.el.angle_deg,
            "spot_x_mm": s.spot_error_x * 1000.0,
            "spot_z_mm": s.spot_error_z * 1000.0,
            "zenith_deg": s.zenith,
            "altitude_deg": s.altitude,
            "solar_azimuth_deg": s.solar_azimuth,
            "rx_m": s.rx,
            "ry_m": s.ry,
            "rz_m": s.rz,
            "peralte_deg": s.peralte,
            "cdr_deg": s.cdr,
            "az_motor_on": s.az.motor_on,
            "el_motor_on": s.el.motor_on,
            "az_pwm": s.az.pwm,
            "el_pwm": s.el.pwm,
        }

    def record_sample(self) -> None:
        """Guarda una muestra de sesion si no se esta reproduciendo replay."""
        if not self.replay_active and self.state.iterations > 0:
            self.samples.append(self.snapshot())

    def apply_replay_sample(self, sample: dict[str, object]) -> None:
        """Carga una muestra grabada en el estado visible del gemelo."""
        s = self.state
        s.az.angle_deg = float(sample["az_deg"])
        s.el.angle_deg = float(sample["el_deg"])
        s.az.target_deg = float(sample["az_target_deg"])
        s.el.target_deg = float(sample["el_target_deg"])
        s.spot_error_x = float(sample["spot_x_mm"]) / 1000.0
        s.spot_error_z = float(sample["spot_z_mm"]) / 1000.0
        s.zenith = float(sample["zenith_deg"])
        s.altitude = float(sample["altitude_deg"])
        s.solar_azimuth = float(sample["solar_azimuth_deg"])
        s.az.counts = int(round(s.az.angle_deg * s.az.counts_per_degree))
        s.el.counts = int(round(s.el.angle_deg * s.el.counts_per_degree))

    def start_replay(self) -> None:
        """Activa reproduccion ciclica de las muestras capturadas."""
        if not self.samples:
            self.log_event("Replay sin datos")
            return
        self.replay_active = True
        self.replay_index = 0
        self.log_event(f"Replay iniciado con {len(self.samples)} muestras")

    def stop_replay(self) -> None:
        """Sale de replay y vuelve a simulacion viva."""
        if self.replay_active:
            self.log_event("Replay detenido; retorno a vivo")
        self.replay_active = False

    def export_csv(self) -> None:
        """Exporta las muestras capturadas a un archivo CSV."""
        if not self.samples:
            self.log_event("Export CSV sin muestras")
            return

        # Las exportaciones se proponen en digital_twin/logs, pero el usuario
        # puede elegir otra ruta mediante el dialogo de guardado.
        default_dir = Path(__file__).resolve().parent / "logs"
        default_dir.mkdir(exist_ok=True)
        default_name = f"gemelo_digital_{_dt.datetime.now():%Y%m%d_%H%M%S}.csv"
        try:
            path_text = filedialog.asksaveasfilename(
                title="Exportar datos del gemelo",
                initialdir=str(default_dir),
                initialfile=default_name,
                defaultextension=".csv",
                filetypes=(("CSV", "*.csv"), ("Todos", "*.*")),
            )
        except tk.TclError:
            path_text = str(default_dir / default_name)
        if not path_text:
            return
        path = Path(path_text)
        fieldnames = list(self.samples[0].keys())
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.samples)
        self.log_event(f"CSV exportado: {path.name}")
        try:
            messagebox.showinfo("Export CSV", f"Datos exportados:\n{path}")
        except tk.TclError:
            pass

    def sync_from_state(self) -> None:
        """Redibuja controles custom y actualiza estilos de modo."""
        for gauge in self.gauges:
            gauge.redraw()
        for switch in self.switches:
            switch.redraw()
        self.update_mode_visuals()

    def update_mode_visuals(self) -> None:
        """Resalta el modo activo y habilita/deshabilita controles manuales."""
        for key, button in self.mode_buttons.items():
            button.configure(style="ActiveMode.TButton" if key == self.current_mode else "Mode.TButton")
        manual_state = "normal" if self.current_mode == "manual" else "disabled"
        for button in self.manual_controls:
            button.configure(state=manual_state)

    def loop(self) -> None:
        """Ciclo principal de la aplicacion.

        En cada iteracion:
        1. Calcula dt desde el ciclo anterior.
        2. Si hay replay, carga la siguiente muestra.
        3. Si esta en vivo, lee controles y avanza la simulacion.
        4. Actualiza lecturas, registra muestra y redibuja pestanas.
        5. Programa el siguiente ciclo con root.after().
        """
        now = _dt.datetime.now()
        dt = max(0.001, (now - self.last_tick).total_seconds())
        self.last_tick = now
        if self.replay_active and self.samples:
            sample = list(self.samples)[self.replay_index]
            self.apply_replay_sample(sample)
            self.replay_index += 1
            if self.replay_index >= len(self.samples):
                self.replay_index = 0
        else:
            self.apply_controls()
            if self.jog_command and not self.state.automatic:
                axis, direction = self.jog_command
                if axis == "az":
                    self.state.az.jog(direction, dt)
                else:
                    self.state.el.jog(direction, dt)
            target_override = (0.0, 90.0) if self.current_mode == "home" else None
            self.state.update(dt, target_override=target_override)
        self.update_readouts()
        self.record_sample()
        self.draw_scene()
        self.draw_receiver_view()
        self.draw_solar_path()
        self.draw_diagnostic_view()
        self.draw_logic()
        self.draw_event_log()
        self.sync_from_state()
        delay_ms = int(max(20, self.state.delay_s * 1000.0))
        self.root.after(delay_ms, self.loop)

    def update_readouts(self) -> None:
        """Actualiza los textos numericos del panel de status."""
        s = self.state
        status_label, status_color, status_detail = self.system_status()
        if status_label != self.last_status_label:
            self.log_event(f"Estado: {status_label}")
            self.last_status_label = status_label
        self.state_banner.configure(text=f"Estado: {status_label}", bg=status_color)
        self.state_detail.configure(text=status_detail)
        limit_text = "; ".join(self.limit_messages()) if self.limit_messages() else "Dentro de rango"
        values = {
            "zenith": f"{s.zenith:8.4f}",
            "altitude": f"{s.altitude:8.4f}",
            "solar_azimuth": f"{s.solar_azimuth:8.4f}",
            "el_angle": f"{s.el.angle_deg:8.4f}",
            "az_angle": f"{s.az.angle_deg:8.4f}",
            "target_elev": f"{s.el.target_deg:8.4f}",
            "target_acim": f"{s.az.target_deg:8.4f}",
            "el_counts": f"{s.el.counts:d}",
            "az_counts": f"{s.az.counts:d}",
            "spot": f"{s.spot_error_x * 1000.0:7.1f} / {s.spot_error_z * 1000.0:7.1f}",
            "angular_error": f"{wrap_deg(s.az.target_deg - s.az.angle_deg):6.2f} / {s.el.target_deg - s.el.angle_deg:6.2f}",
            "limit_status": limit_text,
            "motor_status": f"AZ {'ON' if s.az.motor_on else 'OFF'} | EL {'ON' if s.el.motor_on else 'OFF'}",
            "iterations": f"{s.iterations:d}",
        }
        for key, text in values.items():
            self.readouts[key].configure(text=text)

    def project(self, point: tuple[float, float, float], width: int, height: int, scale: float = 540.0) -> tuple[float, float, float]:
        """Proyecta un punto 3D del modelo a coordenadas 2D de Canvas.

        No es un motor 3D real; es una proyeccion ortografica simple con cuatro
        vistas seleccionables. Devuelve tambien una profundidad y2 que podria
        usarse para ordenar objetos si se requiriera.
        """
        x, y, z = point
        mode_var = self.vars.get("view_mode")
        mode = str(mode_var.get()) if mode_var else "Isometrica"
        if mode == "Frontal":
            yaw, pitch = 0.0 * DEG, 0.0 * DEG
        elif mode == "Lateral":
            yaw, pitch = -90.0 * DEG, 0.0 * DEG
        elif mode == "Superior":
            yaw, pitch = -90.0 * DEG, 89.0 * DEG
        else:
            yaw, pitch = -38.0 * DEG, 24.0 * DEG
        x1 = x * math.cos(yaw) - y * math.sin(yaw)
        y1 = x * math.sin(yaw) + y * math.cos(yaw)
        z1 = z
        y2 = y1 * math.cos(pitch) - z1 * math.sin(pitch)
        z2 = y1 * math.sin(pitch) + z1 * math.cos(pitch)
        return width * 0.50 + x1 * scale, height * 0.62 - z2 * scale, y2

    def arc3d(
        self,
        canvas: tk.Canvas,
        center: tuple[float, float, float],
        radius: float,
        start_deg: float,
        end_deg: float,
        color: str,
        width_line: int = 2,
        plane: str = "xy",
    ) -> None:
        """Dibuja un arco 3D aproximado en plano XY o YZ."""
        steps = max(8, int(abs(end_deg - start_deg) / 8.0))
        points: list[float] = []
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        for i in range(steps + 1):
            a = (start_deg + (end_deg - start_deg) * i / steps) * DEG
            if plane == "xy":
                p = (center[0] + math.sin(a) * radius, center[1] + math.cos(a) * radius, center[2])
            else:
                p = (center[0], center[1] + math.cos(a) * radius, center[2] + math.sin(a) * radius)
            x, y, _ = self.project(p, w, h)
            points.extend([x, y])
        if len(points) >= 4:
            canvas.create_line(*points, fill=color, width=width_line)

    def line3d(self, canvas: tk.Canvas, a: tuple[float, float, float], b: tuple[float, float, float], color: str, width_line: int = 2, dash: tuple[int, int] | None = None) -> None:
        """Dibuja una linea entre dos puntos 3D proyectados."""
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        ax, ay, _ = self.project(a, w, h)
        bx, by, _ = self.project(b, w, h)
        canvas.create_line(ax, ay, bx, by, fill=color, width=width_line, dash=dash)

    def text3d(
        self,
        canvas: tk.Canvas,
        point: tuple[float, float, float],
        text: str,
        color: str,
        font: tuple[str, int, str] | tuple[str, int] = ("Segoe UI", 9, "bold"),
    ) -> None:
        """Dibuja una etiqueta asociada a una posicion 3D."""
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        x, y, _ = self.project(point, w, h)
        canvas.create_text(x, y, text=text, fill=color, font=font)

    def poly3d(self, canvas: tk.Canvas, points: list[tuple[float, float, float]], fill: str, outline: str) -> None:
        """Dibuja un poligono 3D proyectando todos sus vertices."""
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        xy = []
        for p in points:
            x, y, _ = self.project(p, w, h)
            xy.extend([x, y])
        canvas.create_polygon(*xy, fill=fill, outline=outline, width=2)

    def facet3d(
        self,
        canvas: tk.Canvas,
        center: tuple[float, float, float],
        ux: tuple[float, float, float],
        uz: tuple[float, float, float],
        radius: float,
        fill: str,
    ) -> None:
        """Dibuja una faceta circular aproximada del concentrador."""
        points = []
        for i in range(10):
            a = TAU * i / 10.0
            points.append(v_add(center, v_add(v_mul(ux, math.cos(a) * radius), v_mul(uz, math.sin(a) * radius))))
        self.poly3d(canvas, points, fill, "#554a35")

    def draw_scene(self) -> None:
        """Dibuja la escena 3D principal del gemelo.

        Incluye:
        - piso y brujula de convencion este/oeste/sur/norte;
        - base, horquilla y espejo del heliostato;
        - concentrador abierto de 18 facetas sobre riel/mesa;
        - vector solar, normal, rayo reflejado y cono de tolerancia cdr;
        - etiquetas y recuadro de estado.
        """
        c = self.scene_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#101821", outline="")
        c.create_text(20, 20, anchor="w", text="Representacion 3D en tiempo real", fill="#e8eef8", font=("Segoe UI", 15, "bold"))
        c.create_text(20, 46, anchor="w", text="+x oeste, +y sur, +z cenit | sin control fisico", fill="#aeb9c8", font=("Segoe UI", 10))
        base_half = clamp(self.state.base_width_m / 2.0, 0.06, 0.22)
        base_depth = clamp(self.state.base_width_m * 0.58, 0.08, 0.26)
        center_z = clamp(self.state.fork_height_m * 0.55, 0.10, 0.24)
        mirror_half = clamp(self.state.mirror_size_m / 2.0, 0.05, 0.16)

        # Rejilla del suelo para dar referencia espacial.
        for i in range(-4, 5):
            self.line3d(c, (-0.35, i * 0.12, -0.02), (0.35, i * 0.12, -0.02), "#25384a", 1)
            self.line3d(c, (i * 0.12, -0.12, -0.02), (i * 0.12, 0.75, -0.02), "#25384a", 1)

        # Brujula del sistema local. Es clave para no confundir este y oeste.
        self.line3d(c, (-0.22, 0, 0), (0.22, 0, 0), "#ff6b6b", 3)
        self.line3d(c, (0, -0.22, 0), (0, 0.22, 0), "#66d083", 3)
        self.line3d(c, (0, 0, 0), (0, 0, 0.22), "#72a7ff", 3)
        self.text3d(c, (0.27, 0, 0.0), "Oeste +x", "#ff8a8a")
        self.text3d(c, (-0.27, 0, 0.0), "Este -x", "#ff8a8a")
        self.text3d(c, (0, 0.27, 0.0), "Sur +y", "#8df0a5")
        self.text3d(c, (0, -0.27, 0.0), "Norte -y", "#8df0a5")
        self.text3d(c, (0, 0, 0.25), "Cenit +z", "#9bc2ff")
        self.arc3d(c, (0, 0, -0.018), 0.26, self.state.az.limit_min, self.state.az.limit_max, "#6f8aa8", 2)
        actual_radial = normal_from_angles(self.state.az.angle_deg, 0.0)
        target_radial = normal_from_angles(self.state.az.target_deg, 0.0)
        self.line3d(c, (0, 0, -0.016), v_mul(actual_radial, 0.27), "#f8d447", 2)
        self.line3d(c, (0, 0, -0.012), v_mul(target_radial, 0.24), "#ffffff", 2, dash=(4, 3))

        # Base triangular/robusta inspirada en las fotos del mini horno.
        self.poly3d(c, [(-base_half, -base_depth, -0.02), (base_half, -base_depth, -0.02), (base_half * 1.15, base_depth, -0.02), (-base_half * 1.15, base_depth, -0.02)], "#263649", "#718093")
        self.line3d(c, (0, 0, -0.02), (0, 0, center_z), "#9ea7b3", 5)
        self.line3d(c, (-base_half, -base_depth, -0.02), (0, 0, center_z), "#3c5874", 3)
        self.line3d(c, (base_half, -base_depth, -0.02), (0, 0, center_z), "#3c5874", 3)
        self.line3d(c, (0, base_depth, -0.02), (0, 0, center_z), "#3c5874", 3)
        self.arc3d(c, (0.0, -0.03, center_z), mirror_half * 1.6, self.state.el.limit_min, self.state.el.limit_max, "#7fd3ff", 2, plane="yz")

        # Orientacion real del espejo en este instante.
        n = self.state.actual_normal
        up = (0.0, 0.0, 1.0)
        u = v_cross(up, n)
        if v_norm(u) < 1e-9:
            u = (1.0, 0.0, 0.0)
        u = v_unit(u)
        v = v_unit(v_cross(n, u))
        center = (0.0, 0.0, center_z)
        fork_half = mirror_half * 1.35
        self.line3d(c, (-fork_half, 0.0, center_z), (-fork_half, 0.0, center_z + mirror_half), "#8ea3b8", 4)
        self.line3d(c, (fork_half, 0.0, center_z), (fork_half, 0.0, center_z + mirror_half), "#8ea3b8", 4)
        self.line3d(c, (-fork_half, 0.0, center_z + mirror_half), (fork_half, 0.0, center_z + mirror_half), "#8ea3b8", 3)
        half = mirror_half
        corners = [
            v_add(center, v_add(v_mul(u, -half), v_mul(v, -half))),
            v_add(center, v_add(v_mul(u, half), v_mul(v, -half))),
            v_add(center, v_add(v_mul(u, half), v_mul(v, half))),
            v_add(center, v_add(v_mul(u, -half), v_mul(v, half))),
        ]
        # Espejo plano y bastidor posterior reticulado.
        self.poly3d(c, corners, "#dceff5", "#cdefff")
        self.line3d(c, corners[0], corners[2], "#9fb0ba", 1)
        self.line3d(c, corners[1], corners[3], "#9fb0ba", 1)
        self.line3d(c, v_add(corners[0], v_mul(n, -0.01)), v_add(corners[1], v_mul(n, -0.01)), "#71808a", 3)
        self.line3d(c, v_add(corners[3], v_mul(n, -0.01)), v_add(corners[2], v_mul(n, -0.01)), "#71808a", 3)
        for k in (-0.05, 0.05):
            self.line3d(c, v_add(center, v_mul(u, k)), v_add(v_add(center, v_mul(u, k)), v_mul(v, 0.12)), "#b8c9d1", 1)
            self.line3d(c, v_add(center, v_mul(v, k)), v_add(v_add(center, v_mul(v, k)), v_mul(u, 0.12)), "#b8c9d1", 1)
        self.line3d(c, center, v_add(center, v_mul(n, 0.18)), "#f8d447", 3)
        if self.state.az.ina or self.state.az.inb:
            direction = "AZ +" if self.state.az.ina else "AZ -"
            c.create_text(24, 78, anchor="w", text=f"Movimiento {direction}", fill="#ffdf6e", font=("Segoe UI", 11, "bold"))
        if self.state.el.ina or self.state.el.inb:
            direction = "EL +" if self.state.el.ina else "EL -"
            c.create_text(24, 102, anchor="w", text=f"Movimiento {direction}", fill="#7fd3ff", font=("Segoe UI", 11, "bold"))

        # Target/concentrador. El vector R apunta del heliostato hacia este
        # punto, que por defecto queda hacia el sur (+y).
        target = self.state.target_vector
        target_center = v_add(target, (0.0, 0.0, 0.12))
        rail_end = max(self.state.rail_length_m, target[1] + 0.08)
        self.line3d(c, (0, 0, -0.015), (0, rail_end, -0.015), "#d7d7d7", 4)
        t_unit = v_unit(target)
        sx = v_unit(v_cross((0, 0, 1), t_unit))
        if v_norm(sx) < 1e-9:
            sx = (1, 0, 0)
        sz = v_unit(v_cross(t_unit, sx))
        ring_radius = clamp(self.state.receiver_screen_m, 0.06, 0.24)
        table_z = -0.015
        table_y = target[1]
        table_half = ring_radius * 1.25
        self.poly3d(
            c,
            [
                (-table_half, table_y - 0.08, table_z),
                (table_half, table_y - 0.08, table_z),
                (table_half, table_y + 0.08, table_z),
                (-table_half, table_y + 0.08, table_z),
            ],
            "#3c454d",
            "#7b8794",
        )
        # Concentrador idealizado con 18 facetas circulares.
        for i in range(18):
            radius = ring_radius * (0.32 if i < 6 else 0.61)
            count = 6 if i < 6 else 12
            idx = i if i < 6 else i - 6
            angle = TAU * idx / count + (TAU / 24.0 if i >= 6 else 0.0)
            facet_center = v_add(target_center, v_add(v_mul(sx, math.cos(angle) * radius), v_mul(sz, math.sin(angle) * radius)))
            facet_center = v_sub(facet_center, v_mul(t_unit, 0.015 + 0.018 * (radius / ring_radius)))
            color = "#c9b074" if i % 3 == 0 else "#d6c08b"
            self.facet3d(c, facet_center, sx, sz, ring_radius * 0.16, color)
        self.facet3d(c, target_center, sx, sz, ring_radius * 0.08, "#f2e7bd")
        self.line3d(c, v_add(target_center, v_mul(sz, -ring_radius * 0.95)), v_add(target_center, v_mul(sz, ring_radius * 0.95)), "#9b7a2f", 3)
        self.line3d(c, v_add(target_center, v_mul(sx, -ring_radius)), v_add(target_center, v_mul(sx, ring_radius)), "#9b7a2f", 3)
        for leg in (-0.13, 0.13):
            base = v_add(target, v_add(v_mul(sx, leg), (0.0, 0.0, -0.015)))
            top = v_add(target_center, v_mul(sx, leg * 0.7))
            self.line3d(c, base, top, "#8a8a8a", 3)

        # Rayos: el punteado viene desde el Sol hacia el espejo; el solido va
        # desde el espejo hacia el concentrador. El cono muestra tolerancia cdr.
        sun_start = v_add(center, v_mul(self.state.sun_vector, 0.35))
        self.line3d(c, sun_start, center, "#ffbf4d", 3, dash=(5, 3))
        self.line3d(c, center, target_center, "#ffef6a", 3)
        self.text3d(c, v_add(sun_start, (0.0, 0.0, 0.035)), "Sol", "#ffcf69")
        self.text3d(c, v_add(v_add(center, v_mul(n, 0.18)), (0.0, 0.0, 0.025)), "Normal", "#f8d447")
        target_distance = max(0.05, v_norm(self.state.target_vector))
        cone_radius = clamp(target_distance * math.tan(max(0.0, self.state.cdr) * DEG) * self.state.uncertainty_gain, 0.003, 0.08)
        for edge in (
            v_add(target_center, v_mul(sx, cone_radius)),
            v_add(target_center, v_mul(sx, -cone_radius)),
            v_add(target_center, v_mul(sz, cone_radius)),
            v_add(target_center, v_mul(sz, -cone_radius)),
        ):
            self.line3d(c, center, edge, "#fff4a8", 1, dash=(3, 4))
        if all(math.isfinite(p) for p in self.state.spot_point):
            spot = v_add(self.state.spot_point, (0.0, 0.0, 0.12))
            px, py, _ = self.project(spot, w, h)
            c.create_oval(px - 5, py - 5, px + 5, py + 5, fill="#ff3333", outline="#ffffff", width=1)

        status_label, status_color, status_detail = self.system_status()
        sun_side = "Oeste" if self.state.sun_vector[0] > 0.02 else "Este" if self.state.sun_vector[0] < -0.02 else "Centro"
        normal_side = "Oeste" if self.state.ideal_normal[0] > 0.02 else "Este" if self.state.ideal_normal[0] < -0.02 else "Centro"
        info = (
            f"Acim actual {self.state.az.angle_deg:6.2f} deg  -> {self.state.az.target_deg:6.2f} deg\n"
            f"Elev actual {self.state.el.angle_deg:6.2f} deg  -> {self.state.el.target_deg:6.2f} deg\n"
            f"Spot error {self.state.spot_error_x * 1000.0:7.1f} mm, {self.state.spot_error_z * 1000.0:7.1f} mm\n"
            f"Sol: {sun_side} | Normal ideal: {normal_side}\n"
            f"Vista: {self.vars['view_mode'].get()} | Concentrador: 18 facetas"
        )
        c.create_rectangle(w - 390, 18, w - 18, 172, fill="#172432", outline="#4f6f8d")
        c.create_rectangle(w - 390, 18, w - 18, 43, fill=status_color, outline="#4f6f8d")
        c.create_text(w - 374, 30, anchor="w", text=status_label, fill="#ffffff", font=("Segoe UI", 10, "bold"))
        c.create_text(w - 374, 54, anchor="nw", text=info, fill="#e8eef8", font=("Consolas", 10))
        c.create_text(w - 374, 152, anchor="w", text=status_detail[:68], fill="#b8c7d9", font=("Segoe UI", 9))

    def draw_axes(self, c: tk.Canvas, x0: int, y0: int, x1: int, y1: int, title: str, y_label: str) -> None:
        """Dibuja un marco cartesiano simple para graficas 2D."""
        c.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#999999")
        c.create_line(x0 + 45, y1 - 30, x1 - 15, y1 - 30, fill="#222222")
        c.create_line(x0 + 45, y0 + 15, x0 + 45, y1 - 30, fill="#222222")
        c.create_text(x0 + 12, y0 + 8, anchor="nw", text=title, fill="#111111", font=("Segoe UI", 11, "bold"))
        c.create_text(x0 + 8, (y0 + y1) / 2, text=y_label, angle=90, fill="#333333", font=("Segoe UI", 9))

    def plot_series(self, c: tk.Canvas, box: tuple[int, int, int, int], values: list[float], color: str, ymin: float | None = None, ymax: float | None = None) -> None:
        """Grafica una serie temporal dentro de un rectangulo de Canvas."""
        if len(values) < 2:
            return
        x0, y0, x1, y1 = box
        left, top, right, bottom = x0 + 45, y0 + 18, x1 - 16, y1 - 30
        if ymin is None:
            ymin = min(values)
        if ymax is None:
            ymax = max(values)
        if abs(ymax - ymin) < 1e-9:
            ymin -= 1.0
            ymax += 1.0
        pts = []
        count = len(values)
        for idx, value in enumerate(values):
            x = left + (right - left) * idx / (count - 1)
            y = bottom - (bottom - top) * (value - ymin) / (ymax - ymin)
            pts.extend([x, y])
        c.create_line(*pts, fill=color, width=2)
        c.create_text(right - 5, top + 5, anchor="ne", text=f"{ymax:.1f}", fill="#555555", font=("Consolas", 8))
        c.create_text(right - 5, bottom - 13, anchor="ne", text=f"{ymin:.1f}", fill="#555555", font=("Consolas", 8))

    def draw_receiver_view(self) -> None:
        """Dibuja la pantalla del concentrador y la posicion del spot.

        Verde = objetivo ideal en el centro de la pantalla.
        Rojo = punto donde el modelo calcula que cae el rayo reflejado.
        La linea roja muestra el historial reciente del spot.
        """
        c = self.receiver_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        hist = list(self.state.history)
        c.create_text(24, 22, anchor="w", text="Pantalla del concentrador: posicion del spot", fill="#111111", font=("Segoe UI", 15, "bold"))
        cx, cy = w * 0.43, h * 0.52
        radius = min(w, h) * 0.34
        c.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill="#e9dec0", outline="#7a6b44", width=3)
        c.create_line(cx - radius, cy, cx + radius, cy, fill="#a09068", width=1)
        c.create_line(cx, cy - radius, cx, cy + radius, fill="#a09068", width=1)
        for r in (0.25, 0.5, 0.75):
            rr = radius * r
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline="#c2b28a")
        for i in range(18):
            a = TAU * i / 18.0
            c.create_line(cx, cy, cx + math.cos(a) * radius, cy + math.sin(a) * radius, fill="#d0bf96")
        scale = radius / 160.0
        pts = []
        for p in hist[-220:]:
            x = cx + p["err_x"] * 1000.0 * scale
            y = cy - p["err_z"] * 1000.0 * scale
            if cx - radius <= x <= cx + radius and cy - radius <= y <= cy + radius:
                pts.extend([x, y])
        if len(pts) >= 4:
            c.create_line(*pts, fill="#cc3333", width=2)
        sx = cx + self.state.spot_error_x * 1000.0 * scale
        sz = cy - self.state.spot_error_z * 1000.0 * scale
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#2fbf62", outline="#ffffff", width=2)
        c.create_oval(sx - 8, sz - 8, sx + 8, sz + 8, fill="#ff3030", outline="#ffffff", width=2)
        tol = max(5.0, self.state.cdr * 35.0) * scale
        c.create_oval(cx - tol, cy - tol, cx + tol, cy + tol, outline="#31a354", width=2, dash=(5, 3))
        error_mag = math.hypot(self.state.spot_error_x, self.state.spot_error_z) * 1000.0
        text_x = w * 0.74
        c.create_rectangle(text_x - 18, 92, w - 28, h - 72, fill="#ffffff", outline="#c7c7c7")
        c.create_text(text_x, 118, anchor="w", text="Lectura directa", fill="#111111", font=("Segoe UI", 13, "bold"))
        c.create_text(text_x, 160, anchor="w", text=f"Error X: {self.state.spot_error_x * 1000.0:8.1f} mm", fill="#a41d1d", font=("Consolas", 13))
        c.create_text(text_x, 190, anchor="w", text=f"Error Z: {self.state.spot_error_z * 1000.0:8.1f} mm", fill="#1d6f42", font=("Consolas", 13))
        c.create_text(text_x, 220, anchor="w", text=f"Error total: {error_mag:7.1f} mm", fill="#111111", font=("Consolas", 13, "bold"))
        c.create_text(text_x, 250, anchor="w", text=f"cdr: +/- {self.state.cdr:.3f} deg", fill="#111111", font=("Consolas", 12))
        c.create_text(text_x, 285, anchor="w", text="Verde = objetivo\nRojo = spot simulado\nLinea roja = historial reciente", fill="#333333", font=("Segoe UI", 10))
        c.create_text(text_x, 365, anchor="w", text="Esta vista responde a la pregunta:\n?donde esta cayendo el rayo?", fill="#555555", font=("Segoe UI", 11))

    def active_datetime(self) -> _dt.datetime:
        """Devuelve la fecha/hora que esta usando el gemelo en este instante."""
        return _dt.datetime.now() if self.state.use_live_time else self.state.simulated_time

    def draw_solar_path(self) -> None:
        """Dibuja la trayectoria solar diaria para la fecha activa.

        La grafica usa altura solar contra acimut de laboratorio. Sirve para
        verificar visualmente si el Sol esta hacia el este, sur, oeste o norte.
        """
        c = self.solar_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        c.create_text(24, 22, anchor="w", text="Trayectoria solar del dia", fill="#111111", font=("Segoe UI", 15, "bold"))
        when = self.active_datetime()
        day0 = when.replace(hour=0, minute=0, second=0, microsecond=0)
        left, top, right, bottom = 72, 78, w - 58, h - 92
        c.create_rectangle(left, top, right, bottom, fill="#ffffff", outline="#999999")
        c.create_text(left, bottom + 38, anchor="w", text="Acimut de laboratorio: negativo = este, 0 = sur, positivo = oeste, +/-180 = norte", fill="#333333", font=("Segoe UI", 10))
        c.create_text(left - 46, top + 8, anchor="w", text="Altura", fill="#333333", font=("Segoe UI", 10))
        for alt_tick in range(0, 91, 15):
            y = bottom - (bottom - top) * alt_tick / 90.0
            c.create_line(left, y, right, y, fill="#e4e4e4")
            c.create_text(left - 12, y, anchor="e", text=str(alt_tick), fill="#555555", font=("Consolas", 8))
        for az_tick in range(-180, 181, 45):
            x = left + (right - left) * (az_tick + 180.0) / 360.0
            c.create_line(x, top, x, bottom, fill="#eeeeee")
            c.create_text(x, bottom + 14, text=str(az_tick), fill="#555555", font=("Consolas", 8))
        pts: list[float] = []
        daylight: list[float] = []
        for minute in range(0, 24 * 60 + 1, 10):
            sample_time = day0 + _dt.timedelta(minutes=minute)
            _zen, alt, az, _source = solar_position(sample_time, self.state.lat_deg, self.state.lon_deg, self.state.method)
            x = left + (right - left) * clamp((az + 180.0) / 360.0, 0.0, 1.0)
            y = bottom - (bottom - top) * clamp(alt / 90.0, 0.0, 1.0)
            if alt > 0:
                daylight.extend([x, y])
            pts.extend([x, y])
        if len(pts) >= 4:
            c.create_line(*pts, fill="#b7b7b7", width=1, dash=(3, 3))
        if len(daylight) >= 4:
            c.create_line(*daylight, fill="#d08a00", width=3)
        active_x = left + (right - left) * clamp((self.state.solar_azimuth + 180.0) / 360.0, 0.0, 1.0)
        active_y = bottom - (bottom - top) * clamp(self.state.altitude / 90.0, 0.0, 1.0)
        c.create_oval(active_x - 7, active_y - 7, active_x + 7, active_y + 7, fill="#ff3030", outline="#ffffff", width=2)
        c.create_line(active_x, top, active_x, bottom, fill="#ffb4b4", dash=(4, 3))
        c.create_line(left, active_y, right, active_y, fill="#ffb4b4", dash=(4, 3))
        summary = (
            f"Fecha usada: {when:%Y-%m-%d %H:%M:%S}\n"
            f"Metodo: {self.state.solar_source}\n"
            f"Altura: {self.state.altitude:6.2f} deg\n"
            f"Acimut lab: {self.state.solar_azimuth:6.2f} deg\n"
            f"Zenit: {self.state.zenith:6.2f} deg"
        )
        c.create_rectangle(w - 330, 72, w - 42, 215, fill="#ffffff", outline="#bbbbbb")
        c.create_text(w - 310, 92, anchor="nw", text=summary, fill="#222222", font=("Consolas", 11))
        if self.state.altitude <= 0:
            c.create_rectangle(w - 330, 235, w - 42, 286, fill="#fff1f2", outline="#fecdd3")
            c.create_text(w - 314, 260, anchor="w", text="Sol bajo horizonte", fill="#9f1239", font=("Segoe UI", 11, "bold"))

    def draw_diagnostic_view(self) -> None:
        """Dibuja diagnostico numerico de errores, motores, vectores y alertas."""
        c = self.diagnostic_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        hist = list(self.state.history)
        c.create_text(24, 22, anchor="w", text="Diagnostico de seguimiento", fill="#111111", font=("Segoe UI", 15, "bold"))
        az_err = wrap_deg(self.state.az.target_deg - self.state.az.angle_deg)
        el_err = self.state.el.target_deg - self.state.el.angle_deg
        spot_err = math.hypot(self.state.spot_error_x, self.state.spot_error_z) * 1000.0
        metrics = [
            ("Error acimut", az_err, "deg", 25.0, "#2b6cb0"),
            ("Error elevacion", el_err, "deg", 25.0, "#805ad5"),
            ("Error spot", spot_err, "mm", 250.0, "#c53030"),
        ]
        x0, y0 = 42, 80
        for i, (label, value, unit, limit, color) in enumerate(metrics):
            y = y0 + i * 82
            c.create_text(x0, y, anchor="w", text=label, fill="#111111", font=("Segoe UI", 12, "bold"))
            c.create_rectangle(x0, y + 24, x0 + 420, y + 48, fill="#e6e6e6", outline="#bdbdbd")
            frac = clamp(abs(value) / limit, 0.0, 1.0)
            c.create_rectangle(x0, y + 24, x0 + 420 * frac, y + 48, fill=color, outline="")
            c.create_text(x0 + 438, y + 36, anchor="w", text=f"{value:8.2f} {unit}", fill="#111111", font=("Consolas", 12, "bold"))
        chart_right = w - 42 if w < 980 else w - 520
        box = (42, 350, chart_right, h - 42)
        self.draw_axes(c, *box, "Historial util: error total del spot", "mm")
        errs = [math.hypot(p["err_x"], p["err_z"]) * 1000.0 for p in hist]
        ymax = max(errs + [10.0])
        self.plot_series(c, box, errs, "#c53030", 0.0, min(max(ymax, 10.0), 500.0))
        c.create_text(w - 360, 100, anchor="nw", text=(
            f"Acimut real/obj: {self.state.az.angle_deg:6.2f} / {self.state.az.target_deg:6.2f} deg\n"
            f"Elev real/obj:  {self.state.el.angle_deg:6.2f} / {self.state.el.target_deg:6.2f} deg\n"
            f"Motor acim: {'ON' if self.state.az.motor_on else 'OFF'}   PWM {self.state.az.pwm * 100:4.0f}%\n"
            f"Motor elev: {'ON' if self.state.el.motor_on else 'OFF'}   PWM {self.state.el.pwm * 100:4.0f}%\n"
            f"cdr (+/-): {self.state.cdr:6.3f} deg\n"
            f"Metodo: {self.state.solar_source}\n"
            f"Tiempo usado: {self.active_datetime():%Y-%m-%d %H:%M:%S}"
        ), fill="#222222", font=("Consolas", 11))
        vector_x = max(42, w - 460)
        vector_y = 282
        c.create_rectangle(vector_x, vector_y, w - 42, vector_y + 54, fill="#ffffff", outline="#bbbbbb")
        status_label, status_color, _detail = self.system_status()
        c.create_rectangle(vector_x, vector_y, w - 42, vector_y + 24, fill=status_color, outline="#bbbbbb")
        c.create_text(vector_x + 10, vector_y + 12, anchor="w", text=f"Estado operacional: {status_label}", fill="#ffffff", font=("Segoe UI", 10, "bold"))
        alerts = self.validation_messages()
        c.create_text(
            vector_x + 10,
            vector_y + 36,
            anchor="w",
            text=(" | ".join(alerts[:2]) if alerts else "Sin alertas"),
            fill="#222222",
            font=("Segoe UI", 9),
        )
        s = self.state
        vector_text = (
            f"S solar   = ({s.sun_vector[0]:+.3f}, {s.sun_vector[1]:+.3f}, {s.sun_vector[2]:+.3f})\n"
            f"R target  = ({s.target_vector[0]:+.3f}, {s.target_vector[1]:+.3f}, {s.target_vector[2]:+.3f}) m\n"
            f"N ideal   = ({s.ideal_normal[0]:+.3f}, {s.ideal_normal[1]:+.3f}, {s.ideal_normal[2]:+.3f})\n"
            f"N actual  = ({s.actual_normal[0]:+.3f}, {s.actual_normal[1]:+.3f}, {s.actual_normal[2]:+.3f})\n"
            f"Target crudo EL: {s.raw_target_elev:+.2f} deg | Peralte helio: {s.peralte:+.2f} deg"
        )
        c.create_text(vector_x, vector_y + 74, anchor="nw", text=vector_text, fill="#222222", font=("Consolas", 10))

    def draw_logic(self) -> None:
        """Dibuja un diagrama de flujo de la logica interna del gemelo."""
        c = self.logic_canvas
        c.delete("all")
        w, _h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, 900, fill="#f7f7f7", outline="")
        blocks = [
            ("Hora/Fecha + ubicacion", "D&B / REDA aprox.\nzenit, altura, acimut"),
            ("Trayectoria solar", "curva diaria\nmarca hora activa"),
            ("Vector solar", "Sx = cos(Alfa) sin(Acim)\nSy = cos(Alfa) cos(Acim)\nSz = sin(Alfa)"),
            ("Target", "R = (RX, RY, RZ)\nmodelo escalado opcional"),
            ("Normal ideal", "N = unit(S + unit(R))\nAcim/Elev del heliostato"),
            ("Calibracion", "peralte, offsets, cdr\nlimites y conteos"),
            ("Motor simulado", "PWM por perilla\nencoder y limites\nmovimiento fluido"),
            ("Concentrador", "18 facetas\nspot y error sobre pantalla"),
            ("Alertas", "info, advertencia\ncritica"),
            ("Gemelo visual", "heliostato + concentrador\ncono cdr y rayos"),
            ("Datos", "muestras de sesion\nreplay y CSV"),
        ]
        x, y = 40, 50
        prev_center = None
        for title, body in blocks:
            c.create_rectangle(x, y, x + 260, y + 92, fill="#ffffff", outline="#777777", width=2)
            c.create_rectangle(x, y, x + 260, y + 26, fill="#d8b54b", outline="#777777")
            c.create_text(x + 10, y + 13, anchor="w", text=title, fill="#00185e", font=("Segoe UI", 10, "bold"))
            c.create_text(x + 12, y + 40, anchor="nw", text=body, fill="#222222", font=("Consolas", 9))
            center = (x + 130, y + 46)
            if prev_center:
                c.create_line(prev_center[0] + 130, prev_center[1], x, center[1], arrow="last", fill="#333333", width=2)
            prev_center = center
            x += 300
            if x + 280 > w:
                x = 40
                y += 140
                prev_center = None

    def draw_event_log(self) -> None:
        """Dibuja estado actual, validaciones activas y bitacora reciente."""
        c = self.log_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f7f7f7", outline="")
        c.create_text(24, 22, anchor="w", text="Eventos y validaciones", fill="#111111", font=("Segoe UI", 15, "bold"))
        status_label, status_color, status_detail = self.system_status()
        c.create_rectangle(24, 58, w - 24, 104, fill="#ffffff", outline="#c7c7c7")
        c.create_rectangle(24, 58, 190, 104, fill=status_color, outline="#c7c7c7")
        c.create_text(40, 81, anchor="w", text=status_label, fill="#ffffff", font=("Segoe UI", 11, "bold"))
        c.create_text(210, 81, anchor="w", text=status_detail, fill="#222222", font=("Segoe UI", 10))
        alerts = self.alert_items()
        y = 130
        c.create_text(24, y, anchor="w", text="Validaciones activas", fill="#111111", font=("Segoe UI", 12, "bold"))
        y += 28
        if alerts:
            colors = {
                "critica": ("#fff1f2", "#fecdd3", "#9f1239", "CRITICA"),
                "advertencia": ("#fff7ed", "#fed7aa", "#9a3412", "ADVERTENCIA"),
                "info": ("#eff6ff", "#bfdbfe", "#1d4ed8", "INFO"),
            }
            for severity, alert in alerts[:6]:
                bg, outline, fg, label = colors.get(severity, colors["info"])
                c.create_rectangle(24, y - 10, w - 24, y + 18, fill=bg, outline=outline)
                c.create_text(38, y + 4, anchor="w", text=f"{label}: {alert}", fill=fg, font=("Segoe UI", 10, "bold" if severity != "info" else "normal"))
                y += 34
        else:
            c.create_rectangle(24, y - 10, w - 24, y + 18, fill="#ecfdf5", outline="#a7f3d0")
            c.create_text(38, y + 4, anchor="w", text="Sin alertas", fill="#14532d", font=("Segoe UI", 10))
            y += 34
        y += 14
        c.create_text(24, y, anchor="w", text="Bitacora reciente", fill="#111111", font=("Segoe UI", 12, "bold"))
        y += 26
        c.create_rectangle(24, y, w - 24, h - 24, fill="#101821", outline="#4f6f8d")
        log_lines = list(self.event_log)[-22:]
        for idx, line in enumerate(log_lines):
            c.create_text(42, y + 20 + idx * 20, anchor="w", text=line, fill="#dbeafe", font=("Consolas", 10))


def run_self_test() -> None:
    """Prueba rapida sin abrir GUI.

    Verifica que el modelo pueda calcular geometria, objetivos y error de spot
    durante varios pasos sin producir NaN o excepciones.
    """
    state = TwinState()
    for _ in range(20):
        state.compute_geometry()
        state.update(0.05)
    assert math.isfinite(state.target_acim)
    assert math.isfinite(state.target_elev)
    assert math.isfinite(state.spot_error_x)
    print("self-test ok")


def main() -> None:
    """Punto de entrada de linea de comandos."""
    parser = argparse.ArgumentParser(description="Gemelo digital del mini horno solar / mini heliostato.")
    parser.add_argument("--self-test", action="store_true", help="Run geometry/model checks without opening the GUI.")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return
    root = tk.Tk()
    DigitalTwinApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
