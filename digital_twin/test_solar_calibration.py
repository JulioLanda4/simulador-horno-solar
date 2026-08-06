"""Regresiones de zona horaria y conversion mecanica/optica del heliostato."""

from __future__ import annotations

import datetime as dt
import unittest

from digital_twin.run_digital_twin import (
    MINIHORNO_PROFILE,
    TwinState,
    angles_from_normal,
    solar_position_db,
    wrap_deg,
)


class SolarCalibrationTests(unittest.TestCase):
    @staticmethod
    def tracked_minihorno(when: dt.datetime) -> TwinState:
        state = TwinState()
        for name, value in MINIHORNO_PROFILE.items():
            if hasattr(state, name):
                setattr(state, name, value)
        state.use_live_time = False
        state.simulated_time = when
        state.advance_solar_time = False
        state.compute_geometry()
        state.az.angle_deg = state.target_acim
        state.el.angle_deg = state.target_elev
        state.az.counts = int(round(state.az.angle_deg * state.az.counts_per_degree))
        state.el.counts = int(round(state.el.angle_deg * state.el.counts_per_degree))
        state.compute_geometry()
        return state

    def test_nonzero_peralte_does_not_displace_ideal_spot(self) -> None:
        dates = (
            dt.datetime(2026, 3, 21, 9, 0),
            dt.datetime(2026, 6, 21, 12, 0),
            dt.datetime(2026, 8, 3, 12, 0),
            dt.datetime(2026, 12, 21, 15, 0),
        )
        for when in dates:
            with self.subTest(when=when):
                state = self.tracked_minihorno(when)
                self.assertAlmostEqual(state.peralte, 0.40)
                self.assertLess(state.ideal_spot_radial, 1e-9)
                self.assertLess(state.error_spot_radial, 1e-9)
                self.assertLess(state.corrected_spot_radial, 1e-9)

    def test_pointing_offsets_are_applied_once_after_peralte_conversion(self) -> None:
        state = self.tracked_minihorno(dt.datetime(2026, 8, 3, 12, 0))
        ideal_az, ideal_el = angles_from_normal(state.ideal_normal)
        state.offset_acim = 0.30
        state.offset_ele = -0.25
        state.compute_geometry()
        state.az.angle_deg = state.target_acim
        state.el.angle_deg = state.target_elev
        state.compute_geometry()
        actual_az, actual_el = angles_from_normal(state.actual_normal)

        self.assertAlmostEqual(wrap_deg(actual_az - ideal_az), 0.30, places=9)
        self.assertAlmostEqual(actual_el - ideal_el, -0.25, places=9)

    def test_peralte_error_is_independent_and_manual_correction_cancels_it(self) -> None:
        state = self.tracked_minihorno(dt.datetime(2026, 8, 3, 12, 0))
        state.error_config.enable_peralte_error = True
        state.error_config.peralte_error_deg = 0.40
        state.compute_geometry()
        uncorrected = state.error_spot_radial

        state.error_config.correction_elevation_deg = -0.40
        state.compute_geometry()

        self.assertGreater(uncorrected, 0.05)
        self.assertLess(state.corrected_spot_radial, 1e-9)

    def test_equal_target_and_heliostat_position_shifts_cancel(self) -> None:
        state = self.tracked_minihorno(dt.datetime(2026, 8, 3, 12, 0))
        state.error_config.enable_target_position_error = True
        state.error_config.target_error_x_m = 0.10
        state.error_config.enable_heliostat_position_error = True
        state.error_config.heliostat_error_x_m = 0.10

        state.compute_geometry()

        self.assertLess(state.error_spot_radial, 1e-9)

    def test_combined_error_sources_never_contaminate_ideal_case(self) -> None:
        state = self.tracked_minihorno(dt.datetime(2026, 8, 3, 12, 0))
        config = state.error_config
        config.enable_elevation_offset = True
        config.elevation_offset_deg = -0.25
        config.enable_azimuth_offset = True
        config.azimuth_offset_deg = 0.30
        config.enable_north_south_misalignment = True
        config.north_south_misalignment_deg = 0.10
        config.enable_target_position_error = True
        config.target_error_x_m = 0.05
        config.enable_heliostat_position_error = True
        config.heliostat_error_z_m = 0.03
        config.enable_peralte_error = True
        config.peralte_error_deg = 0.20
        config.enable_backlash = True
        config.backlash_deg = 0.05
        config.enable_directional_error = True
        config.downward_error_deg = -0.04
        config.enable_random_noise = True
        config.random_noise_std_deg = 0.02
        state.resample_motion_errors(1.0, -1.0)

        state.compute_geometry()

        self.assertLess(state.ideal_spot_radial, 1e-9)
        self.assertGreater(state.error_spot_radial, 0.01)

    def test_minihorno_uses_civil_timezone_instead_of_nearest_meridian(self) -> None:
        when = dt.datetime(2026, 8, 3, 12, 0)
        _zen, _alt, azimuth_utc_minus_6 = solar_position_db(
            when,
            float(MINIHORNO_PROFILE["lat_deg"]),
            float(MINIHORNO_PROFILE["lon_deg"]),
            "D&B",
            float(MINIHORNO_PROFILE["utc_offset_hours"]),
        )
        _zen, _alt, azimuth_wrong_utc_minus_7 = solar_position_db(
            when,
            float(MINIHORNO_PROFILE["lat_deg"]),
            float(MINIHORNO_PROFILE["lon_deg"]),
            "D&B",
            -7.0,
        )

        self.assertLess(azimuth_utc_minus_6, 0.0)
        self.assertGreater(azimuth_wrong_utc_minus_7, 0.0)

    def test_live_clock_is_expressed_in_configured_utc_offset(self) -> None:
        state = TwinState()
        state.use_live_time = True
        state.utc_offset_hours = 3.0
        before = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)
        active = state.active_datetime()
        after = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=3)

        self.assertLessEqual(before.replace(tzinfo=None), active)
        self.assertLessEqual(active, after.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
