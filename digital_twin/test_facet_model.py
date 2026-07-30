"""Pruebas del concentrador facetado y rayos centrales de la Etapa 8."""

from __future__ import annotations

import datetime as dt
import math
import time
import unittest

from digital_twin.facet_model import (
    build_compact_facets,
    build_rectangular_facets,
    optimal_facet_offsets,
    trace_facets,
)
from digital_twin.run_digital_twin import TwinState


class FacetModelTests(unittest.TestCase):
    """Valida foco ideal, desalineacion, activacion y costo ligero."""

    center = (0.0, 1.0, 0.0)
    focus = (0.0, 0.75, 0.0)
    receiver_normal = (0.0, 1.0, 0.0)

    def test_ideal_facet_sends_central_ray_to_focus(self) -> None:
        facets = build_rectangular_facets(
            concentrator_center=self.center,
            focus=self.focus,
            rows=1,
            columns=1,
            focal_distance_m=0.25,
        )

        results = trace_facets(facets, (0.0, 0.0, 0.0), self.focus, self.receiver_normal)

        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0].impact_point)
        self.assertLess(results[0].focus_error_m, 1e-12)
        self.assertAlmostEqual(facets[0].size, 0.03)
        self.assertAlmostEqual(facets[0].focal_distance or 0.0, 0.25)
        self.assertIsNotNone(facets[0].aim_direction)

    def test_misaligned_facet_displaces_impact(self) -> None:
        facets = build_rectangular_facets(
            concentrator_center=self.center,
            focus=self.focus,
            rows=1,
            columns=1,
            misaligned_facet_id="F1",
            horizontal_misalignment_deg=0.5,
        )

        result = trace_facets(facets, (0.0, 0.0, 0.0), self.focus, self.receiver_normal)[0]

        self.assertTrue(math.isfinite(result.focus_error_m))
        self.assertGreater(result.focus_error_m, 0.001)

    def test_inactive_facet_has_no_ray_contribution(self) -> None:
        facets = build_rectangular_facets(
            concentrator_center=self.center,
            focus=self.focus,
            rows=1,
            columns=1,
            active_ids=set(),
        )

        results = trace_facets(facets, (0.0, 0.0, 0.0), self.focus, self.receiver_normal)

        self.assertFalse(facets[0].active)
        self.assertEqual(results, [])

    def test_nine_facets_remain_lightweight(self) -> None:
        started = time.perf_counter()
        for _ in range(500):
            facets = build_rectangular_facets(
                concentrator_center=self.center,
                focus=self.focus,
                rows=3,
                columns=3,
                focal_distance_m=0.25,
            )
            results = trace_facets(
                facets,
                (0.0, 0.0, 0.0),
                self.focus,
                self.receiver_normal,
            )
            self.assertEqual(len(results), 9)
        elapsed_s = time.perf_counter() - started

        self.assertLess(elapsed_s, 2.0)

    def test_shape_and_arbitrary_count_use_centered_compact_layout(self) -> None:
        for shape, count in (("Cuadrada", 10), ("Circular", 19), ("Hexagonal", 23)):
            with self.subTest(shape=shape, count=count):
                facets = build_compact_facets(
                    concentrator_center=self.center,
                    focus=self.focus,
                    count=count,
                    shape=shape,
                    size_m=0.03,
                    gap_m=0.002,
                    focal_distance_m=0.25,
                )

                self.assertEqual(len(facets), count)
                self.assertTrue(all(facet.shape == shape for facet in facets))
                self.assertAlmostEqual(
                    sum(facet.layout_u_m for facet in facets) / count,
                    0.0,
                    places=12,
                )
                self.assertAlmostEqual(
                    sum(facet.layout_v_m for facet in facets) / count,
                    0.0,
                    places=12,
                )
                minimum_distance = min(
                    math.hypot(
                        first.layout_u_m - second.layout_u_m,
                        first.layout_v_m - second.layout_v_m,
                    )
                    for index, first in enumerate(facets)
                    for second in facets[index + 1 :]
                )
                self.assertGreaterEqual(minimum_distance + 1e-12, 0.032)

    def test_nineteen_circular_facets_form_two_compact_rings(self) -> None:
        pitch_m = 0.032
        offsets = optimal_facet_offsets(19, "Circular", 0.03, 0.002)
        maximum_radius = max(math.hypot(u_m, v_m) for u_m, v_m in offsets)

        self.assertLessEqual(maximum_radius, 2.01 * pitch_m)

    def test_incident_bundle_is_parallel_for_all_facets(self) -> None:
        facets = build_compact_facets(
            concentrator_center=self.center,
            focus=self.focus,
            count=19,
            shape="Circular",
            size_m=0.03,
            gap_m=0.002,
        )
        results = trace_facets(
            facets,
            (0.0, 0.0, 0.0),
            self.focus,
            self.receiver_normal,
        )

        reference = results[0].incident_direction
        for result in results[1:]:
            for component, reference_component in zip(result.incident_direction, reference):
                self.assertAlmostEqual(component, reference_component, places=12)

    def test_twin_state_reports_active_facets_and_focus_error(self) -> None:
        state = TwinState()
        state.use_live_time = False
        state.set_simulated_start_time(dt.datetime(2026, 6, 21, 12, 0, 0))
        state.facet_field_enabled = True
        state.facet_misaligned_id = "F5"
        state.facet_horizontal_misalignment_deg = 0.5

        state.compute_geometry()

        self.assertEqual(len(state.facets), 9)
        self.assertEqual(len(state.facet_ray_results), 9)
        self.assertGreater(state.facet_error_max_m, 0.001)
        self.assertLess(state.facet_compute_ms, 100.0)

        state.facet_active_ids.remove("F5")
        state.compute_geometry()

        self.assertEqual(len(state.facet_ray_results), 8)
        self.assertTrue(all(result.facet_id != "F5" for result in state.facet_ray_results))


if __name__ == "__main__":
    unittest.main()
