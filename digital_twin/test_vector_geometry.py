"""Pruebas de vectores geometricos y ley de reflexion de la Etapa 2."""

from __future__ import annotations

import unittest

from digital_twin.run_digital_twin import (
    TwinState,
    angle_between,
    compute_heliostat_normal,
    compute_reflection_diagnostics,
    normalize,
    reflect_vector,
    v_mul,
    v_norm,
)


class VectorGeometryTests(unittest.TestCase):
    """Valida la optica en el marco +x oeste, +y sur, +z cenit."""

    def assert_vector_almost_equal(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
    ) -> None:
        for actual_component, expected_component in zip(actual, expected):
            self.assertAlmostEqual(actual_component, expected_component, places=9)

    def test_normalize_returns_unit_vector(self) -> None:
        unit = normalize((3.0, -4.0, 12.0))

        self.assertAlmostEqual(v_norm(unit), 1.0, places=12)
        self.assertEqual(normalize((0.0, 0.0, 0.0)), (0.0, 0.0, 0.0))

    def test_ideal_normal_reflects_sun_toward_target(self) -> None:
        sun_direction = normalize((-0.35, 0.72, 0.60))
        target_direction = normalize((0.18, 0.97, -0.16))
        normal = compute_heliostat_normal(sun_direction, target_direction)
        reflected = reflect_vector(v_mul(sun_direction, -1.0), normal)

        self.assertAlmostEqual(v_norm(normal), 1.0, places=12)
        self.assertAlmostEqual(v_norm(reflected), 1.0, places=12)
        self.assert_vector_almost_equal(reflected, target_direction)

    def test_incidence_equals_reflection(self) -> None:
        sun_direction = normalize((0.42, 0.68, 0.60))
        target_direction = normalize((-0.08, 0.99, -0.10))
        normal = compute_heliostat_normal(sun_direction, target_direction)
        diagnostics = compute_reflection_diagnostics(sun_direction, normal, target_direction)

        self.assertAlmostEqual(
            diagnostics.incidence_angle_deg,
            diagnostics.reflection_angle_deg,
            places=10,
        )
        self.assertAlmostEqual(diagnostics.target_difference_deg, 0.0, places=9)

    def test_reflected_ray_matches_target_in_three_orientations(self) -> None:
        cases = (
            ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            ((-0.6, 0.5, 0.62), (0.3, 0.94, -0.15)),
            ((0.7, -0.1, 0.7), (-0.2, 0.95, 0.23)),
        )
        for sun_raw, target_raw in cases:
            with self.subTest(sun=sun_raw, target=target_raw):
                sun = normalize(sun_raw)
                target = normalize(target_raw)
                normal = compute_heliostat_normal(sun, target)
                reflected = reflect_vector(v_mul(sun, -1.0), normal)
                self.assertLess(angle_between(reflected, target), 1e-6)

    def test_nonideal_normal_produces_target_difference(self) -> None:
        sun = normalize((0.2, 0.8, 0.56))
        target = normalize((0.0, 1.0, -0.08))
        nonideal_normal = normalize((0.25, 0.90, 0.36))
        diagnostics = compute_reflection_diagnostics(sun, nonideal_normal, target)

        self.assertGreater(diagnostics.target_difference_deg, 0.1)
        self.assertAlmostEqual(
            diagnostics.incidence_angle_deg,
            diagnostics.reflection_angle_deg,
            places=10,
        )

    def test_undefined_vectors_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compute_heliostat_normal((0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        with self.assertRaises(ValueError):
            compute_heliostat_normal((0.0, 1.0, 0.0), (0.0, -1.0, 0.0))
        with self.assertRaises(ValueError):
            reflect_vector((0.0, 0.0, 0.0), (0.0, 1.0, 0.0))

    def test_vector_visibility_flags_are_independent(self) -> None:
        state = TwinState()
        names = (
            "show_sun_vector",
            "show_normal_vector",
            "show_reflected_vector",
            "show_target_direction",
            "show_target_line",
        )
        for name in names:
            self.assertTrue(getattr(state, name))
            setattr(state, name, False)
            self.assertFalse(getattr(state, name))


if __name__ == "__main__":
    unittest.main()
