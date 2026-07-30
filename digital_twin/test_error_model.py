"""Pruebas de errores geometricos y mecanicos de la Etapa 6."""

from __future__ import annotations

import datetime as dt
import math
import unittest

from digital_twin.error_model import ErrorConfig, ErrorModel, MotionErrorSample
from digital_twin.run_digital_twin import TwinState


class ErrorModelTests(unittest.TestCase):
    """Valida activacion independiente, repetibilidad y sentido mecanico."""

    def test_all_disabled_preserves_nominal_target_and_normal(self) -> None:
        config = ErrorConfig()
        model = ErrorModel(config)
        nominal_target = (0.1, 0.5, -0.03)
        sample = model.sample_motion(2.0, -1.0)

        ideal_normal = model.normal_from_command(15.0, 40.0, sample, False)
        error_normal = model.normal_from_command(15.0, 40.0, sample, True)

        self.assertEqual(model.effective_target(nominal_target, True), nominal_target)
        self.assertEqual(error_normal, ideal_normal)
        self.assertEqual(config.active_error_names(), [])

    def test_angular_errors_can_be_enabled_independently(self) -> None:
        cases = (
            ("enable_elevation_offset", "elevation_offset_deg", 0.4, 1),
            ("enable_azimuth_offset", "azimuth_offset_deg", 0.5, 0),
            ("enable_north_south_misalignment", "north_south_misalignment_deg", 0.6, 0),
            ("enable_peralte_error", "peralte_error_deg", 0.7, 1),
        )
        zero_sample = MotionErrorSample()
        for enable_name, value_name, value, component in cases:
            with self.subTest(error=value_name):
                config = ErrorConfig()
                setattr(config, enable_name, True)
                setattr(config, value_name, value)
                az_error, el_error = ErrorModel(config).angular_errors(zero_sample, False)
                values = (az_error, el_error)
                self.assertAlmostEqual(values[component], value)
                self.assertAlmostEqual(values[1 - component], 0.0)
                self.assertEqual(len(config.active_error_names()), 1)

    def test_target_and_heliostat_position_errors_have_opposite_signs(self) -> None:
        nominal = (0.0, 0.5, 0.0)
        target_config = ErrorConfig(
            enable_target_position_error=True,
            target_error_x_m=0.01,
            target_error_y_m=0.02,
            target_error_z_m=-0.03,
        )
        heliostat_config = ErrorConfig(
            enable_heliostat_position_error=True,
            heliostat_error_x_m=0.01,
            heliostat_error_y_m=0.02,
            heliostat_error_z_m=-0.03,
        )

        self.assertEqual(
            ErrorModel(target_config).effective_target(nominal, True),
            (0.01, 0.52, -0.03),
        )
        self.assertEqual(
            ErrorModel(heliostat_config).effective_target(nominal, True),
            (-0.01, 0.48, 0.03),
        )

    def test_positive_offset_is_repeatable(self) -> None:
        config = ErrorConfig(enable_elevation_offset=True, elevation_offset_deg=0.5)
        model = ErrorModel(config)
        sample = MotionErrorSample()

        first = model.normal_from_command(0.0, 45.0, sample, True)
        second = model.normal_from_command(0.0, 45.0, sample, True)
        ideal = model.normal_from_command(0.0, 45.0, sample, False)

        self.assertEqual(first, second)
        self.assertNotEqual(first, ideal)

    def test_noise_is_small_seeded_and_controllable(self) -> None:
        config_a = ErrorConfig(
            enable_random_noise=True,
            random_noise_std_deg=0.01,
            random_seed=77,
        )
        config_b = ErrorConfig(
            enable_random_noise=True,
            random_noise_std_deg=0.01,
            random_seed=77,
        )

        sample_a = ErrorModel(config_a).sample_motion(0.0, 0.0)
        sample_b = ErrorModel(config_b).sample_motion(0.0, 0.0)

        self.assertEqual(sample_a, sample_b)
        self.assertLess(abs(sample_a.noise_az_deg), 0.05)
        self.assertLess(abs(sample_a.noise_el_deg), 0.05)

    def test_backlash_changes_sign_with_motion_direction(self) -> None:
        config = ErrorConfig(enable_backlash=True, backlash_deg=0.8)
        model = ErrorModel(config)

        positive = model.sample_motion(2.0, 3.0)
        negative = model.sample_motion(-2.0, -3.0)

        self.assertAlmostEqual(positive.backlash_az_deg, -0.8)
        self.assertAlmostEqual(positive.backlash_el_deg, -0.8)
        self.assertAlmostEqual(negative.backlash_az_deg, 0.8)
        self.assertAlmostEqual(negative.backlash_el_deg, 0.8)

    def test_upward_and_downward_errors_are_distinct(self) -> None:
        config = ErrorConfig(
            enable_directional_error=True,
            upward_error_deg=0.25,
            downward_error_deg=-0.40,
        )
        model = ErrorModel(config)

        self.assertAlmostEqual(model.sample_motion(0.0, 1.0).directional_el_deg, 0.25)
        self.assertAlmostEqual(model.sample_motion(0.0, -1.0).directional_el_deg, -0.40)

    def test_manual_correction_can_cancel_constant_offsets(self) -> None:
        config = ErrorConfig(
            enable_azimuth_offset=True,
            azimuth_offset_deg=0.7,
            enable_elevation_offset=True,
            elevation_offset_deg=-0.4,
            correction_azimuth_deg=-0.7,
            correction_elevation_deg=0.4,
        )
        model = ErrorModel(config)
        sample = MotionErrorSample()

        ideal = model.normal_from_command(12.0, 38.0, sample, False)
        corrected = model.normal_from_command(12.0, 38.0, sample, True, corrected=True)

        for ideal_component, corrected_component in zip(ideal, corrected):
            self.assertAlmostEqual(ideal_component, corrected_component, places=12)

    def test_twin_state_compares_three_cases_without_changing_ideal(self) -> None:
        state = TwinState()
        state.use_live_time = False
        state.set_simulated_start_time(dt.datetime(2026, 6, 21, 12, 0, 0))
        state.advance_solar_time = False
        state.peralte = 0.0
        state.compute_geometry()
        state.az.angle_deg = state.target_acim
        state.el.angle_deg = state.target_elev
        state.error_config.enable_elevation_offset = True
        state.error_config.elevation_offset_deg = 0.5
        state.error_config.correction_elevation_deg = -0.5
        state.compute_geometry()

        self.assertTrue(math.isfinite(state.ideal_spot_radial))
        self.assertLess(state.ideal_spot_radial, 1e-9)
        self.assertGreater(state.error_spot_radial, state.ideal_spot_radial)
        self.assertLess(state.corrected_spot_radial, state.error_spot_radial)


if __name__ == "__main__":
    unittest.main()
