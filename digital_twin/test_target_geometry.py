"""Pruebas de la geometria del target virtual de la Etapa 1."""

from __future__ import annotations

import math
import unittest

from digital_twin.run_digital_twin import (
    classify_target_error,
    compute_target_impact,
    intersect_ray_plane,
    target_coordinate_frame,
    world_to_target_coordinates,
)


class TargetGeometryTests(unittest.TestCase):
    """Valida el target en el marco global +x oeste, +y sur, +z cenit."""

    def assert_point_almost_equal(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
    ) -> None:
        for actual_component, expected_component in zip(actual, expected):
            self.assertAlmostEqual(actual_component, expected_component, places=9)

    def test_ray_to_center_has_near_zero_error(self) -> None:
        target = (0.0, 5.0, -0.2)
        impact = compute_target_impact((0.0, 0.0, 0.0), target, target, 0.01)

        self.assertIsNotNone(impact.point)
        self.assert_point_almost_equal(impact.point, target)  # type: ignore[arg-type]
        self.assertAlmostEqual(impact.u_m, 0.0, places=9)
        self.assertAlmostEqual(impact.v_m, 0.0, places=9)
        self.assertAlmostEqual(impact.radial_error_m, 0.0, places=9)
        self.assertEqual(impact.status, "centrado")

    def test_horizontal_error_is_positive_toward_west(self) -> None:
        target = (0.0, 5.0, 0.0)
        normal, u_axis, v_axis = target_coordinate_frame(target)
        point, _t = intersect_ray_plane(
            (0.0, 0.0, 0.0),
            (0.1, 1.0, 0.0),
            target,
            normal,
        )

        self.assertIsNotNone(point)
        u_m, v_m = world_to_target_coordinates(point, target, u_axis, v_axis)  # type: ignore[arg-type]
        self.assertGreater(u_m, 0.0)
        self.assertAlmostEqual(u_m, 0.5, places=9)
        self.assertAlmostEqual(v_m, 0.0, places=9)

    def test_parallel_ray_returns_none(self) -> None:
        point, ray_parameter = intersect_ray_plane(
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 5.0, 0.0),
            (0.0, 1.0, 0.0),
        )

        self.assertIsNone(point)
        self.assertIsNone(ray_parameter)

    def test_moving_target_updates_intersection(self) -> None:
        first_target = (0.0, 5.0, 0.0)
        moved_target = (0.3, 4.2, 0.4)
        first = compute_target_impact((0.0, 0.0, 0.0), first_target, first_target, 0.01)
        moved = compute_target_impact((0.0, 0.0, 0.0), moved_target, moved_target, 0.01)

        self.assertIsNotNone(first.point)
        self.assertIsNotNone(moved.point)
        self.assert_point_almost_equal(first.point, first_target)  # type: ignore[arg-type]
        self.assert_point_almost_equal(moved.point, moved_target)  # type: ignore[arg-type]
        self.assertNotEqual(first.point, moved.point)
        self.assertAlmostEqual(moved.radial_error_m, 0.0, places=9)

    def test_intersection_behind_origin_is_rejected(self) -> None:
        point, ray_parameter = intersect_ray_plane(
            (0.0, 0.0, 0.0),
            (0.0, -1.0, 0.0),
            (0.0, 5.0, 0.0),
            (0.0, 1.0, 0.0),
        )

        self.assertIsNone(point)
        self.assertIsNone(ray_parameter)

    def test_status_thresholds(self) -> None:
        self.assertEqual(classify_target_error(0.001, 0.010), "centrado")
        self.assertEqual(classify_target_error(0.006, 0.010), "aceptable")
        self.assertEqual(classify_target_error(0.012, 0.010), "fuera de tolerancia")
        self.assertTrue(math.isfinite(0.012))


if __name__ == "__main__":
    unittest.main()
