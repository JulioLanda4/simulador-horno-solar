"""Pruebas del pseudotrazado de intensidad de la Etapa 9."""

from __future__ import annotations

import datetime as dt
import math
import unittest

from digital_twin.facet_model import FacetRayResult
from digital_twin.run_digital_twin import TwinState
from digital_twin.spot_model import (
    SpotContribution,
    contribution_from_ray,
    generate_spot_map,
)


class SpotModelTests(unittest.TestCase):
    """Valida manchas, superposicion, inclinacion, normalizacion y centroide."""

    receiver_normal = (0.0, 1.0, 0.0)

    @staticmethod
    def ray_result(
        facet_id: str,
        u_m: float,
        v_m: float,
        direction: tuple[float, float, float] = (0.0, -1.0, 0.0),
    ) -> FacetRayResult:
        return FacetRayResult(
            facet_id=facet_id,
            facet_center=(0.0, 1.0, 0.0),
            incident_direction=(0.0, 1.0, 0.0),
            reflected_direction=direction,
            impact_point=(u_m, 0.75, v_m),
            impact_u_m=u_m,
            impact_v_m=v_m,
            focus_error_m=math.hypot(u_m, v_m),
        )

    def test_single_facet_spot_is_centered_on_its_impact(self) -> None:
        contribution = contribution_from_ray(
            self.ray_result("F1", 0.010, -0.006),
            self.receiver_normal,
            base_sigma_m=0.002,
        )
        self.assertIsNotNone(contribution)

        result = generate_spot_map([contribution], half_size_m=0.03, resolution=81)

        self.assertAlmostEqual(result.metrics.centroid_u_m, 0.010, delta=0.0001)
        self.assertAlmostEqual(result.metrics.centroid_v_m, -0.006, delta=0.0001)

    def test_multiple_facets_generate_combined_distribution(self) -> None:
        contributions = [
            SpotContribution("F1", -0.008, 0.0, 0.002, 0.002, 0.0, 1.0),
            SpotContribution("F2", 0.008, 0.0, 0.002, 0.002, 0.0, 1.0),
        ]

        combined = generate_spot_map(contributions, half_size_m=0.025, resolution=81)
        single = generate_spot_map(contributions[:1], half_size_m=0.025, resolution=81)

        self.assertAlmostEqual(combined.metrics.centroid_u_m, 0.0, delta=0.0001)
        self.assertGreater(
            combined.metrics.equivalent_diameter_m,
            single.metrics.equivalent_diameter_m,
        )

    def test_oblique_incidence_deforms_spot_into_ellipse(self) -> None:
        tilted_direction = (math.sqrt(3.0) / 2.0, -0.5, 0.0)
        contribution = contribution_from_ray(
            self.ray_result("F1", 0.0, 0.0, tilted_direction),
            self.receiver_normal,
            base_sigma_m=0.002,
        )
        self.assertIsNotNone(contribution)
        assert contribution is not None

        result = generate_spot_map([contribution], half_size_m=0.025, resolution=101)

        self.assertAlmostEqual(contribution.sigma_major_m, 0.004, places=6)
        self.assertGreater(result.metrics.major_sigma_m / result.metrics.minor_sigma_m, 1.8)
        self.assertIn(result.metrics.shape, ("Eliptica", "Alargada"))

    def test_total_and_peak_normalization(self) -> None:
        contribution = SpotContribution("F1", 0.0, 0.0, 0.002, 0.002, 0.0, 1.0)

        total_result = generate_spot_map(
            [contribution],
            half_size_m=0.02,
            resolution=61,
            normalization="Total = 1",
        )
        peak_result = generate_spot_map(
            [contribution],
            half_size_m=0.02,
            resolution=61,
            normalization="Pico = 1",
        )

        self.assertAlmostEqual(sum(total_result.intensity), 1.0, places=12)
        self.assertAlmostEqual(max(peak_result.intensity), 1.0, places=12)

    def test_centroid_respects_relative_energy(self) -> None:
        contributions = [
            SpotContribution("F1", -0.010, 0.0, 0.0015, 0.0015, 0.0, 1.0),
            SpotContribution("F2", 0.010, 0.0, 0.0015, 0.0015, 0.0, 3.0),
        ]

        result = generate_spot_map(contributions, half_size_m=0.025, resolution=101)

        self.assertAlmostEqual(result.metrics.centroid_u_m, 0.005, delta=0.00015)
        self.assertAlmostEqual(result.metrics.centroid_v_m, 0.0, delta=0.00005)

    def test_twin_state_builds_normalized_spot_map(self) -> None:
        state = TwinState()
        state.use_live_time = False
        state.set_simulated_start_time(dt.datetime(2026, 6, 21, 12, 0, 0))
        state.facet_field_enabled = True
        state.spot_map_enabled = True
        state.spot_normalization = "Total = 1"

        state.compute_geometry()

        self.assertIsNotNone(state.spot_map_result)
        assert state.spot_map_result is not None
        self.assertAlmostEqual(sum(state.spot_map_result.intensity), 1.0, places=12)
        self.assertLess(state.spot_metrics.centroid_error_m, 1e-6)
        self.assertLess(state.spot_compute_ms, 100.0)


if __name__ == "__main__":
    unittest.main()
