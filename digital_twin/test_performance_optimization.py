"""Pruebas de las optimizaciones que no deben alterar el modelo fisico."""

import unittest
from types import SimpleNamespace

try:
    from digital_twin.run_digital_twin import (
        DigitalTwinApp,
        MINIHORNO_PROFILE,
        TwinState,
        normalize_spot_resolution,
        render_interval_for_quality,
        spot_heat_color,
    )
except ModuleNotFoundError:
    from run_digital_twin import (
        DigitalTwinApp,
        MINIHORNO_PROFILE,
        TwinState,
        normalize_spot_resolution,
        render_interval_for_quality,
        spot_heat_color,
    )


class RenderQualityTests(unittest.TestCase):
    def test_quality_profiles_only_define_render_intervals(self) -> None:
        self.assertEqual(render_interval_for_quality("Alta"), 0.0)
        self.assertGreater(
            render_interval_for_quality("Rapida"),
            render_interval_for_quality("Equilibrada"),
        )

    def test_unknown_quality_uses_balanced_profile(self) -> None:
        self.assertEqual(
            render_interval_for_quality("desconocida"),
            render_interval_for_quality("Equilibrada"),
        )

    def test_valid_odd_resolution_is_not_changed(self) -> None:
        self.assertEqual(normalize_spot_resolution(101), 101)
        self.assertEqual(normalize_spot_resolution(121), 121)

    def test_even_resolution_moves_to_next_odd_value(self) -> None:
        self.assertEqual(normalize_spot_resolution(100), 101)
        self.assertEqual(normalize_spot_resolution(120), 121)

    def test_minihorno_profile_has_complete_geometry_and_valid_resolution(self) -> None:
        required = {
            "rx",
            "ry",
            "rz",
            "utc_offset_hours",
            "mirror_size_m",
            "base_width_m",
            "fork_height_m",
            "rail_length_m",
            "receiver_screen_m",
            "facet_shape",
            "facet_count",
            "facet_size_m",
            "facet_focal_distance_m",
        }
        self.assertTrue(required.issubset(MINIHORNO_PROFILE))
        self.assertEqual(MINIHORNO_PROFILE["mirror_size_m"], 2.0)
        self.assertEqual(MINIHORNO_PROFILE["utc_offset_hours"], -6.0)
        self.assertFalse(MINIHORNO_PROFILE["scale_to_model"])
        self.assertEqual(
            normalize_spot_resolution(int(MINIHORNO_PROFILE["spot_map_resolution"])),
            MINIHORNO_PROFILE["spot_map_resolution"],
        )

    def test_spot_heat_color_clamps_below_zero_and_above_peak(self) -> None:
        self.assertEqual(spot_heat_color(-1.0, 1.0), spot_heat_color(0.0, 1.0))
        self.assertEqual(spot_heat_color(2.0, 1.0), spot_heat_color(1.0, 1.0))


class OpticalCacheTests(unittest.TestCase):
    def make_enabled_state(self) -> TwinState:
        state = TwinState()
        state.use_live_time = False
        state.facet_field_enabled = True
        state.spot_map_enabled = True
        state.compute_geometry()
        return state

    def test_unchanged_geometry_reuses_facets_and_spot(self) -> None:
        state = self.make_enabled_state()
        facets = state.facets
        spot_map = state.spot_map_result

        state.compute_geometry()

        self.assertIs(state.facets, facets)
        self.assertIs(state.spot_map_result, spot_map)
        self.assertEqual(state.facet_cache_hits, 1)
        self.assertEqual(state.spot_cache_hits, 1)

    def test_spot_parameter_change_only_rebuilds_spot(self) -> None:
        state = self.make_enabled_state()
        facets = state.facets
        spot_map = state.spot_map_result
        state.spot_map_resolution = 53

        state.compute_geometry()

        self.assertIs(state.facets, facets)
        self.assertIsNot(state.spot_map_result, spot_map)
        self.assertEqual(state.spot_map_result.resolution, 53)

    def test_facet_parameter_change_rebuilds_facets_and_spot(self) -> None:
        state = self.make_enabled_state()
        facets = state.facets
        spot_map = state.spot_map_result
        state.facet_size_m += 0.001

        state.compute_geometry()

        self.assertIsNot(state.facets, facets)
        self.assertIsNot(state.spot_map_result, spot_map)

    def test_disabling_model_clears_results_and_cache(self) -> None:
        state = self.make_enabled_state()
        state.facet_field_enabled = False

        state.compute_geometry()

        self.assertEqual(state.facets, [])
        self.assertEqual(state.facet_ray_results, [])
        self.assertIsNone(state.spot_map_result)
        self.assertIsNone(state._facet_cache_signature)
        self.assertIsNone(state._spot_cache_signature)


class _FakeVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class _FakeCanvas:
    def __init__(self, width: int = 800, height: int = 600) -> None:
        self.width = width
        self.height = height
        self.cursor = ""

    def winfo_width(self) -> int:
        return self.width

    def winfo_height(self) -> int:
        return self.height

    def configure(self, **options: str) -> None:
        self.cursor = options.get("cursor", self.cursor)


class FreeViewPanTests(unittest.TestCase):
    def make_app(self, mode: str = "Libre") -> DigitalTwinApp:
        app = object.__new__(DigitalTwinApp)
        app.vars = {"view_mode": _FakeVar(mode)}
        app.free_view_yaw_deg = -38.0
        app.free_view_pitch_deg = 24.0
        app.free_view_pan_x_px = 0.0
        app.free_view_pan_y_px = 0.0
        app.free_view_pan_drag_origin = None
        app.scene_canvas = _FakeCanvas()
        app.render_pending = False
        app.request_render = lambda _event=None: setattr(app, "render_pending", True)
        return app

    def test_left_drag_moves_free_view_in_screen_pixels(self) -> None:
        app = self.make_app()

        app.start_free_view_pan(SimpleNamespace(x=100, y=120))
        app.drag_free_view_pan(SimpleNamespace(x=145, y=95))

        self.assertEqual(app.free_view_pan_x_px, 45.0)
        self.assertEqual(app.free_view_pan_y_px, -25.0)
        self.assertTrue(app.render_pending)
        self.assertEqual(app.scene_canvas.cursor, "fleur")

    def test_fixed_view_ignores_left_drag_and_pan_offset(self) -> None:
        app = self.make_app("Frontal")
        app.free_view_pan_x_px = 90.0
        app.free_view_pan_y_px = -60.0

        app.start_free_view_pan(SimpleNamespace(x=20, y=30))
        center_x, center_y, _depth = app.project((0.0, 0.0, 0.0), 800, 600, 1.0)

        self.assertIsNone(app.free_view_pan_drag_origin)
        self.assertEqual((center_x, center_y), (400.0, 372.0))

    def test_free_view_projection_applies_pan_offset(self) -> None:
        app = self.make_app()
        app.free_view_pan_x_px = 35.0
        app.free_view_pan_y_px = -18.0

        center_x, center_y, _depth = app.project((0.0, 0.0, 0.0), 800, 600, 1.0)

        self.assertEqual((center_x, center_y), (435.0, 354.0))


if __name__ == "__main__":
    unittest.main()
