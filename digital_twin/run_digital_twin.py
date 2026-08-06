"""
Gemelo digital del mini horno solar / mini heliostato.

Version estable 2.0.

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
import time
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

try:
    from digital_twin.correction_model import CorrectionConfig, CorrectionModel
except ModuleNotFoundError:  # Permite ejecutar directamente este archivo .py.
    from correction_model import CorrectionConfig, CorrectionModel

try:
    from digital_twin.facet_model import (
        Facet,
        FacetRayResult,
        build_compact_facets,
        trace_facets,
    )
except ModuleNotFoundError:  # Permite ejecutar directamente este archivo .py.
    from facet_model import (
        Facet,
        FacetRayResult,
        build_compact_facets,
        trace_facets,
    )

try:
    from digital_twin.spot_model import (
        SpotMapResult,
        SpotMetrics,
        contribution_from_ray,
        generate_spot_map,
    )
except ModuleNotFoundError:  # Permite ejecutar directamente este archivo .py.
    from spot_model import SpotMapResult, SpotMetrics, contribution_from_ray, generate_spot_map


TAU = 2.0 * math.pi
DEG = math.pi / 180.0
RAD = 180.0 / math.pi
APP_VERSION = "2.0.0"
APP_RELEASE = "2.0"
PVLIB_STATUS: bool | None = None
RENDER_QUALITY_INTERVALS_S = {
    "Rapida": 0.20,
    "Equilibrada": 0.08,
    "Alta": 0.0,
}
MINIHORNO_PROFILE = {
    "lat_deg": 18.85,
    "lon_deg": -99.233333,
    "utc_offset_hours": -6.0,
    "rx": 0.0,
    "ry": 5.55,
    "rz": -0.40,
    "peralte": 0.40,
    "scale_to_model": False,
    "mirror_size_m": 2.00,
    "base_width_m": 1.90,
    "fork_height_m": 2.20,
    "rail_length_m": 5.50,
    "receiver_screen_m": 1.60,
    "target_scale_m": 0.10,
    "target_tolerance_m": 0.010,
    "uncertainty_gain": 1.0,
    "az_limit_min": -95.0,
    "az_limit_max": 95.0,
    "el_limit_min": 0.0,
    "el_limit_max": 90.0,
    "az_counts_per_degree": 1000.0,
    "el_counts_per_degree": 1000.0,
    "az_deg_per_second": 9.0,
    "el_deg_per_second": 9.0,
    "facet_shape": "Cuadrada",
    "facet_count": 9,
    "facet_gap_m": 0.030,
    "facet_size_m": 0.300,
    "facet_focal_distance_m": 2.500,
    "spot_base_sigma_m": 0.003,
    "spot_map_half_size_m": 0.050,
    "spot_map_resolution": 51,
}

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


def choose_scene_front_group(
    heliostat_depth: float,
    concentrator_depth: float,
    previous_group: str,
    hysteresis: float,
) -> str:
    """Elige el grupo frontal sin alternar cuando las profundidades empatan."""
    depth_gap = concentrator_depth - heliostat_depth
    if abs(depth_gap) <= max(0.0, hysteresis) and previous_group in (
        "heliostat",
        "concentrator",
    ):
        return previous_group
    return "heliostat" if heliostat_depth < concentrator_depth else "concentrator"


def render_interval_for_quality(quality: str) -> float:
    """Devuelve el intervalo minimo entre dibujos para una calidad grafica.

    Este intervalo solo limita el redibujado de Tkinter; el paso temporal y
    los calculos fisicos conservan su frecuencia configurada.
    """
    return RENDER_QUALITY_INTERVALS_S.get(quality, RENDER_QUALITY_INTERVALS_S["Equilibrada"])


def normalize_spot_resolution(value: int) -> int:
    """Limita la resolucion a 21-121 y conserva cualquier valor impar valido."""
    bounded = max(21, min(int(value), 121))
    return bounded if bounded % 2 == 1 else min(121, bounded + 1)


def spot_heat_color(value: float, maximum: float) -> str:
    """Convierte una intensidad del spot en un color de mapa termico."""
    ratio = clamp(value / maximum if maximum > 1e-18 else 0.0, 0.0, 1.0)
    stops = (
        (0.00, (2, 6, 23)),
        (0.20, (30, 64, 175)),
        (0.45, (6, 182, 212)),
        (0.70, (250, 204, 21)),
        (1.00, (220, 38, 38)),
    )
    for stop_index in range(len(stops) - 1):
        start_value, start_rgb = stops[stop_index]
        end_value, end_rgb = stops[stop_index + 1]
        if ratio <= end_value:
            fraction = (ratio - start_value) / max(1e-12, end_value - start_value)
            red, green, blue = (
                round(start + (end - start) * fraction)
                for start, end in zip(start_rgb, end_rgb)
            )
            return f"#{red:02x}{green:02x}{blue:02x}"
    return "#dc2626"


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
    utc_offset_hours: float | None = None,
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
    # El meridiano horario depende de la zona civil, no del meridiano
    # geografico mas cercano. En Temixco la longitud -99.23 deg pertenece a
    # UTC-6 (meridiano -90 deg); inferir -105 deg desplaza el Sol una hora.
    if utc_offset_hours is None:
        utc_offset_hours = round(lon_deg / 15.0)
    standard_meridian = 15.0 * clamp(float(utc_offset_hours), -14.0, 14.0)
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
    utc_offset_hours: float | None = None,
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
            zen, alt, az = solar_position_db(
                when, lat_deg, lon_deg, "REDA", utc_offset_hours
            )
            return zen, alt, az, "SPA/PVLIB no disponible; usando REDA aprox."
        try:
            import pandas as pd  # type: ignore
            from pvlib import solarposition  # type: ignore

            PVLIB_STATUS = True
            localized_when = when
            if when.tzinfo is None and utc_offset_hours is not None:
                localized_when = when.replace(
                    tzinfo=_dt.timezone(
                        _dt.timedelta(hours=clamp(float(utc_offset_hours), -14.0, 14.0))
                    )
                )
            timestamp = pd.DatetimeIndex([pd.Timestamp(localized_when)])
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
            zen, alt, az = solar_position_db(
                when, lat_deg, lon_deg, "REDA", utc_offset_hours
            )
            return zen, alt, az, "SPA/PVLIB no disponible; usando REDA aprox."
    zen, alt, az = solar_position_db(
        when, lat_deg, lon_deg, method, utc_offset_hours
    )
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
    utc_offset_hours: float = -6.0
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
    scale_to_model: bool = False
    offset_ele: float = 0.0
    offset_acim: float = 0.0
    camera_offset_ele: float = 0.0
    camera_offset_acim: float = 0.0
    cdr: float = 0.07
    delay_s: float = 0.05
    target_scale_m: float = 0.10
    target_tolerance_m: float = 0.010
    mirror_size_m: float = 2.00
    base_width_m: float = 1.90
    fork_height_m: float = 2.20
    rail_length_m: float = 5.50
    receiver_screen_m: float = 1.60
    uncertainty_gain: float = 1.0
    tracking: bool = True
    automatic: bool = True
    free_mode: bool = False
    show_sun_vector: bool = True
    show_normal_vector: bool = True
    show_reflected_vector: bool = True
    show_target_direction: bool = True
    show_target_line: bool = True
    show_mechanical_guides: bool = False
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
    correction_config: CorrectionConfig = field(default_factory=CorrectionConfig)
    correction_model: CorrectionModel = field(init=False, repr=False)
    drift_correction_az_deg: float = 0.0
    drift_correction_el_deg: float = 0.0
    drift_correction_pending: bool = False
    drift_corrected_this_step: bool = False
    facet_field_enabled: bool = False
    facet_shape: str = "Cuadrada"
    facet_count: int = 9
    facet_rows: int = 3
    facet_columns: int = 3
    facet_spacing_m: float = 0.035
    facet_gap_m: float = 0.030
    facet_size_m: float = 0.300
    facet_focal_distance_m: float = 2.500
    facet_misaligned_id: str = "F5"
    facet_horizontal_misalignment_deg: float = 0.0
    facet_vertical_misalignment_deg: float = 0.0
    facet_view_mode: str = "Resumen"
    facet_active_ids: set[str] = field(
        default_factory=lambda: {f"F{index}" for index in range(1, 10)}
    )
    facets: list[Facet] = field(default_factory=list)
    facet_ray_results: list[FacetRayResult] = field(default_factory=list)
    facet_focus: tuple[float, float, float] = (0.0, 0.0, 0.0)
    facet_receiver_normal: tuple[float, float, float] = (0.0, 1.0, 0.0)
    facet_error_max_m: float = 0.0
    facet_error_average_m: float = 0.0
    facet_compute_ms: float = 0.0
    facet_cache_hits: int = 0
    _facet_previous_count: int = field(default=9, repr=False)
    _facet_cache_signature: tuple[object, ...] | None = field(default=None, repr=False)
    spot_map_enabled: bool = False
    spot_base_sigma_m: float = 0.003
    spot_map_half_size_m: float = 0.050
    spot_map_resolution: int = 51
    spot_normalization: str = "Total = 1"
    spot_map_result: SpotMapResult | None = field(default=None, repr=False)
    spot_metrics: SpotMetrics = field(default_factory=SpotMetrics)
    spot_compute_ms: float = 0.0
    spot_cache_hits: int = 0
    _spot_cache_signature: tuple[object, ...] | None = field(default=None, repr=False)
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
        self.correction_model = CorrectionModel(self.correction_config)
        if self.initial_simulated_time is None:
            self.initial_simulated_time = self.simulated_time
        self.set_history_limit(self.history_limit)

    def active_datetime(self) -> _dt.datetime:
        """Devuelve la hora civil coherente con la zona UTC configurada."""
        if not self.use_live_time:
            return self.simulated_time
        timezone = _dt.timezone(
            _dt.timedelta(hours=clamp(float(self.utc_offset_hours), -14.0, 14.0))
        )
        return _dt.datetime.now(_dt.timezone.utc).astimezone(timezone).replace(
            tzinfo=None
        )

    def set_simulated_start_time(self, when: _dt.datetime) -> None:
        """Define fecha/hora inicial y coloca el reloj exactamente en ella."""
        self.initial_simulated_time = when
        self.simulated_time = when
        self.seconds_since_last_correction = 0.0
        self.clear_history()
        self.reset_tracking_schedule()
        self.reset_drift_correction()

    def reset_simulated_time(self) -> None:
        """Regresa el reloj a la fecha/hora inicial configurada."""
        if self.initial_simulated_time is None:
            self.initial_simulated_time = self.simulated_time
        self.simulated_time = self.initial_simulated_time
        self.seconds_since_last_correction = 0.0
        self.clear_history()
        self.reset_tracking_schedule()
        self.reset_drift_correction()

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

    def reset_drift_correction(self) -> None:
        """Borra la compensacion dinamica sin cambiar los errores simulados."""
        self.correction_model.reset()
        self.drift_correction_az_deg = 0.0
        self.drift_correction_el_deg = 0.0
        self.drift_correction_pending = False
        self.drift_corrected_this_step = False

    def invalidate_optical_cache(self) -> None:
        """Fuerza el siguiente calculo de facetas y mapa de intensidad."""
        self._facet_cache_signature = None
        self._spot_cache_signature = None

    def request_drift_correction(self) -> None:
        """Solicita una observacion/correccion del impacto en el siguiente paso."""
        self.drift_correction_pending = True

    def _update_drift_correction(self, simulated_elapsed_s: float) -> bool:
        """Actualiza la estrategia y dice si cambio la compensacion angular."""
        previous = (self.drift_correction_az_deg, self.drift_correction_el_deg)
        target_distance_m = v_norm(self.scenario_target_vector("Con error"))
        correction_az, correction_el = self.correction_model.update(
            simulated_elapsed_s=simulated_elapsed_s,
            observed_u_m=self.corrected_spot_u,
            observed_v_m=self.corrected_spot_v,
            target_distance_m=target_distance_m,
            # "Impacto observado" es deliberadamente manual: solo el boton
            # solicita una captura. La estrategia de camara conserva su propio
            # temporizador automatico dentro de CorrectionModel.
            observation_trigger=False,
            force=self.drift_correction_pending,
        )
        self.drift_correction_az_deg = correction_az
        self.drift_correction_el_deg = correction_el
        self.drift_corrected_this_step = self.correction_model.corrected_this_step
        self.drift_correction_pending = False
        return self.drift_corrected_this_step or previous != (
            self.drift_correction_az_deg,
            self.drift_correction_el_deg,
        )

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
        """Captura la normal solar actual sin teletransportar los ejes.

        La orden retenida cambia de inmediato, pero la posicion mecanica se
        actualiza despues mediante ``AxisState.update_closed_loop``. Asi, una
        entrada a Automatico y cada actualizacion periodica respetan PWM,
        velocidad maxima, cdr, motores habilitados y limites.
        """
        if self.tracking_schedule_initialized:
            self._finish_tracking_interval()
        self.held_target_acim = self.target_acim
        self.held_target_elev = self.target_elev
        az_delta = wrap_deg(self.held_target_acim - self.az.angle_deg)
        el_delta = self.held_target_elev - self.el.angle_deg
        self.motion_error_sample = self.error_model.sample_motion(az_delta, el_delta)
        self.az.target_deg = self.held_target_acim
        self.el.target_deg = self.held_target_elev
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
        """Devuelve la normal optica ideal, con error o compensada.

        El encoder de elevacion usa la coordenada mecanica, que incluye el
        peralte calibrado. Para recuperar la elevacion fisica de la normal hay
        que descontarlo una sola vez. Los offsets, en cambio, son ajustes
        deliberados de punteria y por eso permanecen en la orden resultante.
        """
        corrected = mode.strip().lower() == "corregido"
        command_az = self.az.angle_deg
        command_el = self.el.angle_deg - self.peralte
        if corrected:
            command_az += self.drift_correction_az_deg
            command_el += self.drift_correction_el_deg
        return self.error_model.normal_from_command(
            command_az,
            command_el,
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

    def compute_facet_field(self) -> None:
        """Construye y traza el concentrador solo cuando cambia su geometria."""
        if not self.facet_field_enabled:
            self.facets = []
            self.facet_ray_results = []
            self.facet_error_max_m = 0.0
            self.facet_error_average_m = 0.0
            self.facet_compute_ms = 0.0
            self.spot_map_result = None
            self.spot_metrics = SpotMetrics()
            self.spot_compute_ms = 0.0
            self.invalidate_optical_cache()
            return
        started = time.perf_counter()
        concentrator_center = self.scenario_target_vector(self.error_mode)
        axis = v_unit(concentrator_center)
        focal_distance = max(0.001, float(self.facet_focal_distance_m))
        facet_signature: tuple[object, ...] = (
            concentrator_center,
            self.facet_count,
            self.facet_shape,
            max(0.001, float(self.facet_size_m)),
            max(0.0, float(self.facet_gap_m)),
            focal_distance,
            tuple(sorted(self.facet_active_ids)),
            self.facet_misaligned_id,
            self.facet_horizontal_misalignment_deg,
            self.facet_vertical_misalignment_deg,
        )
        if facet_signature == self._facet_cache_signature and self.facets:
            self.facet_cache_hits += 1
            self.compute_spot_distribution()
            return
        if v_norm(axis) < 1e-12:
            self.facets = []
            self.facet_ray_results = []
            self.facet_error_max_m = float("nan")
            self.facet_error_average_m = float("nan")
            self.facet_compute_ms = (time.perf_counter() - started) * 1000.0
            self.spot_map_result = None
            self.spot_metrics = SpotMetrics()
            self.spot_compute_ms = 0.0
            self.invalidate_optical_cache()
            return
        self.facet_focus = v_sub(concentrator_center, v_mul(axis, focal_distance))
        self.facet_receiver_normal = axis
        self.facets = build_compact_facets(
            concentrator_center=concentrator_center,
            focus=self.facet_focus,
            count=self.facet_count,
            shape=self.facet_shape,
            size_m=max(0.001, float(self.facet_size_m)),
            gap_m=max(0.0, float(self.facet_gap_m)),
            focal_distance_m=focal_distance,
            active_ids=set(self.facet_active_ids),
            misaligned_facet_id=self.facet_misaligned_id,
            horizontal_misalignment_deg=self.facet_horizontal_misalignment_deg,
            vertical_misalignment_deg=self.facet_vertical_misalignment_deg,
        )
        self.facet_ray_results = trace_facets(
            self.facets,
            heliostat_origin=(0.0, 0.0, 0.0),
            receiver_center=self.facet_focus,
            receiver_normal=self.facet_receiver_normal,
        )
        errors = [
            result.focus_error_m
            for result in self.facet_ray_results
            if math.isfinite(result.focus_error_m)
        ]
        self.facet_error_max_m = max(errors, default=0.0)
        self.facet_error_average_m = sum(errors) / len(errors) if errors else 0.0
        self.facet_compute_ms = (time.perf_counter() - started) * 1000.0
        self._facet_cache_signature = facet_signature
        self._spot_cache_signature = None
        self.compute_spot_distribution()

    def compute_spot_distribution(self) -> None:
        """Superpone manchas solo si cambiaron rayos o parametros del mapa."""
        if not self.spot_map_enabled or not self.facet_ray_results:
            self.spot_map_result = None
            self.spot_metrics = SpotMetrics()
            self.spot_compute_ms = 0.0
            self._spot_cache_signature = None
            return
        spot_signature: tuple[object, ...] = (
            self._facet_cache_signature,
            max(1e-5, float(self.spot_base_sigma_m)),
            max(0.001, float(self.spot_map_half_size_m)),
            self.spot_map_resolution,
            self.spot_normalization,
        )
        if spot_signature == self._spot_cache_signature and self.spot_map_result is not None:
            self.spot_cache_hits += 1
            return
        started = time.perf_counter()
        facet_by_id = {facet.id: facet for facet in self.facets}
        contributions = []
        for result in self.facet_ray_results:
            facet = facet_by_id.get(result.facet_id)
            if facet is None:
                continue
            if facet.shape == "Circular":
                area_factor = math.pi / 4.0
            elif facet.shape == "Hexagonal":
                area_factor = math.sqrt(3.0) / 2.0
            else:
                area_factor = 1.0
            receiver_cosine = abs(
                v_dot(v_unit(result.reflected_direction), v_unit(self.facet_receiver_normal))
            )
            contribution = contribution_from_ray(
                result,
                receiver_normal=self.facet_receiver_normal,
                base_sigma_m=max(1e-5, float(self.spot_base_sigma_m)),
                weight=area_factor * receiver_cosine,
            )
            if contribution is not None:
                contributions.append(contribution)
        self.spot_map_result = generate_spot_map(
            contributions,
            half_size_m=max(0.001, float(self.spot_map_half_size_m)),
            resolution=self.spot_map_resolution,
            normalization=self.spot_normalization,
        )
        self.spot_metrics = self.spot_map_result.metrics
        self.spot_compute_ms = (time.perf_counter() - started) * 1000.0
        self._spot_cache_signature = spot_signature

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
        when = self.active_datetime()
        self.zenith, self.altitude, self.solar_azimuth, self.solar_source = solar_position(
            when,
            self.lat_deg,
            self.lon_deg,
            self.method,
            self.utc_offset_hours,
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
        self.compute_facet_field()

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

        En seguimiento automatico el Sol se recalcula siempre y el target
        retenido solo cambia al vencer el intervalo configurado. La pose avanza
        continuamente hacia ese target mediante el modelo de motor. El modo
        Home conserva su movimiento suave independiente del programador.
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
        self.drift_corrected_this_step = False

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
            self.az.update_closed_loop(dt, self.cdr)
            self.el.update_closed_loop(dt, self.cdr)
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
        # La estrategia observa el impacto corregido anterior y actualiza una
        # sola vez por paso. Luego se recalculan los tres escenarios para que
        # la interfaz muestre inmediatamente el efecto de la compensacion.
        correction_changed = self._update_drift_correction(solar_elapsed_s)
        if correction_changed:
            self.target_vector = self.scenario_target_vector(self.error_mode)
            self.actual_normal = self.scenario_normal(self.error_mode)
            self.compute_spot_error()
            self.compute_error_comparison()
        self.iterations += 1
        self.set_history_limit(self.history_limit)
        self.history.append(
            {
                "t": self.iterations,
                "solar_time": self.active_datetime().isoformat(timespec="milliseconds"),
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
                "drift_correction_strategy": self.correction_config.strategy,
                "drift_correction_az_deg": self.drift_correction_az_deg,
                "drift_correction_el_deg": self.drift_correction_el_deg,
                "drift_correction_count": self.correction_model.update_count,
                "drift_corrected": self.drift_corrected_this_step,
                "facet_field_enabled": self.facet_field_enabled,
                "facet_shape": self.facet_shape,
                "facet_count": self.facet_count,
                "facet_active_count": len(self.facet_ray_results),
                "facet_error_max_m": self.facet_error_max_m,
                "facet_error_average_m": self.facet_error_average_m,
                "facet_compute_ms": self.facet_compute_ms,
                "spot_map_enabled": self.spot_map_enabled,
                "spot_centroid_error_m": self.spot_metrics.centroid_error_m,
                "spot_maximum_intensity": self.spot_metrics.maximum_intensity,
                "spot_equivalent_diameter_m": self.spot_metrics.equivalent_diameter_m,
                "spot_shape": self.spot_metrics.shape,
                "spot_compute_ms": self.spot_compute_ms,
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
        super().__init__(master, width=170, height=142, bg="#d8d8d8", highlightthickness=1, **kwargs)
        self.label = label
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self.set_from_pointer)
        self.bind("<B1-Motion>", self.set_from_pointer)

    def set_from_pointer(self, event: tk.Event) -> None:
        """Convierte la posicion del mouse dentro de la perilla a un valor 0..1."""
        cx, cy = 85, 82
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
        self.create_text(85, 12, text=self.label, fill="#001a70", font=("Segoe UI", 9, "bold"))
        cx, cy, r = 85, 82, 40
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#eeeeee", outline="#888888", width=2)
        for i in range(11):
            value = i / 10.0
            ang = math.radians(220.0 - 260.0 * value)
            x1 = cx + math.cos(ang) * (r + 1)
            y1 = cy - math.sin(ang) * (r + 1)
            x2 = cx + math.cos(ang) * (r + 9)
            y2 = cy - math.sin(ang) * (r + 9)
            self.create_line(x1, y1, x2, y2, fill="#111111", width=1)
            tx = cx + math.cos(ang) * (r + 18)
            ty = cy - math.sin(ang) * (r + 18)
            self.create_text(tx, ty, text=f"{value:.1g}", font=("Segoe UI", 7))
        val = clamp(self.variable.get(), 0.0, 1.0)
        ang = math.radians(220.0 - 260.0 * val)
        nx = cx + math.cos(ang) * (r - 8)
        ny = cy - math.sin(ang) * (r - 8)
        self.create_line(cx, cy, nx, ny, fill="#d38a00", width=4)
        self.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill="#ffcc33", outline="#777777")
        # El porcentaje vive dentro de la perilla para no chocar con las
        # etiquetas inferiores 0 y 1 de la escala.
        self.create_text(85, 111, text=f"{val * 100:.0f} %", fill="#111111", font=("Consolas", 9, "bold"))


class Switch(tk.Canvas):
    """Switch ON/OFF dibujado en Canvas.

    Reemplaza las casillas con X para que el panel sea mas claro visualmente.
    El valor real vive en una BooleanVar de Tkinter.
    """

    def __init__(self, master: tk.Misc, text: str, variable: tk.BooleanVar, command: Callable[[], None] | None = None) -> None:
        super().__init__(master, width=230, height=34, bg="#d6d6d6", highlightthickness=0)
        self.text = text
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self.toggle)
        self.bind("<Configure>", lambda _event: self.redraw())
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
        canvas_width = max(190, self.winfo_width())
        x1 = canvas_width - 8
        x0, y0, y1 = x1 - 58, 6, 28
        self.create_text(
            0,
            17,
            anchor="w",
            text=self.text,
            width=max(80, x0 - 10),
            fill="#111111",
            font=("Segoe UI", 9),
        )
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
    actualiza lecturas y redibuja solamente la vista activa.
    """

    def __init__(self, root: tk.Tk) -> None:
        """Crea estado inicial, ventana, estilos, controles y arranca el ciclo."""
        self.root = root
        self.state = TwinState()
        self.last_tick = _dt.datetime.now()
        self.jog_command: tuple[str, int] | None = None
        self.vars: dict[str, tk.Variable] = {}
        self.entries: dict[str, ttk.Entry] = {}
        self.entry_groups: dict[str, list[ttk.Entry]] = {}
        self.collapsible_sections: dict[str, dict[str, object]] = {}
        self.readouts: dict[str, ttk.Label] = {}
        self.gauges: list[Gauge] = []
        self.switches: list[Switch] = []
        self.mode_buttons: dict[str, ttk.Button] = {}
        self.time_mode_buttons: dict[str, ttk.Button] = {}
        self.simulated_time_setup_widgets: list[tk.Widget] = []
        self.manual_controls: list[ttk.Button] = []
        self.current_mode = "manual"
        self.session_started = False
        self.event_log: deque[str] = deque(maxlen=80)
        self.samples: deque[dict[str, object]] = deque(maxlen=20000)
        self.replay_active = False
        self.replay_index = 0
        self.replay_samples: list[dict[str, object]] = []
        self.last_status_label = ""
        self.invalid_time_text = ""
        self.invalid_control_text = ""
        self.last_time_input: tuple[str, str] | None = None
        self.last_specific_time_enabled = False
        self.last_tracking_enabled = self.state.tracking
        self.last_tracking_interval_choice = "1 s"
        self.render_pending = True
        self.last_render_time = 0.0
        self.last_render_duration_ms = 0.0
        self.last_loop_duration_ms = 0.0
        self.render_fps = 0.0
        self._rendered_frames = 0
        self._fps_window_started = time.perf_counter()
        self.view_drawers: dict[tk.Canvas, Callable[[], None]] = {}
        self.free_view_yaw_deg = -38.0
        self.free_view_pitch_deg = 24.0
        self.scene_projection_scale = 540.0
        self.scene_front_group = "heliostat"
        self.scene_target_center = (0.0, 0.0, 0.0)
        self.free_view_drag_origin: tuple[int, int] | None = None
        self.free_view_pan_x_px = 0.0
        self.free_view_pan_y_px = 0.0
        self.free_view_pan_drag_origin: tuple[int, int] | None = None
        self.drift_expanded_index: int | None = None
        self.drift_graph_boxes: list[tuple[int, tuple[int, int, int, int]]] = []
        self.drift_back_box: tuple[int, int, int, int] | None = None
        self.facet_expanded_panel: str | None = None
        self.facet_panel_boxes: dict[str, tuple[int, int, int, int]] = {}
        self.facet_back_box: tuple[int, int, int, int] | None = None
        self.loop_after_id: str | None = None
        self.is_closing = False
        self.state.automatic = False
        self.state.free_mode = True
        self.state.running = False
        self.state.advance_solar_time = False
        self.set_home_pose_instant()
        self.root.title(
            f"Gemelo digital - Mini horno solar / Mini heliostato IER - Version {APP_RELEASE}"
        )
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(1580, max(1000, screen_width - 40))
        window_height = min(930, max(640, screen_height - 80))
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(min(1180, window_width), min(680, window_height))
        self.root.configure(bg="#242424")
        self.configure_style()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.log_event("Listo para configurar; selecciona el origen temporal y pulsa Iniciar")
        self.sync_from_state()
        self.loop()

    def close(self) -> None:
        """Cancela el temporizador de Tkinter y cierra la ventana limpiamente."""
        self.is_closing = True
        if self.loop_after_id is not None:
            try:
                self.root.after_cancel(self.loop_after_id)
            except tk.TclError:
                pass
            self.loop_after_id = None
        self.root.destroy()

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
        style.configure(
            "PauseAction.TButton",
            background="#b42318",
            foreground="#ffffff",
            borderwidth=1,
            padding=5,
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "PauseAction.TButton",
            background=[("active", "#d92d20"), ("disabled", "#6b7280")],
            foreground=[("disabled", "#e5e7eb")],
        )
        style.configure(
            "ResumeAction.TButton",
            background="#16834f",
            foreground="#ffffff",
            borderwidth=1,
            padding=5,
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "ResumeAction.TButton",
            background=[("active", "#1f9d63"), ("disabled", "#6b7280")],
            foreground=[("disabled", "#e5e7eb")],
        )
        style.configure(
            "HomeAction.TButton",
            background="#c79424",
            foreground="#111827",
            borderwidth=1,
            padding=4,
            font=("Segoe UI", 9, "bold"),
        )
        style.map("HomeAction.TButton", background=[("active", "#e0ad38"), ("disabled", "#8b8b8b")])
        style.configure(
            "DataAction.TButton",
            background="#355d7a",
            foreground="#ffffff",
            borderwidth=1,
            padding=4,
            font=("Segoe UI", 8, "bold"),
        )
        style.map(
            "DataAction.TButton",
            background=[("active", "#46789c"), ("disabled", "#5f6770")],
            foreground=[("disabled", "#c7cbd1")],
        )
        style.configure("Readout.TLabel", background="#e9e9e9", foreground="#cc0000", relief="sunken", padding=4, font=("Consolas", 10, "bold"))
        style.configure("Invalid.TEntry", fieldbackground="#ffd9d9", foreground="#8b0000")
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
        self.var("time_mode_choice", "Tiempo real" if self.state.use_live_time else "Fecha simulada")
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
        for correction_name in (
            "enabled",
            "strategy",
            "constant_az_deg",
            "constant_el_deg",
            "time_az_rate_deg_per_hour",
            "time_el_rate_deg_per_hour",
            "polynomial_az_c0",
            "polynomial_az_c1",
            "polynomial_az_c2",
            "polynomial_el_c0",
            "polynomial_el_c1",
            "polynomial_el_c2",
            "image_gain_az",
            "image_gain_el",
            "image_max_step_deg",
            "camera_interval_s",
        ):
            self.var(
                f"correction_{correction_name}",
                getattr(self.state.correction_config, correction_name),
            )
        for facet_name in (
            "facet_field_enabled",
            "facet_shape",
            "facet_count",
            "facet_gap_m",
            "facet_size_m",
            "facet_focal_distance_m",
            "facet_misaligned_id",
            "facet_horizontal_misalignment_deg",
            "facet_vertical_misalignment_deg",
            "facet_view_mode",
        ):
            self.var(facet_name, getattr(self.state, facet_name))
        for spot_name in (
            "spot_map_enabled",
            "spot_base_sigma_m",
            "spot_map_half_size_m",
            "spot_map_resolution",
            "spot_normalization",
        ):
            self.var(spot_name, getattr(self.state, spot_name))
        for name in (
            "show_sun_vector",
            "show_normal_vector",
            "show_reflected_vector",
            "show_target_direction",
            "show_target_line",
            "show_mechanical_guides",
        ):
            self.var(name, getattr(self.state, name))
        self.var("method", self.state.method)
        self.var("view_mode", "Isometrica")
        self.var("render_quality", "Equilibrada")
        self.var("geometry_profile", "Minihorno IER")
        self.var("mode_status", "MODO ACTIVO: MANUAL / MOVIMIENTO LIBRE")
        self.var("date_text", self.state.simulated_time.strftime("%Y-%m-%d"))
        self.var("time_text", self.state.simulated_time.strftime("%H:%M:%S"))
        for name in (
            "lat_deg",
            "lon_deg",
            "utc_offset_hours",
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

        ttk.Label(
            left,
            text=f"Sistema de Control Horno Solar IER - Gemelo Digital v{APP_RELEASE}",
            style="Title.TLabel",
        ).pack(fill="x", padx=10, pady=(10, 8))
        self.build_mode_block(left)
        self.build_time_block(left)
        self.build_motor_block(left)
        self.build_auto_block(left)
        self.build_vector_block(left)
        self.build_error_block(left)
        self.build_correction_block(left)
        self.build_facet_block(left)

        # Las vistas graficas del gemelo se organizan como pestanas para que el
        # usuario pueda cambiar entre 3D, spot, trayectoria solar y diagnostico.
        self.notebook = ttk.Notebook(right)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.scene_canvas = tk.Canvas(self.notebook, bg="#101821", highlightthickness=0)
        self.receiver_canvas = tk.Canvas(self.notebook, bg="#f4f4f4", highlightthickness=0)
        self.solar_canvas = tk.Canvas(self.notebook, bg="#f4f4f4", highlightthickness=0)
        self.drift_canvas = tk.Canvas(self.notebook, bg="#f4f4f4", highlightthickness=0)
        self.facet_canvas = tk.Canvas(self.notebook, bg="#f4f4f4", highlightthickness=0)
        self.spot_canvas = self.facet_canvas
        self.diagnostic_canvas = tk.Canvas(self.notebook, bg="#f4f4f4", highlightthickness=0)
        self.notebook.add(self.scene_canvas, text="Gemelo 3D")
        self.notebook.add(self.receiver_canvas, text="Pantalla / spot y error")
        self.notebook.add(self.solar_canvas, text="Trayectoria solar")
        self.notebook.add(self.drift_canvas, text="Deriva y correccion")
        self.notebook.add(self.facet_canvas, text="Facetas / rayos / intensidad")
        self.notebook.add(self.diagnostic_canvas, text="Diagnostico")
        self.view_drawers = {
            self.scene_canvas: self.draw_scene,
            self.receiver_canvas: self.draw_receiver_view,
            self.solar_canvas: self.draw_solar_path,
            self.drift_canvas: self.draw_drift_view,
            self.facet_canvas: self.draw_facet_view,
            self.diagnostic_canvas: self.draw_diagnostic_view,
        }
        self.notebook.bind("<<NotebookTabChanged>>", self.request_render)
        for canvas in self.view_drawers:
            canvas.bind("<Configure>", self.request_render, add="+")
        self.scene_canvas.bind("<ButtonPress-3>", self.start_free_view_drag)
        self.scene_canvas.bind("<B3-Motion>", self.drag_free_view)
        self.scene_canvas.bind("<ButtonRelease-3>", self.stop_free_view_drag)
        self.scene_canvas.bind("<ButtonPress-1>", self.start_free_view_pan)
        self.scene_canvas.bind("<B1-Motion>", self.drag_free_view_pan)
        self.scene_canvas.bind("<ButtonRelease-1>", self.stop_free_view_pan)
        self.drift_canvas.bind("<Button-1>", self.handle_drift_click)
        self.facet_canvas.bind("<Button-1>", self.handle_facet_click)
        self.build_bottom_panel(main)

    def create_collapsible_section(
        self,
        parent: ttk.Frame,
        title: str,
        expanded: bool = False,
    ) -> ttk.Frame:
        """Crea una seccion lateral plegable y devuelve su area de contenido."""
        outer = ttk.Frame(parent, style="Panel.TFrame")
        outer.pack(fill="x", padx=10, pady=4)
        header = ttk.Button(
            outer,
            text=f"{'▼' if expanded else '▶'}  {title}",
            style="Mode.TButton",
            command=lambda name=title: self.toggle_collapsible_section(name),
        )
        header.pack(fill="x")
        content = ttk.Frame(outer, style="Panel.TFrame", relief="ridge", borderwidth=1)
        self.collapsible_sections[title] = {
            "header": header,
            "content": content,
            "expanded": expanded,
        }
        if expanded:
            content.pack(fill="x")
        return content

    def toggle_collapsible_section(self, title: str) -> None:
        """Abre o cierra una seccion lateral sin alterar sus valores."""
        section = self.collapsible_sections[title]
        expanded = not bool(section["expanded"])
        header = section["header"]
        content = section["content"]
        if not isinstance(header, ttk.Button) or not isinstance(content, ttk.Frame):
            return
        if expanded:
            content.pack(fill="x")
        else:
            content.pack_forget()
        section["expanded"] = expanded
        header.configure(text=f"{'▼' if expanded else '▶'}  {title}")

    def build_mode_block(self, parent: ttk.Frame) -> None:
        """Construye el bloque de modo: Automatico, Manual, Home y fecha activa."""
        frame = self.create_collapsible_section(parent, "Modo", expanded=True)
        self.mode_label = ttk.Label(frame, textvariable=self.vars["mode_status"], style="ModeStatus.TLabel")
        self.mode_label.pack(fill="x", padx=10, pady=(8, 6))
        row = ttk.Frame(frame, style="Inset.TFrame")
        row.pack(fill="x", padx=10, pady=(0, 8))
        for col, (key, text) in enumerate((("auto", "Automatico"), ("manual", "Manual"), ("home", "Home"))):
            button = ttk.Button(row, text=text, style="Mode.TButton", command=lambda k=key: self.set_mode(k))
            button.grid(row=0, column=col, sticky="ew", padx=4, pady=5)
            self.mode_buttons[key] = button
            row.columnconfigure(col, weight=1)
        automatic_options = ttk.Frame(frame, style="Inset.TFrame")
        automatic_options.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(
            automatic_options,
            text="Opciones del modo Automatico",
            style="Small.TLabel",
        ).pack(side="left", padx=(8, 2))
        self.add_switch(automatic_options, "Seguimiento solar", "tracking")
        for i in range(3):
            row.columnconfigure(i, weight=1)
        self.update_mode_visuals()

    def build_time_block(self, parent: ttk.Frame) -> None:
        """Permite elegir un unico origen temporal antes de iniciar la sesion."""
        frame = self.create_collapsible_section(parent, "Tiempo del experimento", expanded=True)
        selector = ttk.Frame(frame, style="Inset.TFrame")
        selector.pack(fill="x", padx=8, pady=(7, 3))
        ttk.Label(
            selector,
            text="1. Elige el origen del tiempo",
            style="Small.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(5, 2))
        for column, (key, text) in enumerate(
            (("Tiempo real", "TIEMPO REAL"), ("Fecha simulada", "FECHA SIMULADA"))
        ):
            button = ttk.Button(
                selector,
                text=text,
                style="Mode.TButton",
                command=lambda selected=key: self.select_time_mode(selected),
            )
            button.grid(row=1, column=column, sticky="ew", padx=4, pady=(2, 6))
            selector.columnconfigure(column, weight=1)
            self.time_mode_buttons[key] = button

        self.time_setup_status_label = ttk.Label(
            frame,
            text="Tiempo real seleccionado: se usara el reloj civil del perfil UTC.",
            style="ModeStatus.TLabel",
            anchor="w",
        )
        self.time_setup_status_label.pack(fill="x", padx=8, pady=3)

        date_row = ttk.Frame(frame, style="Inset.TFrame")
        date_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(date_row, text="Fecha simulada", style="Small.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w", padx=4, pady=(4, 1)
        )
        ttk.Label(date_row, text="Fecha", style="Small.TLabel").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.simulated_date_entry = ttk.Entry(date_row, textvariable=self.vars["date_text"], width=12)
        self.simulated_date_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Label(date_row, text="Hora", style="Small.TLabel").grid(row=1, column=2, sticky="w", padx=4, pady=4)
        self.simulated_time_entry = ttk.Entry(date_row, textvariable=self.vars["time_text"], width=12)
        self.simulated_time_entry.grid(row=1, column=3, sticky="ew", padx=4, pady=4)
        date_row.columnconfigure(1, weight=1)
        date_row.columnconfigure(3, weight=1)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=(3, 7))
        ttk.Label(grid, text="Velocidad simulada", style="Small.TLabel").grid(row=0, column=0, sticky="w", padx=2, pady=2)
        self.time_scale_menu = ttk.OptionMenu(
            grid,
            self.vars["time_scale_choice"],
            self.vars["time_scale_choice"].get(),
            "1x",
            "10x",
            "60x",
            "120x",
            "600x",
            command=lambda _=None: self.apply_controls(),
        )
        self.time_scale_menu.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self.simulation_step_entry = self.add_entry(grid, "Paso manual (s)", "simulation_step_s", 1, 0)
        self.apply_time_button = ttk.Button(
            grid,
            text="APLICAR FECHA Y HORA",
            style="HomeAction.TButton",
            command=self.apply_initial_datetime,
        )
        self.apply_time_button.grid(row=0, column=2, columnspan=2, sticky="ew", padx=3, pady=3)
        self.step_time_button = ttk.Button(
            grid,
            text="AVANZAR UN PASO",
            style="DataAction.TButton",
            command=self.step_simulation_clock,
        )
        self.step_time_button.grid(row=1, column=2, sticky="ew", padx=3, pady=3)
        self.reset_time_button = ttk.Button(
            grid,
            text="REINICIAR TIEMPO",
            style="DataAction.TButton",
            command=self.reset_simulation_clock,
        )
        self.reset_time_button.grid(row=1, column=3, sticky="ew", padx=3, pady=3)
        self.clock_status_label = ttk.Label(
            grid,
            text="",
            style="Readout.TLabel",
            anchor="center",
        )
        self.clock_status_label.grid(row=2, column=0, columnspan=4, sticky="ew", padx=3, pady=(6, 2))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)
        self.simulated_time_setup_widgets = [
            self.simulated_date_entry,
            self.simulated_time_entry,
            self.time_scale_menu,
            self.simulation_step_entry,
            self.apply_time_button,
        ]
        self.update_time_controls()

    def build_motor_block(self, parent: ttk.Frame) -> None:
        """Construye controles manuales de motores y perillas de velocidad."""
        frame = self.create_collapsible_section(parent, "Control Motor Acimut / Elevacion")
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
        frame = self.create_collapsible_section(parent, "Ubicacion, vector solar y concentrador")
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
        self.add_entry(location, "Zona UTC (h)", "utc_offset_hours", 4, 0)
        ttk.Label(location, text="Metodo solar", style="Small.TLabel").grid(row=5, column=0, sticky="w", pady=2, padx=2)
        ttk.OptionMenu(location, self.vars["method"], self.state.method, "D&B", "REDA", "SPA/PVLIB", command=lambda _=None: self.apply_controls()).grid(row=5, column=1, sticky="ew", pady=2)
        for idx, key in enumerate(("zenith", "altitude", "solar_azimuth")):
            label = ("Angulo Zenit", "Altura Solar", "Angulo Acimut")[idx]
            ttk.Label(location, text=label, style="Small.TLabel").grid(row=6 + idx, column=0, sticky="w", pady=2, padx=2)
            out = ttk.Label(location, text="0.000", style="Readout.TLabel")
            out.grid(row=6 + idx, column=1, sticky="ew", pady=2, padx=2)
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
        frame = self.create_collapsible_section(parent, "Seguimiento y objetivo", expanded=True)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.add_switch(grid, "Target R a escala maqueta", "scale_to_model", row=0, col=2)
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
        self.tracking_correction_button = ttk.Button(
            grid,
            text="CORREGIR AHORA",
            style="Gold.TButton",
            command=self.request_tracking_correction,
        )
        self.tracking_correction_button.grid(row=1, column=2, columnspan=2, sticky="ew", padx=4, pady=3)
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
            "Libre",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=4, column=1, sticky="ew", pady=2, padx=2)
        ttk.Button(
            grid,
            text="Restablecer vista libre",
            style="Manual.TButton",
            command=self.reset_free_view,
        ).grid(row=4, column=2, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Label(grid, text="Calidad grafica", style="Small.TLabel").grid(
            row=5, column=0, sticky="w", pady=2, padx=2
        )
        ttk.OptionMenu(
            grid,
            self.vars["render_quality"],
            self.vars["render_quality"].get(),
            "Rapida",
            "Equilibrada",
            "Alta",
            command=self.set_render_quality,
        ).grid(row=5, column=1, sticky="ew", pady=2, padx=2)
        ttk.Label(
            grid,
            text="Afecta solo el dibujo, no la fisica.",
            style="Small.TLabel",
        ).grid(row=5, column=2, columnspan=2, sticky="w", pady=2, padx=4)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

    def build_vector_block(self, parent: ttk.Frame) -> None:
        """Construye controles independientes de visibilidad para la vista 3D."""
        frame = self.create_collapsible_section(parent, "Vectores geometricos visibles")
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        controls = (
            ("Solar incidente", "show_sun_vector", 0, 0),
            ("Normal heliostato", "show_normal_vector", 0, 2),
            ("Rayo reflejado", "show_reflected_vector", 1, 0),
            ("Direccion objetivo", "show_target_direction", 1, 2),
            ("Linea heliostato-target", "show_target_line", 2, 0),
            ("Guias de limites mecanicos", "show_mechanical_guides", 2, 2),
        )
        for label, varname, row, col in controls:
            self.add_switch(grid, label, varname, row=row, col=col)
        for col in range(4):
            grid.columnconfigure(col, weight=1)

    def build_error_block(self, parent: ttk.Frame) -> None:
        """Construye activadores y parametros del modelo de errores."""
        frame = self.create_collapsible_section(parent, "Errores geometricos y mecanicos")
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

    def build_correction_block(self, parent: ttk.Frame) -> None:
        """Construye las cinco estrategias progresivas de correccion de deriva."""
        frame = self.create_collapsible_section(parent, "Correccion de deriva")
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)

        def add_parameter_row(
            row: int,
            left_parameter: tuple[str, str],
            right_parameter: tuple[str, str],
        ) -> None:
            """Mantiene dos parametros separados aunque el panel sea angosto."""
            row_frame = ttk.Frame(grid, style="Panel.TFrame")
            row_frame.grid(row=row, column=0, columnspan=4, sticky="ew", pady=1)
            row_frame.columnconfigure(0, weight=1, uniform="correction_parameter")
            row_frame.columnconfigure(1, weight=1, uniform="correction_parameter")
            for column, (label, varname) in enumerate((left_parameter, right_parameter)):
                pair = ttk.Frame(row_frame, style="Panel.TFrame")
                pair.grid(row=0, column=column, sticky="ew", padx=(0, 4) if column == 0 else (4, 0))
                pair.columnconfigure(1, weight=1)
                ttk.Label(pair, text=label, style="Small.TLabel").grid(row=0, column=0, sticky="w", padx=2, pady=2)
                entry = ttk.Entry(pair, textvariable=self.vars[varname], width=9)
                entry.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
                entry.bind("<Return>", lambda _event: self.apply_controls())
                entry.bind("<FocusOut>", lambda _event: self.apply_controls())
                entry.bind("<KeyRelease>", lambda _event: self.validate_numeric_entries())

        self.add_switch(grid, "Activar correccion", "correction_enabled", row=0, col=0)
        ttk.Label(grid, text="Estrategia", style="Small.TLabel").grid(
            row=1, column=0, sticky="w", padx=2, pady=2
        )
        ttk.OptionMenu(
            grid,
            self.vars["correction_strategy"],
            self.vars["correction_strategy"].get(),
            *CorrectionModel.STRATEGIES,
            command=lambda _=None: self.apply_controls(),
        ).grid(row=1, column=1, columnspan=3, sticky="ew", padx=2, pady=2)

        ttk.Label(grid, text="Offset constante", style="Small.TLabel").grid(
            row=2, column=0, columnspan=4, sticky="w", padx=2, pady=(6, 2)
        )
        add_parameter_row(
            3,
            ("AZ deg", "correction_constant_az_deg"),
            ("EL deg", "correction_constant_el_deg"),
        )

        ttk.Label(grid, text="Dependiente del tiempo", style="Small.TLabel").grid(
            row=4, column=0, columnspan=4, sticky="w", padx=2, pady=(6, 2)
        )
        add_parameter_row(
            5,
            ("AZ deg/h", "correction_time_az_rate_deg_per_hour"),
            ("EL deg/h", "correction_time_el_rate_deg_per_hour"),
        )

        ttk.Label(grid, text="Polinomio c0 + c1*t + c2*t^2 (t en horas)", style="Small.TLabel").grid(
            row=6, column=0, columnspan=4, sticky="w", padx=2, pady=(6, 2)
        )
        add_parameter_row(
            7,
            ("AZ c0", "correction_polynomial_az_c0"),
            ("AZ c1", "correction_polynomial_az_c1"),
        )
        add_parameter_row(
            8,
            ("AZ c2", "correction_polynomial_az_c2"),
            ("EL c0", "correction_polynomial_el_c0"),
        )
        add_parameter_row(
            9,
            ("EL c1", "correction_polynomial_el_c1"),
            ("EL c2", "correction_polynomial_el_c2"),
        )

        ttk.Label(grid, text="Impacto observado / camara", style="Small.TLabel").grid(
            row=10, column=0, columnspan=4, sticky="w", padx=2, pady=(6, 2)
        )
        add_parameter_row(
            11,
            ("Ganancia AZ", "correction_image_gain_az"),
            ("Ganancia EL", "correction_image_gain_el"),
        )
        add_parameter_row(
            12,
            ("Paso max deg", "correction_image_max_step_deg"),
            ("Camara cada s", "correction_camera_interval_s"),
        )

        buttons = ttk.Frame(grid, style="Panel.TFrame")
        buttons.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(7, 2))
        self.drift_correction_button = ttk.Button(
            buttons,
            text="CORREGIR DESDE IMPACTO",
            style="Gold.TButton",
            command=self.request_drift_correction,
        )
        self.drift_correction_button.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.reset_drift_button = ttk.Button(
            buttons,
            text="RESET CORRECCION",
            style="Manual.TButton",
            command=self.reset_drift_correction,
        )
        self.reset_drift_button.pack(side="left", fill="x", expand=True, padx=(3, 0))
        self.correction_status_label = ttk.Label(
            grid,
            text="Sin correccion dinamica",
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        )
        self.correction_status_label.grid(
            row=14, column=0, columnspan=4, sticky="ew", padx=2, pady=(5, 2)
        )
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)

    def build_facet_block(self, parent: ttk.Frame) -> None:
        """Construye forma, cantidad y controles del concentrador facetado."""
        frame = self.create_collapsible_section(parent, "Facetas: geometria, rayos e intensidad")
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.add_switch(grid, "Activar modelo", "facet_field_enabled", row=0, col=0)
        ttk.OptionMenu(
            grid,
            self.vars["facet_shape"],
            self.vars["facet_shape"].get(),
            "Cuadrada",
            "Circular",
            "Hexagonal",
            command=lambda _=None: (self.mark_custom_profile(), self.apply_controls()),
        ).grid(row=1, column=2, columnspan=2, sticky="ew", padx=2, pady=(7, 2))
        ttk.Label(grid, text="Forma", style="Small.TLabel").grid(
            row=1, column=0, sticky="w", padx=2, pady=(7, 2)
        )
        self.add_entry(grid, "Numero facetas", "facet_count", 2, 0)
        self.add_entry(grid, "Tamano (m)", "facet_size_m", 2, 2)
        self.add_entry(grid, "Separacion extra (m)", "facet_gap_m", 3, 0)
        self.add_entry(grid, "Distancia focal (m)", "facet_focal_distance_m", 3, 2)
        ttk.Label(
            grid,
            text="Selecciona una faceta por ID para desalinearla o cambiar su estado",
            style="Small.TLabel",
        ).grid(row=4, column=0, columnspan=4, sticky="w", padx=2, pady=(7, 2))
        self.add_entry(grid, "ID (ej. F12)", "facet_misaligned_id", 5, 0)
        self.add_entry(grid, "Desalin. horiz deg", "facet_horizontal_misalignment_deg", 5, 2)
        self.add_entry(grid, "Desalin. vert deg", "facet_vertical_misalignment_deg", 6, 0)
        selected_buttons = ttk.Frame(grid, style="Panel.TFrame")
        selected_buttons.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(7, 2))
        ttk.Button(
            selected_buttons,
            text="ACTIVAR SELECCIONADA",
            style="Gold.TButton",
            command=lambda: self.set_selected_facet_active(True),
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(
            selected_buttons,
            text="DESACTIVAR SELECCIONADA",
            style="Manual.TButton",
            command=lambda: self.set_selected_facet_active(False),
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))
        buttons = ttk.Frame(grid, style="Panel.TFrame")
        buttons.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(3, 2))
        ttk.Button(
            buttons,
            text="TODAS ON",
            style="Gold.TButton",
            command=lambda: self.set_all_facets_active(True),
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(
            buttons,
            text="TODAS OFF",
            style="Manual.TButton",
            command=lambda: self.set_all_facets_active(False),
        ).pack(side="left", fill="x", expand=True, padx=(3, 0))
        self.facet_status_label = ttk.Label(
            grid,
            text="Modelo de facetas desactivado",
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        )
        self.facet_status_label.grid(
            row=9, column=0, columnspan=4, sticky="ew", padx=2, pady=(5, 2)
        )
        ttk.Label(
            grid,
            text=(
                "Distribucion: reticula para cuadradas o empaquetamiento triangular "
                "para circulares y hexagonales. Tamano = lado, diametro o ancho entre caras."
            ),
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        ).grid(row=10, column=0, columnspan=4, sticky="ew", padx=2, pady=(2, 2))
        ttk.Label(grid, text="Vista del esquema", style="Small.TLabel").grid(
            row=11, column=0, sticky="w", padx=2, pady=(6, 2)
        )
        ttk.OptionMenu(
            grid,
            self.vars["facet_view_mode"],
            self.vars["facet_view_mode"].get(),
            "Resumen",
            "Superior X-Y",
            "Lateral Y-Z",
            "3D isometrica",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=11, column=1, columnspan=3, sticky="ew", padx=2, pady=(6, 2))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)
        self.build_spot_block(frame)

    def build_spot_block(self, parent: ttk.Frame) -> None:
        """Agrega el mapa de intensidad dentro del unico modulo de facetas."""
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(
            parent,
            text="Spot aproximado e intensidad del conjunto de facetas",
            style="Small.TLabel",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(0, 2))
        grid = ttk.Frame(parent, style="Panel.TFrame")
        grid.pack(fill="x", padx=8, pady=7)
        self.add_switch(grid, "Activar mapa", "spot_map_enabled", row=0, col=0)
        self.add_entry(grid, "Sigma base (m)", "spot_base_sigma_m", 1, 0)
        self.add_entry(grid, "Rango +/- (m)", "spot_map_half_size_m", 1, 2)
        self.add_entry(grid, "Resolucion impar", "spot_map_resolution", 2, 0)
        ttk.Label(grid, text="Normalizacion", style="Small.TLabel").grid(
            row=2, column=2, sticky="w", padx=2, pady=2
        )
        ttk.OptionMenu(
            grid,
            self.vars["spot_normalization"],
            self.vars["spot_normalization"].get(),
            "Total = 1",
            "Pico = 1",
            "Sin normalizar",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=2, column=3, sticky="ew", padx=2, pady=2)
        self.spot_status_label = ttk.Label(
            grid,
            text="Mapa de intensidad desactivado",
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        )
        self.spot_status_label.grid(
            row=3, column=0, columnspan=4, sticky="ew", padx=2, pady=(6, 2)
        )
        ttk.Label(
            grid,
            text="Cada impacto genera una gaussiana; la incidencia oblicua la alarga.",
            style="Small.TLabel",
            wraplength=450,
            justify="left",
        ).grid(row=4, column=0, columnspan=4, sticky="ew", padx=2, pady=(2, 2))
        for col in (1, 3):
            grid.columnconfigure(col, weight=1)

    def build_calibration_tab(self, parent: ttk.Frame) -> None:
        """Permite cargar el Minihorno o calibrar una geometria propia."""
        parent.columnconfigure((0, 1, 2), weight=1)
        parent.rowconfigure(1, weight=1)
        profile_bar = ttk.Frame(parent, style="Panel.TFrame")
        profile_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=(7, 4))
        ttk.Label(profile_bar, text="Perfil geometrico", style="Small.TLabel").pack(side="left", padx=(2, 6))
        ttk.OptionMenu(
            profile_bar,
            self.vars["geometry_profile"],
            self.vars["geometry_profile"].get(),
            "Minihorno IER",
            "Diseno personalizado",
        ).pack(side="left", padx=3)
        ttk.Button(
            profile_bar,
            text="CARGAR PERFIL",
            style="Gold.TButton",
            command=self.load_geometry_profile,
        ).pack(side="left", padx=6)
        self.profile_status_label = ttk.Label(
            profile_bar,
            text="Minihorno IER precargado; cualquier edicion cambia a Diseno personalizado.",
            style="Small.TLabel",
        )
        self.profile_status_label.pack(side="left", padx=8)

        heliostat = ttk.LabelFrame(parent, text="Heliostato y movimiento", style="Block.TLabelframe")
        receiver = ttk.LabelFrame(parent, text="Concentrador y receptor", style="Block.TLabelframe")
        calibration = ttk.LabelFrame(parent, text="Ubicacion y calibracion", style="Block.TLabelframe")
        for column, card in enumerate((heliostat, receiver, calibration)):
            card.grid(row=1, column=column, sticky="nsew", padx=(10 if column == 0 else 4, 10 if column == 2 else 4), pady=(2, 8))
            card.columnconfigure(1, weight=1)
            card.columnconfigure(3, weight=1)

        heliostat_fields = (
            ("Espejo lado (m)", "mirror_size_m"),
            ("Base ancho (m)", "base_width_m"),
            ("Horquilla alto (m)", "fork_height_m"),
            ("Riel largo (m)", "rail_length_m"),
            ("Peralte (deg)", "peralte"),
            ("Acimut min (deg)", "az_limit_min"),
            ("Acimut max (deg)", "az_limit_max"),
            ("Elevacion min (deg)", "el_limit_min"),
            ("Elevacion max (deg)", "el_limit_max"),
            ("Vel. acimut (deg/s)", "az_deg_per_second"),
            ("Vel. elevacion (deg/s)", "el_deg_per_second"),
        )
        for index, (label, name) in enumerate(heliostat_fields):
            self.add_profile_entry(heliostat, label, name, index // 2, (index % 2) * 2)

        receiver_fields = (
            ("Target RX (m)", "rx"),
            ("Target RY (m)", "ry"),
            ("Target RZ relativo (m)", "rz"),
            ("Pantalla diam. (m)", "receiver_screen_m"),
            ("Escala target +/- (m)", "target_scale_m"),
            ("Tolerancia target (m)", "target_tolerance_m"),
            ("Numero de facetas", "facet_count"),
            ("Tamano faceta (m)", "facet_size_m"),
            ("Separacion facetas (m)", "facet_gap_m"),
            ("Distancia focal (m)", "facet_focal_distance_m"),
        )
        for index, (label, name) in enumerate(receiver_fields):
            self.add_profile_entry(receiver, label, name, index // 2, (index % 2) * 2)
        ttk.Label(receiver, text="Forma de faceta", style="Small.TLabel").grid(row=5, column=0, sticky="w", padx=2, pady=2)
        ttk.OptionMenu(
            receiver,
            self.vars["facet_shape"],
            self.vars["facet_shape"].get(),
            "Cuadrada",
            "Circular",
            "Hexagonal",
            command=lambda _=None: (self.mark_custom_profile(), self.apply_controls()),
        ).grid(row=5, column=1, columnspan=3, sticky="ew", padx=2, pady=2)
        ttk.Label(
            receiver,
            text="RX/RY/RZ se miden desde el centro optico del espejo, no desde el suelo.",
            style="Small.TLabel",
            wraplength=420,
            justify="left",
        ).grid(row=6, column=0, columnspan=4, sticky="ew", padx=2, pady=(4, 2))

        calibration_fields = (
            ("Latitud (deg)", "lat_deg"),
            ("Longitud (deg)", "lon_deg"),
            ("Zona horaria UTC (h)", "utc_offset_hours"),
            ("Offset elevacion (deg)", "offset_ele"),
            ("Offset acimut (deg)", "offset_acim"),
            ("Offset camara EL (deg)", "camera_offset_ele"),
            ("Offset camara AZ (deg)", "camera_offset_acim"),
            ("Zona cdr (deg)", "cdr"),
            ("Encoder acimut (ct/deg)", "az_counts_per_degree"),
            ("Encoder elevacion (ct/deg)", "el_counts_per_degree"),
            ("Sigma spot (m)", "spot_base_sigma_m"),
            ("Rango spot +/- (m)", "spot_map_half_size_m"),
            ("Resolucion spot", "spot_map_resolution"),
        )
        for index, (label, name) in enumerate(calibration_fields):
            self.add_profile_entry(calibration, label, name, index // 2, (index % 2) * 2)
        ttk.Label(calibration, text="Metodo solar", style="Small.TLabel").grid(
            row=7, column=0, sticky="w", padx=2, pady=(4, 2)
        )
        ttk.OptionMenu(
            calibration,
            self.vars["method"],
            self.vars["method"].get(),
            "D&B",
            "REDA",
            "SPA/PVLIB",
            command=lambda _=None: self.apply_controls(),
        ).grid(row=7, column=1, columnspan=3, sticky="ew", padx=2, pady=(4, 2))
        for label, key, row, column in (
            ("Zenit", "zenith", 8, 0),
            ("Altura solar", "altitude", 8, 2),
            ("Acimut solar", "solar_azimuth", 9, 0),
        ):
            ttk.Label(calibration, text=label, style="Small.TLabel").grid(
                row=row, column=column, sticky="w", padx=2, pady=2
            )
            out = ttk.Label(calibration, text="0.0000", style="Readout.TLabel")
            out.grid(row=row, column=column + 1, sticky="ew", padx=2, pady=2)
            self.readouts[key] = out

    def load_geometry_profile(self) -> None:
        """Carga valores conocidos del Minihorno o conserva el perfil propio."""
        profile = str(self.vars["geometry_profile"].get())
        if profile != "Minihorno IER":
            self.profile_status_label.configure(text="Diseno personalizado activo; edita libremente las medidas.")
            self.log_event("Perfil personalizado seleccionado")
            return
        for name, value in MINIHORNO_PROFILE.items():
            self.vars[name].set(value)
        self.state.facet_active_ids = {f"F{index}" for index in range(1, int(MINIHORNO_PROFILE["facet_count"]) + 1)}
        self.state.invalidate_optical_cache()
        self.apply_controls()
        self.profile_status_label.configure(text="Perfil Minihorno IER restaurado con dimensiones y calibracion precargadas.")
        self.log_event("Perfil Minihorno IER cargado")
        self.request_render()

    def mark_custom_profile(self, _event: object = None) -> None:
        """Marca el perfil como propio cuando cambia una medida calibrable."""
        self.vars["geometry_profile"].set("Diseno personalizado")
        if hasattr(self, "profile_status_label"):
            self.profile_status_label.configure(text="Diseno personalizado activo; cambios aplicados al gemelo.")

    def build_bottom_panel(self, parent: ttk.Frame) -> None:
        """Crea las pestanas inferiores de status, eventos y calibracion."""
        bottom_area = ttk.Frame(parent, style="Dark.TFrame")
        bottom_area.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        bottom_area.columnconfigure(0, weight=1)
        bottom_area.rowconfigure(0, weight=1)
        self.bottom_notebook = ttk.Notebook(bottom_area, height=300)
        self.bottom_notebook.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )
        persistent_panel = ttk.Frame(bottom_area, style="Dark.TFrame", width=366)
        persistent_panel.grid(row=0, column=1, sticky="nsew")
        persistent_panel.grid_propagate(False)
        status_tab = ttk.Frame(self.bottom_notebook, style="Panel.TFrame")
        events_tab = ttk.Frame(self.bottom_notebook, style="Panel.TFrame")
        calibration_tab = ttk.Frame(self.bottom_notebook, style="Panel.TFrame")
        self.bottom_notebook.add(status_tab, text="Status del heliostato")
        self.bottom_notebook.add(events_tab, text="Eventos y validaciones")
        self.bottom_notebook.add(calibration_tab, text="Calibracion y perfiles")
        self.build_status_block(status_tab)
        self.build_events_panel(events_tab)
        self.build_calibration_tab(calibration_tab)
        self.build_fixed_action_bar(persistent_panel)

    def build_status_block(self, parent: ttk.Frame) -> None:
        """Construye un status inferior compacto con controles globales."""
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        grid = ttk.Frame(frame, style="Panel.TFrame")
        grid.pack(fill="both", expand=True)
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
        self.state_banner.grid(row=0, column=0, columnspan=8, sticky="ew", pady=(0, 3))
        self.state_detail = ttk.Label(
            grid,
            text="",
            style="Small.TLabel",
            wraplength=1450,
            justify="left",
        )
        self.state_detail.grid(row=1, column=0, columnspan=8, sticky="ew", pady=(0, 4))
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
            ("Rendimiento interfaz", "performance"),
        ]
        for index, (label, key) in enumerate(labels):
            group = index % 4
            ui_row = index // 4 + 2
            label_col = group * 2
            ttk.Label(grid, text=label, style="Small.TLabel").grid(
                row=ui_row,
                column=label_col,
                sticky="w",
                padx=(3, 4),
                pady=1,
            )
            out = ttk.Label(grid, text="0", style="Readout.TLabel")
            out.grid(row=ui_row, column=label_col + 1, sticky="ew", padx=(0, 8), pady=1)
            self.readouts[key] = out
        for column in (1, 3, 5, 7):
            grid.columnconfigure(column, weight=1)

    def build_fixed_action_bar(self, parent: ttk.Frame) -> None:
        """Muestra reloj y operaciones de sesion en un panel siempre visible."""
        clock = tk.Frame(parent, bg="#172432", bd=1, relief="ridge")
        clock.pack(fill="x", padx=2, pady=(0, 3))
        tk.Label(
            clock,
            text="RELOJ DEL EXPERIMENTO",
            bg="#172432",
            fg="#f4d35e",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(3, 0))
        clock_value_row = tk.Frame(clock, bg="#172432")
        clock_value_row.pack(fill="x", padx=10)
        self.persistent_date_label = tk.Label(
            clock_value_row,
            text="0000-00-00",
            bg="#172432",
            fg="#ffffff",
            font=("Consolas", 11, "bold"),
        )
        self.persistent_date_label.pack(side="left", anchor="s")
        self.persistent_time_label = tk.Label(
            clock_value_row,
            text="00:00:00",
            bg="#172432",
            fg="#5ee67a",
            font=("Consolas", 18, "bold"),
        )
        self.persistent_time_label.pack(side="right", anchor="e")
        self.persistent_mode_label = tk.Label(
            clock,
            text="TIEMPO REAL | multiplicador 1x",
            bg="#172432",
            fg="#dbeafe",
            justify="left",
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.persistent_mode_label.pack(fill="x", padx=10, pady=(0, 3))

        bar = ttk.Frame(parent, style="Dark.TFrame")
        bar.pack(fill="both", expand=True, padx=2)
        # El panel recibe su tamano del contenedor fijo. Los textos de ayuda
        # no deben cambiar su geometria al entrar o salir el cursor.
        bar.grid_propagate(False)
        self.operation_state_label = tk.Label(
            bar,
            text="SIMULACION EN CURSO",
            bg="#16834f",
            fg="#ffffff",
            anchor="w",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        )
        self.operation_state_label.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.action_context_label = tk.Label(
            bar,
            text="En vivo; esperando muestras de la sesion.",
            bg="#242424",
            fg="#cbd5e1",
            anchor="w",
            justify="left",
            width=46,
            height=2,
            wraplength=338,
            font=("Segoe UI", 8),
        )
        self.action_context_label.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(1, 1))

        self.run_button = ttk.Button(
            bar,
            text="PAUSAR SIMULACION",
            style="PauseAction.TButton",
            command=self.toggle_run,
        )
        self.run_button.grid(row=2, column=0, columnspan=2, sticky="ew", pady=1)
        self.home_button = ttk.Button(
            bar,
            text="HOME 0 / 90 deg",
            style="HomeAction.TButton",
            command=self.home_position,
        )
        self.home_button.grid(row=3, column=0, sticky="ew", padx=(0, 3), pady=1)
        self.configure_session_button = ttk.Button(
            bar,
            text="CONFIGURAR",
            style="DataAction.TButton",
            command=self.return_to_configuration,
        )
        self.configure_session_button.grid(row=3, column=1, sticky="ew", padx=(3, 0), pady=1)

        tk.Label(
            bar,
            text="DATOS E HISTORIAL",
            bg="#242424",
            fg="#f4d35e",
            anchor="w",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self.export_button = ttk.Button(
            bar,
            text="GUARDAR CSV",
            style="DataAction.TButton",
            command=self.export_csv,
        )
        self.export_button.grid(row=5, column=0, sticky="ew", padx=(0, 3), pady=1)
        self.replay_button = ttk.Button(
            bar,
            text="REPRODUCIR",
            style="DataAction.TButton",
            command=self.start_replay,
        )
        self.replay_button.grid(row=5, column=1, sticky="ew", padx=(3, 0), pady=1)
        self.live_button = ttk.Button(
            bar,
            text="SALIR DE REPLAY",
            style="ResumeAction.TButton",
            command=self.stop_replay,
        )
        self.live_button.grid(row=6, column=0, sticky="ew", padx=(0, 3), pady=1)
        self.about_button = ttk.Button(
            bar,
            text="MANUAL",
            style="DataAction.TButton",
            command=self.show_model_information,
        )
        self.about_button.grid(row=6, column=1, sticky="ew", padx=(3, 0), pady=1)

        action_hints = (
            (self.run_button, "Inicia, pausa o reanuda usando el origen temporal elegido."),
            (self.home_button, "Mueve suavemente el heliostato a acimut 0 y elevacion 90 deg."),
            (self.configure_session_button, "Detiene la ejecucion y desbloquea los parametros de tiempo."),
            (self.about_button, "Abre el manual completo de uso y la referencia tecnica."),
            (self.export_button, "Guarda en CSV las muestras acumuladas de esta sesion."),
            (self.replay_button, "Reproduce ciclicamente las muestras acumuladas."),
            (self.live_button, "Sale de la reproduccion y recupera la simulacion activa."),
        )
        self.action_hint_active = False
        for button, hint in action_hints:
            button.bind("<Enter>", lambda _event, text=hint: self.show_action_hint(text))
            button.bind("<Leave>", self.clear_action_hint)
        bar.rowconfigure(1, minsize=34)
        bar.columnconfigure(0, weight=1, uniform="main_actions")
        bar.columnconfigure(1, weight=1, uniform="main_actions")
        self.update_action_panel()

    def build_events_panel(self, parent: ttk.Frame) -> None:
        """Construye validaciones activas y bitacora reciente lado a lado."""
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=2)
        parent.rowconfigure(1, weight=1)
        ttk.Label(parent, text="Validaciones activas", style="Small.TLabel").grid(
            row=0, column=0, sticky="w", padx=10, pady=(7, 2)
        )
        ttk.Label(parent, text="Bitacora reciente", style="Small.TLabel").grid(
            row=0, column=1, sticky="w", padx=10, pady=(7, 2)
        )
        self.validation_text = tk.Text(
            parent,
            height=8,
            wrap="word",
            bg="#fffdf5",
            fg="#222222",
            relief="sunken",
            font=("Segoe UI", 9),
        )
        self.validation_text.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 8))
        self.event_text = tk.Text(
            parent,
            height=8,
            wrap="none",
            bg="#101821",
            fg="#dbeafe",
            relief="sunken",
            font=("Consolas", 9),
        )
        self.event_text.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 8))
        self.validation_text.configure(state="disabled")
        self.event_text.configure(state="disabled")

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
            switch.pack(fill="x", padx=12, pady=2)
        else:
            switch.grid(row=row, column=col, columnspan=2, sticky="ew", padx=4, pady=2)
        return switch

    def add_entry(self, parent: ttk.Frame, label: str, varname: str, row: int, col: int) -> ttk.Entry:
        """Agrega etiqueta + caja de texto y aplica cambios con Enter o foco fuera."""
        ttk.Label(parent, text=label, style="Small.TLabel").grid(row=row, column=col, sticky="w", pady=2, padx=2)
        entry = ttk.Entry(parent, textvariable=self.vars[varname], width=9)
        entry.grid(row=row, column=col + 1, sticky="ew", pady=2, padx=2)
        entry.bind("<Return>", lambda _event: self.apply_controls())
        entry.bind("<FocusOut>", lambda _event: self.apply_controls())
        entry.bind("<KeyRelease>", lambda _event: self.validate_numeric_entries())
        if varname in MINIHORNO_PROFILE:
            entry.bind("<KeyRelease>", self.mark_custom_profile, add="+")
        self.entries[varname] = entry
        self.entry_groups.setdefault(varname, []).append(entry)
        return entry

    def add_profile_entry(
        self,
        parent: ttk.Frame,
        label: str,
        varname: str,
        row: int,
        col: int,
    ) -> ttk.Entry:
        """Agrega una medida cuya edicion activa el perfil personalizado."""
        return self.add_entry(parent, label, varname, row, col)

    def validate_numeric_entries(self) -> list[str]:
        """Resalta campos numericos invalidos y devuelve sus nombres internos."""
        invalid: list[str] = []
        text_fields = {"facet_misaligned_id"}
        integer_fields = {
            "history_limit",
            "error_random_seed",
            "facet_count",
            "spot_map_resolution",
        }
        for name, entries in self.entry_groups.items():
            entry = entries[0]
            if name in text_fields:
                for item in entries:
                    item.configure(style="TEntry")
                continue
            try:
                text = entry.get().strip()
                int(text) if name in integer_fields else float(text)
            except ValueError:
                invalid.append(name)
                for item in entries:
                    item.configure(style="Invalid.TEntry")
            else:
                for item in entries:
                    item.configure(style="TEntry")
        return invalid

    def set_normalized_entry_value(self, name: str, value: object) -> None:
        """Actualiza un campo saneado sin interrumpir una edicion en curso."""
        entries = self.entry_groups.get(name, [])
        if any(self.root.focus_get() is entry for entry in entries):
            return
        self.vars[name].set(value)

    def log_event(self, message: str) -> None:
        """Agrega un mensaje a la bitacora evitando duplicados consecutivos."""
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        if self.event_log and self.event_log[-1].endswith(message):
            return
        self.event_log.append(f"{stamp}  {message}")

    def _show_model_information_legacy(self) -> None:
        """Muestra la logica conceptual fuera de las vistas de simulacion."""
        window = tk.Toplevel(self.root)
        window.title("Acerca del gemelo digital")
        window.geometry("760x620")
        window.minsize(620, 480)
        text = tk.Text(
            window,
            wrap="word",
            bg="#f7f7f7",
            fg="#222222",
            padx=18,
            pady=16,
            font=("Segoe UI", 10),
        )
        text.pack(fill="both", expand=True)
        information = (
            "FLUJO CONCEPTUAL DEL GEMELO DIGITAL\n\n"
            "1. Fecha, hora y ubicacion -> posicion solar.\n"
            "2. Posicion solar -> vector S en +x oeste, +y sur, +z cenit.\n"
            "3. Target RX/RY/RZ -> direccion deseada de reflexion.\n"
            "4. La bisectriz entre Sol y target produce la normal ideal.\n"
            "5. El modelo de errores perturba geometria y movimiento.\n"
            "6. Motores, limites, PWM y encoder actualizan la pose simulada.\n"
            "7. El rayo reflejado intersecta el plano del target.\n"
            "8. Las estrategias de correccion intentan regresar el impacto al centro.\n"
            "9. El concentrador facetado produce rayos centrales y un spot aproximado.\n"
            "10. Las muestras alimentan graficas, replay y exportacion CSV.\n\n"
            "Este programa es un simulador: no abre puertos seriales, no usa GPIO "
            "y no controla hardware fisico. La documentacion de uso y la "
            "referencia tecnica estan disponibles en el boton MANUAL."
        )
        text.insert("1.0", information)
        text.configure(state="disabled")

    @staticmethod
    def create_formula_card(parent: tk.Misc, formula: str, card_width: int) -> tk.Canvas:
        """Construye una tarjeta matematica compacta, con fracciones apiladas."""
        fraction_parts = {
            "N̂ = (Ŝ + T̂) / ‖Ŝ + T̂‖": ("N̂ =", "Ŝ + T̂", "‖Ŝ + T̂‖"),
            "λ = ((R − O) · nᵣ) / (dᵣ · nᵣ)": ("λ =", "(R − O) · nᵣ", "dᵣ · nᵣ"),
            "σmayor = σbase / |cos(incidencia)|": (
                "σₘₐᵧₒᵣ =",
                "σᵦₐₛₑ",
                "|cos(incidencia)|",
            ),
        }
        pretty_formula = (
            formula.replace("σmayor", "σₘₐᵧₒᵣ")
            .replace("σmenor", "σₘₑₙₒᵣ")
            .replace("σbase", "σᵦₐₛₑ")
            .replace("ωmáx", "ωₘₐₓ")
        )
        is_fraction = formula in fraction_parts
        card_height = 86 if is_fraction else 62
        card = tk.Canvas(
            parent,
            width=card_width,
            height=card_height,
            bg="#edf4f8",
            highlightbackground="#c7d7e2",
            highlightthickness=1,
            relief="flat",
        )
        card.create_rectangle(0, 0, 5, card_height, fill="#178ca4", outline="")
        card.create_text(
            17,
            11,
            anchor="nw",
            text="ECUACIÓN",
            fill="#527080",
            font=("Segoe UI", 7, "bold"),
        )
        if not is_fraction:
            card.create_text(
                card_width * 0.52,
                card_height * 0.57,
                text=pretty_formula,
                fill="#102a43",
                font=("Cambria Math", 15),
            )
            return card

        prefix, numerator, denominator = fraction_parts[formula]
        fraction_x = card_width * 0.60
        numerator_id = card.create_text(
            fraction_x,
            29,
            text=numerator,
            fill="#102a43",
            font=("Cambria Math", 14),
        )
        denominator_id = card.create_text(
            fraction_x,
            64,
            text=denominator,
            fill="#102a43",
            font=("Cambria Math", 14),
        )
        numerator_box = card.bbox(numerator_id) or (0, 0, 0, 0)
        denominator_box = card.bbox(denominator_id) or (0, 0, 0, 0)
        fraction_left = min(numerator_box[0], denominator_box[0]) - 10
        fraction_right = max(numerator_box[2], denominator_box[2]) + 10
        card.create_line(
            fraction_left,
            46,
            fraction_right,
            46,
            fill="#102a43",
            width=2,
        )
        card.create_text(
            fraction_left - 14,
            46,
            anchor="e",
            text=prefix,
            fill="#102a43",
            font=("Cambria Math", 15),
        )
        return card

    def show_model_information(self) -> None:
        """Abre el manual de usuario y la referencia tecnica del gemelo."""
        window = tk.Toplevel(self.root)
        window.title("Manual de usuario - Gemelo digital del mini horno solar")
        width = min(1040, self.root.winfo_screenwidth() - 80)
        height = min(760, self.root.winfo_screenheight() - 100)
        window.geometry(f"{width}x{height}")
        window.minsize(760, 560)
        header = tk.Frame(window, bg="#172432")
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"MANUAL DE USUARIO DEL GEMELO DIGITAL - VERSION {APP_RELEASE}",
            bg="#172432",
            fg="#f4d35e",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w", padx=20, pady=(14, 2))
        tk.Label(
            header,
            text="Uso completo de la interfaz, experimentos, resultados, fundamentos y formulas",
            bg="#172432",
            fg="#dbeafe",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=20, pady=(0, 14))
        user_sections = (
            (
                "Inicio rapido",
                """QUE HACE EL PROGRAMA
El gemelo digital reproduce el comportamiento geometrico y temporal de un heliostato que dirige radiacion solar hacia un concentrador. Permite trabajar con el perfil precargado Minihorno IER o con un diseno propio, comparar errores, ensayar correcciones, estudiar facetas y guardar los resultados.

El programa abre detenido. Esto es intencional: primero se configuran el perfil, el tiempo, el modo y el experimento; despues se pulsa INICIAR. Ningun control de esta aplicacion mueve hardware real.

PRIMERA SIMULACION RECOMENDADA
1. En la pestana inferior Calibracion y perfiles, selecciona Minihorno IER y pulsa CARGAR PERFIL.
2. En Tiempo del experimento, elige TIEMPO REAL o FECHA SIMULADA.
3. Si eliges Fecha simulada, escribe fecha en formato AAAA-MM-DD, hora HH:MM:SS, selecciona la velocidad y pulsa APLICAR FECHA Y HORA.
4. En Modo, selecciona Automatico y deja Seguimiento solar en ON.
5. Para una prueba nominal, deja Caso mostrado = Ideal, correccion y facetas desactivadas.
6. Revisa que no haya campos rojos ni alertas criticas.
7. Pulsa el boton verde INICIAR TIEMPO REAL o INICIAR FECHA SIMULADA.
8. Observa Gemelo 3D, Pantalla / spot y error, Trayectoria solar y Diagnostico.
9. Pulsa PAUSAR cuando quieras inspeccionar un instante, exportar o reproducir las muestras.

REGLAS PRACTICAS
Los campos numericos se aplican al pulsar Enter o al salir del campo. Un campo rojo contiene un valor no interpretable y bloquea el inicio. Los paneles de la izquierda son desplegables: abrirlos o cerrarlos no cambia sus valores.

El recuadro fijo inferior derecho siempre muestra la fecha, hora, origen temporal y multiplicador activos. Es la referencia definitiva para saber si se trabaja en tiempo real, fecha simulada, pausa o replay.""",
            ),
            (
                "Mapa de la interfaz",
                """DISTRIBUCION GENERAL
La pantalla esta dividida en cuatro zonas:
1. Izquierda: configuracion y controles desplegables.
2. Derecha: vistas graficas del experimento.
3. Inferior: status, eventos, validaciones, calibracion y perfiles.
4. Inferior derecha: reloj y acciones principales siempre visibles.

PANEL IZQUIERDO
Usa la rueda del mouse para desplazarte. Cada barra dorada abre o cierra un apartado. Los apartados son Modo, Tiempo del experimento, Control Motor, Seguimiento y objetivo, Vectores geometricos, Errores, Correccion de deriva y Facetas.

VISTAS DERECHAS
Las pestanas cambian solo la representacion visual; no reinician la simulacion. Las vistas son Gemelo 3D, Pantalla / spot y error, Trayectoria solar, Deriva y correccion, Facetas / rayos / intensidad y Diagnostico.

PANEL INFERIOR
Status del heliostato muestra variables instantaneas. Eventos y validaciones explica alertas y conserva una bitacora. Calibracion y perfiles contiene todas las dimensiones, ubicacion y parametros del sistema.

CODIGO DE ESTADO
Verde indica operacion normal o llegada al objetivo. Azul identifica configuracion o movimiento manual. Dorado indica movimiento, replay o advertencia. Rojo indica pausa o una condicion critica. El texto del banner siempre tiene prioridad sobre el color.

CONVENCION ESPACIAL
+x = oeste, -x = este, +y = sur, -y = norte y +z = cenit. El acimut de laboratorio usa 0 deg al sur, valores positivos hacia el oeste y negativos hacia el este.""",
            ),
            (
                "Modos, reloj y sesion",
                """MODO AUTOMATICO
Calcula la orientacion requerida a partir del Sol y el target. Seguimiento solar ON permite actualizar el objetivo con el intervalo elegido. Si esta OFF, el objetivo queda retenido. CORREGIR AHORA fuerza una actualizacion cuando el seguimiento esta activo.

MODO MANUAL
Permite ordenar directamente los motores simulados. Ajusta cada perilla PWM, comprueba que el switch del motor este ON y pulsa Oeste/Este o Bajar/Subir. El movimiento continua hasta pulsar Detener, pausar la sesion o alcanzar un limite. El modo manual no intenta centrar automaticamente el spot.

MODO HOME
Fija como objetivo acimut 0 deg y elevacion 90 deg. El heliostato se mueve gradualmente desde su posicion actual segun PWM y velocidad; no salta de forma instantanea.

TIEMPO REAL
Usa el reloj civil actual con la zona UTC configurada en el perfil. No admite avance manual, reinicio ni multiplicador temporal. El tiempo no comienza a procesarse hasta pulsar INICIAR TIEMPO REAL.

FECHA SIMULADA
Usa el instante escrito por el usuario. APLICAR FECHA Y HORA valida y fija el origen. La velocidad 1x, 10x, 60x, 120x o 600x multiplica solamente el avance del reloj solar. El paso manual se expresa en segundos.

CONTROLES CUANDO LA SIMULACION ESTA PAUSADA
AVANZAR UN PASO mueve el reloj la cantidad indicada y recalcula la geometria. REINICIAR TIEMPO vuelve al origen aplicado y limpia trayectoria, programador de seguimiento y correccion dinamica. Ambos requieren Fecha simulada, una sesion iniciada y pausa activa.

CICLO DE LA SESION
INICIAR valida la configuracion y comienza a registrar muestras. PAUSAR congela tiempo y motores. REANUDAR continua la misma sesion. CONFIGURAR detiene la ejecucion y desbloquea la seleccion temporal, pero no borra automaticamente las muestras exportables. HOME solicita el retorno 0/90 mientras la sesion esta activa.""",
            ),
            (
                "Controles de seguimiento",
                """CONTROL MOTOR ACIMUT / ELEVACION
PWM define la fraccion de la velocidad maxima de cada eje. Motor ON/OFF habilita o impide su actuacion. Los botones direccionales se usan principalmente en Manual. Los contadores de encoder se calculan con los conteos por grado configurados.

ACTUALIZAR CADA
En Automatico determina cada cuanto se recalcula el objetivo retenido: 1, 5, 10, 30 o 60 segundos del reloj del experimento. Manual evita actualizaciones periodicas y deja CORREGIR AHORA como orden explicita.

CONSIDERACION CDR
Es la banda angular de llegada. Dentro de +/- cdr el controlador considera que el eje ya esta en objetivo y deja de actuar. Un valor excesivo reduce precision; uno demasiado pequeno puede producir actividad continua cerca del objetivo.

REFRESCO Y RENDIMIENTO
Refresco (s) controla el ciclo de actualizacion numerica. Calidad grafica Rapida, Equilibrada o Alta cambia la frecuencia del dibujo, no la fisica. Usa Rapida con muchas facetas o una resolucion alta del mapa.

LIMITE HISTORIAL
Controla cuantas muestras conserva la trayectoria que alimenta las graficas temporales. Limpiar trayectoria borra esa historia visual; no equivale a borrar el archivo CSV ya guardado.

TARGET R A ESCALA MAQUETA
Aplica el factor historico 0.0844 solo a RX/RY/RZ. Debe permanecer OFF cuando todas las dimensiones se introducen en metros reales. Activarlo por error modifica la distancia optica y puede desplazar o invalidar el impacto.

VECTORES GEOMETRICOS VISIBLES
Solar incidente muestra la direccion de llegada del Sol. Normal heliostato muestra la normal del espejo. Rayo reflejado muestra la salida optica. Direccion objetivo representa el vector al target. Linea heliostato-target une ambos centros como referencia. Guias mecanicas dibuja arcos y limites auxiliares; puede ocultarse para una vista mas limpia.""",
            ),
            (
                "Errores y correccion",
                """CASO MOSTRADO
Ideal ignora perturbaciones. Con error aplica todos los errores cuyo switch este ON. Corregido aplica esos mismos errores y agrega compensaciones manuales y dinamicas. Las tres soluciones se calculan en paralelo para que la pantalla pueda compararlas aunque solo una gobierne la vista principal.

ERRORES ANGULARES
Offset elevacion y Offset acimut agregan sesgos fijos. Eje norte-sur representa una desalineacion del eje. Error peralte perturba la relacion entre lectura mecanica y normal optica.

ERRORES DE POSICION
Error posicion target desplaza el receptor en X/Y/Z. Error coord. helio desplaza el origen del heliostato. Las coordenadas siguen +x oeste, +y sur y +z cenit, y se expresan en metros.

ERRORES DE MOVIMIENTO
Backlash agrega holgura al invertir el sentido. Error subida/bajada permite sesgos diferentes segun direccion. Ruido aleatorio usa una desviacion sigma en grados y una semilla reproducible. NUEVA MUESTRA cambia la realizacion aleatoria sin cambiar los parametros.

COMPENSACION MANUAL
Corr. acimut y Corr. elev. se aplican al caso Corregido. Son utiles para estudiar que compensacion fija minimiza el error conocido.

CORRECCION DE DERIVA
Activa el modulo y elige una estrategia: sin correccion, offset constante, dependencia temporal, polinomio, impacto observado o camara periodica. Solo los parametros de la estrategia seleccionada afectan el resultado.

CORREGIR DESDE IMPACTO
Disponible con Impacto observado o Camara periodica. Convierte u/v en un incremento angular limitado por Paso max deg y ponderado por Ganancia AZ/EL. Cada pulsacion aplica un paso, por lo que se puede observar la convergencia. RESET CORRECCION borra la compensacion dinamica y su contador.

LECTURA DE RESULTADOS
Compara el radio Ideal, Con error y Corregido. Una correccion es beneficiosa cuando el radio corregido disminuye sin introducir alertas, saturacion de ejes o perdida de impacto.""",
            ),
            (
                "Facetas e intensidad",
                """ACTIVAR MODELO
Habilita el concentrador facetado. Si esta OFF, el heliostato y el target siguen funcionando, pero no se calculan contribuciones individuales ni mapa de intensidad.

GEOMETRIA
Forma admite Cuadrada, Circular o Hexagonal. Numero facetas define cuantas piezas genera el algoritmo. Tamano significa lado para cuadradas, diametro para circulares y ancho entre caras para hexagonales. Separacion extra se agrega entre piezas. Distancia focal define la convergencia de los rayos centrales.

ACOMODO AUTOMATICO
Las cuadradas usan reticula compacta centrada. Circulares y hexagonales usan empaquetamiento triangular por anillos. El algoritmo centra el conjunto y admite cantidades que no completan una reticula o anillo.

CONTROL POR FACETA
Escribe un ID como F12. Las desalineaciones horizontal y vertical afectan esa faceta. ACTIVAR/DESACTIVAR SELECCIONADA cambia si contribuye al foco. TODAS ON y TODAS OFF operan sobre el conjunto completo.

VISTA DEL ESQUEMA
Resumen combina la geometria y el receptor. Superior X-Y, Lateral Y-Z y 3D isometrica cambian el punto de observacion del trazado. Los rayos solares aparecen como vectores paralelos que nacen en el heliostato sin cubrir visualmente las facetas.

MAPA DE INTENSIDAD
Activar mapa suma una gaussiana por impacto. Sigma base controla el ancho nominal. Rango +/- fija el dominio alrededor del foco. Resolucion impar define el numero de celdas por lado. Normalizacion puede fijar Total = 1, Pico = 1 o conservar la magnitud calculada.

INTERPRETACION
El centroide indica el centro energetico. Sigma mayor/menor y orientacion describen elongacion. Diametro equivalente resume el area. Intensidad total y maxima dependen de la normalizacion. Una faceta apagada o desalineada debe reflejarse tanto en la tabla por faceta como en el mapa.""",
            ),
            (
                "Vistas graficas",
                """GEMELO 3D
Muestra heliostato, concentrador, suelo, target y vectores habilitados. Isometrica, Frontal, Lateral y Superior son vistas fijas. En Libre, arrastra con boton derecho para rotar 360 grados y con boton izquierdo para desplazar la escena. Restablecer vista libre devuelve orientacion y desplazamiento iniciales. La tarjeta Orientacion local muestra ejes X/Y/Z rotados con la misma camara.

PANTALLA / SPOT Y ERROR
El plano usa u horizontal, positivo al oeste, y v vertical, positivo al cenit; ambos en milimetros. El circulo representa el target a escala. Los marcadores Ideal, Con error y Corregido muestran los tres casos y el panel derecho reporta u, v, radio, error angular, distancia y tolerancia. Un punto fuera del circulo esta fuera del receptor, no simplemente fuera de escala.

TRAYECTORIA SOLAR
Eje X: acimut de laboratorio, de -180 a +180 deg. Eje Y: altura solar, de 0 a 90 deg. La curva representa el dia de la fecha activa y las guias marcan el instante usado. El recuadro informa metodo, altura, acimut y zenit. Con Sol bajo el horizonte la geometria optica no es operativa.

DERIVA Y CORRECCION
Reune seis graficas temporales: Error horizontal u, Error vertical v, Error radial, Tiempo desde ultima actualizacion, Error radial sin correccion/corregido y Compensacion angular AZ/EL. El eje horizontal es el tiempo o secuencia de muestras; cada grafica rotula sus unidades verticales. Haz clic en cualquier grafica para ampliarla y usa VOLVER A 6 GRAFICAS para recuperar el tablero.

FACETAS / RAYOS / INTENSIDAD
Combina esquema de rayos, plano receptor, resultados por ID y mapa de intensidad. Haz clic en un panel para ampliarlo y pulsa VOLVER A VISTA GENERAL para regresar. Colores y leyendas identifican normal, incidente, reflejado, facetas activas e inactivas.

DIAGNOSTICO
Las barras superiores muestran Error acimut [deg], Error elevacion [deg] y Error spot [mm]. El historial inferior usa tiempo/muestras en X y distancia radial al centro [mm] en Y. El panel numerico muestra real/objetivo, PWM, cdr, correcciones, estadisticas, metodo y tiempo. Las tarjetas inferiores explican vectores y estado operacional.""",
            ),
            (
                "Panel inferior y acciones",
                """STATUS DEL HELIOSTATO
Presenta medidas instantaneas agrupadas: angulos y objetivos, target, contadores, impacto u/v, error angular, angulos opticos, limites, motores, seguimiento, correcciones, comparacion de casos, historial, iteraciones y rendimiento. Es un tablero de lectura; los cambios se hacen en los controles o en Calibracion.

EVENTOS Y VALIDACIONES
La mitad izquierda resume estado y alertas activas. Critica significa que la geometria o el movimiento no son confiables; advertencia indica una condicion que impide llegar al objetivo; info describe estados normales. La mitad derecha es la bitacora cronologica de cambios, rechazos y acciones.

CALIBRACION Y PERFILES
Contiene tres grupos: Heliostato y movimiento, Concentrador y receptor, y Ubicacion y calibracion. Cargar Minihorno IER restaura todos los valores conocidos. Editar una medida convierte el perfil en Diseno personalizado.

RELOJ DEL EXPERIMENTO
Muestra fecha y hora realmente usadas por el calculo. Debajo indica Tiempo real o Fecha simulada, zona UTC y multiplicador. Durante replay o pausa, el estado correspondiente aparece en el bloque de acciones.

ACCIONES PRINCIPALES
INICIAR/PAUSAR/REANUDAR controla el ciclo de la sesion. HOME 0/90 solicita el retorno de referencia. CONFIGURAR detiene y desbloquea el origen temporal. GUARDAR CSV exporta las muestras. REPRODUCIR recorre ciclicamente las muestras guardadas y exige que la simulacion este pausada. SALIR DE REPLAY vuelve al estado vivo. MANUAL abre esta documentacion.

BOTONES DESHABILITADOS
Un boton gris no es util en el contexto actual. Por ejemplo, Home requiere una sesion en marcha; Replay requiere muestras y pausa; Salir de replay solo se activa durante la reproduccion; Avanzar y Reiniciar requieren Fecha simulada pausada.""",
            ),
            (
                "Calibracion y perfiles",
                """PERFIL MINIHORNO IER
Selecciona Minihorno IER y pulsa CARGAR PERFIL para restaurar dimensiones, ubicacion, limites, encoders, facetas y target precargados. El perfil sirve como referencia reproducible para los experimentos del mini horno.

DISENO PERSONALIZADO
Selecciona Diseno personalizado o edita cualquier campo de calibracion. Todas las longitudes se introducen en metros fisicos completos, los angulos en grados, las velocidades en grados/segundo y los encoders en conteos/grado.

HELIOSTATO Y MOVIMIENTO
Espejo lado cambia la dimension del espejo. Base ancho, Horquilla alto y Riel largo cambian la estructura dibujada. Peralte relaciona elevacion mecanica y normal optica. Limites AZ/EL restringen el movimiento. Velocidades definen grados por segundo a PWM = 100 por ciento.

CONCENTRADOR Y RECEPTOR
RX/RY/RZ son coordenadas desde el centro optico del espejo, no desde el suelo. Pantalla diam. es el diametro fisico del receptor. Escala target +/- controla el rango del grafico y Tolerancia target el circulo de aceptacion. Facetas, tamano, separacion, forma y focal alimentan el mismo modulo lateral.

UBICACION Y CALIBRACION
Latitud y longitud ubican el laboratorio. Zona UTC representa la hora civil independientemente de la longitud. Offsets AZ/EL son calibraciones nominales; offsets de camara representan alineacion de la observacion. Cdr es la banda del controlador. Sigma, rango y resolucion gobiernan el mapa. Metodo solar selecciona D&B, REDA o SPA/PVLIB.

APLICACION DE CAMBIOS
Pulsa Enter o sal del campo. El modelo recalcula y las vistas se actualizan. Si una entrada no es numerica se marca en rojo y el evento correspondiente aparece abajo. Verifica siempre unidades y el switch Target R a escala maqueta antes de interpretar distancias.""",
            ),
            (
                "Datos, replay y CSV",
                """CAPTURA DE MUESTRAS
Mientras una sesion esta iniciada y en marcha, cada ciclo valido agrega una muestra. No se agregan muestras durante pausa ni replay. El historial de graficas y la lista exportable son conceptos relacionados, pero Limpiar trayectoria solo limpia el historial visual.

GUARDAR CSV
Se habilita al existir muestras. Abre un dialogo con nombre gemelo_digital_AAAAMMDD_HHMMSS.csv y propone la carpeta digital_twin/logs. El usuario puede elegir otra ruta. El archivo usa UTF-8, encabezados en la primera fila y una muestra por fila.

CONTENIDO DEL CSV
Incluye fecha/hora y reloj, modo y estado; pose, objetivo y errores AZ/EL; impacto u/v/radial y tolerancia; seguimiento y estadisticas; casos Ideal/Con error/Corregido; estrategia y compensacion de deriva; geometria y resultados de facetas; metricas del mapa; posicion solar y vectores; angulos opticos; target, peralte, motores y PWM.

REPRODUCIR
Primero pausa la simulacion. REPRODUCIR copia las muestras disponibles y las presenta ciclicamente sin generar datos nuevos. Sirve para revisar vistas y diagnostico de una sesion. SALIR DE REPLAY devuelve el control a la sesion; despues puedes reanudar o volver a Configurar.

INTERPRETACION RESPONSABLE
CSV y replay contienen resultados simulados. Conserva junto al archivo el perfil, los errores activados y el origen temporal si necesitas reproducibilidad. No sustituyen medicion experimental ni certificacion del sistema fisico.""",
            ),
            (
                "Experimentos guiados",
                """A. PUNTERIA IDEAL EN UN INSTANTE
Carga Minihorno IER, elige Fecha simulada, aplica una hora con Sol sobre el horizonte, selecciona Automatico + Seguimiento ON, Caso Ideal e inicia. Espera a EN OBJETIVO. Comprueba que el marcador ideal y el error radial sean coherentes con la tolerancia.

B. RECORRIDO SOLAR ACELERADO
Configura una fecha simulada al amanecer y velocidad 600x. Inicia en Automatico. Observa Trayectoria solar, Gemelo 3D y Diagnostico. Pausa en instantes de interes. Un Sol bajo horizonte debe producir alerta y no un impacto aparentemente valido.

C. SENSIBILIDAD A UN ERROR
Parte de Ideal. Activa un unico error, por ejemplo Offset acimut, fija su magnitud y selecciona Con error. Compara u/v/radial con Ideal. Luego selecciona Corregido e introduce una compensacion manual opuesta. Cambia un solo parametro por vez para atribuir el efecto.

D. CONVERGENCIA DESDE IMPACTO
Activa un error conocido. En Correccion de deriva activa Impacto observado, define ganancias moderadas y un paso maximo pequeno. Selecciona Corregido. Pulsa CORREGIR DESDE IMPACTO repetidamente y observa el radio corregido en Deriva y correccion. RESET CORRECCION repite el ensayo desde cero.

E. CONCENTRADOR FACETADO
Activa facetas y mapa. Elige forma, numero, tamano, separacion y focal. Revisa el acomodo. Desalinea F1 y compara tabla, foco y mapa; despues desactiva F1. Usa las vistas ampliables para documentar el cambio.

F. COMPARACION DE METODOS SOLARES
Manteniendo la misma ubicacion y fecha simulada, pausa y vuelve a Configurar antes de cada ensayo. Cambia D&B, REDA y SPA/PVLIB, registra altura/acimut/zenit y exporta sesiones separadas. Si PVLIB no esta disponible, el status informa el metodo de respaldo.

BUENA PRACTICA
Antes de cada experimento anota perfil, tiempo, modo, errores, correccion, facetas y calidad. Cambia una familia de variables por vez y guarda CSV con un nombre descriptivo.""",
            ),
            (
                "Problemas frecuentes",
                """NO PUEDO INICIAR
Busca campos rojos y abre Eventos y validaciones. Corrige formato numerico, limites o fecha/hora. Fecha simulada usa AAAA-MM-DD y HH:MM:SS.

LOS MOTORES MANUALES NO RESPONDEN
La sesion debe estar iniciada y en marcha. Selecciona Manual, activa el motor correspondiente, usa un PWM mayor que cero y comprueba que no este en un limite. Pulsa Detener al terminar.

EL HELIOSTATO NO SIGUE AL SOL
Selecciona Automatico, Seguimiento solar ON y motores ON. Revisa intervalo, cdr, limites y errores. CORREGIR AHORA debe registrar una solicitud en Eventos.

NO HAY IMPACTO O APARECE FUERA DE ESCALA
Comprueba que el Sol este sobre el horizonte, RX/RY/RZ, Target R a escala maqueta, unidades, diametro y escala del target. Un rayo paralelo o dirigido detras del plano receptor no tiene impacto frontal valido.

REPLAY ESTA GRIS
Primero genera muestras y pausa. Replay no se inicia mientras la simulacion avanza. GUARDAR CSV tambien permanece gris hasta existir al menos una muestra.

AVANZAR O REINICIAR ESTA GRIS
Estas acciones solo existen para Fecha simulada, despues de iniciar y mientras esta pausada.

LA VISTA 3D PARECE DESPLAZADA
En vista Libre pulsa Restablecer vista libre. El boton derecho rota y el izquierdo desplaza. Cambiar la camara no modifica la geometria ni el impacto.

LA INTERFAZ VA LENTA
Selecciona Calidad Rapida, reduce resolucion del mapa, cantidad de facetas o limite de historial. La calidad cambia el dibujo, no la solucion fisica.

SPA/PVLIB NO DISPONIBLE
El simulador usa el respaldo indicado y lo registra como informacion. Para una comparacion cientifica, confirma en el status que metodo produjo cada resultado.

RESULTADOS INESPERADOS DESPUES DE CALIBRAR
Recarga Minihorno IER para volver a la referencia. En un diseno propio revisa metros contra milimetros, RZ relativo, zona UTC, offsets y escala maqueta. Activa errores uno por uno.""",
            ),
        )

        technical_sections = (
            (
                "Referencia: vision general",
                """PROPOSITO
Este programa es un gemelo digital didactico del heliostato y concentrador del mini horno solar. Simula geometria solar, orientacion, motores, errores, correcciones, facetas, rayos e intensidad. No controla hardware fisico, no abre puertos seriales y no usa GPIO.

FLUJO DE CALCULO
1. Fecha, hora, latitud y longitud determinan la posicion solar.
2. La posicion solar se transforma en el vector solar S.
3. RX, RY y RZ definen el vector hacia el target.
4. La bisectriz optica produce la normal ideal del heliostato.
5. Errores geometricos y mecanicos perturban la orden o la geometria.
6. El modelo de motores actualiza acimut, elevacion y encoder.
7. La ley de reflexion produce el rayo reflejado.
8. El rayo cruza el plano receptor y genera el error u/v/radial.
9. Las facetas generan rayos centrales y un mapa gaussiano de intensidad.
10. Historial, graficas, replay y CSV registran la evolucion.

CONVENCION GLOBAL
+x = oeste, -x = este, +y = sur, -y = norte, +z = cenit.
El acimut interno usa 0 deg al sur, +90 deg al oeste y -90 deg al este.""",
            ),
            (
                "Referencia: geometria optica",
                """VECTORES PRINCIPALES
Ŝ es el vector unitario desde el heliostato hacia el Sol.
T̂ es la direccion unitaria del target y R = (RX, RY, RZ).
dᵢ = −Ŝ es la direccion incidente sobre el espejo.

NORMAL IDEAL
FORMULA|N̂ = (Ŝ + T̂) / ‖Ŝ + T̂‖
La normal es la bisectriz que permite reflejar la radiacion solar hacia T.

LEY DE REFLEXION
FORMULA|dᵣ = dᵢ − 2(dᵢ · N̂)N̂
El programa comprueba el angulo de incidencia, el de reflexion y la diferencia entre dᵣ y T̂.

INTERSECCION CON EL RECEPTOR
El receptor es un plano que pasa por R y tiene normal nᵣ = R / ‖R‖.
FORMULA|P(λ) = O + λdᵣ
FORMULA|λ = ((R − O) · nᵣ) / (dᵣ · nᵣ)
Si el denominador es casi cero o λ ≤ 0, no hay impacto frontal valido.

COORDENADAS DEL IMPACTO
u es horizontal y positivo hacia el oeste.
v es vertical y positivo hacia el cenit.
FORMULA|eᵣ = √(u² + v²)
eᵣ es el error radial sobre el receptor.""",
            ),
            (
                "Referencia: Sol, reloj y motores",
                """METODOS SOLARES
D&B: aproximacion basada en la formulacion de Duffie-Beckman.
REDA: canal aproximado alternativo para comparacion.
SPA/PVLIB: usa pvlib.solarposition.spa_python cuando esta disponible; si falla, el programa informa el respaldo REDA.
La zona horaria UTC se calibra de forma independiente de la longitud. El perfil Minihorno IER usa UTC−6; D&B, REDA y SPA/PVLIB reciben la misma hora civil.

RELOJ
Antes de iniciar se elige de forma excluyente Tiempo real o Fecha simulada.
Tiempo real usa el reloj civil y la zona UTC del perfil.
Fecha simulada usa el instante introducido por el usuario y evoluciona con multiplicadores 1x, 10x, 60x, 120x y 600x.
El programa abre en Configuracion y no avanza hasta pulsar Iniciar. Durante una pausa de Fecha simulada puede avanzarse un paso o reiniciarse el tiempo. Volver a Configuracion desbloquea nuevamente el origen temporal.

CONTROL DE EJES
FORMULA|e = θobjetivo − θactual
Si |e| ≤ cdr o el motor esta apagado, INA = INB = 0.
FORMULA|ω = PWM · ωmáx
El paso angular se limita para no sobrepasar el objetivo ni los limites mecanicos.
FORMULA|encoder = redondear(θ · conteos/grado)
El peralte convierte entre la lectura mecanica de elevacion y la normal optica. Se suma al objetivo del encoder y se descuenta una vez al reconstruir la normal; no representa por si mismo un error de punteria.

SEGUIMIENTO
En Automatico, el switch Seguimiento solar permite actualizar el objetivo a intervalos de 1, 5, 10, 30 o 60 s solares, o solamente bajo orden manual. Los ejes recorren cada cambio gradualmente desde su posicion actual segun PWM y velocidad maxima.""",
            ),
            (
                "Referencia: errores y correccion",
                """ERRORES DISPONIBLES
Offsets de acimut/elevacion, desalineacion norte-sur, error de posicion del target o heliostato, error de peralte, backlash, diferencia subida/bajada y ruido aleatorio reproducible por semilla.

CASOS COMPARABLES
Ideal: geometria nominal sin perturbaciones.
Con error: aplica los errores habilitados.
Corregido: agrega compensaciones manuales y la estrategia dinamica activa.

ESTRATEGIAS DE DERIVA
Sin correccion; offset constante; dependencia lineal con el tiempo; polinomio:
FORMULA|c(t) = c₀ + c₁t + c₂t²
Tambien incluye correccion a partir del impacto observado y actualizacion periodica tipo camara.

CORRECCION DESDE IMPACTO
El error u/v se transforma en una correccion angular usando la distancia al target, ganancias AZ/EL y un paso maximo. Cada pulsacion ejecuta una actualizacion limitada, por lo que la convergencia puede observarse progresivamente.

Las graficas conservan el error sin corregir, el corregido y la compensacion AZ/EL para comparar el efecto real del algoritmo.""",
            ),
            (
                "Referencia: facetas e intensidad",
                """DISTRIBUCION DE FACETAS
Cuadradas: reticula compacta centrada.
Circulares y hexagonales: empaquetamiento triangular compacto por anillos.
El algoritmo admite cantidades arbitrarias y centra la distribucion resultante.

TRAZADO DE RAYOS
Cada faceta recibe el mismo haz incidente paralelo. Su normal se calcula para enviar el rayo central al foco. Una faceta inactiva no contribuye; una desalineacion horizontal o vertical desplaza su impacto.

MAPA APROXIMADO
Cada impacto aporta una gaussiana eliptica:
FORMULA|I(u,v) = w · exp{−½[(a/σmayor)² + (b/σmenor)²]}
FORMULA|σmenor = σbase
FORMULA|σmayor = σbase / |cos(incidencia)|
Solo se evalua hasta 3.5 sigma para reducir calculo.

METRICAS
Centroide, error del centroide, intensidad maxima/total, sigma mayor/menor, orientacion, radio y diametro equivalentes. La forma se clasifica como circular, eliptica o alargada a partir de la razon entre sigmas.

La normalizacion puede fijar intensidad total = 1, pico = 1 o conservar los valores sin normalizar.""",
            ),
            (
                "Referencia: unidades y alcance",
                """UNIDADES DE ENTRADA
Todas las dimensiones de calibracion se introducen en metros fisicos completos. Los angulos se introducen en grados y las velocidades en grados por segundo.

Ejemplo del perfil Minihorno IER:
lado del espejo = 2.0 m; ancho de base = 1.9 m; altura de horquilla = 2.2 m; riel = 5.5 m; diametro de receptor = 1.6 m; distancia focal de facetas = 2.5 m.

RX, RY y RZ son coordenadas relativas al centro optico del espejo. Por ello RZ = -0.40 m coloca el centro del concentrador 0.40 m por debajo del centro del heliostato, no 0.40 m por debajo del suelo.

La vista 3D ajusta automaticamente su escala de pantalla. Cambiar el zoom visual no cambia las medidas ni las ecuaciones.

La opcion Target R a escala maqueta aplica el factor historico 0.0844 solamente a RX/RY/RZ para reproducir experimentos anteriores del modelo reducido. Debe permanecer apagada cuando se trabaja enteramente en dimensiones reales.

RENDIMIENTO
Rapida limita el dibujo aproximadamente a 5 FPS; Equilibrada a 12.5 FPS; Alta dibuja en cada ciclo. Estas opciones no modifican la fisica. Facetas y mapa de intensidad usan cache mientras no cambie la geometria.

LIMITACIONES
El dibujo 3D es una proyeccion ortografica ligera, no un CAD ni un trazador de rayos de alta fidelidad. El spot es un modelo gaussiano aproximado. Los motores, encoders y camara son simulados. Los resultados deben validarse experimentalmente antes de usarse para decisiones de diseno o seguridad.""",
            ),
        )
        sections = user_sections + technical_sections
        body = ttk.Frame(window, style="Panel.TFrame")
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        navigation = tk.Frame(body, bg="#e5edf2", bd=1, relief="solid")
        navigation.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        navigation.rowconfigure(1, weight=1)
        navigation.columnconfigure(0, weight=1)
        tk.Label(
            navigation,
            text="CONTENIDO DEL MANUAL",
            bg="#172432",
            fg="#f4d35e",
            anchor="w",
            padx=10,
            pady=9,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew")
        section_list = tk.Listbox(
            navigation,
            width=32,
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
            bg="#e5edf2",
            fg="#172432",
            selectbackground="#178ca4",
            selectforeground="#ffffff",
            font=("Segoe UI", 9),
        )
        section_scroll = ttk.Scrollbar(navigation, orient="vertical", command=section_list.yview)
        section_list.configure(yscrollcommand=section_scroll.set)
        section_list.grid(row=1, column=0, sticky="nsew", padx=(0, 1), pady=1)
        section_scroll.grid(row=1, column=1, sticky="ns", pady=1)

        article = ttk.Frame(body, style="Panel.TFrame")
        article.grid(row=0, column=1, sticky="nsew")
        article.rowconfigure(1, weight=1)
        article.columnconfigure(0, weight=1)
        page_title = tk.Label(
            article,
            text="",
            bg="#0f4c5c",
            fg="#ffffff",
            anchor="w",
            padx=14,
            pady=9,
            font=("Segoe UI", 13, "bold"),
        )
        page_title.grid(row=0, column=0, columnspan=2, sticky="ew")
        text = tk.Text(
            article,
            wrap="word",
            bg="#f7f7f7",
            fg="#222222",
            padx=20,
            pady=16,
            font=("Segoe UI", 10),
            spacing1=2,
            spacing3=5,
            cursor="arrow",
        )
        scroll = ttk.Scrollbar(article, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        text.tag_configure(
            "heading",
            foreground="#0f4c5c",
            font=("Segoe UI", 11, "bold"),
            spacing1=10,
            spacing3=4,
        )
        formula_width = max(430, min(760, width - 390))

        def show_section(index: int) -> None:
            """Carga una pagina del manual sin crear docenas de pestanas."""
            if not 0 <= index < len(sections):
                return
            title, content = sections[index]
            page_title.configure(text=title.upper())
            text.configure(state="normal")
            for child in text.winfo_children():
                child.destroy()
            text.delete("1.0", "end")
            for line in content.splitlines():
                if line.startswith("FORMULA|"):
                    formula = line[len("FORMULA|"):]
                    card = self.create_formula_card(text, formula, formula_width)
                    text.window_create("end", window=card, padx=18, pady=5)
                    text.insert("end", "\n")
                    continue
                tag = None
                if line and line.upper() == line and any(character.isalpha() for character in line):
                    tag = "heading"
                text.insert("end", f"{line}\n", tag)
            text.configure(state="disabled")
            text.yview_moveto(0.0)

        for title, _content in sections:
            section_list.insert("end", title)
        section_list.bind(
            "<<ListboxSelect>>",
            lambda _event: show_section(section_list.curselection()[0])
            if section_list.curselection()
            else None,
        )
        section_list.selection_set(0)
        section_list.activate(0)
        show_section(0)

    @staticmethod
    def replace_readonly_text(widget: tk.Text, value: str) -> None:
        """Actualiza un Text de solo lectura evitando escrituras innecesarias."""
        current = widget.get("1.0", "end-1c")
        if current == value:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def update_events_panel(self) -> None:
        """Sincroniza el panel inferior con status, alertas y bitacora."""
        status_label, _status_color, status_detail = self.system_status()
        alerts = self.alert_items()
        if alerts:
            validation_lines = [
                f"{severity.upper()}: {message}" for severity, message in alerts
            ]
        else:
            validation_lines = ["SIN ALERTAS ACTIVAS"]
        validation_text = (
            f"ESTADO: {status_label}\n{status_detail}\n\n"
            + "\n".join(validation_lines)
        )
        event_text = "\n".join(list(self.event_log)[-80:]) or "Sin eventos registrados"
        self.replace_readonly_text(self.validation_text, validation_text)
        self.replace_readonly_text(self.event_text, event_text)

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
        if self.invalid_control_text:
            messages.append(("critica", self.invalid_control_text))
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
        elif self.replay_active:
            label, color = "REPLAY", "#9a6700"
        elif not self.session_started:
            label, color = "CONFIGURACION", "#245a7a"
        elif not s.running:
            label, color = "PAUSADO", "#9f1239"
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
            f"Tiempo {self.vars['time_mode_choice'].get()}",
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

    def show_action_hint(self, text: str) -> None:
        """Muestra una explicacion breve al pasar el cursor por una accion."""
        self.action_hint_active = True
        if hasattr(self, "action_context_label"):
            self.action_context_label.configure(text=text)

    def clear_action_hint(self, _event: tk.Event | None = None) -> None:
        """Recupera el resumen de estado al abandonar un boton."""
        self.action_hint_active = False
        self.update_action_panel()

    def update_action_panel(self) -> None:
        """Sincroniza textos, colores y disponibilidad del panel de operacion."""
        if not hasattr(self, "operation_state_label"):
            return
        sample_count = len(self.samples)
        time_mode = str(self.vars["time_mode_choice"].get())
        if self.replay_active:
            state_text = "REPRODUCIENDO SESION"
            state_color = "#9a6700"
            context = f"Replay ciclico: {sample_count} muestras. La simulacion esta temporalmente sustituida."
        elif not self.session_started:
            state_text = "LISTO PARA CONFIGURAR"
            state_color = "#245a7a"
            context = f"Origen elegido: {time_mode}. Ajusta parametros y pulsa Iniciar."
        elif self.state.running:
            state_text = "SIMULACION EN CURSO"
            state_color = "#16834f"
            context = (
                f"{time_mode}; {sample_count} muestras disponibles."
                if sample_count
                else f"{time_mode}; esperando muestras de la sesion."
            )
        else:
            state_text = "SIMULACION PAUSADA"
            state_color = "#9f1239"
            context = f"Estado congelado; {sample_count} muestras disponibles."
        self.operation_state_label.configure(text=state_text, bg=state_color)
        if not getattr(self, "action_hint_active", False):
            self.action_context_label.configure(text=context)

        if not self.session_started:
            run_text = "INICIAR TIEMPO REAL" if time_mode == "Tiempo real" else "INICIAR FECHA SIMULADA"
            run_style = "ResumeAction.TButton"
        elif self.state.running:
            run_text = "PAUSAR SIMULACION"
            run_style = "PauseAction.TButton"
        else:
            run_text = "REANUDAR SIMULACION"
            run_style = "ResumeAction.TButton"
        self.run_button.configure(text=run_text, style=run_style)

        def set_enabled(button: ttk.Button, enabled: bool) -> None:
            button.state(["!disabled"] if enabled else ["disabled"])

        set_enabled(self.run_button, not self.replay_active)
        set_enabled(self.home_button, self.state.running and not self.replay_active)
        set_enabled(
            self.configure_session_button,
            self.session_started or self.replay_active,
        )
        set_enabled(
            self.replay_button,
            sample_count > 0 and not self.state.running and not self.replay_active,
        )
        set_enabled(self.live_button, self.replay_active)
        set_enabled(self.export_button, sample_count > 0)

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

    def request_drift_correction(self) -> None:
        """Solicita una actualizacion basada en el impacto observado."""
        self.apply_controls()
        if not self.state.correction_config.enabled:
            self.log_event("Activa Correccion de deriva antes de corregir")
            return
        if self.state.correction_config.strategy not in (
            "Impacto observado",
            "Camara periodica",
        ):
            self.log_event("El boton de impacto requiere estrategia observada o camara")
            return
        self.state.request_drift_correction()
        self.log_event("Correccion desde impacto solicitada")

    def reset_drift_correction(self) -> None:
        """Reinicia la compensacion y su historial de actualizaciones."""
        self.state.reset_drift_correction()
        self.log_event("Correccion de deriva reiniciada")

    def set_all_facets_active(self, active: bool) -> None:
        """Activa o desactiva todas las contribuciones configuradas."""
        self.apply_controls()
        self.state.facet_active_ids = (
            {f"F{index}" for index in range(1, self.state.facet_count + 1)}
            if active
            else set()
        )
        self.state.compute_geometry()
        self.log_event("Todas las facetas activadas" if active else "Todas las facetas desactivadas")

    def set_selected_facet_active(self, active: bool) -> None:
        """Cambia el estado de la faceta escrita en el campo de seleccion."""
        self.apply_controls()
        facet_id = self.state.facet_misaligned_id.strip().upper()
        valid_ids = {f"F{index}" for index in range(1, self.state.facet_count + 1)}
        if facet_id not in valid_ids:
            self.log_event(f"ID de faceta fuera de rango: {facet_id or '(vacio)'}")
            return
        if active:
            self.state.facet_active_ids.add(facet_id)
        else:
            self.state.facet_active_ids.discard(facet_id)
        self.state.compute_geometry()
        self.log_event(f"{facet_id} {'activada' if active else 'desactivada'}")

    def select_time_mode(self, mode: str) -> None:
        """Selecciona tiempo real o fecha simulada durante configuracion."""
        if self.session_started or self.replay_active:
            self.log_event("Vuelve a Configuracion para cambiar el origen del tiempo")
            return
        if mode not in ("Tiempo real", "Fecha simulada"):
            return
        self.vars["time_mode_choice"].set(mode)
        simulated = mode == "Fecha simulada"
        self.vars["specific_time"].set(simulated)
        self.vars["advance_solar_time"].set(False)
        self.state.use_live_time = not simulated
        self.state.advance_solar_time = False
        self.apply_controls()
        self.update_time_controls()
        self.update_action_panel()
        self.request_render()
        self.log_event(f"Origen temporal seleccionado: {mode}")

    def update_time_controls(self) -> None:
        """Habilita controles temporales segun modo y etapa de la sesion."""
        if not hasattr(self, "time_setup_status_label"):
            return
        mode = str(self.vars["time_mode_choice"].get())
        simulated = mode == "Fecha simulada"
        configuration_open = not self.session_started and not self.replay_active
        for key, button in self.time_mode_buttons.items():
            button.configure(style="ActiveMode.TButton" if key == mode else "Mode.TButton")
            button.state(["!disabled"] if configuration_open else ["disabled"])

        setup_enabled = simulated and configuration_open
        for widget in self.simulated_time_setup_widgets:
            try:
                widget.configure(state="normal" if setup_enabled else "disabled")
            except tk.TclError:
                pass
        paused_simulation = simulated and self.session_started and not self.state.running and not self.replay_active
        self.step_time_button.state(["!disabled"] if paused_simulation else ["disabled"])
        self.reset_time_button.state(["!disabled"] if paused_simulation else ["disabled"])

        if not configuration_open:
            status = f"{mode} bloqueado durante la ejecucion. Usa CONFIGURAR para cambiarlo."
        elif simulated:
            status = "Fecha simulada: configura fecha, hora y velocidad antes de iniciar."
        else:
            status = "Tiempo real: se usara el reloj civil y la zona UTC del perfil."
        self.time_setup_status_label.configure(text=status)

    def apply_initial_datetime(self) -> bool:
        """Aplica los campos de fecha/hora como nuevo origen de simulacion."""
        if self.session_started or self.replay_active:
            self.log_event("La fecha inicial solo puede cambiarse en Configuracion")
            return False
        if str(self.vars["time_mode_choice"].get()) != "Fecha simulada":
            self.log_event("Selecciona Fecha simulada antes de aplicar fecha y hora")
            return False
        date_text = str(self.vars["date_text"].get()).strip()
        time_text = str(self.vars["time_text"].get()).strip()
        try:
            when = _dt.datetime.fromisoformat(f"{date_text}T{time_text}")
        except ValueError:
            self.invalid_time_text = "Fecha/hora especifica invalida"
            self.log_event(self.invalid_time_text)
            return False
        self.vars["specific_time"].set(True)
        self.vars["advance_solar_time"].set(False)
        self.state.use_live_time = False
        self.state.advance_solar_time = False
        self.state.set_simulated_start_time(when)
        self.last_time_input = (date_text, time_text)
        self.last_specific_time_enabled = True
        self.invalid_time_text = ""
        self.log_event(f"Tiempo inicial aplicado: {when:%Y-%m-%d %H:%M:%S}")
        return True

    def reset_simulation_clock(self) -> None:
        """Reinicia el reloj en el origen definido y limpia su trayectoria."""
        self.apply_controls()
        if self.state.use_live_time:
            self.log_event("Reinicio de tiempo requiere el modo Fecha simulada")
            return
        if not self.session_started or self.state.running or self.replay_active:
            self.log_event("Reiniciar tiempo requiere una simulacion iniciada y pausada")
            return
        self.vars["advance_solar_time"].set(False)
        self.state.advance_solar_time = False
        self.state.reset_simulated_time()
        self.state.compute_geometry()
        self.log_event(f"Reloj reiniciado: {self.state.simulated_time:%Y-%m-%d %H:%M:%S}")

    def step_simulation_clock(self) -> None:
        """Pausa el reloj y ejecuta un avance manual de tamaño configurable."""
        self.apply_controls()
        if self.state.use_live_time:
            self.log_event("Avance por paso requiere el modo Fecha simulada")
            return
        if not self.session_started or self.state.running or self.replay_active:
            self.log_event("Avance por paso requiere una simulacion iniciada y pausada")
            return
        self.vars["advance_solar_time"].set(False)
        self.state.advance_solar_time = False
        advanced_s = self.state.step_simulated_time()
        self.state.compute_geometry()
        self.log_event(f"Paso de tiempo: +{advanced_s:g} s")

    def toggle_run(self) -> None:
        """Inicia, pausa o reanuda la sesion con el origen temporal elegido."""
        if self.replay_active:
            return
        started_now = False
        if not self.session_started:
            self.apply_controls()
            if self.invalid_control_text:
                self.log_event("No se puede iniciar: corrige los campos invalidos")
                return
            mode = str(self.vars["time_mode_choice"].get())
            if mode == "Fecha simulada" and not self.apply_initial_datetime():
                return
            self.session_started = True
            self.state.use_live_time = mode == "Tiempo real"
            self.state.running = True
            self.state.advance_solar_time = mode == "Fecha simulada"
            self.vars["advance_solar_time"].set(self.state.advance_solar_time)
            self.state.reset_tracking_schedule()
            self.last_tick = _dt.datetime.now()
            started_now = True
            self.log_event(f"Sesion iniciada con {mode.lower()}")
        else:
            self.state.running = not self.state.running
            if self.state.running and str(self.vars["time_mode_choice"].get()) == "Fecha simulada":
                self.state.advance_solar_time = True
                self.vars["advance_solar_time"].set(True)
        if not self.state.running:
            # Una pausa global tambien cancela cualquier orden manual que
            # pudiera seguir activa al mantener pulsado un control de jog.
            self.jog_command = None
            self.state.az.ina = self.state.az.inb = 0
            self.state.el.ina = self.state.el.inb = 0
            self.log_event("Simulacion pausada")
        elif not started_now:
            self.last_tick = _dt.datetime.now()
            self.log_event("Simulacion reanudada")
        self.update_time_controls()
        self.update_action_panel()

    def return_to_configuration(self) -> None:
        """Detiene la ejecucion y desbloquea la preparacion temporal."""
        self.replay_active = False
        self.replay_samples = []
        self.session_started = False
        self.state.running = False
        self.state.advance_solar_time = False
        self.vars["advance_solar_time"].set(False)
        self.jog_command = None
        self.state.az.ina = self.state.az.inb = 0
        self.state.el.ina = self.state.el.inb = 0
        self.state.invalidate_optical_cache()
        self.update_time_controls()
        self.update_action_panel()
        self.log_event("Configuracion habilitada; la sesion permanece detenida")

    def start_jog(self, axis: str, direction: int) -> None:
        """Inicia movimiento manual continuo en un eje."""
        if not self.session_started or not self.state.running or self.replay_active:
            self.log_event("Inicia la simulacion antes de mover los ejes manualmente")
            return
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
        invalid_controls = self.validate_numeric_entries()
        if invalid_controls:
            message = "Campos numericos invalidos: " + ", ".join(invalid_controls)
            if message != self.invalid_control_text:
                self.log_event(message)
            self.invalid_control_text = message
            self.request_render()
            return
        if self.invalid_control_text:
            self.log_event("Campos numericos validos restaurados")
            self.invalid_control_text = ""

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

        # Metodo solar y origen temporal. La interfaz presenta una eleccion
        # excluyente: Tiempo real o Fecha simulada.
        self.state.method = str(self.vars["method"].get())
        specific_time_enabled = str(self.vars["time_mode_choice"].get()) == "Fecha simulada"
        self.vars["specific_time"].set(specific_time_enabled)
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
            interval_text = interval_choice.lower().strip()
            if interval_text.endswith("s"):
                interval_text = interval_text[:-1].strip()
            interval_value = float(interval_text)
            self.state.configure_tracking_updates(interval_value)
        self.last_tracking_interval_choice = interval_choice

        config = self.state.error_config
        for var_name, var in self.vars.items():
            if not var_name.startswith("error_"):
                continue
            config_name = var_name[len("error_") :]
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

        correction_config = self.state.correction_config
        for var_name, var in self.vars.items():
            if not var_name.startswith("correction_"):
                continue
            config_name = var_name[len("correction_") :]
            if not hasattr(correction_config, config_name):
                continue
            try:
                value = var.get()
                current = getattr(correction_config, config_name)
                if isinstance(current, bool):
                    setattr(correction_config, config_name, bool(value))
                elif isinstance(current, str):
                    setattr(correction_config, config_name, str(value))
                else:
                    setattr(correction_config, config_name, float(value))
            except (tk.TclError, TypeError, ValueError):
                pass
        correction_config.image_max_step_deg = max(
            0.0, float(correction_config.image_max_step_deg)
        )
        correction_config.camera_interval_s = max(
            0.001, float(correction_config.camera_interval_s)
        )

        new_facet_count = max(1, min(int(self.state.facet_count), 61))
        self.set_normalized_entry_value("facet_count", new_facet_count)
        previous_facet_count = self.state._facet_previous_count
        if new_facet_count > previous_facet_count:
            self.state.facet_active_ids.update(
                f"F{index}" for index in range(previous_facet_count + 1, new_facet_count + 1)
            )
        valid_facet_ids = {f"F{index}" for index in range(1, new_facet_count + 1)}
        self.state.facet_active_ids.intersection_update(valid_facet_ids)
        self.state.facet_count = new_facet_count
        self.state._facet_previous_count = new_facet_count
        if self.state.facet_shape not in ("Cuadrada", "Circular", "Hexagonal"):
            self.state.facet_shape = "Cuadrada"
        self.state.facet_gap_m = max(0.0, float(self.state.facet_gap_m))
        self.state.facet_size_m = max(0.001, float(self.state.facet_size_m))
        self.state.facet_focal_distance_m = max(
            0.001, float(self.state.facet_focal_distance_m)
        )
        self.state.facet_misaligned_id = self.state.facet_misaligned_id.strip().upper() or "F1"

        self.state.spot_base_sigma_m = max(1e-5, float(self.state.spot_base_sigma_m))
        self.state.spot_map_half_size_m = max(
            0.001, float(self.state.spot_map_half_size_m)
        )
        spot_resolution = normalize_spot_resolution(self.state.spot_map_resolution)
        self.state.spot_map_resolution = spot_resolution
        self.set_normalized_entry_value("spot_map_resolution", spot_resolution)
        if self.state.spot_normalization not in (
            "Total = 1",
            "Pico = 1",
            "Sin normalizar",
        ):
            self.state.spot_normalization = "Total = 1"

        # Variables propias de cada eje: velocidad por PWM, motor ON/OFF,
        # limites, escala de conteo y velocidad maxima.
        self.state.az.pwm = float(self.vars["az_pwm"].get())
        self.state.el.pwm = float(self.vars["el_pwm"].get())
        self.state.az.motor_on = bool(self.vars["az_motor_on"].get())
        self.state.el.motor_on = bool(self.vars["el_motor_on"].get())
        az_limits = sorted(
            (
                float(self.vars["az_limit_min"].get()),
                float(self.vars["az_limit_max"].get()),
            )
        )
        el_limits = sorted(
            (
                float(self.vars["el_limit_min"].get()),
                float(self.vars["el_limit_max"].get()),
            )
        )
        self.state.az.limit_min, self.state.az.limit_max = az_limits
        self.state.el.limit_min, self.state.el.limit_max = el_limits
        self.set_normalized_entry_value("az_limit_min", self.state.az.limit_min)
        self.set_normalized_entry_value("az_limit_max", self.state.az.limit_max)
        self.set_normalized_entry_value("el_limit_min", self.state.el.limit_min)
        self.set_normalized_entry_value("el_limit_max", self.state.el.limit_max)
        self.state.az.counts_per_degree = max(1.0, float(self.vars["az_counts_per_degree"].get()))
        self.state.el.counts_per_degree = max(1.0, float(self.vars["el_counts_per_degree"].get()))
        self.state.az.deg_per_second_at_full_pwm = max(0.1, float(self.vars["az_deg_per_second"].get()))
        self.state.el.deg_per_second_at_full_pwm = max(0.1, float(self.vars["el_deg_per_second"].get()))
        self.state.az.angle_deg = clamp(self.state.az.angle_deg, self.state.az.limit_min, self.state.az.limit_max)
        self.state.el.angle_deg = clamp(self.state.el.angle_deg, self.state.el.limit_min, self.state.el.limit_max)
        self.state.az.counts = int(round(self.state.az.angle_deg * self.state.az.counts_per_degree))
        self.state.el.counts = int(round(self.state.el.angle_deg * self.state.el.counts_per_degree))

        # Saneamiento de parametros para evitar valores negativos o imposibles.
        self.state.lat_deg = clamp(float(self.state.lat_deg), -90.0, 90.0)
        self.state.lon_deg = clamp(float(self.state.lon_deg), -180.0, 180.0)
        self.state.utc_offset_hours = clamp(
            float(self.state.utc_offset_hours), -14.0, 14.0
        )
        self.set_normalized_entry_value("lat_deg", self.state.lat_deg)
        self.set_normalized_entry_value("lon_deg", self.state.lon_deg)
        self.set_normalized_entry_value(
            "utc_offset_hours", self.state.utc_offset_hours
        )
        self.state.cdr = max(0.0, float(self.state.cdr))
        self.state.delay_s = max(0.01, float(self.state.delay_s))
        scale_text = str(self.vars["time_scale_choice"].get()).strip().lower()
        if scale_text.endswith("x"):
            scale_text = scale_text[:-1].strip()
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
            "simulator_version": APP_VERSION,
            "timestamp": s.active_datetime().isoformat(timespec="seconds"),
            "initial_simulated_time": (
                s.initial_simulated_time.isoformat(timespec="seconds")
                if s.initial_simulated_time is not None
                else ""
            ),
            "simulation_clock_running": s.advance_solar_time,
            "simulation_time_scale": s.solar_time_scale,
            "simulation_step_s": s.simulation_step_s,
            "utc_offset_hours": s.utc_offset_hours,
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
            "drift_correction_enabled": s.correction_config.enabled,
            "drift_correction_strategy": s.correction_config.strategy,
            "drift_correction_az_deg": s.drift_correction_az_deg,
            "drift_correction_el_deg": s.drift_correction_el_deg,
            "drift_correction_count": s.correction_model.update_count,
            "drift_corrected": s.drift_corrected_this_step,
            "facet_field_enabled": s.facet_field_enabled,
            "facet_view_mode": s.facet_view_mode,
            "facet_shape": s.facet_shape,
            "facet_count": s.facet_count,
            "facet_size_m": s.facet_size_m,
            "facet_gap_m": s.facet_gap_m,
            "facet_focal_distance_m": s.facet_focal_distance_m,
            "facet_selected_id": s.facet_misaligned_id,
            "facet_active_ids": ",".join(sorted(s.facet_active_ids)),
            "facet_active_count": len(s.facet_ray_results),
            "facet_error_max_mm": s.facet_error_max_m * 1000.0,
            "facet_error_average_mm": s.facet_error_average_m * 1000.0,
            "facet_compute_ms": s.facet_compute_ms,
            "spot_map_enabled": s.spot_map_enabled,
            "spot_base_sigma_m": s.spot_base_sigma_m,
            "spot_map_half_size_m": s.spot_map_half_size_m,
            "spot_map_resolution": s.spot_map_resolution,
            "spot_normalization": s.spot_normalization,
            "spot_centroid_u_mm": s.spot_metrics.centroid_u_m * 1000.0,
            "spot_centroid_v_mm": s.spot_metrics.centroid_v_m * 1000.0,
            "spot_centroid_error_mm": s.spot_metrics.centroid_error_m * 1000.0,
            "spot_maximum_intensity": s.spot_metrics.maximum_intensity,
            "spot_total_intensity": s.spot_metrics.total_intensity,
            "spot_equivalent_diameter_mm": s.spot_metrics.equivalent_diameter_m * 1000.0,
            "spot_shape": s.spot_metrics.shape,
            "spot_compute_ms": s.spot_compute_ms,
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
        if (
            self.session_started
            and self.state.running
            and not self.replay_active
            and self.state.iterations > 0
        ):
            self.samples.append(self.snapshot())

    def apply_replay_sample(self, sample: dict[str, object]) -> None:
        """Carga una muestra grabada en el estado visible del gemelo."""
        s = self.state
        s.invalidate_optical_cache()
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
        s.correction_config.enabled = bool(
            sample.get("drift_correction_enabled", s.correction_config.enabled)
        )
        s.correction_config.strategy = str(
            sample.get("drift_correction_strategy", s.correction_config.strategy)
        )
        s.drift_correction_az_deg = float(
            sample.get("drift_correction_az_deg", s.drift_correction_az_deg)
        )
        s.drift_correction_el_deg = float(
            sample.get("drift_correction_el_deg", s.drift_correction_el_deg)
        )
        s.correction_model.correction_az_deg = s.drift_correction_az_deg
        s.correction_model.correction_el_deg = s.drift_correction_el_deg
        s.correction_model.update_count = int(
            sample.get("drift_correction_count", s.correction_model.update_count)
        )
        s.drift_corrected_this_step = bool(sample.get("drift_corrected", False))
        s.facet_field_enabled = bool(sample.get("facet_field_enabled", s.facet_field_enabled))
        s.facet_view_mode = str(sample.get("facet_view_mode", s.facet_view_mode))
        s.facet_shape = str(sample.get("facet_shape", s.facet_shape))
        s.facet_count = int(sample.get("facet_count", s.facet_count))
        s._facet_previous_count = s.facet_count
        s.facet_size_m = float(sample.get("facet_size_m", s.facet_size_m))
        s.facet_gap_m = float(sample.get("facet_gap_m", s.facet_gap_m))
        s.facet_focal_distance_m = float(
            sample.get("facet_focal_distance_m", s.facet_focal_distance_m)
        )
        s.facet_misaligned_id = str(sample.get("facet_selected_id", s.facet_misaligned_id))
        active_ids_text = str(sample.get("facet_active_ids", ""))
        if active_ids_text:
            s.facet_active_ids = {
                facet_id.strip() for facet_id in active_ids_text.split(",") if facet_id.strip()
            }
        s.facet_error_max_m = float(sample.get("facet_error_max_mm", 0.0)) / 1000.0
        s.facet_error_average_m = float(sample.get("facet_error_average_mm", 0.0)) / 1000.0
        s.facet_compute_ms = float(sample.get("facet_compute_ms", 0.0))
        s.spot_map_enabled = bool(sample.get("spot_map_enabled", s.spot_map_enabled))
        s.spot_base_sigma_m = float(sample.get("spot_base_sigma_m", s.spot_base_sigma_m))
        s.spot_map_half_size_m = float(
            sample.get("spot_map_half_size_m", s.spot_map_half_size_m)
        )
        s.spot_map_resolution = int(sample.get("spot_map_resolution", s.spot_map_resolution))
        s.spot_normalization = str(sample.get("spot_normalization", s.spot_normalization))
        s.spot_metrics = SpotMetrics(
            centroid_u_m=float(sample.get("spot_centroid_u_mm", 0.0)) / 1000.0,
            centroid_v_m=float(sample.get("spot_centroid_v_mm", 0.0)) / 1000.0,
            centroid_error_m=float(sample.get("spot_centroid_error_mm", 0.0)) / 1000.0,
            maximum_intensity=float(sample.get("spot_maximum_intensity", 0.0)),
            total_intensity=float(sample.get("spot_total_intensity", 0.0)),
            equivalent_diameter_m=float(sample.get("spot_equivalent_diameter_mm", 0.0)) / 1000.0,
            equivalent_radius_m=float(sample.get("spot_equivalent_diameter_mm", 0.0)) / 2000.0,
            shape=str(sample.get("spot_shape", "Sin spot")),
        )
        s.spot_compute_ms = float(sample.get("spot_compute_ms", 0.0))
        s.advance_solar_time = bool(sample.get("simulation_clock_running", s.advance_solar_time))
        s.solar_time_scale = float(sample.get("simulation_time_scale", s.solar_time_scale))
        s.simulation_step_s = float(sample.get("simulation_step_s", s.simulation_step_s))
        s.utc_offset_hours = float(sample.get("utc_offset_hours", s.utc_offset_hours))
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
        if self.state.running:
            self.log_event("Pausa la simulacion antes de reproducir el historial")
            return
        self.replay_active = True
        self.replay_index = 0
        self.replay_samples = list(self.samples)
        self.update_time_controls()
        self.update_action_panel()
        self.log_event(f"Replay iniciado con {len(self.samples)} muestras")

    def stop_replay(self) -> None:
        """Sale de replay y vuelve a simulacion viva."""
        if self.replay_active:
            self.log_event("Replay detenido; retorno a vivo")
        self.replay_active = False
        self.replay_samples = []
        self.state.invalidate_optical_cache()
        self.update_time_controls()
        self.update_action_panel()

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
        config = self.state.correction_config
        tolerance_status = (
            "EN TOLERANCIA"
            if math.isfinite(self.state.corrected_spot_radial)
            and self.state.corrected_spot_radial <= self.state.target_tolerance_m
            else "FUERA DE TOLERANCIA"
        )
        status = (
            f"{config.strategy} | AZ {self.state.drift_correction_az_deg:+.4f} deg | "
            f"EL {self.state.drift_correction_el_deg:+.4f} deg | "
            f"actualizaciones {self.state.correction_model.update_count} | {tolerance_status}"
        )
        self.correction_status_label.configure(text=status)
        if self.state.facet_field_enabled:
            facet_status = (
                f"{self.state.facet_shape} | activas {len(self.state.facet_ray_results)}/{self.state.facet_count} | "
                f"error max {self.state.facet_error_max_m * 1000.0:.3f} mm | "
                f"prom {self.state.facet_error_average_m * 1000.0:.3f} mm | "
                f"calculo {self.state.facet_compute_ms:.3f} ms | "
                f"cache {self.state.facet_cache_hits}"
            )
        else:
            facet_status = "Modelo de facetas desactivado"
        self.facet_status_label.configure(text=facet_status)
        if self.state.spot_map_enabled and self.state.spot_map_result is not None:
            metrics = self.state.spot_metrics
            spot_status = (
                f"Centroide {metrics.centroid_u_m * 1000.0:+.2f} / "
                f"{metrics.centroid_v_m * 1000.0:+.2f} mm | "
                f"diametro eq. {metrics.equivalent_diameter_m * 1000.0:.2f} mm | "
                f"{metrics.shape} | {self.state.spot_compute_ms:.2f} ms | "
                f"cache {self.state.spot_cache_hits}"
            )
        elif self.state.spot_map_enabled:
            spot_status = "Activa el concentrador y al menos una faceta"
        else:
            spot_status = "Mapa de intensidad desactivado"
        self.spot_status_label.configure(text=spot_status)
        self.update_events_panel()
        self.update_mode_visuals()

    def update_mode_visuals(self) -> None:
        """Resalta el modo activo y habilita/deshabilita controles manuales."""
        for key, button in self.mode_buttons.items():
            button.configure(style="ActiveMode.TButton" if key == self.current_mode else "Mode.TButton")
            button.configure(state="disabled" if self.replay_active else "normal")
        manual_state = (
            "normal"
            if self.current_mode == "manual"
            and self.session_started
            and self.state.running
            and not self.replay_active
            else "disabled"
        )
        for button in self.manual_controls:
            button.configure(state=manual_state)
        if hasattr(self, "tracking_correction_button"):
            tracking_ready = (
                self.session_started
                and self.state.running
                and not self.replay_active
                and self.current_mode == "auto"
                and self.state.tracking
            )
            self.tracking_correction_button.configure(
                state="normal" if tracking_ready else "disabled"
            )
        if hasattr(self, "drift_correction_button"):
            drift_ready = (
                self.session_started
                and self.state.running
                and not self.replay_active
                and self.state.correction_config.enabled
                and self.state.correction_config.strategy
                in ("Impacto observado", "Camara periodica")
            )
            self.drift_correction_button.configure(
                state="normal" if drift_ready else "disabled"
            )
            correction_present = (
                self.state.correction_model.update_count > 0
                or abs(self.state.drift_correction_az_deg) > 1e-12
                or abs(self.state.drift_correction_el_deg) > 1e-12
            )
            self.reset_drift_button.configure(
                state="normal" if correction_present and not self.replay_active else "disabled"
            )

    def set_render_quality(self, _selection: object = None) -> None:
        """Aplica el perfil grafico y solicita un dibujo inmediato."""
        quality = str(self.vars["render_quality"].get())
        if quality not in RENDER_QUALITY_INTERVALS_S:
            quality = "Equilibrada"
            self.vars["render_quality"].set(quality)
        self.request_render()
        self.log_event(f"Calidad grafica: {quality}")

    def reset_free_view(self) -> None:
        """Regresa la camara libre a su orientacion y encuadre iniciales."""
        self.free_view_yaw_deg = -38.0
        self.free_view_pitch_deg = 24.0
        self.free_view_pan_x_px = 0.0
        self.free_view_pan_y_px = 0.0
        self.free_view_drag_origin = None
        self.free_view_pan_drag_origin = None
        self.vars["view_mode"].set("Libre")
        self.request_render()
        self.log_event("Vista libre restablecida")

    def start_free_view_drag(self, event: tk.Event) -> None:
        """Inicia la rotacion libre con el boton derecho del mouse."""
        self.vars["view_mode"].set("Libre")
        self.free_view_drag_origin = (int(event.x), int(event.y))
        self.request_render()

    def drag_free_view(self, event: tk.Event) -> None:
        """Rota la camara libre en acimut y elevacion sin cambiar el modelo."""
        if self.free_view_drag_origin is None:
            return
        previous_x, previous_y = self.free_view_drag_origin
        delta_x = int(event.x) - previous_x
        delta_y = int(event.y) - previous_y
        self.free_view_yaw_deg = wrap_deg(self.free_view_yaw_deg + delta_x * 0.45)
        self.free_view_pitch_deg = clamp(
            self.free_view_pitch_deg - delta_y * 0.45,
            -89.0,
            89.0,
        )
        self.free_view_drag_origin = (int(event.x), int(event.y))
        self.request_render()

    def stop_free_view_drag(self, _event: tk.Event) -> None:
        """Finaliza la rotacion libre conservando el angulo alcanzado."""
        self.free_view_drag_origin = None

    def start_free_view_pan(self, event: tk.Event) -> None:
        """Inicia el desplazamiento de la escena con el boton izquierdo."""
        if str(self.vars["view_mode"].get()) != "Libre":
            return
        self.free_view_pan_drag_origin = (int(event.x), int(event.y))
        self.scene_canvas.configure(cursor="fleur")

    def drag_free_view_pan(self, event: tk.Event) -> None:
        """Desplaza el encuadre libre sin modificar la geometria simulada."""
        if self.free_view_pan_drag_origin is None:
            return
        previous_x, previous_y = self.free_view_pan_drag_origin
        delta_x = int(event.x) - previous_x
        delta_y = int(event.y) - previous_y
        width = max(1, self.scene_canvas.winfo_width())
        height = max(1, self.scene_canvas.winfo_height())
        self.free_view_pan_x_px = clamp(
            self.free_view_pan_x_px + delta_x,
            -width * 0.45,
            width * 0.45,
        )
        self.free_view_pan_y_px = clamp(
            self.free_view_pan_y_px + delta_y,
            -height * 0.45,
            height * 0.45,
        )
        self.free_view_pan_drag_origin = (int(event.x), int(event.y))
        self.request_render()

    def stop_free_view_pan(self, _event: tk.Event) -> None:
        """Finaliza el desplazamiento conservando el encuadre alcanzado."""
        self.free_view_pan_drag_origin = None
        self.scene_canvas.configure(cursor="")

    def request_render(self, _event: object = None) -> None:
        """Marca la vista activa para redibujarla en el siguiente ciclo."""
        self.render_pending = True

    def draw_active_view(self) -> str:
        """Dibuja exclusivamente la pestana visible y devuelve su nombre."""
        selected = self.notebook.select()
        if not selected:
            return "Sin vista"
        canvas = self.root.nametowidget(selected)
        drawer = self.view_drawers.get(canvas)
        if drawer is not None:
            drawer()
        return str(self.notebook.tab(selected, "text"))

    def performance_summary(self) -> str:
        """Resume costo del ciclo y frecuencia grafica sin alterar la fisica."""
        quality = str(self.vars["render_quality"].get())
        return (
            f"{quality} | {self.render_fps:4.1f} FPS | "
            f"ciclo {self.last_loop_duration_ms:5.1f} ms | "
            f"dibujo {self.last_render_duration_ms:5.1f} ms"
        )

    def loop(self) -> None:
        """Ciclo principal de la aplicacion.

        En cada iteracion:
        1. Calcula dt desde el ciclo anterior.
        2. Si hay replay, carga la siguiente muestra.
        3. Si esta en vivo, lee controles y avanza la simulacion.
        4. Registra la muestra y, cuando corresponde, redibuja la pestana activa.
        5. Programa el siguiente ciclo con root.after().
        """
        loop_started = time.perf_counter()
        now = _dt.datetime.now()
        dt = max(0.001, (now - self.last_tick).total_seconds())
        self.last_tick = now
        if self.replay_active and self.replay_samples:
            sample = self.replay_samples[self.replay_index]
            self.apply_replay_sample(sample)
            self.replay_index += 1
            if self.replay_index >= len(self.replay_samples):
                self.replay_index = 0
        else:
            self.apply_controls()
            if (
                self.session_started
                and self.state.running
                and self.jog_command
                and not self.state.automatic
            ):
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
            if not self.session_started:
                # En Configuracion se actualiza la vista previa geometrica,
                # pero no avanzan motores, historial ni reloj simulado.
                self.state.compute_geometry()
            else:
                self.state.update(dt, target_override=target_override)
        self.record_sample()
        render_now = time.perf_counter()
        quality = str(self.vars["render_quality"].get())
        render_interval_s = render_interval_for_quality(quality)
        if (
            self.render_pending
            or render_interval_s <= 0.0
            or render_now - self.last_render_time >= render_interval_s
        ):
            render_started = time.perf_counter()
            self.update_readouts()
            self.draw_active_view()
            self.sync_from_state()
            self.last_render_duration_ms = (time.perf_counter() - render_started) * 1000.0
            self.last_render_time = render_now
            self.render_pending = False
            self._rendered_frames += 1
            fps_elapsed = render_now - self._fps_window_started
            if fps_elapsed >= 0.5:
                self.render_fps = self._rendered_frames / fps_elapsed
                self._rendered_frames = 0
                self._fps_window_started = render_now
        self.last_loop_duration_ms = (time.perf_counter() - loop_started) * 1000.0
        delay_ms = int(max(20, self.state.delay_s * 1000.0))
        if not self.is_closing:
            self.loop_after_id = self.root.after(delay_ms, self.loop)

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
        active_time = self.active_datetime()
        if self.replay_active:
            lifecycle = "REPLAY"
        elif not self.session_started:
            lifecycle = "CONFIGURACION"
        elif s.running:
            lifecycle = "EN EJECUCION"
        else:
            lifecycle = "PAUSADO"
        if s.use_live_time:
            clock_text = (
                f"{lifecycle} | TIEMPO REAL | UTC{s.utc_offset_hours:+g} | "
                f"{active_time:%Y-%m-%d %H:%M:%S} | 1x"
            )
            persistent_mode = (
                f"{lifecycle} | TIEMPO REAL | UTC{s.utc_offset_hours:+g} | 1x"
            )
        else:
            clock_text = (
                f"{lifecycle} | FECHA SIMULADA | UTC{s.utc_offset_hours:+g} | "
                f"{active_time:%Y-%m-%d %H:%M:%S} | "
                f"{s.solar_time_scale:g}x"
            )
            persistent_mode = (
                f"{lifecycle} | FECHA SIMULADA | "
                f"UTC{s.utc_offset_hours:+g} | {s.solar_time_scale:g}x"
            )
        self.clock_status_label.configure(text=clock_text)
        self.persistent_date_label.configure(text=f"{active_time:%Y-%m-%d}")
        self.persistent_time_label.configure(text=f"{active_time:%H:%M:%S}")
        self.persistent_mode_label.configure(text=persistent_mode)
        self.update_time_controls()
        self.update_action_panel()
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
            "performance": self.performance_summary(),
        }
        for key, text in values.items():
            self.readouts[key].configure(text=text)

    def project(self, point: tuple[float, float, float], width: int, height: int, scale: float | None = None) -> tuple[float, float, float]:
        """Proyecta un punto 3D del modelo a coordenadas 2D de Canvas.

        No es un motor 3D real; es una proyeccion ortografica simple con vistas
        fijas y una camara libre. Devuelve tambien una profundidad y2 que podria
        usarse para ordenar objetos si se requiriera.
        """
        x, y, z = point
        if scale is None:
            scale = self.scene_projection_scale
        mode_var = self.vars.get("view_mode")
        mode = str(mode_var.get()) if mode_var else "Isometrica"
        if mode == "Libre":
            yaw, pitch = self.free_view_yaw_deg * DEG, self.free_view_pitch_deg * DEG
        elif mode == "Frontal":
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
        pan_x = self.free_view_pan_x_px if mode == "Libre" else 0.0
        pan_y = self.free_view_pan_y_px if mode == "Libre" else 0.0
        return width * 0.50 + pan_x + x1 * scale, height * 0.62 + pan_y - z2 * scale, y2

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
        - piso y leyenda de convencion este/oeste/sur/norte;
        - base, soporte central y espejo del heliostato;
        - concentrador abierto de 18 facetas sobre riel/mesa;
        - vector solar, normal, rayo reflejado y cono de tolerancia cdr;
        - etiquetas y recuadro de estado.
        """
        c = self.scene_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#101821", outline="", tags=("scene_background",))
        c.create_text(20, 20, anchor="w", text="Representacion 3D en tiempo real", fill="#e8eef8", font=("Segoe UI", 15, "bold"), tags=("scene_overlay",))
        c.create_text(20, 46, anchor="w", text="+x oeste, +y sur, +z cenit | sin control fisico", fill="#aeb9c8", font=("Segoe UI", 10), tags=("scene_overlay",))
        c.create_text(
            20,
            66,
            anchor="w",
            text="Vista libre: arrastre derecho = rotar | arrastre izquierdo = desplazar",
            fill="#8ce8f2" if str(self.vars["view_mode"].get()) == "Libre" else "#aeb9c8",
            font=("Segoe UI", 9, "bold"),
            tags=("scene_overlay",),
        )
        target = self.state.target_vector
        rail_extent = max(self.state.rail_length_m, abs(target[1]), 0.10)
        scene_extent = max(
            rail_extent,
            self.state.mirror_size_m,
            self.state.base_width_m,
            self.state.fork_height_m,
            self.state.receiver_screen_m,
            0.10,
        )
        self.scene_projection_scale = min(
            540.0,
            max(18.0, min(w * 0.54, h * 0.68) / scene_extent),
        )
        base_half = max(0.01, self.state.base_width_m / 2.0)
        base_depth = max(0.01, self.state.base_width_m * 0.58)
        center_z = max(0.01, self.state.fork_height_m)
        mirror_half = max(0.01, self.state.mirror_size_m / 2.0)

        # Rejilla del suelo dimensionada con la geometria fisica activa.
        ground_before = set(c.find_all())
        grid_half_width = max(self.state.base_width_m, self.state.receiver_screen_m) * 0.75
        grid_start_y = -rail_extent * 0.08
        grid_end_y = rail_extent * 1.05
        for index in range(9):
            grid_y = grid_start_y + (grid_end_y - grid_start_y) * index / 8.0
            self.line3d(c, (-grid_half_width, grid_y, -0.02), (grid_half_width, grid_y, -0.02), "#25384a", 1)
        for index in range(-4, 5):
            grid_x = grid_half_width * index / 4.0
            self.line3d(c, (grid_x, grid_start_y, -0.02), (grid_x, grid_end_y, -0.02), "#25384a", 1)

        if self.state.show_mechanical_guides:
            az_arc_radius = max(scene_extent * 0.07, base_half * 0.75)
            self.arc3d(c, (0, 0, -0.018), az_arc_radius, self.state.az.limit_min, self.state.az.limit_max, "#6f8aa8", 2)
            actual_radial = normal_from_angles(self.state.az.angle_deg, 0.0)
            target_radial = normal_from_angles(self.state.az.target_deg, 0.0)
            self.line3d(c, (0, 0, -0.016), v_mul(actual_radial, az_arc_radius * 1.04), "#f8d447", 2)
            self.line3d(c, (0, 0, -0.012), v_mul(target_radial, az_arc_radius * 0.92), "#ffffff", 2, dash=(4, 3))
        ground_items = sorted(set(c.find_all()) - ground_before)
        for item in ground_items:
            c.addtag_withtag("scene_ground", item)
        # La rejilla y las guias pertenecen siempre al plano inferior. Esta
        # capa explicita evita que una elevacion posterior de objetos 3D las
        # coloque accidentalmente sobre la estructura.
        c.tag_raise("scene_ground", "scene_background")

        # Base triangular/robusta inspirada en las fotos del mini horno.
        heliostat_before = set(c.find_all())
        # La base fisica es un bastidor, no una placa opaca. El contorno
        # conserva la referencia espacial sin crear un rectangulo gris.
        self.poly3d(c, [(-base_half, -base_depth, -0.02), (base_half, -base_depth, -0.02), (base_half * 1.15, base_depth, -0.02), (-base_half * 1.15, base_depth, -0.02)], "", "#718093")
        self.line3d(c, (0, 0, -0.02), (0, 0, center_z), "#9ea7b3", 5)
        self.line3d(c, (-base_half, -base_depth, -0.02), (0, 0, center_z), "#3c5874", 3)
        self.line3d(c, (base_half, -base_depth, -0.02), (0, 0, center_z), "#3c5874", 3)
        self.line3d(c, (0, base_depth, -0.02), (0, 0, center_z), "#3c5874", 3)
        if self.state.show_mechanical_guides:
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
        vector_legend: list[tuple[str, str]] = []
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
            normal_end = v_add(center, v_mul(n, mirror_half * 0.90))
            self.line3d(c, center, normal_end, "#f8d447", 3)
            vector_legend.append(("Normal N", "#f8d447"))
        if self.state.az.ina or self.state.az.inb:
            direction = "AZ +" if self.state.az.ina else "AZ -"
            c.create_text(24, 78, anchor="w", text=f"Movimiento {direction}", fill="#ffdf6e", font=("Segoe UI", 11, "bold"))
        if self.state.el.ina or self.state.el.inb:
            direction = "EL +" if self.state.el.ina else "EL -"
            c.create_text(24, 102, anchor="w", text=f"Movimiento {direction}", fill="#7fd3ff", font=("Segoe UI", 11, "bold"))
        heliostat_items = sorted(set(c.find_all()) - heliostat_before)

        # Target/concentrador. El vector R apunta del heliostato hacia este
        # punto, que por defecto queda hacia el sur (+y).
        target_before = set(c.find_all())
        receiver_radius = max(0.01, self.state.receiver_screen_m / 2.0)
        # R esta definido desde el centro optico del espejo. Para dibujarlo en
        # el mundo, donde el suelo es z=0, hay que trasladarlo por ``center``.
        target_center = v_add(center, target)
        self.scene_target_center = target_center
        rail_end = max(self.state.rail_length_m, target[1] + scene_extent * 0.02)
        self.line3d(c, (0, 0, -0.015), (0, rail_end, -0.015), "#d7d7d7", 4)
        t_unit = v_unit(target)
        sx = self.state.target_u_axis
        sz = self.state.target_v_axis
        ring_radius = receiver_radius
        table_z = -0.015
        table_y = target[1]
        table_half = ring_radius * 1.25
        self.poly3d(
            c,
            [
                (-table_half, table_y - ring_radius * 0.50, table_z),
                (table_half, table_y - ring_radius * 0.50, table_z),
                (table_half, table_y + ring_radius * 0.50, table_z),
                (-table_half, table_y + ring_radius * 0.50, table_z),
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
        for leg in (-ring_radius * 0.80, ring_radius * 0.80):
            base = (sx[0] * leg, table_y, table_z)
            top = v_add(target_center, v_mul(sx, leg * 0.7))
            self.line3d(c, base, top, "#8a8a8a", 3)
        target_items = sorted(set(c.find_all()) - target_before)

        # Orden de pintado segun profundidad de camara. Esto evita que el
        # concentrador aparezca artificialmente encima del heliostato al
        # rotar la vista libre hacia la parte posterior.
        helio_depth = self.project(center, w, h)[2]
        target_depth = self.project(target_center, w, h)[2]
        self.scene_front_group = choose_scene_front_group(
            helio_depth,
            target_depth,
            self.scene_front_group,
            hysteresis=max(0.005, scene_extent * 0.002),
        )
        front_items = heliostat_items if self.scene_front_group == "heliostat" else target_items
        # Los IDs de Canvas crecen en el mismo orden en que se pintaron. Al
        # elevarlos ordenados se conserva el apilado interno de poligonos y
        # lineas; iterar un set aqui producia parpadeo y cruces aleatorios.
        for item in sorted(front_items):
            c.tag_raise(item)

        # Vectores opticos con controles independientes para evitar saturacion.
        vector_length = max(mirror_half * 1.25, scene_extent * 0.10)
        sun_start = v_add(center, v_mul(self.state.sun_vector, vector_length))
        if self.state.show_sun_vector:
            self.line3d(c, sun_start, center, "#ff9f43", 3, dash=(5, 3))
            vector_legend.append(("Incidente -S", "#ffb765"))

        reflected_end = target_center
        if self.state.spot_valid:
            reflected_end = v_add(center, self.state.spot_point)
        elif all(math.isfinite(value) for value in self.state.reflected_direction):
            reflected_end = v_add(center, v_mul(self.state.reflected_direction, vector_length))
        if self.state.show_reflected_vector:
            self.line3d(c, center, reflected_end, "#fff06a", 4)
            vector_legend.append(("Reflejado", "#fff49b"))

        target_direction_end = v_add(center, v_mul(t_unit, vector_length))
        if self.state.show_target_direction:
            self.line3d(c, center, target_direction_end, "#58d6e7", 3)
            vector_legend.append(("Objetivo T", "#8ce8f2"))
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
        if vector_legend:
            # Las etiquetas en los extremos convergian sobre el espejo en
            # vistas laterales o ventanas pequenas. Una leyenda fija conserva
            # la relacion color-vector sin tapar la geometria.
            legend_right = w - 14
            legend_top = 48
            legend_left = max(10, legend_right - 142)
            legend_bottom = legend_top + 20 * len(vector_legend) + 8
            c.create_rectangle(
                legend_left,
                legend_top,
                legend_right,
                legend_bottom,
                fill="#142231",
                outline="#41566a",
                tags=("scene_overlay",),
            )
            for index, (label, color) in enumerate(vector_legend):
                label_y = legend_top + 15 + index * 20
                c.create_line(legend_left + 9, label_y, legend_left + 27, label_y, fill=color, width=3, tags=("scene_overlay",))
                c.create_text(
                    legend_left + 34,
                    label_y,
                    anchor="w",
                    text=label,
                    fill=color,
                    font=("Segoe UI", 8, "bold"),
                    tags=("scene_overlay",),
                )
        if all(math.isfinite(p) for p in self.state.spot_point):
            spot = v_add(center, self.state.spot_point)
            px, py, _ = self.project(spot, w, h)
            c.create_oval(px - 5, py - 5, px + 5, py + 5, fill="#ff3333", outline="#ffffff", width=1)

        # Indicador de ejes en una tarjeta fija. Sus vectores usan la misma
        # rotacion que la escena, por lo que explican la direccion visible de
        # norte/sur, este/oeste y cenit al mover la camara.
        orientation_left = 18
        orientation_top = max(92, h - 146)
        orientation_right = orientation_left + 292
        orientation_bottom = orientation_top + 128
        c.create_rectangle(
            orientation_left,
            orientation_top,
            orientation_right,
            orientation_bottom,
            fill="#142231",
            outline="#41566a",
            tags=("scene_overlay",),
        )
        c.create_text(
            orientation_left + 10,
            orientation_top + 13,
            anchor="w",
            text="ORIENTACION LOCAL  -  GIRA CON LA VISTA",
            fill="#e8eef8",
            font=("Segoe UI", 8, "bold"),
            tags=("scene_overlay",),
        )

        gizmo_scale = 40.0
        projected_origin = self.project((0.0, 0.0, 0.0), w, h, scale=gizmo_scale)
        gizmo_center_x = orientation_left + 76
        gizmo_center_y = orientation_top + 72
        axis_specs = (
            ("X", (1.0, 0.0, 0.0), "#ff8a8a"),
            ("Y", (0.0, 1.0, 0.0), "#8df0a5"),
            ("Z", (0.0, 0.0, 1.0), "#9bc2ff"),
        )
        for axis_name, axis_vector, color in axis_specs:
            projected_axis = self.project(axis_vector, w, h, scale=gizmo_scale)
            axis_dx = projected_axis[0] - projected_origin[0]
            axis_dy = projected_axis[1] - projected_origin[1]
            screen_length = math.hypot(axis_dx, axis_dy)
            if screen_length >= 7.0:
                negative_x = gizmo_center_x - axis_dx
                negative_y = gizmo_center_y - axis_dy
                positive_x = gizmo_center_x + axis_dx
                positive_y = gizmo_center_y + axis_dy
                c.create_line(
                    negative_x,
                    negative_y,
                    positive_x,
                    positive_y,
                    fill=color,
                    width=2,
                    arrow="both",
                    arrowshape=(7, 8, 3),
                    tags=("scene_overlay",),
                )
                c.create_text(
                    positive_x + axis_dx / screen_length * 8,
                    positive_y + axis_dy / screen_length * 8,
                    text=f"+{axis_name}",
                    fill=color,
                    font=("Consolas", 7, "bold"),
                    tags=("scene_overlay",),
                )
                c.create_text(
                    negative_x - axis_dx / screen_length * 8,
                    negative_y - axis_dy / screen_length * 8,
                    text=f"-{axis_name}",
                    fill=color,
                    font=("Consolas", 7, "bold"),
                    tags=("scene_overlay",),
                )
            else:
                # En una vista exactamente frontal un eje puede apuntar hacia
                # dentro/fuera de la pantalla. El circulo indica ese eje de
                # profundidad en vez de inventar una direccion 2D.
                marker_offset = {"X": -16, "Y": 0, "Z": 16}[axis_name]
                marker_x = gizmo_center_x + marker_offset
                c.create_oval(
                    marker_x - 5,
                    gizmo_center_y - 5,
                    marker_x + 5,
                    gizmo_center_y + 5,
                    outline=color,
                    width=2,
                    tags=("scene_overlay",),
                )
                c.create_text(
                    marker_x,
                    gizmo_center_y + 13,
                    text=axis_name,
                    fill=color,
                    font=("Consolas", 7, "bold"),
                    tags=("scene_overlay",),
                )
        c.create_oval(
            gizmo_center_x - 3,
            gizmo_center_y - 3,
            gizmo_center_x + 3,
            gizmo_center_y + 3,
            fill="#ffffff",
            outline="",
            tags=("scene_overlay",),
        )

        orientation_rows = (
            ("#ff8a8a", "X  + Oeste / - Este"),
            ("#8df0a5", "Y  + Sur / - Norte"),
            ("#9bc2ff", "Z  + Cenit / - Suelo"),
        )
        for row_index, (color, label) in enumerate(orientation_rows):
            row_y = orientation_top + 50 + row_index * 25
            c.create_line(
                orientation_left + 142,
                row_y,
                orientation_left + 160,
                row_y,
                fill=color,
                width=3,
                tags=("scene_overlay",),
            )
            c.create_text(
                orientation_left + 168,
                row_y,
                anchor="w",
                text=label,
                fill=color,
                font=("Consolas", 8, "bold"),
                tags=("scene_overlay",),
            )

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
        c.create_rectangle(w - 390, 18, w - 18, 172, fill="#172432", outline="#4f6f8d", tags=("scene_overlay",))
        c.create_rectangle(w - 390, 18, w - 18, 43, fill=status_color, outline="#4f6f8d", tags=("scene_overlay",))
        c.create_text(w - 374, 30, anchor="w", text=status_label, fill="#ffffff", font=("Segoe UI", 10, "bold"), tags=("scene_overlay",))
        c.create_text(w - 374, 54, anchor="nw", text=info, fill="#e8eef8", font=("Consolas", 10), tags=("scene_overlay",))
        c.create_text(w - 374, 152, anchor="w", text=status_detail[:68], fill="#b8c7d9", font=("Segoe UI", 9), tags=("scene_overlay",))
        c.tag_raise("scene_overlay")

    def draw_axes(
        self,
        c: tk.Canvas,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        title: str,
        y_label: str,
        x_label: str = "Muestras recientes: izquierda = antigua, derecha = actual",
    ) -> None:
        """Dibuja marco, titulo y nombres explicitos para ambos ejes."""
        c.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#999999")
        c.create_line(x0 + 45, y1 - 30, x1 - 15, y1 - 30, fill="#222222")
        c.create_line(x0 + 45, y0 + 15, x0 + 45, y1 - 30, fill="#222222")
        c.create_text(x0 + 12, y0 + 8, anchor="nw", text=title, fill="#111111", font=("Segoe UI", 11, "bold"))
        c.create_text(x0 + 8, (y0 + y1) / 2, text=y_label, angle=90, fill="#333333", font=("Segoe UI", 9))
        c.create_text((x0 + x1) / 2, y1 - 10, text=x_label, fill="#333333", font=("Segoe UI", 8))

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
        c.create_text(
            24,
            22,
            anchor="w",
            text="Pantalla / spot y comparacion de errores",
            fill="#111111",
            font=("Segoe UI", 15, "bold"),
        )
        panel_width = clamp(w * 0.31, 300.0, 380.0)
        panel_left = w - panel_width - 24.0
        graph_left = 72.0
        graph_right = panel_left - 28.0
        graph_top = 90.0
        graph_bottom = h - 48.0
        half_pixels = max(
            40.0,
            min((graph_right - graph_left) / 2.0, (graph_bottom - graph_top) / 2.0),
        )
        left, top = graph_left, graph_top
        right, bottom = left + 2.0 * half_pixels, top + 2.0 * half_pixels
        cx, cy = left + half_pixels, top + half_pixels
        half_range_m = max(0.001, self.state.target_scale_m)
        pixels_per_m = half_pixels / half_range_m
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
        c.create_text(left, top - 12, anchor="w", text="v [mm]  cenit +", fill="#333333", font=("Segoe UI", 9, "bold"))
        c.create_text(left, bottom + 30, anchor="w", text="cruz = centro nominal", fill="#6b7280", font=("Segoe UI", 8))

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
        # El centro nominal es una referencia geometrica, no el caso Ideal.
        # Se dibuja como cruz neutra para no confundirlo con el marcador verde.
        c.create_line(cx - 7, cy, cx + 7, cy, fill="#374151", width=2)
        c.create_line(cx, cy - 7, cx, cy + 7, fill="#374151", width=2)

        comparison_cases = (
            ("Ideal", self.state.ideal_spot_u, self.state.ideal_spot_v, self.state.ideal_spot_radial, "#16883f"),
            ("Con error", self.state.error_spot_u, self.state.error_spot_v, self.state.error_spot_radial, "#d62828"),
            ("Corregido", self.state.corrected_spot_u, self.state.corrected_spot_v, self.state.corrected_spot_radial, "#2563eb"),
        )
        legend_x = left
        legend_step = max(98.0, (right - left) / 3.0)
        for index, (label, u_m, v_m, _radial_m, color) in enumerate(comparison_cases):
            item_x = legend_x + index * legend_step
            c.create_oval(item_x, 54, item_x + 10, 64, fill=color, outline="#ffffff")
            c.create_text(item_x + 15, 59, anchor="w", text=label, fill=color, font=("Segoe UI", 8, "bold"))
            if math.isfinite(u_m) and math.isfinite(v_m):
                px = clamp(cx + u_m * pixels_per_m, left, right)
                py = clamp(cy - v_m * pixels_per_m, top, bottom)
                c.create_oval(px - 5, py - 5, px + 5, py + 5, fill=color, outline="#ffffff", width=1)

        outside_view = False
        if self.state.spot_valid:
            raw_x = cx + self.state.spot_error_u * pixels_per_m
            raw_y = cy - self.state.spot_error_v * pixels_per_m
            outside_view = not (left <= raw_x <= right and top <= raw_y <= bottom)
            marker_x = clamp(raw_x, left, right)
            marker_y = clamp(raw_y, top, bottom)
            active_case_color = {
                "Ideal": "#16883f",
                "Con error": "#d62828",
                "Corregido": "#2563eb",
            }.get(self.state.error_mode, "#374151")
            # Un aro identifica el caso activo sin recolorear el punto segun su
            # tolerancia; el estado de tolerancia ya se informa en el panel.
            c.create_oval(
                marker_x - 9,
                marker_y - 9,
                marker_x + 9,
                marker_y + 9,
                outline=active_case_color,
                width=3,
            )
            if outside_view:
                label_y = marker_y + 17 if raw_y < top else marker_y - 17
                label_x = clamp(marker_x, left + 54, right - 54)
                c.create_text(
                    label_x,
                    label_y,
                    text="fuera de escala",
                    fill="#9f1239",
                    font=("Segoe UI", 9, "bold"),
                )

        text_x = panel_left + 20
        panel_right = w - 24
        panel_top = 76.0
        panel_bottom = h - 20.0
        c.create_rectangle(panel_left, panel_top, panel_right, panel_bottom, fill="#ffffff", outline="#c7c7c7")
        c.create_text(text_x, panel_top + 23, anchor="w", text="Lectura actual", fill="#111111", font=("Segoe UI", 13, "bold"))
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
        c.create_text(text_x, panel_top + 50, anchor="nw", text=readout_lines, fill="#222222", font=("Consolas", 9))
        status_color = {
            "centrado": "#16883f",
            "aceptable": "#b7791f",
            "fuera de tolerancia": "#b91c1c",
            "sin impacto": "#6b7280",
        }.get(self.state.spot_status, "#6b7280")
        status_top = panel_top + 140
        c.create_rectangle(text_x, status_top, panel_right - 18, status_top + 30, fill=status_color, outline="")
        c.create_text(text_x + 10, status_top + 15, anchor="w", text=self.state.spot_status.upper(), fill="#ffffff", font=("Segoe UI", 10, "bold"))
        c.create_text(text_x, panel_top + 187, anchor="w", text="Comparacion sobre el target", fill="#111111", font=("Segoe UI", 12, "bold"))
        active_names = self.state.error_config.active_error_names()
        active_text = ", ".join(active_names) if active_names else "ninguno"
        c.create_text(
            text_x,
            panel_top + 211,
            anchor="w",
            text=f"Errores activos: {active_text[:74]}",
            fill="#444444",
            font=("Segoe UI", 9),
        )
        row_y = panel_top + 238
        row_step = min(62.0, max(32.0, (panel_bottom - row_y - 4.0) / 3.0))
        max_radial_mm = max(
            [radial_m * 1000.0 for _label, _u, _v, radial_m, _color in comparison_cases if math.isfinite(radial_m)]
            + [1.0]
        )
        for label, u_m, v_m, radial_m, color in comparison_cases:
            c.create_text(text_x, row_y, anchor="w", text=label, fill=color, font=("Segoe UI", 10, "bold"))
            if math.isfinite(radial_m):
                c.create_text(
                    text_x,
                    row_y + 17,
                    anchor="w",
                    text=f"u {u_m * 1000.0:+7.2f} | v {v_m * 1000.0:+7.2f} | r {radial_m * 1000.0:7.2f} mm",
                    fill="#222222",
                    font=("Consolas", 8),
                )
                if row_step >= 39.0:
                    bar_right = panel_right - 28
                    c.create_rectangle(text_x, row_y + 29, bar_right, row_y + 35, fill="#e5e7eb", outline="")
                    fill_right = text_x + (bar_right - text_x) * radial_m * 1000.0 / max_radial_mm
                    c.create_rectangle(text_x, row_y + 29, fill_right, row_y + 35, fill=color, outline="")
            else:
                c.create_text(text_x, row_y + 17, anchor="w", text="sin impacto", fill="#6b7280", font=("Consolas", 8))
            row_y += row_step
        if h > 560:
            c.create_text(
                text_x,
                h - 38,
                anchor="sw",
                text=(
                    f"Escala +/- {half_range_m * 1000.0:.0f} mm | "
                    f"tolerancia {self.state.target_tolerance_m * 1000.0:.1f} mm | "
                    "trayectoria roja"
                ),
                fill="#444444",
                font=("Segoe UI", 8),
            )

    def active_datetime(self) -> _dt.datetime:
        """Devuelve la fecha/hora que esta usando el gemelo en este instante."""
        return self.state.active_datetime()

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
        has_side_summary = w >= 900
        summary_width = 320 if has_side_summary else 0
        left, top = 72, 78
        right = w - summary_width - (66 if has_side_summary else 58)
        bottom = h - 92
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
            _zen, alt, az, _source = solar_position(
                sample_time,
                self.state.lat_deg,
                self.state.lon_deg,
                self.state.method,
                self.state.utc_offset_hours,
            )
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
            f"UTC del perfil: {self.state.utc_offset_hours:+g}\n"
            f"Metodo: {self.state.solar_source}\n"
            f"Altura: {self.state.altitude:6.2f} deg\n"
            f"Acimut lab: {self.state.solar_azimuth:6.2f} deg\n"
            f"Zenit: {self.state.zenith:6.2f} deg"
        )
        if has_side_summary:
            summary_left = right + 24
            c.create_rectangle(summary_left, 72, w - 24, 235, fill="#ffffff", outline="#bbbbbb")
            c.create_text(summary_left + 18, 90, anchor="nw", text=summary, fill="#222222", font=("Consolas", 10))
        else:
            compact_summary = (
                f"{when:%Y-%m-%d %H:%M:%S} | UTC {self.state.utc_offset_hours:+g} | "
                f"Alt {self.state.altitude:.2f} deg | Az {self.state.solar_azimuth:.2f} deg"
            )
            c.create_text(24, 51, anchor="w", text=compact_summary, fill="#374151", font=("Consolas", 8))
        if self.state.altitude <= 0:
            alert_left = right + 24 if has_side_summary else max(left, right - 230)
            alert_right = w - 24 if has_side_summary else right
            c.create_rectangle(alert_left, 247, alert_right, 294, fill="#fff1f2", outline="#fecdd3")
            c.create_text(alert_left + 16, 270, anchor="w", text="Sol bajo horizonte", fill="#9f1239", font=("Segoe UI", 11, "bold"))

    def _draw_drift_view_legacy(self) -> None:
        """Grafica la deriva del spot y el tiempo desde la ultima correccion."""
        c = self.drift_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        hist = list(self.state.history)
        tracking_text = "ACTIVO" if self.state.tracking else "DETENIDO / POSE FIJA"
        tracking_color = "#16883f" if self.state.tracking else "#b91c1c"
        c.create_text(24, 22, anchor="w", text="Deriva temporal y correccion del punto reflejado", fill="#111111", font=("Segoe UI", 15, "bold"))
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
                f"correcciones {self.state.tracking_update_count}   |   "
                f"estrategia {self.state.correction_config.strategy}"
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
        row_height = (bottom - top - 2 * gap) / 3.0
        boxes = tuple(
            (
                int(left if column == 0 else mid_x + gap / 2),
                int(top + row * (row_height + gap)),
                int(mid_x - gap / 2 if column == 0 else right),
                int(top + row * (row_height + gap) + row_height),
            )
            for row in range(3)
            for column in range(2)
        )
        titles = (
            "Error horizontal u vs tiempo",
            "Error vertical v vs tiempo",
            "Error radial vs tiempo",
            "Tiempo desde ultima actualizacion",
            "Error radial sin correccion / corregido",
            "Compensacion angular aplicada",
        )
        labels = (
            "Error u [mm]",
            "Error v [mm]",
            "Error radial [mm]",
            "Tiempo [s solares]",
            "Error radial [mm]",
            "Correccion [deg]",
        )
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

        for box, title, label, color, values in zip(boxes[:4], titles[:4], labels[:4], colors, series):
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

        def finite_history(key: str, scale: float = 1.0) -> list[float]:
            values: list[float] = []
            for sample in hist:
                value = float(sample.get(key, 0.0))
                values.append(value * scale if math.isfinite(value) else 0.0)
            return values

        without_mm = finite_history("error_spot_radial", 1000.0)
        corrected_mm = finite_history("corrected_spot_radial", 1000.0)
        correction_az = finite_history("drift_correction_az_deg")
        correction_el = finite_history("drift_correction_el_deg")
        comparison_box = boxes[4]
        angular_box = boxes[5]
        self.draw_axes(c, *comparison_box, titles[4], labels[4])
        radial_max = max(without_mm + corrected_mm + [1.0])
        self.plot_series(c, comparison_box, without_mm, "#d62828", 0.0, radial_max)
        self.plot_series(c, comparison_box, corrected_mm, "#2563eb", 0.0, radial_max)
        c.create_text(
            comparison_box[2] - 18,
            comparison_box[1] + 30,
            anchor="ne",
            text="rojo: sin correccion | azul: corregido",
            fill="#333333",
            font=("Segoe UI", 8, "bold"),
        )
        self.draw_axes(c, *angular_box, titles[5], labels[5])
        angular_extent = max([abs(value) for value in correction_az + correction_el] + [0.1])
        self.plot_series(c, angular_box, correction_az, "#7c3aed", -angular_extent, angular_extent)
        self.plot_series(c, angular_box, correction_el, "#0f766e", -angular_extent, angular_extent)
        c.create_text(
            angular_box[2] - 18,
            angular_box[1] + 30,
            anchor="ne",
            text="morado: AZ | verde: EL",
            fill="#333333",
            font=("Segoe UI", 8, "bold"),
        )

        # Marcas verticales doradas: instantes en que se capturo un nuevo target.
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

    def draw_drift_view(self) -> None:
        """Dibuja seis graficas de deriva o una sola ampliada al hacer clic."""
        c = self.drift_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        hist = list(self.state.history)
        tracking_text = "ACTIVO" if self.state.tracking else "DETENIDO / POSE FIJA"
        tracking_color = "#16883f" if self.state.tracking else "#b91c1c"
        c.create_text(24, 22, anchor="w", text="Deriva temporal y correccion del punto reflejado", fill="#111111", font=("Segoe UI", 15, "bold"))
        c.create_rectangle(24, 46, w - 24, 80, fill="#ffffff", outline="#c7c7c7")
        c.create_rectangle(24, 46, 245, 80, fill=tracking_color, outline="")
        c.create_text(38, 63, anchor="w", text=f"SEGUIMIENTO: {tracking_text}", fill="#ffffff", font=("Segoe UI", 10, "bold"))
        c.create_text(
            265,
            63,
            anchor="w",
            text=(
                f"Hora solar {self.active_datetime():%Y-%m-%d %H:%M:%S} | "
                f"intervalo {'Manual' if self.state.tracking_updates_manual else f'{self.state.tracking_update_interval_s:g} s'} | "
                f"desde actualizacion {self.state.seconds_since_tracking_update:.1f} s | "
                f"correcciones {self.state.tracking_update_count} | "
                f"estrategia {self.state.correction_config.strategy}"
            ),
            fill="#222222",
            font=("Consolas", 9),
        )
        titles = (
            "Error horizontal u vs tiempo",
            "Error vertical v vs tiempo",
            "Error radial vs tiempo",
            "Tiempo desde ultima actualizacion",
            "Error radial sin correccion / corregido",
            "Compensacion angular aplicada",
        )
        labels = (
            "Error u [mm]",
            "Error v [mm]",
            "Error radial [mm]",
            "Tiempo [s solares]",
            "Error radial [mm]",
            "Correccion [deg]",
        )
        if self.drift_expanded_index is None:
            gap, left, right, top, bottom = 18, 24, w - 24, 96, h - 28
            mid_x = (left + right) // 2
            row_height = (bottom - top - 2 * gap) / 3.0
            boxes = tuple(
                (
                    int(left if column == 0 else mid_x + gap / 2),
                    int(top + row * (row_height + gap)),
                    int(mid_x - gap / 2 if column == 0 else right),
                    int(top + row * (row_height + gap) + row_height),
                )
                for row in range(3)
                for column in range(2)
            )
            graph_indices = tuple(range(6))
            self.drift_back_box = None
            c.create_text(w - 30, 22, anchor="e", text="Haz clic en una grafica para ampliarla", fill="#475569", font=("Segoe UI", 9, "italic"))
        else:
            boxes = ((24, 96, w - 24, h - 28),)
            graph_indices = (self.drift_expanded_index,)
            self.drift_back_box = (w - 205, 12, w - 24, 40)
            c.create_rectangle(*self.drift_back_box, fill="#46566a", outline="#263445")
            c.create_text((self.drift_back_box[0] + self.drift_back_box[2]) / 2, 26, text="VOLVER A 6 GRAFICAS", fill="#ffffff", font=("Segoe UI", 9, "bold"))
        self.drift_graph_boxes = list(zip(graph_indices, boxes))

        def history_values(key: str, scale: float = 1.0, valid_only: bool = False) -> list[float]:
            values: list[float] = []
            for sample in hist:
                if valid_only and not sample.get("spot_valid", True):
                    continue
                value = float(sample.get(key, 0.0))
                if math.isfinite(value):
                    values.append(value * scale)
            return values

        primary_series = (
            history_values("err_u", 1000.0, True),
            history_values("err_v", 1000.0, True),
            history_values("err_radial", 1000.0, True),
            history_values("elapsed_since_tracking_update_s"),
        )
        without_mm = history_values("error_spot_radial", 1000.0)
        corrected_mm = history_values("corrected_spot_radial", 1000.0)
        correction_az = history_values("drift_correction_az_deg")
        correction_el = history_values("drift_correction_el_deg")
        colors = ("#2563eb", "#805ad5", "#c53030", "#16883f")

        for graph_index, box in self.drift_graph_boxes:
            self.draw_axes(c, *box, titles[graph_index], labels[graph_index])
            if graph_index < 4:
                values = primary_series[graph_index]
                if graph_index in (2, 3):
                    self.plot_series(c, box, values, colors[graph_index], 0.0, max(values + [1.0]))
                else:
                    extent = max([abs(value) for value in values] + [1.0])
                    self.plot_series(c, box, values, colors[graph_index], -extent, extent)
            elif graph_index == 4:
                upper = max(without_mm + corrected_mm + [1.0])
                self.plot_series(c, box, without_mm, "#d62828", 0.0, upper)
                self.plot_series(c, box, corrected_mm, "#2563eb", 0.0, upper)
                c.create_text(box[2] - 18, box[1] + 30, anchor="ne", text="rojo: sin correccion | azul: corregido", fill="#333333", font=("Segoe UI", 8, "bold"))
            else:
                extent = max([abs(value) for value in correction_az + correction_el] + [0.1])
                self.plot_series(c, box, correction_az, "#7c3aed", -extent, extent)
                self.plot_series(c, box, correction_el, "#0f766e", -extent, extent)
                c.create_text(box[2] - 18, box[1] + 30, anchor="ne", text="morado: AZ | verde: EL", fill="#333333", font=("Segoe UI", 8, "bold"))
            if graph_index == 2 and len(hist) >= 2:
                plot_left, plot_right = box[0] + 45, box[2] - 16
                plot_top, plot_bottom = box[1] + 18, box[3] - 30
                for sample_index, sample in enumerate(hist):
                    if sample.get("tracking_corrected", False):
                        marker_x = plot_left + (plot_right - plot_left) * sample_index / (len(hist) - 1)
                        c.create_line(marker_x, plot_top, marker_x, plot_bottom, fill="#d69e2e", width=1, dash=(3, 3))
                c.create_text(box[2] - 24, box[1] + 28, anchor="ne", text="dorado = correccion", fill="#9a6700", font=("Segoe UI", 8, "bold"))
            if hist:
                first_time = str(hist[0].get("solar_time", ""))[11:19]
                last_time = str(hist[-1].get("solar_time", ""))[11:19]
                c.create_text(box[0] + 48, box[3] - 13, anchor="w", text=first_time, fill="#666666", font=("Consolas", 8))
                c.create_text(box[2] - 18, box[3] - 13, anchor="e", text=last_time, fill="#666666", font=("Consolas", 8))
        if not hist:
            c.create_text(w / 2, h / 2, text="Sin muestras: inicia la simulacion para formar la trayectoria", fill="#6b7280", font=("Segoe UI", 13, "bold"))

    def handle_drift_click(self, event: tk.Event) -> None:
        """Amplia la grafica pulsada o vuelve a la cuadricula de seis."""
        if self.drift_expanded_index is not None:
            if self.drift_back_box is not None:
                x1, y1, x2, y2 = self.drift_back_box
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.drift_expanded_index = None
                    self.request_render()
            return
        for graph_index, (x1, y1, x2, y2) in self.drift_graph_boxes:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.drift_expanded_index = graph_index
                self.request_render()
                return

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
            f"Compensacion manual AZ/EL: {s.error_config.correction_azimuth_deg:+.4f} / {s.error_config.correction_elevation_deg:+.4f} deg\n"
            f"Correccion deriva AZ/EL: {s.drift_correction_az_deg:+.4f} / {s.drift_correction_el_deg:+.4f} deg"
        )
        c.create_text(panel_x, y + 8, anchor="nw", text=sample_text, fill="#222222", font=("Consolas", 10))

    def draw_correction_view(self) -> None:
        """Compara deriva sin/con correccion y grafica el comando aplicado."""
        c = self.correction_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        s = self.state
        c.create_text(
            24,
            22,
            anchor="w",
            text="Correccion progresiva de deriva",
            fill="#111111",
            font=("Segoe UI", 15, "bold"),
        )
        tolerance_status = (
            "EN TOLERANCIA"
            if math.isfinite(s.corrected_spot_radial)
            and s.corrected_spot_radial <= s.target_tolerance_m
            else "FUERA DE TOLERANCIA"
        )
        summary = (
            f"{s.correction_config.strategy} | AZ {s.drift_correction_az_deg:+.4f} deg | "
            f"EL {s.drift_correction_el_deg:+.4f} deg | "
            f"actualizaciones {s.correction_model.update_count} | {tolerance_status}"
        )
        c.create_text(24, 52, anchor="w", text=summary, fill="#333333", font=("Consolas", 10))
        top_box = (24, 82, w - 24, int(h * 0.52))
        bottom_box = (24, int(h * 0.57), w - 24, h - 34)
        self.draw_axes(c, *top_box, "Error radial: sin correccion vs corregido", "Error radial [mm]")
        self.draw_axes(c, *bottom_box, "Compensacion angular aplicada", "Correccion [deg]")

        hist = list(s.history)
        if not hist:
            c.create_text(
                w / 2,
                h / 2,
                text="Sin muestras: inicia la simulacion para comparar",
                fill="#6b7280",
                font=("Segoe UI", 12, "bold"),
            )
            return

        def finite_value(sample: dict[str, object], key: str) -> float:
            value = float(sample.get(key, 0.0))
            return value if math.isfinite(value) else 0.0

        without_mm = [finite_value(sample, "error_spot_radial") * 1000.0 for sample in hist]
        corrected_mm = [finite_value(sample, "corrected_spot_radial") * 1000.0 for sample in hist]
        correction_az = [finite_value(sample, "drift_correction_az_deg") for sample in hist]
        correction_el = [finite_value(sample, "drift_correction_el_deg") for sample in hist]
        radial_max = max(without_mm + corrected_mm + [1.0])
        angular_extent = max([abs(value) for value in correction_az + correction_el] + [0.1])
        self.plot_series(c, top_box, without_mm, "#d62828", 0.0, radial_max)
        self.plot_series(c, top_box, corrected_mm, "#2563eb", 0.0, radial_max)
        self.plot_series(c, bottom_box, correction_az, "#7c3aed", -angular_extent, angular_extent)
        self.plot_series(c, bottom_box, correction_el, "#0f766e", -angular_extent, angular_extent)
        c.create_text(w - 42, 100, anchor="ne", text="rojo: sin correccion   azul: corregido", fill="#333333", font=("Segoe UI", 9, "bold"))
        c.create_text(w - 42, bottom_box[1] + 18, anchor="ne", text="morado: AZ   verde: EL", fill="#333333", font=("Segoe UI", 9, "bold"))

        if len(hist) >= 2:
            left = top_box[0] + 45
            right = top_box[2] - 16
            top = top_box[1] + 18
            bottom = top_box[3] - 30
            for idx, sample in enumerate(hist):
                if bool(sample.get("drift_corrected", False)):
                    x = left + (right - left) * idx / (len(hist) - 1)
                    c.create_line(x, top, x, bottom, fill="#d69e2e", width=1, dash=(3, 3))

    def draw_facet_view(self) -> None:
        """Dibuja facetas, rayos centrales e impactos sobre el receptor."""
        c = self.facet_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#f4f4f4", outline="")
        s = self.state
        c.create_text(
            24,
            22,
            anchor="w",
            text="Facetas: geometria, rayos, foco e intensidad",
            fill="#111111",
            font=("Segoe UI", 15, "bold"),
        )
        summary = (
            f"{s.facet_shape} | activas {len(s.facet_ray_results)}/{s.facet_count} | foco {s.facet_focal_distance_m:.3f} m | "
            f"error max {s.facet_error_max_m * 1000.0:.3f} mm | "
            f"calculo {s.facet_compute_ms:.3f} ms"
        )
        c.create_text(24, 52, anchor="w", text=summary, fill="#333333", font=("Consolas", 10))
        self.facet_back_box = None
        if self.facet_expanded_panel is None:
            c.create_text(w - 28, 22, anchor="e", text="Haz clic en un panel para ampliarlo", fill="#475569", font=("Segoe UI", 9, "italic"))
        else:
            self.facet_back_box = (w - 205, 12, w - 24, 40)
            c.create_rectangle(*self.facet_back_box, fill="#46566a", outline="#263445")
            c.create_text((self.facet_back_box[0] + self.facet_back_box[2]) / 2, 26, text="VOLVER A VISTA GENERAL", fill="#ffffff", font=("Segoe UI", 9, "bold"))
        if not s.facet_field_enabled:
            c.create_text(
                w / 2,
                h / 2,
                text="Activa 'Concentrador facetado' para calcular la distribucion seleccionada",
                fill="#6b7280",
                font=("Segoe UI", 13, "bold"),
            )
            return

        if self.facet_expanded_panel == "receiver":
            panel = (24, 82, w - 24, h - 28)
            self.facet_panel_boxes = {"receiver": panel}
            self.draw_facet_receiver_expanded(c, panel)
            return
        if self.facet_expanded_panel == "schematic":
            schematic = (24, 82, w - 24, h - 28)
            receiver = (0, 0, 0, 0)
            self.facet_panel_boxes = {"schematic": schematic}
        else:
            schematic = (24, 82, int(w * 0.48), int(h * 0.60))
            receiver = (int(w * 0.52), 82, w - 24, int(h * 0.60))
            self.facet_panel_boxes = {"schematic": schematic, "receiver": receiver}
        c.create_rectangle(*schematic, fill="#101821", outline="#718096")
        c.create_text(schematic[0] + 12, schematic[1] + 10, anchor="nw", text=f"Esquema: {s.facet_view_mode}", fill="#ffffff", font=("Segoe UI", 11, "bold"))
        if self.facet_expanded_panel is None:
            c.create_rectangle(*receiver, fill="#fffdf5", outline="#8a7b58", width=2)
            receiver_title = "Plano receptor / foco"
            if s.spot_map_enabled and s.spot_map_result is not None:
                receiver_title += " + mapa de intensidad"
            c.create_text(receiver[0] + 12, receiver[1] + 10, anchor="nw", text=receiver_title, fill="#111111", font=("Segoe UI", 11, "bold"))

        result_by_id = {result.facet_id: result for result in s.facet_ray_results}
        mirror_normal = s.actual_normal
        if v_norm(mirror_normal) < 1e-9:
            mirror_normal = normal_from_angles(s.az.angle_deg, s.el.angle_deg - s.peralte)
        mirror_normal = v_unit(mirror_normal)
        mirror_u = v_cross((0.0, 0.0, 1.0), mirror_normal)
        if v_norm(mirror_u) < 1e-9:
            mirror_u = (1.0, 0.0, 0.0)
        mirror_u = v_unit(mirror_u)
        mirror_v = v_unit(v_cross(mirror_normal, mirror_u))
        mirror_half = max(0.025, s.mirror_size_m / 2.0)

        def draw_facet_shape(
            center_x: float,
            center_y: float,
            radius_px: float,
            shape: str,
            fill: str,
        ) -> None:
            radius_px = clamp(radius_px, 3.0, 11.0)
            if shape == "Circular":
                c.create_oval(
                    center_x - radius_px,
                    center_y - radius_px,
                    center_x + radius_px,
                    center_y + radius_px,
                    fill=fill,
                    outline="#ffffff",
                )
            elif shape == "Hexagonal":
                points: list[float] = []
                for vertex in range(6):
                    angle = math.radians(-90.0 + vertex * 60.0)
                    points.extend(
                        [
                            center_x + radius_px * math.cos(angle),
                            center_y + radius_px * math.sin(angle),
                        ]
                    )
                c.create_polygon(*points, fill=fill, outline="#ffffff")
            else:
                c.create_rectangle(
                    center_x - radius_px,
                    center_y - radius_px,
                    center_x + radius_px,
                    center_y + radius_px,
                    fill=fill,
                    outline="#ffffff",
                )

        if s.facet_view_mode == "Resumen":
            helio_x = schematic[0] + 58
            axis_y = (schematic[1] + schematic[3]) / 2.0
            concentrator_x = schematic[2] - 58
            focus_x = concentrator_x - (concentrator_x - helio_x) * 0.36
            max_layout_extent = max(
                [
                    max(abs(facet.layout_u_m), abs(facet.layout_v_m))
                    for facet in s.facets
                ]
                + [s.facet_size_m]
            )
            layout_scale = min(900.0, 72.0 / max(1e-6, max_layout_extent))
            facet_radius = s.facet_size_m * layout_scale * 0.45
            target_axis = v_unit(s.target_vector)
            normal_axis_component = v_dot(mirror_normal, target_axis)
            normal_vertical_component = mirror_normal[2]
            mirror_direction_x = -normal_vertical_component
            mirror_direction_y = -normal_axis_component
            mirror_direction_norm = max(
                1e-9,
                math.hypot(mirror_direction_x, mirror_direction_y),
            )
            mirror_direction_x /= mirror_direction_norm
            mirror_direction_y /= mirror_direction_norm
            mirror_display_half = 62.0
            mirror_screen_normal_x = -mirror_direction_y
            mirror_screen_normal_y = mirror_direction_x
            mirror_polygon = []
            for along, across in (
                (-mirror_display_half, -6.0),
                (mirror_display_half, -6.0),
                (mirror_display_half, 6.0),
                (-mirror_display_half, 6.0),
            ):
                mirror_polygon.extend(
                    [
                        helio_x + mirror_direction_x * along + mirror_screen_normal_x * across,
                        axis_y + mirror_direction_y * along + mirror_screen_normal_y * across,
                    ]
                )
            c.create_polygon(*mirror_polygon, fill="#b8d8ff", outline="#ffffff", width=2)
            c.create_line(helio_x, axis_y + 5, helio_x, axis_y + 84, fill="#94a3b8", width=3)
            c.create_line(helio_x - 15, axis_y + 84, helio_x + 15, axis_y + 84, fill="#94a3b8", width=3)
            c.create_text(
                helio_x,
                axis_y + 101,
                text=f"Heliostato  AZ {s.az.angle_deg:.1f} / EL {s.el.angle_deg:.1f}",
                fill="#dbeafe",
                font=("Segoe UI", 8, "bold"),
            )
            for fraction in (-0.72, -0.36, 0.0, 0.36, 0.72):
                ray_start_x = helio_x + mirror_direction_x * mirror_display_half * fraction
                ray_start_y = axis_y + mirror_direction_y * mirror_display_half * fraction
                c.create_line(
                    ray_start_x,
                    ray_start_y,
                    ray_start_x + 56.0,
                    ray_start_y,
                    fill="#ffb454",
                    width=2,
                    arrow="last",
                )
            c.create_line(helio_x, axis_y, concentrator_x, axis_y, fill="#64748b", dash=(4, 4))
            c.create_line(focus_x, axis_y - 55, focus_x, axis_y + 55, fill="#58d6e7", width=2)
            c.create_text(focus_x, axis_y - 66, text="Receptor", fill="#8ce8f2", font=("Segoe UI", 9, "bold"))
            for facet in s.facets:
                facet_y = axis_y - facet.layout_v_m * layout_scale
                facet_x = concentrator_x + facet.layout_u_m * layout_scale
                color = "#d6b95f" if facet.active else "#5f6570"
                draw_facet_shape(facet_x, facet_y, facet_radius, facet.shape, color)
                if s.facet_count <= 18 or facet.id == s.facet_misaligned_id:
                    c.create_text(facet_x + 9, facet_y, anchor="w", text=facet.id, fill="#ffffff", font=("Consolas", 8))
                if not facet.active:
                    continue
                result = result_by_id.get(facet.id)
                ray_color = "#66d9ef" if result and math.isfinite(result.focus_error_m) else "#ef4444"
                impact_y = axis_y
                if result and math.isfinite(result.impact_v_m):
                    impact_y -= clamp(result.impact_v_m * 1200.0, -55.0, 55.0)
                c.create_line(facet_x, facet_y, focus_x, impact_y, fill=ray_color, width=1)
        else:
            mirror_corners = [
                v_add(v_mul(mirror_u, sign_u * mirror_half), v_mul(mirror_v, sign_v * mirror_half))
                for sign_u, sign_v in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
            ]
            world_points = [s.facet_focus, *mirror_corners]
            world_points.extend(facet.center for facet in s.facets)
            world_points.extend(
                result.impact_point
                for result in s.facet_ray_results
                if result.impact_point is not None
            )

            def raw_projection(point: tuple[float, float, float]) -> tuple[float, float]:
                x_m, y_m, z_m = point
                if s.facet_view_mode == "Superior X-Y":
                    return (y_m, x_m)
                if s.facet_view_mode == "Lateral Y-Z":
                    return (y_m, z_m)
                return (x_m - 0.65 * y_m, z_m - 0.25 * x_m - 0.22 * y_m)

            raw_points = [raw_projection(point) for point in world_points]
            min_x = min(point[0] for point in raw_points)
            max_x = max(point[0] for point in raw_points)
            min_y = min(point[1] for point in raw_points)
            max_y = max(point[1] for point in raw_points)
            span_x = max(0.05, max_x - min_x)
            span_y = max(0.05, max_y - min_y)
            usable_w = max(10.0, schematic[2] - schematic[0] - 80.0)
            usable_h = max(10.0, schematic[3] - schematic[1] - 72.0)
            projection_scale = min(usable_w / span_x, usable_h / span_y)
            middle_x = (min_x + max_x) / 2.0
            middle_y = (min_y + max_y) / 2.0
            screen_cx = (schematic[0] + schematic[2]) / 2.0
            screen_cy = (schematic[1] + schematic[3]) / 2.0 + 8.0

            def project_facet(point: tuple[float, float, float]) -> tuple[float, float]:
                projected_x, projected_y = raw_projection(point)
                return (
                    screen_cx + (projected_x - middle_x) * projection_scale,
                    screen_cy - (projected_y - middle_y) * projection_scale,
                )

            focus_px, focus_py = project_facet(s.facet_focus)
            mirror_polygon: list[float] = []
            for corner in mirror_corners:
                corner_x, corner_y = project_facet(corner)
                mirror_polygon.extend([corner_x, corner_y])
            c.create_polygon(*mirror_polygon, fill="#8fc5ff", outline="#ffffff", width=2)
            mirror_center_x, mirror_center_y = project_facet((0.0, 0.0, 0.0))
            c.create_line(
                mirror_center_x,
                mirror_center_y + 5,
                mirror_center_x,
                mirror_center_y + 28,
                fill="#94a3b8",
                width=3,
            )
            c.create_line(
                mirror_center_x - 16,
                mirror_center_y + 28,
                mirror_center_x + 16,
                mirror_center_y + 28,
                fill="#94a3b8",
                width=3,
            )
            normal_tip_x, normal_tip_y = project_facet(v_mul(mirror_normal, mirror_half * 0.8))
            c.create_line(
                mirror_center_x,
                mirror_center_y,
                normal_tip_x,
                normal_tip_y,
                fill="#f472b6",
                width=2,
                arrow="last",
            )
            c.create_text(
                mirror_center_x,
                mirror_center_y + 18,
                text=f"Heliostato  AZ {s.az.angle_deg:.1f} / EL {s.el.angle_deg:.1f}",
                fill="#dbeafe",
                font=("Segoe UI", 8, "bold"),
            )
            shared_incident = (
                s.facets[0].incident_direction
                if s.facets and s.facets[0].incident_direction is not None
                else v_unit(s.target_vector)
            )
            for fraction_u, fraction_v in (
                (-0.55, -0.45),
                (0.0, -0.45),
                (0.55, -0.45),
                (-0.55, 0.45),
                (0.0, 0.45),
                (0.55, 0.45),
            ):
                ray_start = v_add(
                    v_mul(mirror_u, mirror_half * fraction_u),
                    v_mul(mirror_v, mirror_half * fraction_v),
                )
                ray_end = v_add(ray_start, v_mul(shared_incident, 0.075))
                ray_start_x, ray_start_y = project_facet(ray_start)
                ray_end_x, ray_end_y = project_facet(ray_end)
                c.create_line(
                    ray_start_x,
                    ray_start_y,
                    ray_end_x,
                    ray_end_y,
                    fill="#ffb454",
                    width=2,
                    arrow="last",
                )
            c.create_oval(focus_px - 7, focus_py - 7, focus_px + 7, focus_py + 7, fill="#58d6e7", outline="#ffffff")
            c.create_text(focus_px, focus_py - 17, text="Foco", fill="#8ce8f2", font=("Segoe UI", 9, "bold"))
            for facet in s.facets:
                facet_px, facet_py = project_facet(facet.center)
                color = "#d6b95f" if facet.active else "#5f6570"
                draw_facet_shape(
                    facet_px,
                    facet_py,
                    facet.size * projection_scale * 0.42,
                    facet.shape,
                    color,
                )
                if s.facet_count <= 18 or facet.id == s.facet_misaligned_id:
                    c.create_text(facet_px + 7, facet_py - 7, anchor="w", text=facet.id, fill="#ffffff", font=("Consolas", 7))
                normal_end = v_add(facet.center, v_mul(facet.normal, 0.035))
                normal_px, normal_py = project_facet(normal_end)
                c.create_line(facet_px, facet_py, normal_px, normal_py, fill="#f472b6", width=2)
                if not facet.active:
                    continue
                result = result_by_id.get(facet.id)
                if result is not None:
                    endpoint = result.impact_point
                    if endpoint is None:
                        endpoint = v_add(facet.center, v_mul(result.reflected_direction, s.facet_focal_distance_m))
                    impact_px, impact_py = project_facet(endpoint)
                    ray_color = "#66d9ef" if math.isfinite(result.focus_error_m) else "#ef4444"
                    c.create_line(facet_px, facet_py, impact_px, impact_py, fill=ray_color, width=1)
            axes_label = {
                "Superior X-Y": "horizontal y sur / vertical x oeste",
                "Lateral Y-Z": "y sur / z cenit",
                "3D isometrica": "3D: x oeste, y sur, z cenit",
            }.get(s.facet_view_mode, "")
            c.create_text(schematic[0] + 12, schematic[3] - 14, anchor="sw", text="n rosa | incidente naranja | reflejado cian | " + axes_label, fill="#dbeafe", font=("Segoe UI", 8))

        if self.facet_expanded_panel == "schematic":
            return

        receiver_cx = (receiver[0] + receiver[2]) / 2.0
        receiver_cy = (receiver[1] + receiver[3]) / 2.0
        half_pixels = max(35.0, min((receiver[2] - receiver[0]) * 0.37, (receiver[3] - receiver[1]) * 0.30))
        spot_result = s.spot_map_result if s.spot_map_enabled else None
        half_range_m = (
            spot_result.half_size_m
            if spot_result is not None
            else max(0.005, s.facet_error_max_m * 1.25)
        )
        pixels_per_m = half_pixels / half_range_m
        if spot_result is not None:
            display_resolution = min(31, spot_result.resolution)
            cell = 2.0 * half_pixels / display_resolution
            maximum = max(spot_result.intensity, default=0.0)
            for display_row in range(display_resolution):
                source_row = round(display_row * (spot_result.resolution - 1) / (display_resolution - 1))
                y1 = receiver_cy + half_pixels - (display_row + 1) * cell
                for display_column in range(display_resolution):
                    source_column = round(display_column * (spot_result.resolution - 1) / (display_resolution - 1))
                    value = spot_result.value(source_row, source_column)
                    x1 = receiver_cx - half_pixels + display_column * cell
                    c.create_rectangle(
                        x1,
                        y1,
                        x1 + cell + 1,
                        y1 + cell + 1,
                        fill=spot_heat_color(value, maximum),
                        outline="",
                    )
            c.create_rectangle(
                receiver_cx - half_pixels,
                receiver_cy - half_pixels,
                receiver_cx + half_pixels,
                receiver_cy + half_pixels,
                outline="#111827",
                width=2,
            )
        c.create_line(receiver_cx - half_pixels, receiver_cy, receiver_cx + half_pixels, receiver_cy, fill="#a89b78")
        c.create_line(receiver_cx, receiver_cy - half_pixels, receiver_cx, receiver_cy + half_pixels, fill="#a89b78")
        c.create_oval(receiver_cx - 5, receiver_cy - 5, receiver_cx + 5, receiver_cy + 5, outline="#16883f", width=2)
        for result in s.facet_ray_results:
            if not (math.isfinite(result.impact_u_m) and math.isfinite(result.impact_v_m)):
                continue
            px = clamp(receiver_cx + result.impact_u_m * pixels_per_m, receiver_cx - half_pixels, receiver_cx + half_pixels)
            py = clamp(receiver_cy - result.impact_v_m * pixels_per_m, receiver_cy - half_pixels, receiver_cy + half_pixels)
            color = "#2563eb" if result.focus_error_m < 1e-6 else "#d62828"
            c.create_oval(px - 5, py - 5, px + 5, py + 5, fill=color, outline="#ffffff")
            if s.facet_count <= 18 or result.facet_id == s.facet_misaligned_id:
                c.create_text(px + 7, py - 7, anchor="w", text=result.facet_id, fill=color, font=("Consolas", 8, "bold"))
        footer = f"u oeste + / v cenit + | escala +/- {half_range_m * 1000.0:.1f} mm"
        if spot_result is not None:
            metrics = spot_result.metrics
            footer += (
                f" | centroide {metrics.centroid_error_m * 1000.0:.2f} mm"
                f" | diam. eq. {metrics.equivalent_diameter_m * 1000.0:.2f} mm"
            )
        c.create_text(receiver_cx, receiver[3] - 14, text=footer, fill="#333333", font=("Segoe UI", 8, "bold"))

        table_top = int(h * 0.64)
        c.create_text(24, table_top, anchor="w", text="Resultados por faceta", fill="#111111", font=("Segoe UI", 12, "bold"))
        visible_facets = s.facets[:18]
        rows_per_column = 6
        column_width = (w - 48.0) / 3.0
        for index, facet in enumerate(visible_facets):
            column = index // rows_per_column
            row = index % rows_per_column
            x = 24 + column * column_width
            y = table_top + 32 + row * 33
            result = result_by_id.get(facet.id)
            if not facet.active:
                detail = "INACTIVA - sin contribucion"
                color = "#6b7280"
            elif result is None or not math.isfinite(result.focus_error_m):
                detail = "sin cruce con receptor"
                color = "#b91c1c"
            else:
                detail = (
                    f"u {result.impact_u_m * 1000.0:+7.3f} | "
                    f"v {result.impact_v_m * 1000.0:+7.3f} | "
                    f"err {result.focus_error_m * 1000.0:7.3f} mm"
                )
                color = "#16883f" if result.focus_error_m < 1e-6 else "#b91c1c"
            c.create_text(x, y, anchor="w", text=f"{facet.id}: {detail}", fill=color, font=("Consolas", 8))
        if len(s.facets) > len(visible_facets):
            c.create_text(
                w - 24,
                table_top,
                anchor="e",
                text=f"Se muestran 18 de {len(s.facets)}; todos los impactos permanecen en la grafica",
                fill="#6b7280",
                font=("Segoe UI", 9),
            )

    def draw_facet_receiver_expanded(
        self,
        c: tk.Canvas,
        panel: tuple[int, int, int, int],
    ) -> None:
        """Amplia el plano receptor con mapa termico, impactos y metricas."""
        s = self.state
        x0, y0, x1, y1 = panel
        c.create_rectangle(*panel, fill="#101821", outline="#718096", width=2)
        c.create_text(x0 + 16, y0 + 14, anchor="nw", text="Plano receptor / foco e intensidad", fill="#ffffff", font=("Segoe UI", 13, "bold"))
        spot_result = s.spot_map_result if s.spot_map_enabled else None
        map_size = max(120.0, min(y1 - y0 - 100.0, (x1 - x0) * 0.57))
        left = x0 + 36.0
        top = y0 + 58.0
        right = left + map_size
        bottom = top + map_size
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0
        half_range_m = spot_result.half_size_m if spot_result is not None else max(0.005, s.facet_error_max_m * 1.25)
        maximum = max(spot_result.intensity, default=0.0) if spot_result is not None else 0.0
        if spot_result is not None:
            display_resolution = min(41, spot_result.resolution)
            cell = map_size / display_resolution
            for display_row in range(display_resolution):
                source_row = round(display_row * (spot_result.resolution - 1) / (display_resolution - 1))
                draw_y = bottom - (display_row + 1) * cell
                for display_column in range(display_resolution):
                    source_column = round(display_column * (spot_result.resolution - 1) / (display_resolution - 1))
                    value = spot_result.value(source_row, source_column)
                    draw_x = left + display_column * cell
                    c.create_rectangle(draw_x, draw_y, draw_x + cell + 1, draw_y + cell + 1, fill=spot_heat_color(value, maximum), outline="")
        else:
            c.create_rectangle(left, top, right, bottom, fill="#fffdf5", outline="")
            c.create_text(center_x, center_y, text="Mapa de intensidad desactivado", fill="#64748b", font=("Segoe UI", 11, "bold"))
        c.create_rectangle(left, top, right, bottom, outline="#cbd5e1", width=2)
        c.create_line(left, center_y, right, center_y, fill="#a89b78")
        c.create_line(center_x, top, center_x, bottom, fill="#a89b78")
        c.create_oval(center_x - 6, center_y - 6, center_x + 6, center_y + 6, outline="#22c55e", width=2)
        pixels_per_m = map_size / (2.0 * half_range_m)
        for ray in s.facet_ray_results:
            if not (math.isfinite(ray.impact_u_m) and math.isfinite(ray.impact_v_m)):
                continue
            px = clamp(center_x + ray.impact_u_m * pixels_per_m, left, right)
            py = clamp(center_y - ray.impact_v_m * pixels_per_m, top, bottom)
            color = "#ffffff" if spot_result is not None else "#d62828"
            c.create_oval(px - 5, py - 5, px + 5, py + 5, fill=color, outline="#111827")
            if s.facet_count <= 18 or ray.facet_id == s.facet_misaligned_id:
                c.create_text(px + 7, py - 7, anchor="w", text=ray.facet_id, fill=color, font=("Consolas", 8, "bold"))
        c.create_text(center_x, bottom + 22, text=f"u [mm] oeste + | rango +/- {half_range_m * 1000.0:.1f} mm", fill="#dbeafe", font=("Segoe UI", 9, "bold"))
        c.create_text(left - 18, center_y, text="v [mm] cenit +", angle=90, fill="#dbeafe", font=("Segoe UI", 9, "bold"))

        details_left = right + 32
        c.create_rectangle(details_left, top, x1 - 24, bottom, fill="#172432", outline="#475569")
        if spot_result is None:
            details = (
                "Activa el mapa de intensidad en el menu de facetas.\n\n"
                f"Facetas activas: {len(s.facet_ray_results)}/{s.facet_count}\n"
                f"Error maximo de foco: {s.facet_error_max_m * 1000.0:.3f} mm\n"
                f"Error promedio: {s.facet_error_average_m * 1000.0:.3f} mm"
            )
        else:
            metrics = spot_result.metrics
            details = (
                "METRICAS DEL SPOT\n\n"
                f"Facetas activas: {len(s.facet_ray_results)}/{s.facet_count}\n"
                f"Normalizacion: {spot_result.normalization}\n"
                f"Resolucion: {spot_result.resolution} x {spot_result.resolution}\n"
                f"Centroide u/v: {metrics.centroid_u_m * 1000.0:+.3f} / {metrics.centroid_v_m * 1000.0:+.3f} mm\n"
                f"Error centroide: {metrics.centroid_error_m * 1000.0:.3f} mm\n"
                f"Diametro equivalente: {metrics.equivalent_diameter_m * 1000.0:.3f} mm\n"
                f"Sigma mayor/menor: {metrics.major_sigma_m * 1000.0:.3f} / {metrics.minor_sigma_m * 1000.0:.3f} mm\n"
                f"Orientacion: {metrics.orientation_deg:+.2f} deg\n"
                f"Forma: {metrics.shape}\n"
                f"Pico / total: {metrics.maximum_intensity:.6f} / {metrics.total_intensity:.6f}\n"
                f"Calculo: {s.spot_compute_ms:.3f} ms"
            )
        c.create_text(details_left + 18, top + 18, anchor="nw", text=details, fill="#dbeafe", font=("Consolas", 10))
        if spot_result is not None:
            legend_y = bottom - 42
            legend_width = max(60.0, x1 - details_left - 70.0)
            for index in range(40):
                lx1 = details_left + 18 + legend_width * index / 40.0
                lx2 = details_left + 18 + legend_width * (index + 1) / 40.0
                c.create_rectangle(lx1, legend_y, lx2 + 1, legend_y + 16, fill=spot_heat_color(maximum * index / 39.0, maximum), outline="")
            c.create_text(details_left + 18, legend_y + 24, anchor="nw", text="0", fill="#cbd5e1", font=("Consolas", 8))
            c.create_text(details_left + 18 + legend_width, legend_y + 24, anchor="ne", text=f"pico {maximum:.4g}", fill="#cbd5e1", font=("Consolas", 8))

    def handle_facet_click(self, event: tk.Event) -> None:
        """Amplia esquema o receptor y permite regresar a la vista combinada."""
        if self.facet_expanded_panel is not None:
            if self.facet_back_box is not None:
                x1, y1, x2, y2 = self.facet_back_box
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    self.facet_expanded_panel = None
                    self.request_render()
            return
        for panel_name, (x1, y1, x2, y2) in self.facet_panel_boxes.items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.facet_expanded_panel = panel_name
                self.request_render()
                return

    def draw_spot_view(self) -> None:
        """Dibuja el mapa combinado de intensidad y sus metricas energeticas."""
        c = self.spot_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        c.create_rectangle(0, 0, w, h, fill="#101821", outline="")
        s = self.state
        c.create_text(
            24,
            22,
            anchor="w",
            text="Mapa aproximado de intensidad por faceta",
            fill="#ffffff",
            font=("Segoe UI", 15, "bold"),
        )
        if not s.spot_map_enabled:
            c.create_text(
                w / 2,
                h / 2,
                text="Activa 'Spot aproximado por faceta' para generar el mapa",
                fill="#94a3b8",
                font=("Segoe UI", 13, "bold"),
            )
            return
        result = s.spot_map_result
        if result is None:
            c.create_text(
                w / 2,
                h / 2,
                text="Sin contribuciones: activa el concentrador y al menos una faceta",
                fill="#94a3b8",
                font=("Segoe UI", 13, "bold"),
            )
            return

        map_size = max(180.0, min(h - 125.0, w * 0.62))
        left = 34.0
        top = 78.0
        right = left + map_size
        bottom = top + map_size
        c.create_rectangle(left, top, right, bottom, fill="#020617", outline="#cbd5e1", width=2)
        display_resolution = min(41, result.resolution)
        cell = map_size / display_resolution
        maximum = max(result.intensity, default=0.0)

        def heat_color(value: float) -> str:
            ratio = clamp(value / maximum if maximum > 1e-18 else 0.0, 0.0, 1.0)
            stops = (
                (0.00, (2, 6, 23)),
                (0.20, (30, 64, 175)),
                (0.45, (6, 182, 212)),
                (0.70, (250, 204, 21)),
                (1.00, (220, 38, 38)),
            )
            for stop_index in range(len(stops) - 1):
                start_value, start_rgb = stops[stop_index]
                end_value, end_rgb = stops[stop_index + 1]
                if ratio <= end_value:
                    fraction = (ratio - start_value) / max(1e-12, end_value - start_value)
                    rgb = tuple(
                        round(start + (end - start) * fraction)
                        for start, end in zip(start_rgb, end_rgb)
                    )
                    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            return "#dc2626"

        for display_row in range(display_resolution):
            source_row = round(display_row * (result.resolution - 1) / (display_resolution - 1))
            y1 = bottom - (display_row + 1) * cell
            y2 = bottom - display_row * cell
            for display_column in range(display_resolution):
                source_column = round(
                    display_column * (result.resolution - 1) / (display_resolution - 1)
                )
                value = result.value(source_row, source_column)
                x1 = left + display_column * cell
                c.create_rectangle(
                    x1,
                    y1,
                    x1 + cell + 1,
                    y2 + 1,
                    fill=heat_color(value),
                    outline="",
                )

        pixels_per_m = map_size / (2.0 * result.half_size_m)
        center_x = (left + right) / 2.0
        center_y = (top + bottom) / 2.0
        c.create_line(center_x - 10, center_y, center_x + 10, center_y, fill="#22c55e", width=2)
        c.create_line(center_x, center_y - 10, center_x, center_y + 10, fill="#22c55e", width=2)
        metrics = result.metrics
        centroid_x = center_x + metrics.centroid_u_m * pixels_per_m
        centroid_y = center_y - metrics.centroid_v_m * pixels_per_m
        c.create_line(centroid_x - 9, centroid_y - 9, centroid_x + 9, centroid_y + 9, fill="#ffffff", width=2)
        c.create_line(centroid_x - 9, centroid_y + 9, centroid_x + 9, centroid_y - 9, fill="#ffffff", width=2)
        radius_px = metrics.equivalent_radius_m * pixels_per_m
        c.create_oval(
            centroid_x - radius_px,
            centroid_y - radius_px,
            centroid_x + radius_px,
            centroid_y + radius_px,
            outline="#ffffff",
            dash=(5, 3),
        )
        orientation = math.radians(metrics.orientation_deg)
        axis_half = min(map_size * 0.25, 2.0 * metrics.major_sigma_m * pixels_per_m)
        axis_dx = math.cos(orientation) * axis_half
        axis_dy = -math.sin(orientation) * axis_half
        c.create_line(
            centroid_x - axis_dx,
            centroid_y - axis_dy,
            centroid_x + axis_dx,
            centroid_y + axis_dy,
            fill="#f8fafc",
            width=2,
        )
        c.create_text(center_x, bottom + 25, text="u [mm] oeste +", fill="#cbd5e1", font=("Segoe UI", 9, "bold"))
        c.create_text(left - 18, center_y, text="v [mm] cenit +", angle=90, fill="#cbd5e1", font=("Segoe UI", 9, "bold"))
        c.create_text(left, bottom + 48, anchor="w", text=f"{-result.half_size_m * 1000.0:.1f}", fill="#94a3b8", font=("Consolas", 8))
        c.create_text(right, bottom + 48, anchor="e", text=f"+{result.half_size_m * 1000.0:.1f} mm", fill="#94a3b8", font=("Consolas", 8))

        panel_left = right + 38
        c.create_rectangle(panel_left, 78, w - 26, h - 42, fill="#172432", outline="#475569")
        c.create_text(panel_left + 18, 100, anchor="nw", text="Metricas del spot", fill="#ffffff", font=("Segoe UI", 13, "bold"))
        metric_text = (
            f"Facetas activas: {len(s.facet_ray_results)}\n"
            f"Normalizacion: {result.normalization}\n"
            f"Resolucion: {result.resolution} x {result.resolution}\n"
            f"Centroide u: {metrics.centroid_u_m * 1000.0:+.3f} mm\n"
            f"Centroide v: {metrics.centroid_v_m * 1000.0:+.3f} mm\n"
            f"Error centroide: {metrics.centroid_error_m * 1000.0:.3f} mm\n"
            f"Intensidad maxima: {metrics.maximum_intensity:.6f}\n"
            f"Intensidad total: {metrics.total_intensity:.6f}\n"
            f"Radio equivalente: {metrics.equivalent_radius_m * 1000.0:.3f} mm\n"
            f"Diametro equivalente: {metrics.equivalent_diameter_m * 1000.0:.3f} mm\n"
            f"Sigma mayor/menor: {metrics.major_sigma_m * 1000.0:.3f} / {metrics.minor_sigma_m * 1000.0:.3f} mm\n"
            f"Orientacion: {metrics.orientation_deg:+.2f} deg\n"
            f"Forma global: {metrics.shape}\n"
            f"Tiempo de calculo: {s.spot_compute_ms:.3f} ms"
        )
        c.create_text(panel_left + 18, 142, anchor="nw", text=metric_text, fill="#dbeafe", font=("Consolas", 10))
        legend_y = h - 105
        legend_width = max(80.0, w - panel_left - 80.0)
        for index in range(50):
            x1 = panel_left + 18 + legend_width * index / 50.0
            x2 = panel_left + 18 + legend_width * (index + 1) / 50.0
            c.create_rectangle(x1, legend_y, x2 + 1, legend_y + 18, fill=heat_color(maximum * index / 49.0), outline="")
        c.create_text(panel_left + 18, legend_y + 27, anchor="nw", text="0", fill="#cbd5e1", font=("Consolas", 8))
        c.create_text(panel_left + 18 + legend_width, legend_y + 27, anchor="ne", text=f"pico {maximum:.4g}", fill="#cbd5e1", font=("Consolas", 8))

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
        side_left = max(640.0, w * 0.62)
        x0, y0 = 42, 66
        metric_bar_width = max(250.0, side_left - x0 - 155.0)
        for i, (label, value, unit, limit, color) in enumerate(metrics):
            y = y0 + i * 68
            c.create_text(x0, y, anchor="w", text=label, fill="#111111", font=("Segoe UI", 11, "bold"))
            c.create_rectangle(x0, y + 22, x0 + metric_bar_width, y + 44, fill="#e6e6e6", outline="#bdbdbd")
            frac = clamp(abs(value) / limit, 0.0, 1.0)
            c.create_rectangle(x0, y + 22, x0 + metric_bar_width * frac, y + 44, fill=color, outline="")
            c.create_text(x0 + metric_bar_width + 16, y + 33, anchor="w", text=f"{value:7.2f} {unit}", fill="#111111", font=("Consolas", 11, "bold"))
        chart_top = 298
        chart_right = side_left - 18 if w >= 980 else w - 42
        box = (42, chart_top, int(chart_right), h - 38)
        self.draw_axes(
            c,
            *box,
            "Historial del error radial del spot",
            "Distancia al centro [mm]",
            "Muestras del simulador: izquierda = mas antigua, derecha = actual",
        )
        errs = [
            float(p.get("err_radial", math.hypot(p["err_x"], p["err_z"]))) * 1000.0
            for p in hist
            if p.get("spot_valid", True)
            and math.isfinite(float(p.get("err_radial", math.hypot(p["err_x"], p["err_z"]))))
        ]
        ymax = max(errs + [10.0])
        self.plot_series(c, box, errs, "#c53030", 0.0, min(max(ymax, 10.0), 500.0))
        c.create_text(
            box[0] + 55,
            box[1] + 36,
            anchor="w",
            text="Linea roja: distancia radial entre el impacto y el centro del target",
            fill="#9f1239",
            font=("Segoe UI", 8, "bold"),
        )
        stats_left = side_left + 8 if w >= 980 else max(42, w - 390)
        c.create_rectangle(stats_left, 58, w - 24, 276, fill="#ffffff", outline="#c7c7c7")
        c.create_text(stats_left + 16, 74, anchor="nw", text=(
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
        ), fill="#222222", font=("Consolas", 9))
        vector_x = stats_left
        vector_y = chart_top
        c.create_rectangle(vector_x, vector_y, w - 24, vector_y + 52, fill="#ffffff", outline="#bbbbbb")
        status_label, status_color, _detail = self.system_status()
        c.create_rectangle(vector_x, vector_y, w - 24, vector_y + 24, fill=status_color, outline="#bbbbbb")
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
            f"Angulos i/r = {s.incidence_angle_deg:.3f} / {s.reflection_angle_deg:.3f} deg\n"
            f"Diferencia R-T = {s.reflection_target_error_deg:.4f} deg"
        )
        c.create_text(vector_x + 8, vector_y + 62, anchor="nw", text=vector_text, fill="#222222", font=("Consolas", 8))

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
            ("Concentrador", "forma y cantidad configurables\nun rayo central por faceta"),
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
    for name, value in MINIHORNO_PROFILE.items():
        if hasattr(state, name):
            setattr(state, name, value)
    state.use_live_time = False
    state.simulated_time = _dt.datetime(2026, 6, 21, 12, 0, 0)
    state.advance_solar_time = False
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
    assert state.ideal_spot_radial < 1e-8
    assert state.error_spot_radial < 1e-8
    assert state.corrected_spot_radial < 1e-8

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
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
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
