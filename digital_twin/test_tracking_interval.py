"""Pruebas del intervalo de actualizacion de seguimiento de la Etapa 5."""

from __future__ import annotations

import datetime as dt
import unittest

from digital_twin.run_digital_twin import TwinState


class TrackingIntervalTests(unittest.TestCase):
    """Valida pose retenida, correcciones, metricas y modo manual."""

    def make_state(self, interval_s: float | None) -> TwinState:
        state = TwinState()
        state.use_live_time = False
        state.set_simulated_start_time(dt.datetime(2026, 6, 21, 12, 0, 0))
        state.advance_solar_time = True
        state.solar_time_scale = 1.0
        state.peralte = 0.0
        state.automatic = True
        state.free_mode = False
        state.tracking = True
        state.cdr = 0.0
        state.configure_tracking_updates(interval_s)
        state.update(0.0)
        state.clear_history()
        return state

    def test_orientation_is_fixed_between_updates(self) -> None:
        state = self.make_state(10.0)
        initial_normal = state.actual_normal

        state.update(4.0)

        self.assertEqual(state.actual_normal, initial_normal)
        self.assertEqual(state.tracking_update_count, 1)
        self.assertAlmostEqual(state.seconds_since_tracking_update, 4.0)
        self.assertGreater(state.spot_error_radial, 0.0)

    def test_due_interval_corrects_pose_and_resets_timer(self) -> None:
        state = self.make_state(10.0)
        initial_normal = state.actual_normal
        state.update(9.0)
        error_before = state.spot_error_radial

        state.update(1.0)

        self.assertNotEqual(state.actual_normal, initial_normal)
        self.assertEqual(state.tracking_update_count, 2)
        self.assertTrue(state.tracking_corrected_this_step)
        self.assertAlmostEqual(state.seconds_since_tracking_update, 0.0)
        self.assertLess(state.spot_error_radial, error_before)

    def test_correction_counter_matches_selected_interval(self) -> None:
        state = self.make_state(5.0)

        for _ in range(20):
            state.update(1.0)

        # Una correccion inicial y cuatro al cumplirse 5, 10, 15 y 20 s.
        self.assertEqual(state.tracking_update_count, 5)

    def test_large_interval_has_more_error_and_sawtooth_drop(self) -> None:
        fast = self.make_state(1.0)
        slow = self.make_state(60.0)

        for _ in range(120):
            fast.update(1.0)
            slow.update(1.0)

        fast_max = max(float(sample["err_radial"]) for sample in fast.history)
        slow_max = max(float(sample["err_radial"]) for sample in slow.history)
        slow_history = list(slow.history)
        correction_indices = [
            idx for idx, sample in enumerate(slow_history) if sample["tracking_corrected"]
        ]

        self.assertGreater(slow_max, fast_max)
        self.assertGreater(slow_max, 0.0001)
        self.assertTrue(correction_indices)
        last_correction = correction_indices[-1]
        self.assertGreater(last_correction, 0)
        self.assertGreater(
            float(slow_history[last_correction - 1]["err_radial"]),
            float(slow_history[last_correction]["err_radial"]),
        )
        self.assertGreaterEqual(slow.tracking_error_max_m, slow.tracking_error_rms_m)
        self.assertGreaterEqual(slow.tracking_error_rms_m, slow.tracking_error_average_m)

    def test_manual_mode_only_corrects_on_request(self) -> None:
        state = self.make_state(None)
        initial_normal = state.actual_normal

        state.update(30.0)
        self.assertEqual(state.tracking_update_count, 1)
        self.assertEqual(state.actual_normal, initial_normal)
        error_before = state.spot_error_radial

        state.request_tracking_update()
        state.update(0.0)

        self.assertEqual(state.tracking_update_count, 2)
        self.assertTrue(state.tracking_corrected_this_step)
        self.assertLess(state.spot_error_radial, error_before)


if __name__ == "__main__":
    unittest.main()
