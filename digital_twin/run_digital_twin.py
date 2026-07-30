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

try:
    from digital_twin.error_model import ErrorConfig, ErrorModel, MotionErrorSample
except ModuleNotFoundError:  # Permite ejecutar directamente este archivo .py.
    from error_model import ErrorConfig, ErrorModel, MotionErrorSample


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


def normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    """Devuelve el vector unitario asociado a ``v``.

    Las componentes pueden pertenecer al marco global ``+x`` oeste, ``+y`` sur,
    ``+z`` cenit o a cualquier marco cartesiano equivalente. Si la magnitud es
    casi cero devuelve el vector cero, igual que la utilidad historica
    :func:`v_unit` que se conserva por compatibilidad.
    """
    return v_unit(v)


def angle_between(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    """Retorna en grados el menor angulo entre dos vectores no nulos."""
    a_unit = normalize(a)
    b_unit = normalize(b)
    if v_norm(a_unit) < 1e-12 or v_norm(b_unit) < 1e-12:
        raise ValueError("No se puede calcular un angulo con un vector nulo")
    return math.acos(clamp(v_dot(a_unit, b_unit), -1.0, 1.0)) * RAD


def reflect_vector(
    incident_direction: tuple[float, float, float],
    normal: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Calcula la direccion reflejada mediante la ley de reflexion.

    ``incident_direction`` es la direccion de propagacion *hacia* el espejo.
    En este proyecto el vector solar ``S`` apunta del heliostato al Sol, por lo
    que debe usarse ``incident_direction = -S``. ``normal`` apunta hacia la cara
    reflectante. El resultado unitario se expresa en el mismo marco global
    ``+x`` oeste, ``+y`` sur, ``+z`` cenit.

    Lanza ``ValueError`` si la direccion incidente o la normal son nulas.
    """
    incident = normalize(incident_direction)
    normal_unit = normalize(normal)
    if v_norm(incident) < 1e-12 or v_norm(normal_unit) < 1e-12:
        raise ValueError("La direccion incidente y la normal deben ser no nulas")
    return normalize(v_sub(incident, v_mul(normal_unit, 2.0 * v_dot(incident, normal_unit))))


def compute_heliostat_normal(
    sun_direction: tuple[float, float, float],
    target_direction: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Calcula la normal ideal como bisectriz entre Sol y objetivo.

    ``sun_direction`` apunta del heliostato hacia el Sol y ``target_direction``
    apunta del heliostato hacia el target. Ambas direcciones se normalizan. La
    bisectriz ``normalize(S + T)`` satisface la ley de reflexion cuando el rayo
    incidente usa la convencion de propagacion ``-S``.

    Lanza ``ValueError`` para vectores nulos o direcciones exactamente opuestas,
    porque en esos casos la bisectriz no queda definida de forma unica.
    """
    sun_unit = normalize(sun_direction)
    target_unit = normalize(target_direction)
    if v_norm(sun_unit) < 1e-12 or v_norm(target_unit) < 1e-12:
        raise ValueError("Las direcciones solar y objetivo deben ser no nulas")
    bisector = v_add(sun_unit, target_unit)
    if v_norm(bisector) < 1e-12:
        raise ValueError("Sol y objetivo opuestos no definen una bisectriz unica")
    return normalize(bisector)


@dataclass(frozen=True)
class ReflectionDiagnostics:
    """Vectores y angulos que permiten verificar la ley de reflexion."""

    incident_direction: tuple[float, float, float]
    reflected_direction: tuple[float, float, float]
    incidence_angle_deg: float
    reflection_angle_deg: float
    target_difference_deg: float


def compute_reflection_diagnostics(
    sun_direction: tuple[float, float, float],
    normal: tuple[float, float, float],
    target_direction: tuple[float, float, float],
) -> ReflectionDiagnostics:
    """Evalua reflexion real y diferencia respecto de la direccion objetivo."""
    sun_unit = normalize(sun_direction)
    normal_unit = normalize(normal)
    target_unit = normalize(target_direction)
    if min(v_norm(sun_unit), v_norm(normal_unit), v_norm(target_unit)) < 1e-12:
        raise ValueError("Los diagnosticos requieren tres vectores no nulos")
    incident = v_mul(sun_unit, -1.0)
    reflected = reflect_vector(incident, normal_unit)
    return ReflectionDiagnostics(
        incident,
        reflected,
        angle_between(sun_unit, normal_unit),
        angle_between(reflected, normal_unit),
        angle_between(reflected, target_unit),
    )


def intersect_ray_plane(
    ray_origin: tuple[float, float, float],
    ray_direction: tuple[float, float, float],
    plane_point: tuple[float, float, float],
    plane_normal: tuple[float, float, float],
    epsilon: float = 1e-9,
) -> tuple[tuple[float, float, float] | None, float | None]:
    """Calcula la interseccion entre un rayo 3D y un plano.

    Todos los puntos usan coordenadas globales en metros con la convencion del
    proyecto: ``+x`` oeste, ``+y`` sur y ``+z`` cenit. Las direcciones se
    normalizan internamente, por lo que ``t`` tambien queda expresado en metros.

    Retorna ``(None, None)`` si una direccion es nula, si el rayo es paralelo al
    plano o si el cruce queda detras del origen. Un cruce en el propio origen es
    valido y retorna ``t = 0``.
    """
    if v_norm(ray_direction) < epsilon or v_norm(plane_normal) < epsilon:
        return None, None
    direction = v_unit(ray_direction)
    normal = v_unit(plane_normal)
    denominator = v_dot(direction, normal)
    if abs(denominator) < epsilon:
        return None, None
    t = v_dot(v_sub(plane_point, ray_origin), normal) / denominator
    if t < -epsilon:
        return None, None
    t = max(0.0, t)
    return v_add(ray_origin, v_mul(direction, t)), t


def world_to_target_coordinates(
    point: tuple[float, float, float],
    target_center: tuple[float, float, float],
    target_u_axis: tuple[float, float, float],
    target_v_axis: tuple[float, float, float],
) -> tuple[float, float]:
    """Convierte un punto global a coordenadas locales ``(u, v)`` del target.

    Los puntos estan en metros y usan ``+x`` oeste, ``+y`` sur, ``+z`` cenit.
    ``u`` es horizontal sobre el target y se orienta hacia el oeste para el
    target nominal situado al sur. ``v`` es vertical y positivo hacia el cenit.
    Los ejes se normalizan y ``v`` se ortogonaliza respecto de ``u``.

    Lanza ``ValueError`` si alguno de los ejes no permite definir un marco 2D.
    """
    if v_norm(target_u_axis) < 1e-12 or v_norm(target_v_axis) < 1e-12:
        raise ValueError("Los ejes locales del target no pueden ser nulos")
    u_axis = v_unit(target_u_axis)
    v_orthogonal = v_sub(target_v_axis, v_mul(u_axis, v_dot(target_v_axis, u_axis)))
    if v_norm(v_orthogonal) < 1e-12:
        raise ValueError("Los ejes locales del target no pueden ser paralelos")
    v_axis = v_unit(v_orthogonal)
    relative = v_sub(point, target_center)
    return v_dot(relative, u_axis), v_dot(relative, v_axis)


def target_coordinate_frame(
    target_center: tuple[float, float, float],
) -> tuple[
    tuple[float, float, float],
    tuple[float, float, float],
    tuple[float, float, float],
]:
    """Construye normal, eje horizontal ``u`` y eje vertical ``v`` del target.

    El plano mira desde el heliostato, situado en el origen optico, hacia el
    centro del target. Para la geometria nominal al sur, ``u`` coincide con
    ``+x`` (oeste) y ``v`` con ``+z`` (cenit). Si el target queda exactamente
    sobre el eje vertical se elige un marco horizontal estable.
    """
    normal = v_unit(target_center)
    if v_norm(normal) < 1e-12:
        raise ValueError("El centro del target no puede coincidir con el origen optico")
    global_up = (0.0, 0.0, 1.0)
    u_axis = v_cross(normal, global_up)
    if v_norm(u_axis) < 1e-12:
        u_axis = (1.0, 0.0, 0.0)
    else:
        u_axis = v_unit(u_axis)
    v_axis = v_sub(global_up, v_mul(normal, v_dot(global_up, normal)))
    if v_norm(v_axis) < 1e-12:
        v_axis = v_cross(normal, u_axis)
    return normal, u_axis, v_unit(v_axis)


def classify_target_error(radial_error_m: float, tolerance_m: float) -> str:
    """Clasifica el impacto a partir del error radial y la tolerancia en metros."""
    tolerance = max(0.0, tolerance_m)
    centered_limit = max(1e-9, 0.25 * tolerance)
    if radial_error_m <= centered_limit:
        return "centrado"
    if radial_error_m <= tolerance:
        return "aceptable"
    return "fuera de tolerancia"


@dataclass(frozen=True)
class TargetImpact:
    """Resultado geometrico de proyectar un rayo sobre el target virtual."""

    point: tuple[float, float, float] | None
    ray_parameter_m: float | None
    u_m: float | None
    v_m: float | None
    radial_error_m: float | None
    angular_error_deg: float | None
    status: str
    plane_normal: tuple[float, float, float]
    u_axis: tuple[float, float, float]
    v_axis: tuple[float, float, float]


def compute_target_impact(
    ray_origin: tuple[float, float, float],
    ray_direction: tuple[float, float, float],
    target_center: tuple[float, float, float],
    tolerance_m: float,
) -> TargetImpact:
    """Calcula impacto, coordenadas locales y errores del target virtual.

    Las posiciones estan en metros en el marco global ``oeste/sur/cenit``. El
    error angular es la aproximacion ``atan(error radial / distancia al centro)``.
    Si no existe una interseccion frontal valida, las magnitudes del impacto son
    ``None`` y el estado es ``sin impacto``.
    """
    normal, u_axis, v_axis = target_coordinate_frame(target_center)
    point, ray_parameter = intersect_ray_plane(
        ray_origin,
        ray_direction,
        target_center,
        normal,
    )
    if point is None or ray_parameter is None:
        return TargetImpact(
            None,
            None,
            None,
            None,
            None,
            None,
            "sin impacto",
            normal,
            u_axis,
            v_axis,
        )
    u_m, v_m = world_to_target_coordinates(point, target_center, u_axis, v_axis)
    radial_error_m = math.hypot(u_m, v_m)
    center_distance_m = v_norm(v_sub(target_center, ray_origin))
    angular_error_deg = math.atan2(radial_error_m, max(center_distance_m, 1e-12)) * RAD
    return TargetImpact(
        point,
        ray_parameter,
        u_m,
        v_m,
        radial_error_m,
        angular_error_deg,
        classify_target_error(radial_error_m, tolerance_m),
        normal,
        u_axis,
        v_axis,
    )


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
    advance_solar_time: bool = True
    solar_time_scale: float = 60.0
    initial_simulated_time: _dt.datetime | None = None
    simulation_step_s: float = 60.0
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
    target_scale_m: float = 0.10
    target_tolerance_m: float = 0.010
    mirror_size_m: float = 0.20
    base_width_m: float = 0.19
    fork_height_m: float = 0.22
    rail_length_m: float = 0.55
    receiver_screen_m: float = 0.16
    uncertainty_gain: float = 1.0
    tracking: bool = True
    automatic: bool = True
    free_mode: bool = False
    show_sun_vector: bool = True
    show_normal_vector: bool = True
    show_reflected_vector: bool = True
    show_target_direction: bool = True
    show_target_line: bool = True
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
    spot_error_u: float = 0.0
    spot_error_v: float = 0.0
    spot_error_radial: float = 0.0
    spot_error_angular_deg: float = 0.0
    spot_status: str = "centrado"
    spot_valid: bool = True
    spot_ray_t: float = 0.0
    spot_point: tuple[float, float, float] = (0.0, 0.0, 0.0)
    incident_direction: tuple[float, float, float] = (0.0, -1.0, 0.0)
    reflected_direction: tuple[float, float, float] = (0.0, 1.0, 0.0)
    incidence_angle_deg: float = 0.0
    reflection_angle_deg: float = 0.0
    reflection_target_error_deg: float = 0.0
    target_plane_normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    target_u_axis: tuple[float, float, float] = (1.0, 0.0, 0.0)
    target_v_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    sun_vector: tuple[float, float, float] = (0.0, 1.0, 0.0)
    target_vector: tuple[float, float, float] = (0.0, 1.0, 0.0)
    ideal_normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    actual_normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    nominal_target_vector: tuple[float, float, float] = (0.0, 1.0, 0.0)
    error_mode: str = "Ideal"
    error_config: ErrorConfig = field(default_factory=ErrorConfig)
    error_model: ErrorModel = field(init=False, repr=False)
    motion_error_sample: MotionErrorSample = field(default_factory=MotionErrorSample)
    ideal_spot_u: float = 0.0
    ideal_spot_v: float = 0.0
    ideal_spot_radial: float = 0.0
    error_spot_u: float = 0.0
    error_spot_v: float = 0.0
    error_spot_radial: float = 0.0
    corrected_spot_u: float = 0.0
    corrected_spot_v: float = 0.0
    corrected_spot_radial: float = 0.0
    history_limit: int = 720
    seconds_since_last_correction: float = 0.0
    correction_count: int = 0
    tracking_update_interval_s: float = 1.0
    tracking_updates_manual: bool = False
    seconds_since_tracking_update: float = 0.0
    tracking_update_count: int = 0
    tracking_schedule_initialized: bool = False
    tracking_update_pending: bool = False
    tracking_corrected_this_step: bool = False
    held_target_acim: float = 0.0
    held_target_elev: float = 0.0
    tracking_error_max_m: float = 0.0
    tracking_error_average_m: float = 0.0
    tracking_error_rms_m: float = 0.0
    _interval_error_max_m: float = field(default=0.0, repr=False)
    _interval_error_sum_m: float = field(default=0.0, repr=False)
    _interval_error_sq_sum_m: float = field(default=0.0, repr=False)
    _interval_error_samples: int = field(default=0, repr=False)
    _last_tracking_state: bool = field(default=True, repr=False)
    history: deque = field(default_factory=lambda: deque(maxlen=720))

    def __post_init__(self) -> None:
        """Inicializa el origen reiniciable del reloj simulado."""
        self.error_model = ErrorModel(self.error_config)
        if self.initial_simulated_time is None:
            self.initial_simulated_time = self.simulated_time
        self.set_history_limit(self.history_limit)

    def set_simulated_start_time(self, when: _dt.datetime) -> None:
        """Define fecha/hora inicial y coloca el reloj exactamente en ella."""
        self.initial_simulated_time = when
        self.simulated_time = when
        self.seconds_since_last_correction = 0.0
        self.clear_history()
        self.reset_tracking_schedule()

    def reset_simulated_time(self) -> None:
        """Regresa el reloj a la fecha/hora inicial configurada."""
        if self.initial_simulated_time is None:
            self.initial_simulated_time = self.simulated_time
        self.simulated_time = self.initial_simulated_time
        self.seconds_since_last_correction = 0.0
        self.clear_history()
        self.reset_tracking_schedule()

    def step_simulated_time(self, seconds: float | None = None) -> float:
        """Avanza manualmente una cantidad definida y devuelve ese avance."""
        step_s = self.simulation_step_s if seconds is None else float(seconds)
        step_s = max(0.0, step_s)
        if self.use_live_time:
            return 0.0
        self.simulated_time += _dt.timedelta(seconds=step_s)
        self.seconds_since_last_correction += step_s
        self.seconds_since_tracking_update += step_s
        return step_s

    def advance_simulation_clock(self, real_elapsed_s: float) -> float:
        """Avanza el reloj segun su multiplicador y devuelve segundos simulados."""
        real_elapsed_s = max(0.0, float(real_elapsed_s))
        if self.use_live_time:
            return real_elapsed_s
        if not self.advance_solar_time:
            return 0.0
        simulated_elapsed_s = real_elapsed_s * max(0.0, self.solar_time_scale)
        self.simulated_time += _dt.timedelta(seconds=simulated_elapsed_s)
        return simulated_elapsed_s

    def set_history_limit(self, limit: int) -> None:
        """Cambia el limite conservando las muestras mas recientes."""
        bounded_limit = max(2, min(int(limit), 20000))
        self.history_limit = bounded_limit
        if self.history.maxlen != bounded_limit:
            self.history = deque(self.history, maxlen=bounded_limit)

    def clear_history(self) -> None:
        """Elimina la trayectoria acumulada sin alterar el estado fisico."""
        self.history.clear()

    def mark_correction(self) -> None:
        """Registra una actuacion de los ejes y reinicia su cronometro."""
        self.seconds_since_last_correction = 0.0
        self.correction_count += 1

    def configure_tracking_updates(self, interval_s: float | None) -> None:
        """Configura intervalo automatico o modo manual y reinicia su ciclo."""
        manual = interval_s is None
        new_interval = self.tracking_update_interval_s if manual else max(0.001, float(interval_s))
        if manual != self.tracking_updates_manual or abs(new_interval - self.tracking_update_interval_s) > 1e-12:
            self.tracking_updates_manual = manual
            self.tracking_update_interval_s = new_interval
            self.reset_tracking_schedule()

    def reset_tracking_schedule(self) -> None:
        """Reinicia contador, temporizador, target retenido y estadisticas."""
        self.seconds_since_tracking_update = 0.0
        self.tracking_update_count = 0
        self.tracking_schedule_initialized = False
        self.tracking_update_pending = False
        self.tracking_corrected_this_step = False
        self.held_target_acim = self.az.angle_deg
        self.held_target_elev = self.el.angle_deg
        self.tracking_error_max_m = 0.0
        self.tracking_error_average_m = 0.0
        self.tracking_error_rms_m = 0.0
        self._reset_interval_error_accumulators()

    def request_tracking_update(self) -> None:
        """Solicita una correccion para el siguiente paso del simulador."""
        self.tracking_update_pending = True

    def _reset_interval_error_accumulators(self) -> None:
        self._interval_error_max_m = 0.0
        self._interval_error_sum_m = 0.0
        self._interval_error_sq_sum_m = 0.0
        self._interval_error_samples = 0

    def _accumulate_tracking_error(self) -> None:
        if not self.spot_valid or not math.isfinite(self.spot_error_radial):
            return
        error_m = max(0.0, self.spot_error_radial)
        self._interval_error_max_m = max(self._interval_error_max_m, error_m)
        self._interval_error_sum_m += error_m
        self._interval_error_sq_sum_m += error_m * error_m
        self._interval_error_samples += 1

    def _finish_tracking_interval(self) -> None:
        if self._interval_error_samples:
            count = self._interval_error_samples
            self.tracking_error_max_m = self._interval_error_max_m
            self.tracking_error_average_m = self._interval_error_sum_m / count
            self.tracking_error_rms_m = math.sqrt(self._interval_error_sq_sum_m / count)
        self._reset_interval_error_accumulators()

    def _apply_tracking_update(self) -> None:
        """Captura la normal solar actual y aplica una correccion instantanea."""
        if self.tracking_schedule_initialized:
            self._finish_tracking_interval()
        self.held_target_acim = self.target_acim
        self.held_target_elev = self.target_elev
        az_delta = wrap_deg(self.held_target_acim - self.az.angle_deg)
        el_delta = self.held_target_elev - self.el.angle_deg
        self.motion_error_sample = self.error_model.sample_motion(az_delta, el_delta)
        self.az.target_deg = self.held_target_acim
        self.el.target_deg = self.held_target_elev
        if self.az.motor_on:
            self.az.angle_deg = clamp(self.held_target_acim, self.az.limit_min, self.az.limit_max)
            self.az.counts = int(round(self.az.angle_deg * self.az.counts_per_degree))
        if self.el.motor_on:
            self.el.angle_deg = clamp(self.held_target_elev, self.el.limit_min, self.el.limit_max)
            self.el.counts = int(round(self.el.angle_deg * self.el.counts_per_degree))
        self.az.ina = self.az.inb = self.el.ina = self.el.inb = 0
        self.seconds_since_tracking_update = 0.0
        self.tracking_update_count += 1
        self.tracking_schedule_initialized = True
        self.tracking_update_pending = False
        self.tracking_corrected_this_step = True
        self.mark_correction()

    def resample_motion_errors(self, az_delta_deg: float = 0.0, el_delta_deg: float = 0.0) -> None:
        """Genera una nueva muestra controlada para ruido y errores de sentido."""
        self.motion_error_sample = self.error_model.sample_motion(az_delta_deg, el_delta_deg)

    def _scenario_uses_errors(self, mode: str) -> bool:
        return mode.strip().lower() != "ideal"

    def scenario_target_vector(self, mode: str) -> tuple[float, float, float]:
        """Devuelve el target nominal o el target fisico perturbado."""
        return self.error_model.effective_target(
            self.nominal_target_vector,
            self._scenario_uses_errors(mode),
        )

    def scenario_normal(self, mode: str) -> tuple[float, float, float]:
        """Devuelve la normal comandada ideal, con error o compensada."""
        corrected = mode.strip().lower() == "corregido"
        return self.error_model.normal_from_command(
            self.az.angle_deg,
            self.el.angle_deg + self.peralte,
            self.motion_error_sample,
            include_errors=self._scenario_uses_errors(mode),
            corrected=corrected,
        )

    def _scenario_impact(
        self,
        mode: str,
    ) -> tuple[float, float, float]:
        """Calcula u, v y error radial para un escenario comparable."""
        normal = self.scenario_normal(mode)
        target = self.scenario_target_vector(mode)
        try:
            diagnostics = compute_reflection_diagnostics(self.sun_vector, normal, target)
            impact = compute_target_impact(
                (0.0, 0.0, 0.0),
                diagnostics.reflected_direction,
                target,
                self.target_tolerance_m,
            )
        except ValueError:
            impact = None
        if impact is None or impact.point is None:
            return (float("nan"), float("nan"), float("nan"))
        return (impact.u_m, impact.v_m, impact.radial_error_m)

    def compute_error_comparison(self) -> None:
        """Actualiza simultaneamente los casos ideal, con error y corregido."""
        self.ideal_spot_u, self.ideal_spot_v, self.ideal_spot_radial = self._scenario_impact("Ideal")
        self.error_spot_u, self.error_spot_v, self.error_spot_radial = self._scenario_impact("Con error")
        (
            self.corrected_spot_u,
            self.corrected_spot_v,
            self.corrected_spot_radial,
        ) = self._scenario_impact("Corregido")

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
        self.nominal_target_vector = self.target_vector_scaled()
        t_unit = normalize(self.nominal_target_vector)
        try:
            self.ideal_normal = compute_heliostat_normal(self.sun_vector, t_unit)
        except ValueError:
            self.ideal_normal = (0.0, 0.0, 0.0)
        acim, elev = angles_from_normal(self.ideal_normal)
        self.raw_target_acim = wrap_deg(acim + self.offset_acim + self.camera_offset_acim)
        self.raw_target_elev = elev + self.peralte + self.offset_ele + self.camera_offset_ele
        self.target_acim = self.raw_target_acim
        self.target_elev = clamp(self.raw_target_elev, 0.0, 90.0)
        self.target_saturated = abs(self.raw_target_elev - self.target_elev) > 1e-6
        self.target_vector = self.scenario_target_vector(self.error_mode)
        self.actual_normal = self.scenario_normal(self.error_mode)
        self.compute_spot_error()
        self.compute_error_comparison()

    def compute_spot_error(self) -> None:
        """Calcula el cruce real del rayo reflejado con el target virtual.

        Usa la ley de reflexion:
            reflejado = incidente - 2 * dot(incidente, normal) * normal

        El target es un plano que pasa por ``target_vector`` y cuya normal apunta
        desde el origen optico hacia su centro. Su eje ``u`` es horizontal y
        positivo hacia el oeste; ``v`` es vertical y positivo hacia el cenit.
        Todas las posiciones y errores lineales se guardan en metros.
        """
        try:
            diagnostics = compute_reflection_diagnostics(
                self.sun_vector,
                self.actual_normal,
                self.target_vector,
            )
            self.incident_direction = diagnostics.incident_direction
            self.reflected_direction = diagnostics.reflected_direction
            self.incidence_angle_deg = diagnostics.incidence_angle_deg
            self.reflection_angle_deg = diagnostics.reflection_angle_deg
            self.reflection_target_error_deg = diagnostics.target_difference_deg
            impact = compute_target_impact(
                (0.0, 0.0, 0.0),
                self.reflected_direction,
                self.target_vector,
                self.target_tolerance_m,
            )
        except ValueError:
            self.incident_direction = v_mul(normalize(self.sun_vector), -1.0)
            self.reflected_direction = (float("nan"), float("nan"), float("nan"))
            self.incidence_angle_deg = float("nan")
            self.reflection_angle_deg = float("nan")
            self.reflection_target_error_deg = float("nan")
            impact = None
        if impact is None or impact.point is None:
            self.spot_point = (float("nan"), float("nan"), float("nan"))
            self.spot_error_x = self.spot_error_z = float("nan")
            self.spot_error_u = self.spot_error_v = float("nan")
            self.spot_error_radial = float("nan")
            self.spot_error_angular_deg = float("nan")
            self.spot_status = "sin impacto"
            self.spot_valid = False
            self.spot_ray_t = float("nan")
            return
        self.spot_point = impact.point
        self.spot_ray_t = float(impact.ray_parameter_m)
        self.spot_error_u = float(impact.u_m)
        self.spot_error_v = float(impact.v_m)
        self.spot_error_radial = float(impact.radial_error_m)
        self.spot_error_angular_deg = float(impact.angular_error_deg)
        self.spot_status = impact.status
        self.spot_valid = True
        self.target_plane_normal = impact.plane_normal
        self.target_u_axis = impact.u_axis
        self.target_v_axis = impact.v_axis
        # Alias conservados para no romper historiales, replay ni CSV previos.
        self.spot_error_x = self.spot_error_u
        self.spot_error_z = self.spot_error_v

    def update(self, dt: float, target_override: tuple[float, float] | None = None) -> None:
        """Avanza un paso temporal de la simulacion.

        En seguimiento automatico el Sol se recalcula siempre, pero el target
        retenido y la pose solo cambian al vencer el intervalo configurado. El
        modo Home conserva su movimiento suave independiente del programador.
        """
        if not self.running:
            return
        dt = max(0.0, float(dt))
        solar_elapsed_s = self.advance_simulation_clock(dt)

        # Al apagar seguimiento se congela la pose mecanica, pero el reloj y
        # la posicion solar siguen avanzando. Este desacoplamiento produce la
        # deriva fisica del rayo reflejado sobre el target.
        if self._last_tracking_state and not self.tracking:
            self.seconds_since_last_correction = 0.0
        elif not self._last_tracking_state and self.tracking:
            self.reset_tracking_schedule()
        self._last_tracking_state = self.tracking
        self.tracking_corrected_this_step = False

        self.compute_geometry()
        if target_override:
            self.tracking_schedule_initialized = False
            self.az.target_deg = target_override[0]
            self.el.target_deg = target_override[1]
            previous_az = self.az.angle_deg
            previous_el = self.el.angle_deg
            if self.automatic and not self.free_mode:
                self.az.update_closed_loop(dt, self.cdr)
                self.el.update_closed_loop(dt, self.cdr)
            if (
                abs(self.az.angle_deg - previous_az) > 1e-9
                or abs(self.el.angle_deg - previous_el) > 1e-9
            ):
                self.mark_correction()
            else:
                self.seconds_since_last_correction += solar_elapsed_s
        elif self.automatic and self.tracking and not self.free_mode:
            if not self.tracking_schedule_initialized:
                self._apply_tracking_update()
            else:
                self.seconds_since_tracking_update += solar_elapsed_s
                self.seconds_since_last_correction = self.seconds_since_tracking_update
                self._accumulate_tracking_error()
                interval_due = (
                    not self.tracking_updates_manual
                    and self.seconds_since_tracking_update + 1e-9 >= self.tracking_update_interval_s
                )
                if self.tracking_update_pending or interval_due:
                    self._apply_tracking_update()
            self.az.target_deg = self.held_target_acim
            self.el.target_deg = self.held_target_elev
            self.az.ina = self.az.inb = self.el.ina = self.el.inb = 0
        else:
            self.az.target_deg = self.target_acim
            self.el.target_deg = self.target_elev
            self.az.ina = self.az.inb = self.el.ina = self.el.inb = 0
            self.seconds_since_last_correction += solar_elapsed_s
            if self.tracking_schedule_initialized:
                self.seconds_since_tracking_update += solar_elapsed_s
        # Los motores pueden cambiar la normal durante este mismo paso. El
        # impacto se vuelve a calcular para que la pantalla no lleve un ciclo de
        # retraso respecto de los angulos mostrados.
        self.target_vector = self.scenario_target_vector(self.error_mode)
        self.actual_normal = self.scenario_normal(self.error_mode)
        self.compute_spot_error()
        self.compute_error_comparison()
        self.iterations += 1
        self.set_history_limit(self.history_limit)
        self.history.append(
            {
                "t": self.iterations,
                "solar_time": (
                    _dt.datetime.now() if self.use_live_time else self.simulated_time
                ).isoformat(timespec="milliseconds"),
                "elapsed_since_correction_s": self.seconds_since_last_correction,
                "elapsed_since_tracking_update_s": self.seconds_since_tracking_update,
                "tracking_update_count": self.tracking_update_count,
                "tracking_corrected": self.tracking_corrected_this_step,
                "tracking_interval_s": (
                    "manual" if self.tracking_updates_manual else self.tracking_update_interval_s
                ),
                "tracking_error_max_m": self.tracking_error_max_m,
                "tracking_error_average_m": self.tracking_error_average_m,
                "tracking_error_rms_m": self.tracking_error_rms_m,
                "error_mode": self.error_mode,
                "ideal_spot_radial": self.ideal_spot_radial,
                "error_spot_radial": self.error_spot_radial,
                "corrected_spot_radial": self.corrected_spot_radial,
                "tracking": self.tracking,
                "az": self.az.angle_deg,
                "el": self.el.angle_deg,
                "az_target": self.az.target_deg,
                "el_target": self.el.target_deg,
                "err_x": self.spot_error_x,
                "err_z": self.spot_error_z,
                "err_u": self.spot_error_u,
                "err_v": self.spot_error_v,
                "err_radial": self.spot_error_radial,
                "spot_valid": self.spot_valid,
                "spot": self.spot_point,
                "incidence_deg": self.incidence_angle_deg,
                "reflection_deg": self.reflection_angle_deg,
                "reflection_target_deg": self.reflection_target_error_deg,
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
        self.last_time_input: tuple[str, str] | None = None
        self.last_specific_time_enabled = False
        self.last_tracking_enabled = self.state.tracking
        self.last_tracking_interval_choice = "1 s"
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
        self.var("advance_solar_time", self.state.advance_solar_time)
        self.var("time_scale_choice", f"{self.state.solar_time_scale:g}x")
        self.var("tracking_interval_choice", self.last_tracking_interval_choice)
        self.var("scale_to_model", self.state.scale_to_model)
        self.var("error_mode", self.state.error_mode)
        for error_name in (
            "enable_elevation_offset",
            "elevation_offset_deg",
            "enable_azimuth_offset",
            "azimuth_offset_deg",
            "enable_north_south_misalignment",
            "north_south_misalignment_deg",
            "enable_target_position_error",
            "target_error_x_m",
            "target_error_y_m",
            "target_error_z_m",
            "enable_heliostat_position_error",
            "heliostat_error_x_m",
            "heliostat_error_y_m",
            "heliostat_error_z_m",
            "enable_peralte_error",
            "peralte_error_deg",
            "enable_backlash",
            "backlash_deg",
            "enable_directional_error",
            "upward_error_deg",
            "downward_error_deg",
            "enable_random_noise",
            "random_noise_std_deg",
            "random_seed",
            "correction_azimuth_deg",
            "correction_elevation_deg",
        ):
            self.var(f"error_{error_name}", getattr(self.state.error_config, error_name))
        for name in (
            "show_sun_vector",
            "show_normal_vector",
            "show_reflected_vector",
            "show_target_direction",
            "show_target_line",
        ):
            self.var(name, getattr(self.state, name))
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
            "simulation_step_s",
            "target_scale_m",
            "target_tolerance_m",
            "mirror_size_m",
            "base_width_m",
            "fork_height_m",
            "rail_length_m",
            "receiver_screen_m",
            "uncertainty_gain",
        ):
            self.var(name, getattr(self.state, name))
        self.var("history_limit", self.state.history_limit)
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
        self.build_time_block(left)
        self.build_motor_block(left)
        self.build_geometry_block(left)
        self.build_auto_block(left)
        self.build_vector_block(left)
        self.build_error_block(left)
        self.build_calibration_block(left)
        self.build_status_block(left)

        # Las vistas graficas del gemelo se organizan como pestanas para que el
        # usuario pueda cambiar entre 3D, spot, trayectoria solar y diagnostico.
        notebook = ttk.Notebook(right)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.scene_canvas = tk.Canvas(notebook, bg="#101821", highlightthickness=0)
        self.receiver_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.solar_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.drift_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.error_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.diagnostic_canvas = tk.Canvas(notebook, bg="#f4f4f4", highlightthickness=0)
        self.logic_canvas = tk.Canvas(notebook, bg="#f7f7f7", highlightthickness=0)
        self.log_canvas = tk.Canvas(notebook, bg="#f7f7f7", highlightthickness=0)
        notebook.add(self.scene_canvas, text="Gemelo 3D")
        notebook.add(self.receiver_canvas, text="Pantalla / spot")
        notebook.add(self.solar_canvas, text="Trayectoria solar")
        notebook.add(self.drift_canvas, text="Deriva temporal")
        notebook.add(self.error_canvas, text="Comparacion de errores")
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
            text=(
                "Fecha especifica ON inicia en estos campos. Con 'Avanzar tiempo solar' "
                "el reloj continua desde ese instante."
            ),
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        for i in range(3):
            row.columnconfigure(i, weight=1)
        self.update_mode_visuals()

    def build_time_block(self, parent: ttk.Frame) -> None:
        """Construye los controles independientes del reloj solar simulado."""
        frame = ttk.LabelFrame(parent, text="Reloj de simulacion", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.add_switch(grid, "Reloj simulado", "advance_solar_time", row=0, col=0)
        ttk.Label(grid, text="Multiplicador", style="Small.TLabel").grid(row=0, column=2, sticky="w", padx=2, pady=2)
        ttk.OptionMenu(
            grid,
            self.vars["time_scale_choice"],
            self.vars["time_scale_choice"].get(),
            "1x",
            "10x",
            "60x",
            "120x",
            "600x",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=0, column=3, sticky="ew", padx=2, pady=2)
        self.add_entry(grid, "Paso manual (s)", "simulation_step_s", 1, 0)
        ttk.Button(
            grid,
            text="AVANZAR PASO",
            style="Gold.TButton",
            command=self.step_simulation_clock,
        ).grid(row=1, column=2, columnspan=2, sticky="ew", padx=3, pady=3)
        ttk.Button(
            grid,
            text="PAUSAR / REANUDAR",
            style="Manual.TButton",
            command=self.toggle_simulation_clock,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=3, pady=3)
        ttk.Button(
            grid,
            text="REINICIAR TIEMPO",
            style="Gold.TButton",
            command=self.reset_simulation_clock,
        ).grid(row=2, column=2, columnspan=2, sticky="ew", padx=3, pady=3)
        ttk.Button(
            grid,
            text="APLICAR FECHA/HORA INICIAL",
            style="Gold.TButton",
            command=self.apply_initial_datetime,
        ).grid(row=3, column=0, columnspan=4, sticky="ew", padx=3, pady=3)
        self.clock_status_label = ttk.Label(
            grid,
            text="",
            style="Readout.TLabel",
            anchor="center",
        )
        self.clock_status_label.grid(row=4, column=0, columnspan=4, sticky="ew", padx=3, pady=(6, 2))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)

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
        ttk.Label(grid, text="Actualizar cada", style="Small.TLabel").grid(row=1, column=0, sticky="w", padx=2, pady=2)
        ttk.OptionMenu(
            grid,
            self.vars["tracking_interval_choice"],
            self.vars["tracking_interval_choice"].get(),
            "1 s",
            "5 s",
            "10 s",
            "30 s",
            "60 s",
            "Manual",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(
            grid,
            text="CORREGIR AHORA",
            style="Gold.TButton",
            command=self.request_tracking_correction,
        ).grid(row=1, column=2, columnspan=2, sticky="ew", padx=4, pady=3)
        self.add_entry(grid, "Consideracion (+/- cdr)", "cdr", 2, 0)
        self.add_entry(grid, "Refresco (s)", "delay_s", 2, 2)
        self.add_entry(grid, "Limite historial", "history_limit", 3, 0)
        ttk.Button(
            grid,
            text="Limpiar trayectoria",
            style="Gold.TButton",
            command=self.clear_spot_history,
        ).grid(row=3, column=2, columnspan=2, sticky="ew", padx=4, pady=3)
        ttk.Label(grid, text="Vista 3D", style="Small.TLabel").grid(row=4, column=0, sticky="w", pady=2, padx=2)
        ttk.OptionMenu(
            grid,
            self.vars["view_mode"],
            self.vars["view_mode"].get(),
            "Isometrica",
            "Frontal",
            "Lateral",
            "Superior",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=4, column=1, sticky="ew", pady=2, padx=2)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

    def build_vector_block(self, parent: ttk.Frame) -> None:
        """Construye controles independientes de visibilidad para la vista 3D."""
        frame = ttk.LabelFrame(parent, text="Vectores geometricos visibles", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        controls = (
            ("Solar incidente", "show_sun_vector", 0, 0),
            ("Normal heliostato", "show_normal_vector", 0, 2),
            ("Rayo reflejado", "show_reflected_vector", 1, 0),
            ("Direccion objetivo", "show_target_direction", 1, 2),
            ("Linea heliostato-target", "show_target_line", 2, 0),
        )
        for label, varname, row, col in controls:
            self.add_switch(grid, label, varname, row=row, col=col)
        for col in range(4):
            grid.columnconfigure(col, weight=1)

    def build_error_block(self, parent: ttk.Frame) -> None:
        """Construye activadores y parametros del modelo de errores."""
        frame = ttk.LabelFrame(parent, text="Errores geometricos y mecanicos", style="Block.TLabelframe")
        frame.pack(fill="x", padx=10, pady=5)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        ttk.Label(grid, text="Caso mostrado", style="Small.TLabel").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.OptionMenu(
            grid,
            self.vars["error_mode"],
            self.vars["error_mode"].get(),
            "Ideal",
            "Con error",
            "Corregido",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=0, column=1, columnspan=3, sticky="ew", padx=2, pady=2)

        self.add_switch(grid, "Offset elevacion", "error_enable_elevation_offset", row=1, col=0)
        self.add_entry(grid, "deg", "error_elevation_offset_deg", 1, 2)
        self.add_switch(grid, "Offset acimut", "error_enable_azimuth_offset", row=2, col=0)
        self.add_entry(grid, "deg", "error_azimuth_offset_deg", 2, 2)
        self.add_switch(grid, "Eje norte-sur", "error_enable_north_south_misalignment", row=3, col=0)
        self.add_entry(grid, "deg", "error_north_south_misalignment_deg", 3, 2)

        self.add_switch(grid, "Error posicion target", "error_enable_target_position_error", row=4, col=0)
        self.add_entry(grid, "X (m)", "error_target_error_x_m", 4, 2)
        self.add_entry(grid, "Y (m)", "error_target_error_y_m", 5, 0)
        self.add_entry(grid, "Z (m)", "error_target_error_z_m", 5, 2)

        self.add_switch(grid, "Error coord. helio", "error_enable_heliostat_position_error", row=6, col=0)
        self.add_entry(grid, "X (m)", "error_heliostat_error_x_m", 6, 2)
        self.add_entry(grid, "Y (m)", "error_heliostat_error_y_m", 7, 0)
        self.add_entry(grid, "Z (m)", "error_heliostat_error_z_m", 7, 2)

        self.add_switch(grid, "Error peralte", "error_enable_peralte_error", row=8, col=0)
        self.add_entry(grid, "deg", "error_peralte_error_deg", 8, 2)
        self.add_switch(grid, "Backlash", "error_enable_backlash", row=9, col=0)
        self.add_entry(grid, "deg", "error_backlash_deg", 9, 2)
        self.add_switch(grid, "Error subida/bajada", "error_enable_directional_error", row=10, col=0)
        self.add_entry(grid, "Subida deg", "error_upward_error_deg", 10, 2)
        self.add_entry(grid, "Bajada deg", "error_downward_error_deg", 11, 2)
        self.add_switch(grid, "Ruido aleatorio", "error_enable_random_noise", row=12, col=0)
        self.add_entry(grid, "Sigma deg", "error_random_noise_std_deg", 12, 2)
        self.add_entry(grid, "Semilla", "error_random_seed", 13, 0)
        ttk.Button(
            grid,
            text="NUEVA MUESTRA",
            style="Gold.TButton",
            command=self.resample_errors,
        ).grid(row=13, column=2, columnspan=2, sticky="ew", padx=3, pady=3)

        ttk.Label(grid, text="Compensacion manual para caso Corregido", style="Small.TLabel").grid(
            row=14, column=0, columnspan=4, sticky="w", padx=2, pady=(7, 2)
        )
        self.add_entry(grid, "Corr. acimut deg", "error_correction_azimuth_deg", 15, 0)
        self.add_entry(grid, "Corr. elev. deg", "error_correction_elevation_deg", 15, 2)
        ttk.Label(
            grid,
            text="XYZ usa +x oeste, +y sur, +z cenit. Cada switch es independiente.",
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        ).grid(row=16, column=0, columnspan=4, sticky="ew", padx=2, pady=(5, 2))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)

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
        self.add_entry(grid, "Escala target +/- (m)", "target_scale_m", 3, 2)
        self.add_entry(grid, "Tolerancia target (m)", "target_tolerance_m", 4, 0)
        self.add_entry(grid, "Zona cdr x", "uncertainty_gain", 4, 2)
        ttk.Label(
            grid,
            text="La escala controla el rango visible del target; la tolerancia define la zona aceptable.",
            style="Small.TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=5, column=0, columnspan=4, sticky="ew", padx=2, pady=(2, 8))
        ttk.Label(grid, text="Limites y velocidad del movimiento simulado", style="Small.TLabel").grid(row=6, column=0, columnspan=4, sticky="w", padx=2, pady=(2, 4))
        self.add_entry(grid, "Acimut min (deg)", "az_limit_min", 7, 0)
        self.add_entry(grid, "Acimut max (deg)", "az_limit_max", 7, 2)
        self.add_entry(grid, "Elev min (deg)", "el_limit_min", 8, 0)
        self.add_entry(grid, "Elev max (deg)", "el_limit_max", 8, 2)
        self.add_entry(grid, "Vel acimut (deg/s)", "az_deg_per_second", 9, 0)
        self.add_entry(grid, "Vel elev (deg/s)", "el_deg_per_second", 9, 2)
        ttk.Label(
            grid,
            text="Los conteos de encoder se mantienen internos porque vienen de la escala del VI/LabVIEW y no suelen requerir ajuste manual.",
            style="Small.TLabel",
            wraplength=440,
            justify="left",
        ).grid(row=10, column=0, columnspan=4, sticky="ew", padx=2, pady=(4, 2))
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
            ("Impacto U/V mm", "spot"),
            ("Error angular", "angular_error"),
            ("Incidencia / Reflexion", "optical_angles"),
            ("Reflejado vs objetivo", "reflection_target_error"),
            ("Limites", "limit_status"),
            ("Estado motores", "motor_status"),
            ("Desde ultima correccion", "correction_elapsed"),
            ("Intervalo de seguimiento", "tracking_interval"),
            ("Correcciones programadas", "tracking_update_count"),
            ("Error max/prom/RMS", "tracking_error_stats"),
            ("Caso de errores", "error_case"),
            ("Radial ideal/error/corr.", "error_comparison"),
            ("Historial deriva", "history_status"),
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
        if not s.spot_valid:
            messages.append(("critica", "El rayo reflejado no intersecta el target al frente"))
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
            self.state.reset_tracking_schedule()
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

    def clear_spot_history(self) -> None:
        """Borra la trayectoria y las curvas de deriva acumuladas."""
        removed = len(self.state.history)
        self.state.clear_history()
        self.log_event(f"Trayectoria limpiada ({removed} muestras)")

    def request_tracking_correction(self) -> None:
        """Solicita una actualizacion inmediata de la orientacion retenida."""
        self.apply_controls()
        if not self.state.automatic or self.state.free_mode or not self.state.tracking:
            self.log_event("Correccion requiere modo Automatico y Seguimiento ON")
            return
        self.state.request_tracking_update()
        self.log_event("Correccion manual solicitada")

    def resample_errors(self) -> None:
        """Genera otra muestra de ruido sin cambiar la configuracion."""
        self.apply_controls()
        self.state.resample_motion_errors()
        self.state.compute_geometry()
        self.log_event("Nueva muestra de errores aleatorios")

    def apply_initial_datetime(self) -> None:
        """Aplica los campos de fecha/hora como nuevo origen de simulacion."""
        date_text = str(self.vars["date_text"].get()).strip()
        time_text = str(self.vars["time_text"].get()).strip()
        try:
            when = _dt.datetime.fromisoformat(f"{date_text}T{time_text}")
        except ValueError:
            self.invalid_time_text = "Fecha/hora especifica invalida"
            self.log_event(self.invalid_time_text)
            return
        self.vars["specific_time"].set(True)
        self.state.use_live_time = False
        self.state.set_simulated_start_time(when)
        self.last_time_input = (date_text, time_text)
        self.last_specific_time_enabled = True
        self.invalid_time_text = ""
        self.log_event(f"Tiempo inicial aplicado: {when:%Y-%m-%d %H:%M:%S}")

    def toggle_simulation_clock(self) -> None:
        """Pausa o reanuda solamente el reloj, sin detener la interfaz."""
        if not bool(self.vars["specific_time"].get()):
            self.log_event("El control del reloj requiere Fecha especifica ON")
            return
        running = not bool(self.vars["advance_solar_time"].get())
        self.vars["advance_solar_time"].set(running)
        self.state.advance_solar_time = running
        self.log_event("Reloj simulado reanudado" if running else "Reloj simulado pausado")

    def reset_simulation_clock(self) -> None:
        """Reinicia el reloj en el origen definido y limpia su trayectoria."""
        self.apply_controls()
        if self.state.use_live_time:
            self.log_event("Reinicio de tiempo requiere Fecha especifica ON")
            return
        self.state.reset_simulated_time()
        self.state.compute_geometry()
        self.log_event(f"Reloj reiniciado: {self.state.simulated_time:%Y-%m-%d %H:%M:%S}")

    def step_simulation_clock(self) -> None:
        """Pausa el reloj y ejecuta un avance manual de tamaño configurable."""
        self.apply_controls()
        if self.state.use_live_time:
            self.log_event("Avance por paso requiere Fecha especifica ON")
            return
        self.vars["advance_solar_time"].set(False)
        self.state.advance_solar_time = False
        advanced_s = self.state.step_simulated_time()
        self.state.compute_geometry()
        self.log_event(f"Paso de tiempo: +{advanced_s:g} s")

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
        specific_time_enabled = bool(self.vars["specific_time"].get())
        self.state.use_live_time = not specific_time_enabled
        if not self.state.use_live_time:
            try:
                date_text = str(self.vars["date_text"].get()).strip()
                time_text = str(self.vars["time_text"].get()).strip()
                time_input = (date_text, time_text)
                if time_input != self.last_time_input or not self.last_specific_time_enabled:
                    when = _dt.datetime.fromisoformat(f"{date_text}T{time_text}")
                    self.state.set_simulated_start_time(when)
                    self.last_time_input = time_input
                if self.invalid_time_text:
                    self.log_event("Fecha especifica valida restaurada")
                self.invalid_time_text = ""
            except ValueError:
                if not self.invalid_time_text:
                    self.log_event("Fecha/hora especifica invalida")
                self.invalid_time_text = "Fecha/hora especifica invalida"
        else:
            self.invalid_time_text = ""
        self.last_specific_time_enabled = specific_time_enabled

        tracking_enabled = bool(self.state.tracking)
        if tracking_enabled != self.last_tracking_enabled:
            if tracking_enabled:
                self.log_event("Seguimiento reanudado")
            else:
                self.log_event("Seguimiento detenido: pose mecanica congelada")
            self.last_tracking_enabled = tracking_enabled

        interval_choice = str(self.vars["tracking_interval_choice"].get()).strip()
        if interval_choice.lower() == "manual":
            self.state.configure_tracking_updates(None)
        else:
            interval_value = float(interval_choice.lower().removesuffix("s").strip())
            self.state.configure_tracking_updates(interval_value)
        self.last_tracking_interval_choice = interval_choice

        config = self.state.error_config
        for var_name, var in self.vars.items():
            if not var_name.startswith("error_"):
                continue
            config_name = var_name.removeprefix("error_")
            if not hasattr(config, config_name):
                continue
            try:
                value = var.get()
                current = getattr(config, config_name)
                if isinstance(current, bool):
                    setattr(config, config_name, bool(value))
                elif isinstance(current, int):
                    setattr(config, config_name, int(value))
                else:
                    setattr(config, config_name, float(value))
            except (tk.TclError, TypeError, ValueError):
                pass
        config.backlash_deg = max(0.0, float(config.backlash_deg))
        config.random_noise_std_deg = max(0.0, float(config.random_noise_std_deg))

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
        scale_text = str(self.vars["time_scale_choice"].get()).strip().lower().removesuffix("x")
        self.state.solar_time_scale = max(0.0, min(float(scale_text), 3600.0))
        self.state.simulation_step_s = max(0.0, min(float(self.state.simulation_step_s), 86400.0))
        self.state.set_history_limit(int(self.state.history_limit))
        self.state.target_scale_m = max(0.001, float(self.state.target_scale_m))
        self.state.target_tolerance_m = max(0.0, float(self.state.target_tolerance_m))
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
            "initial_simulated_time": (
                s.initial_simulated_time.isoformat(timespec="seconds")
                if s.initial_simulated_time is not None
                else ""
            ),
            "simulation_clock_running": s.advance_solar_time,
            "simulation_time_scale": s.solar_time_scale,
            "simulation_step_s": s.simulation_step_s,
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
            "spot_u_mm": s.spot_error_u * 1000.0,
            "spot_v_mm": s.spot_error_v * 1000.0,
            "spot_radial_mm": s.spot_error_radial * 1000.0,
            "spot_angular_error_deg": s.spot_error_angular_deg,
            "spot_status": s.spot_status,
            "spot_valid": s.spot_valid,
            "tracking": s.tracking,
            "elapsed_since_correction_s": s.seconds_since_last_correction,
            "correction_count": s.correction_count,
            "tracking_updates_manual": s.tracking_updates_manual,
            "tracking_update_interval_s": s.tracking_update_interval_s,
            "elapsed_since_tracking_update_s": s.seconds_since_tracking_update,
            "tracking_update_count": s.tracking_update_count,
            "tracking_corrected": s.tracking_corrected_this_step,
            "tracking_error_max_mm": s.tracking_error_max_m * 1000.0,
            "tracking_error_average_mm": s.tracking_error_average_m * 1000.0,
            "tracking_error_rms_mm": s.tracking_error_rms_m * 1000.0,
            "error_mode": s.error_mode,
            "active_errors": ", ".join(s.error_config.active_error_names()),
            "ideal_spot_u_mm": s.ideal_spot_u * 1000.0,
            "ideal_spot_v_mm": s.ideal_spot_v * 1000.0,
            "ideal_spot_radial_mm": s.ideal_spot_radial * 1000.0,
            "error_spot_u_mm": s.error_spot_u * 1000.0,
            "error_spot_v_mm": s.error_spot_v * 1000.0,
            "error_spot_radial_mm": s.error_spot_radial * 1000.0,
            "corrected_spot_u_mm": s.corrected_spot_u * 1000.0,
            "corrected_spot_v_mm": s.corrected_spot_v * 1000.0,
            "corrected_spot_radial_mm": s.corrected_spot_radial * 1000.0,
            "zenith_deg": s.zenith,
            "altitude_deg": s.altitude,
            "solar_azimuth_deg": s.solar_azimuth,
            "sun_x": s.sun_vector[0],
            "sun_y": s.sun_vector[1],
            "sun_z": s.sun_vector[2],
            "incident_x": s.incident_direction[0],
            "incident_y": s.incident_direction[1],
            "incident_z": s.incident_direction[2],
            "normal_x": s.actual_normal[0],
            "normal_y": s.actual_normal[1],
            "normal_z": s.actual_normal[2],
            "reflected_x": s.reflected_direction[0],
            "reflected_y": s.reflected_direction[1],
            "reflected_z": s.reflected_direction[2],
            "incidence_deg": s.incidence_angle_deg,
            "reflection_deg": s.reflection_angle_deg,
            "reflection_target_deg": s.reflection_target_error_deg,
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
        s.spot_error_u = float(sample.get("spot_u_mm", sample["spot_x_mm"])) / 1000.0
        s.spot_error_v = float(sample.get("spot_v_mm", sample["spot_z_mm"])) / 1000.0
        s.spot_error_radial = float(
            sample.get("spot_radial_mm", math.hypot(s.spot_error_u, s.spot_error_v) * 1000.0)
        ) / 1000.0
        s.spot_error_angular_deg = float(sample.get("spot_angular_error_deg", 0.0))
        s.spot_status = str(sample.get("spot_status", classify_target_error(s.spot_error_radial, s.target_tolerance_m)))
        s.spot_valid = bool(sample.get("spot_valid", True))
        s.tracking = bool(sample.get("tracking", s.tracking))
        s.seconds_since_last_correction = float(
            sample.get("elapsed_since_correction_s", s.seconds_since_last_correction)
        )
        s.correction_count = int(sample.get("correction_count", s.correction_count))
        s.tracking_updates_manual = bool(sample.get("tracking_updates_manual", s.tracking_updates_manual))
        s.tracking_update_interval_s = float(
            sample.get("tracking_update_interval_s", s.tracking_update_interval_s)
        )
        s.seconds_since_tracking_update = float(
            sample.get("elapsed_since_tracking_update_s", s.seconds_since_tracking_update)
        )
        s.tracking_update_count = int(sample.get("tracking_update_count", s.tracking_update_count))
        s.tracking_corrected_this_step = bool(sample.get("tracking_corrected", False))
        s.tracking_error_max_m = float(sample.get("tracking_error_max_mm", 0.0)) / 1000.0
        s.tracking_error_average_m = float(sample.get("tracking_error_average_mm", 0.0)) / 1000.0
        s.tracking_error_rms_m = float(sample.get("tracking_error_rms_mm", 0.0)) / 1000.0
        s.error_mode = str(sample.get("error_mode", s.error_mode))
        s.ideal_spot_u = float(sample.get("ideal_spot_u_mm", 0.0)) / 1000.0
        s.ideal_spot_v = float(sample.get("ideal_spot_v_mm", 0.0)) / 1000.0
        s.ideal_spot_radial = float(sample.get("ideal_spot_radial_mm", 0.0)) / 1000.0
        s.error_spot_u = float(sample.get("error_spot_u_mm", 0.0)) / 1000.0
        s.error_spot_v = float(sample.get("error_spot_v_mm", 0.0)) / 1000.0
        s.error_spot_radial = float(sample.get("error_spot_radial_mm", 0.0)) / 1000.0
        s.corrected_spot_u = float(sample.get("corrected_spot_u_mm", 0.0)) / 1000.0
        s.corrected_spot_v = float(sample.get("corrected_spot_v_mm", 0.0)) / 1000.0
        s.corrected_spot_radial = float(sample.get("corrected_spot_radial_mm", 0.0)) / 1000.0
        s.advance_solar_time = bool(sample.get("simulation_clock_running", s.advance_solar_time))
        s.solar_time_scale = float(sample.get("simulation_time_scale", s.solar_time_scale))
        s.simulation_step_s = float(sample.get("simulation_step_s", s.simulation_step_s))
        s.zenith = float(sample["zenith_deg"])
        s.altitude = float(sample["altitude_deg"])
        s.solar_azimuth = float(sample["solar_azimuth_deg"])
        s.sun_vector = (
            float(sample.get("sun_x", s.sun_vector[0])),
            float(sample.get("sun_y", s.sun_vector[1])),
            float(sample.get("sun_z", s.sun_vector[2])),
        )
        s.incident_direction = (
            float(sample.get("incident_x", s.incident_direction[0])),
            float(sample.get("incident_y", s.incident_direction[1])),
            float(sample.get("incident_z", s.incident_direction[2])),
        )
        s.actual_normal = (
            float(sample.get("normal_x", s.actual_normal[0])),
            float(sample.get("normal_y", s.actual_normal[1])),
            float(sample.get("normal_z", s.actual_normal[2])),
        )
        s.reflected_direction = (
            float(sample.get("reflected_x", s.reflected_direction[0])),
            float(sample.get("reflected_y", s.reflected_direction[1])),
            float(sample.get("reflected_z", s.reflected_direction[2])),
        )
        s.incidence_angle_deg = float(sample.get("incidence_deg", s.incidence_angle_deg))
        s.reflection_angle_deg = float(sample.get("reflection_deg", s.reflection_angle_deg))
        s.reflection_target_error_deg = float(
            sample.get("reflection_target_deg", s.reflection_target_error_deg)
        )
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
                previous_az = self.state.az.angle_deg
                previous_el = self.state.el.angle_deg
                if axis == "az":
                    self.state.az.jog(direction, dt)
                else:
                    self.state.el.jog(direction, dt)
                self.state.resample_motion_errors(
                    wrap_deg(self.state.az.angle_deg - previous_az),
                    self.state.el.angle_deg - previous_el,
                )
            target_override = (0.0, 90.0) if self.current_mode == "home" else None
            self.state.update(dt, target_override=target_override)
        self.update_readouts()
        self.record_sample()
        self.draw_scene()
        self.draw_receiver_view()
        self.draw_solar_path()
        self.draw_drift_view()
        self.draw_error_view()
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
        impact_text = (
            f"{s.spot_error_u * 1000.0:7.1f} / {s.spot_error_v * 1000.0:7.1f}"
            if s.spot_valid
            else "SIN IMPACTO"
        )
        optical_angles_text = (
            f"{s.incidence_angle_deg:6.3f} / {s.reflection_angle_deg:6.3f} deg"
            if math.isfinite(s.incidence_angle_deg) and math.isfinite(s.reflection_angle_deg)
            else "NO DEFINIDO"
        )
        target_difference_text = (
            f"{s.reflection_target_error_deg:8.4f} deg"
            if math.isfinite(s.reflection_target_error_deg)
            else "NO DEFINIDO"
        )
        if s.use_live_time:
            clock_text = f"TIEMPO REAL | {self.active_datetime():%Y-%m-%d %H:%M:%S}"
        else:
            clock_state = "EN MARCHA" if s.advance_solar_time else "PAUSADO"
            clock_text = (
                f"{clock_state} | {self.active_datetime():%Y-%m-%d %H:%M:%S} | "
                f"{s.solar_time_scale:g}x"
            )
        self.clock_status_label.configure(text=clock_text)
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
            "spot": impact_text,
            "angular_error": f"{wrap_deg(s.az.target_deg - s.az.angle_deg):6.2f} / {s.el.target_deg - s.el.angle_deg:6.2f}",
            "optical_angles": optical_angles_text,
            "reflection_target_error": target_difference_text,
            "limit_status": limit_text,
            "motor_status": f"AZ {'ON' if s.az.motor_on else 'OFF'} | EL {'ON' if s.el.motor_on else 'OFF'}",
            "correction_elapsed": f"{s.seconds_since_last_correction:8.1f} s solares",
            "tracking_interval": (
                f"Manual | {s.seconds_since_tracking_update:7.1f} s"
                if s.tracking_updates_manual
                else f"{s.tracking_update_interval_s:g} s | transcurrido {s.seconds_since_tracking_update:7.1f} s"
            ),
            "tracking_update_count": f"{s.tracking_update_count:d}",
            "tracking_error_stats": (
                f"{s.tracking_error_max_m * 1000.0:6.2f} / "
                f"{s.tracking_error_average_m * 1000.0:6.2f} / "
                f"{s.tracking_error_rms_m * 1000.0:6.2f} mm"
            ),
            "error_case": f"{s.error_mode} | {len(s.error_config.active_error_names())} activos",
            "error_comparison": (
                f"{s.ideal_spot_radial * 1000.0:6.2f} / "
                f"{s.error_spot_radial * 1000.0:6.2f} / "
                f"{s.corrected_spot_radial * 1000.0:6.2f} mm"
            ),
            "history_status": f"{len(s.history):d} / {s.history_limit:d} muestras",
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
        if self.state.show_normal_vector:
            normal_end = v_add(center, v_mul(n, 0.18))
            self.line3d(c, center, normal_end, "#f8d447", 3)
            self.text3d(c, v_add(normal_end, (0.0, 0.0, 0.025)), "Normal N", "#f8d447")
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
        sx = self.state.target_u_axis
        sz = self.state.target_v_axis
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

        # Vectores opticos con controles independientes para evitar saturacion.
        sun_start = v_add(center, v_mul(self.state.sun_vector, 0.35))
        if self.state.show_sun_vector:
            self.line3d(c, sun_start, center, "#ff9f43", 3, dash=(5, 3))
            self.text3d(c, v_add(sun_start, (0.0, 0.0, 0.035)), "Incidente -S", "#ffb765")

        reflected_end = target_center
        if self.state.spot_valid:
            reflected_end = v_add(self.state.spot_point, (0.0, 0.0, 0.12))
        elif all(math.isfinite(value) for value in self.state.reflected_direction):
            reflected_end = v_add(center, v_mul(self.state.reflected_direction, 0.35))
        if self.state.show_reflected_vector:
            self.line3d(c, center, reflected_end, "#fff06a", 4)
            self.text3d(c, v_add(reflected_end, (0.0, 0.0, 0.025)), "Reflejado", "#fff49b")

        target_direction_end = v_add(center, v_mul(t_unit, 0.28))
        if self.state.show_target_direction:
            self.line3d(c, center, target_direction_end, "#58d6e7", 3)
            self.text3d(c, v_add(target_direction_end, (0.0, 0.0, 0.025)), "Objetivo T", "#8ce8f2")
        if self.state.show_target_line:
            self.line3d(c, center, target_center, "#b9c6d3", 2, dash=(3, 5))
            self.text3d(c, v_add(target_center, (0.0, 0.0, 0.035)), "Linea H-target", "#c8d3df")

        target_distance = max(0.05, v_norm(self.state.target_vector))
        cone_radius = clamp(target_distance * math.tan(max(0.0, self.state.cdr) * DEG) * self.state.uncertainty_gain, 0.003, 0.08)
        if self.state.show_target_line:
            for edge in (
                v_add(target_center, v_mul(sx, cone_radius)),
                v_add(target_center, v_mul(sx, -cone_radius)),
                v_add(target_center, v_mul(sz, cone_radius)),
                v_add(target_center, v_mul(sz, -cone_radius)),
            ):
                self.line3d(c, center, edge, "#dce5ed", 1, dash=(3, 4))
        if all(math.isfinite(p) for p in self.state.spot_point):
            spot = v_add(self.state.spot_point, (0.0, 0.0, 0.12))
            px, py, _ = self.project(spot, w, h)
            c.create_oval(px - 5, py - 5, px + 5, py + 5, fill="#ff3333", outline="#ffffff", width=1)

        status_label, status_color, status_detail = self.system_status()
        sun_side = "Oeste" if self.state.sun_vector[0] > 0.02 else "Este" if self.state.sun_vector[0] < -0.02 else "Centro"
        normal_side = "Oeste" if self.state.ideal_normal[0] > 0.02 else "Este" if self.state.ideal_normal[0] < -0.02 else "Centro"
        spot_info = (
            f"Impacto U/V {self.state.spot_error_u * 1000.0:+7.1f}, {self.state.spot_error_v * 1000.0:+7.1f} mm"
            if self.state.spot_valid
            else "Impacto: sin interseccion frontal"
        )
        info = (
            f"Acim actual {self.state.az.angle_deg:6.2f} deg  -> {self.state.az.target_deg:6.2f} deg\n"
            f"Elev actual {self.state.el.angle_deg:6.2f} deg  -> {self.state.el.target_deg:6.2f} deg\n"
            f"{spot_info}\n"
            f"Sol: {sun_side} | Normal ideal: {normal_side}\n"
            f"i/r {self.state.incidence_angle_deg:6.3f}/{self.state.reflection_angle_deg:6.3f} deg | R-T {self.state.reflection_target_error_deg:6.3f} deg\n"
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
        """Dibuja el target virtual y el impacto calculado del rayo reflejado.

        El eje ``u`` es horizontal y positivo hacia el oeste; ``v`` es vertical
        y positivo hacia el cenit. La escala y la tolerancia se leen de
        ``TwinState`` en metros. Si el impacto cae fuera de escala, el marcador
        se fija al borde en su direccion real y se rotula como fuera de vista.
        """
        c = self.receiver_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        hist = list(self.state.history)
        c.create_text(24, 22, anchor="w", text="Target virtual: interseccion rayo-plano", fill="#111111", font=("Segoe UI", 15, "bold"))
        cx, cy = w * 0.37, h * 0.52
        half_pixels = max(40.0, min(w * 0.31, h * 0.40))
        half_range_m = max(0.001, self.state.target_scale_m)
        pixels_per_m = half_pixels / half_range_m
        left, right = cx - half_pixels, cx + half_pixels
        top, bottom = cy - half_pixels, cy + half_pixels
        c.create_rectangle(left, top, right, bottom, fill="#fbf8ed", outline="#6f6040", width=3)

        # Reticula uniforme; las etiquetas expresan milimetros locales.
        divisions = 4
        for i in range(-divisions, divisions + 1):
            offset = half_pixels * i / divisions
            color = "#8a7b58" if i == 0 else "#d6c9a8"
            width_line = 2 if i == 0 else 1
            c.create_line(cx + offset, top, cx + offset, bottom, fill=color, width=width_line)
            c.create_line(left, cy - offset, right, cy - offset, fill=color, width=width_line)
            value_mm = half_range_m * 1000.0 * i / divisions
            if i != 0:
                c.create_text(cx + offset, bottom + 13, text=f"{value_mm:.0f}", fill="#5d5138", font=("Consolas", 8))
                c.create_text(left - 8, cy - offset, anchor="e", text=f"{value_mm:.0f}", fill="#5d5138", font=("Consolas", 8))
        c.create_text(right, bottom + 30, anchor="e", text="u [mm]  oeste +", fill="#333333", font=("Segoe UI", 9, "bold"))
        c.create_text(left, top - 16, anchor="w", text="v [mm]  cenit +", fill="#333333", font=("Segoe UI", 9, "bold"))

        screen_radius_px = min(half_pixels, 0.5 * self.state.receiver_screen_m * pixels_per_m)
        c.create_oval(
            cx - screen_radius_px,
            cy - screen_radius_px,
            cx + screen_radius_px,
            cy + screen_radius_px,
            outline="#9b7a2f",
            width=2,
        )
        tolerance_px = min(half_pixels, self.state.target_tolerance_m * pixels_per_m)
        c.create_oval(
            cx - tolerance_px,
            cy - tolerance_px,
            cx + tolerance_px,
            cy + tolerance_px,
            outline="#159447",
            width=3,
            dash=(5, 3),
        )

        pts = []
        for p in hist[-220:]:
            if not p.get("spot_valid", True):
                continue
            u_m = float(p.get("err_u", p["err_x"]))
            v_m = float(p.get("err_v", p["err_z"]))
            x = cx + u_m * pixels_per_m
            y = cy - v_m * pixels_per_m
            if left <= x <= right and top <= y <= bottom:
                pts.extend([x, y])
        if len(pts) >= 4:
            c.create_line(*pts, fill="#cc3333", width=2)
        c.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#2fbf62", outline="#ffffff", width=2)

        outside_view = False
        if self.state.spot_valid:
            raw_x = cx + self.state.spot_error_u * pixels_per_m
            raw_y = cy - self.state.spot_error_v * pixels_per_m
            outside_view = not (left <= raw_x <= right and top <= raw_y <= bottom)
            marker_x = clamp(raw_x, left, right)
            marker_y = clamp(raw_y, top, bottom)
            marker_color = {
                "centrado": "#16883f",
                "aceptable": "#e09a16",
                "fuera de tolerancia": "#d92828",
            }.get(self.state.spot_status, "#d92828")
            c.create_oval(marker_x - 8, marker_y - 8, marker_x + 8, marker_y + 8, fill=marker_color, outline="#ffffff", width=2)
            if outside_view:
                c.create_text(marker_x, marker_y - 16, text="fuera de escala", fill="#9f1239", font=("Segoe UI", 9, "bold"))

        text_x = w * 0.72
        c.create_rectangle(text_x - 18, 92, w - 28, h - 72, fill="#ffffff", outline="#c7c7c7")
        c.create_text(text_x, 118, anchor="w", text="Lectura directa", fill="#111111", font=("Segoe UI", 13, "bold"))
        if self.state.spot_valid:
            readout_lines = (
                f"Horizontal u: {self.state.spot_error_u * 1000.0:+8.2f} mm\n"
                f"Vertical v:   {self.state.spot_error_v * 1000.0:+8.2f} mm\n"
                f"Error radial: {self.state.spot_error_radial * 1000.0:8.2f} mm\n"
                f"Error angular:{self.state.spot_error_angular_deg:8.4f} deg\n"
                f"Distancia rayo:{self.state.spot_ray_t:7.3f} m"
            )
        else:
            readout_lines = "El rayo es paralelo al plano\no intersecta el target al frente."
        c.create_text(text_x, 154, anchor="nw", text=readout_lines, fill="#222222", font=("Consolas", 11))
        status_color = {
            "centrado": "#16883f",
            "aceptable": "#b7791f",
            "fuera de tolerancia": "#b91c1c",
            "sin impacto": "#6b7280",
        }.get(self.state.spot_status, "#6b7280")
        c.create_rectangle(text_x, 294, w - 46, 328, fill=status_color, outline="")
        c.create_text(text_x + 10, 311, anchor="w", text=self.state.spot_status.upper(), fill="#ffffff", font=("Segoe UI", 11, "bold"))
        c.create_text(
            text_x,
            350,
            anchor="nw",
            text=(
                f"Escala: +/- {half_range_m * 1000.0:.0f} mm\n"
                f"Tolerancia: {self.state.target_tolerance_m * 1000.0:.1f} mm\n"
                f"Pantalla: {self.state.receiver_screen_m * 1000.0:.0f} mm diam.\n"
                "Centro verde | trayectoria roja"
            ),
            fill="#333333",
            font=("Segoe UI", 10),
        )

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

    def draw_drift_view(self) -> None:
        """Grafica la deriva del spot y el tiempo desde la ultima correccion."""
        c = self.drift_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        hist = list(self.state.history)
        tracking_text = "ACTIVO" if self.state.tracking else "DETENIDO / POSE FIJA"
        tracking_color = "#16883f" if self.state.tracking else "#b91c1c"
        c.create_text(24, 22, anchor="w", text="Deriva temporal del punto reflejado", fill="#111111", font=("Segoe UI", 15, "bold"))
        c.create_rectangle(24, 46, w - 24, 80, fill="#ffffff", outline="#c7c7c7")
        c.create_rectangle(24, 46, 245, 80, fill=tracking_color, outline="")
        c.create_text(38, 63, anchor="w", text=f"SEGUIMIENTO: {tracking_text}", fill="#ffffff", font=("Segoe UI", 10, "bold"))
        c.create_text(
            265,
            63,
            anchor="w",
            text=(
                f"Hora solar {self.active_datetime():%Y-%m-%d %H:%M:%S}   |   "
                f"intervalo {'Manual' if self.state.tracking_updates_manual else f'{self.state.tracking_update_interval_s:g} s'}   |   "
                f"desde actualizacion {self.state.seconds_since_tracking_update:.1f} s   |   "
                f"correcciones {self.state.tracking_update_count}"
            ),
            fill="#222222",
            font=("Consolas", 10),
        )

        gap = 18
        left = 24
        right = w - 24
        top = 96
        bottom = h - 28
        mid_x = (left + right) // 2
        mid_y = (top + bottom) // 2
        boxes = (
            (left, top, mid_x - gap // 2, mid_y - gap // 2),
            (mid_x + gap // 2, top, right, mid_y - gap // 2),
            (left, mid_y + gap // 2, mid_x - gap // 2, bottom),
            (mid_x + gap // 2, mid_y + gap // 2, right, bottom),
        )
        titles = (
            "Error horizontal u vs tiempo",
            "Error vertical v vs tiempo",
            "Error radial vs tiempo",
            "Tiempo desde ultima actualizacion",
        )
        labels = ("mm", "mm", "mm", "s solares")
        colors = ("#2563eb", "#805ad5", "#c53030", "#16883f")
        keys = ("err_u", "err_v", "err_radial", "elapsed_since_tracking_update_s")
        series: list[list[float]] = []
        for key in keys:
            values: list[float] = []
            for sample in hist:
                if key != "elapsed_since_tracking_update_s" and not sample.get("spot_valid", True):
                    continue
                value = float(sample.get(key, 0.0))
                if math.isfinite(value):
                    values.append(value if key == "elapsed_since_tracking_update_s" else value * 1000.0)
            series.append(values)

        for box, title, label, color, values in zip(boxes, titles, labels, colors, series):
            self.draw_axes(c, *box, title, label)
            if title == "Error radial vs tiempo":
                upper = max(values + [1.0])
                self.plot_series(c, box, values, color, 0.0, upper)
            elif title == "Tiempo desde ultima actualizacion":
                upper = max(values + [1.0])
                self.plot_series(c, box, values, color, 0.0, upper)
            else:
                extent = max([abs(value) for value in values] + [1.0])
                self.plot_series(c, box, values, color, -extent, extent)

        # Marcas verticales doradas: instantes en que la pose fue corregida.
        if len(hist) >= 2:
            radial_box = boxes[2]
            plot_left = radial_box[0] + 45
            plot_right = radial_box[2] - 16
            plot_top = radial_box[1] + 18
            plot_bottom = radial_box[3] - 30
            for idx, sample in enumerate(hist):
                if sample.get("tracking_corrected", False):
                    marker_x = plot_left + (plot_right - plot_left) * idx / (len(hist) - 1)
                    c.create_line(marker_x, plot_top, marker_x, plot_bottom, fill="#d69e2e", width=1, dash=(3, 3))
            c.create_text(
                radial_box[2] - 24,
                radial_box[1] + 28,
                anchor="ne",
                text="dorado = correccion",
                fill="#9a6700",
                font=("Segoe UI", 8, "bold"),
            )

        if not hist:
            c.create_text(w / 2, h / 2, text="Sin muestras: inicia la simulacion para formar la trayectoria", fill="#6b7280", font=("Segoe UI", 13, "bold"))
        else:
            first_time = str(hist[0].get("solar_time", ""))[11:19]
            last_time = str(hist[-1].get("solar_time", ""))[11:19]
            for box in boxes:
                c.create_text(box[0] + 48, box[3] - 13, anchor="w", text=first_time, fill="#666666", font=("Consolas", 8))
                c.create_text(box[2] - 18, box[3] - 13, anchor="e", text=last_time, fill="#666666", font=("Consolas", 8))

    def draw_error_view(self) -> None:
        """Compara los impactos ideal, perturbado y compensado."""
        c = self.error_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        s = self.state
        c.create_text(24, 22, anchor="w", text="Comparacion de errores geometricos y mecanicos", fill="#111111", font=("Segoe UI", 15, "bold"))
        mode_color = {"Ideal": "#16883f", "Con error": "#b91c1c", "Corregido": "#2563eb"}.get(s.error_mode, "#475569")
        c.create_rectangle(24, 48, 270, 82, fill=mode_color, outline="")
        c.create_text(38, 65, anchor="w", text=f"CASO MOSTRADO: {s.error_mode.upper()}", fill="#ffffff", font=("Segoe UI", 10, "bold"))
        active_names = s.error_config.active_error_names()
        c.create_text(
            292,
            65,
            anchor="w",
            text="Activos: " + (", ".join(active_names) if active_names else "ninguno"),
            fill="#222222",
            font=("Segoe UI", 10),
        )

        cx, cy = w * 0.34, h * 0.52
        half_pixels = max(80.0, min(w * 0.27, h * 0.35))
        half_range_m = max(0.001, s.target_scale_m)
        pixels_per_m = half_pixels / half_range_m
        left, right = cx - half_pixels, cx + half_pixels
        top, bottom = cy - half_pixels, cy + half_pixels
        c.create_rectangle(left, top, right, bottom, fill="#fffdf5", outline="#6f6040", width=3)
        for idx in range(-4, 5):
            offset = half_pixels * idx / 4.0
            color = "#8a7b58" if idx == 0 else "#ded5bc"
            c.create_line(cx + offset, top, cx + offset, bottom, fill=color)
            c.create_line(left, cy - offset, right, cy - offset, fill=color)
        tolerance_px = min(half_pixels, s.target_tolerance_m * pixels_per_m)
        c.create_oval(cx - tolerance_px, cy - tolerance_px, cx + tolerance_px, cy + tolerance_px, outline="#16883f", width=2, dash=(5, 3))
        c.create_text(cx, bottom + 30, text="u [mm] oeste +", fill="#333333", font=("Segoe UI", 9, "bold"))
        c.create_text(left, top - 18, anchor="w", text="v [mm] cenit +", fill="#333333", font=("Segoe UI", 9, "bold"))

        cases = (
            ("Ideal", s.ideal_spot_u, s.ideal_spot_v, s.ideal_spot_radial, "#16883f"),
            ("Con error", s.error_spot_u, s.error_spot_v, s.error_spot_radial, "#d62828"),
            ("Corregido", s.corrected_spot_u, s.corrected_spot_v, s.corrected_spot_radial, "#2563eb"),
        )
        for label, u_m, v_m, _radial_m, color in cases:
            if not (math.isfinite(u_m) and math.isfinite(v_m)):
                continue
            px = clamp(cx + u_m * pixels_per_m, left, right)
            py = clamp(cy - v_m * pixels_per_m, top, bottom)
            radius = 9 if label == s.error_mode else 6
            c.create_oval(px - radius, py - radius, px + radius, py + radius, fill=color, outline="#ffffff", width=2)
            c.create_text(px + 10, py - 10, anchor="w", text=label, fill=color, font=("Segoe UI", 8, "bold"))

        panel_x = w * 0.68
        panel_left = panel_x - 80
        c.create_rectangle(panel_left, 112, w - 28, h - 42, fill="#ffffff", outline="#c7c7c7")
        c.create_text(panel_x, 136, anchor="w", text="Errores sobre el target", fill="#111111", font=("Segoe UI", 13, "bold"))
        y = 176
        max_radial_mm = max(
            [value * 1000.0 for _label, _u, _v, value, _color in cases if math.isfinite(value)] + [1.0]
        )
        for label, u_m, v_m, radial_m, color in cases:
            c.create_text(panel_x, y, anchor="w", text=label, fill=color, font=("Segoe UI", 11, "bold"))
            if math.isfinite(radial_m):
                values_text = f"u {u_m * 1000.0:+8.2f} | v {v_m * 1000.0:+8.2f} | r {radial_m * 1000.0:8.2f} mm"
                c.create_text(panel_x, y + 24, anchor="w", text=values_text, fill="#222222", font=("Consolas", 10))
                c.create_rectangle(panel_x, y + 46, w - 62, y + 62, fill="#ececec", outline="#cccccc")
                bar_end = panel_x + (w - 62 - panel_x) * radial_m * 1000.0 / max_radial_mm
                c.create_rectangle(panel_x, y + 46, bar_end, y + 62, fill=color, outline="")
            else:
                c.create_text(panel_x, y + 24, anchor="w", text="sin impacto", fill="#6b7280", font=("Consolas", 10))
            y += 100

        sample = s.motion_error_sample
        sample_text = (
            "Muestra dependiente del movimiento\n"
            f"Direccion AZ/EL: {sample.az_direction:+d} / {sample.el_direction:+d}\n"
            f"Backlash AZ/EL: {sample.backlash_az_deg:+.4f} / {sample.backlash_el_deg:+.4f} deg\n"
            f"Error subida/bajada: {sample.directional_el_deg:+.4f} deg\n"
            f"Ruido AZ/EL: {sample.noise_az_deg:+.4f} / {sample.noise_el_deg:+.4f} deg\n"
            f"Compensacion AZ/EL: {s.error_config.correction_azimuth_deg:+.4f} / {s.error_config.correction_elevation_deg:+.4f} deg"
        )
        c.create_text(panel_x, y + 8, anchor="nw", text=sample_text, fill="#222222", font=("Consolas", 10))

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
        spot_err = self.state.spot_error_radial * 1000.0 if self.state.spot_valid else 0.0
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
        errs = [
            float(p.get("err_radial", math.hypot(p["err_x"], p["err_z"]))) * 1000.0
            for p in hist
            if p.get("spot_valid", True)
            and math.isfinite(float(p.get("err_radial", math.hypot(p["err_x"], p["err_z"]))))
        ]
        ymax = max(errs + [10.0])
        self.plot_series(c, box, errs, "#c53030", 0.0, min(max(ymax, 10.0), 500.0))
        c.create_text(w - 360, 100, anchor="nw", text=(
            f"Acimut real/obj: {self.state.az.angle_deg:6.2f} / {self.state.az.target_deg:6.2f} deg\n"
            f"Elev real/obj:  {self.state.el.angle_deg:6.2f} / {self.state.el.target_deg:6.2f} deg\n"
            f"Motor acim: {'ON' if self.state.az.motor_on else 'OFF'}   PWM {self.state.az.pwm * 100:4.0f}%\n"
            f"Motor elev: {'ON' if self.state.el.motor_on else 'OFF'}   PWM {self.state.el.pwm * 100:4.0f}%\n"
            f"cdr (+/-): {self.state.cdr:6.3f} deg\n"
            f"Actualizacion: {'Manual' if self.state.tracking_updates_manual else f'{self.state.tracking_update_interval_s:g} s'}\n"
            f"Correcciones: {self.state.tracking_update_count:6d} | desde ultima: {self.state.seconds_since_tracking_update:7.1f} s\n"
            f"Err max/prom/RMS: {self.state.tracking_error_max_m * 1000.0:6.2f} / {self.state.tracking_error_average_m * 1000.0:6.2f} / {self.state.tracking_error_rms_m * 1000.0:6.2f} mm\n"
            f"Metodo: {self.state.solar_source}\n"
            f"Tiempo usado: {self.active_datetime():%Y-%m-%d %H:%M:%S}"
        ), fill="#222222", font=("Consolas", 11))
        vector_x = max(42, w - 460)
        vector_y = 350
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
        target_direction = normalize(s.target_vector)
        vector_text = (
            f"S solar   = ({s.sun_vector[0]:+.3f}, {s.sun_vector[1]:+.3f}, {s.sun_vector[2]:+.3f})\n"
            f"I incidente=({s.incident_direction[0]:+.3f}, {s.incident_direction[1]:+.3f}, {s.incident_direction[2]:+.3f})\n"
            f"T objetivo= ({target_direction[0]:+.3f}, {target_direction[1]:+.3f}, {target_direction[2]:+.3f})\n"
            f"N ideal   = ({s.ideal_normal[0]:+.3f}, {s.ideal_normal[1]:+.3f}, {s.ideal_normal[2]:+.3f})\n"
            f"N actual  = ({s.actual_normal[0]:+.3f}, {s.actual_normal[1]:+.3f}, {s.actual_normal[2]:+.3f})\n"
            f"R reflejado=({s.reflected_direction[0]:+.3f}, {s.reflected_direction[1]:+.3f}, {s.reflected_direction[2]:+.3f})\n"
            f"Angulos i/r = {s.incidence_angle_deg:.4f} / {s.reflection_angle_deg:.4f} deg\n"
            f"Diferencia R-T = {s.reflection_target_error_deg:.5f} deg\n"
            f"Target crudo EL: {s.raw_target_elev:+.2f} deg | Peralte helio: {s.peralte:+.2f} deg\n"
            f"Impacto: {s.spot_status} | error angular: {s.spot_error_angular_deg:.4f} deg"
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

    Verifica el modelo completo, los casos esenciales del target virtual y la
    ley de reflexion sin abrir Tkinter.
    """
    state = TwinState()
    state.use_live_time = False
    state.simulated_time = _dt.datetime(2026, 6, 21, 12, 0, 0)
    state.advance_solar_time = False
    state.peralte = 0.0
    state.compute_geometry()
    state.az.angle_deg = state.target_acim
    state.el.angle_deg = state.target_elev
    for _ in range(20):
        state.update(0.05)
    assert math.isfinite(state.target_acim)
    assert math.isfinite(state.target_elev)
    assert state.spot_valid
    assert math.isfinite(state.spot_error_radial)
    assert state.spot_error_radial < 1e-8

    target = (0.0, 5.0, 0.0)
    centered = compute_target_impact((0.0, 0.0, 0.0), target, target, 0.01)
    assert centered.point is not None
    assert centered.radial_error_m is not None and centered.radial_error_m < 1e-9
    normal, u_axis, v_axis = target_coordinate_frame(target)
    side_point, _t = intersect_ray_plane((0.0, 0.0, 0.0), (0.1, 1.0, 0.0), target, normal)
    assert side_point is not None
    side_u, _side_v = world_to_target_coordinates(side_point, target, u_axis, v_axis)
    assert side_u > 0.0
    parallel_point, parallel_t = intersect_ray_plane(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        target,
        normal,
    )
    assert parallel_point is None and parallel_t is None

    sun_direction = normalize((-0.35, 0.72, 0.60))
    target_direction = normalize((0.18, 0.97, -0.16))
    ideal_normal = compute_heliostat_normal(sun_direction, target_direction)
    optical = compute_reflection_diagnostics(sun_direction, ideal_normal, target_direction)
    assert abs(v_norm(ideal_normal) - 1.0) < 1e-12
    assert abs(v_norm(optical.reflected_direction) - 1.0) < 1e-12
    assert abs(optical.incidence_angle_deg - optical.reflection_angle_deg) < 1e-10
    assert optical.target_difference_deg < 1e-6
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
