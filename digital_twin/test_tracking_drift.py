"""Pruebas de seguimiento detenido y deriva temporal de la Etapa 3."""

from __future__ import annotations

import datetime as dt
import unittest

from digital_twin.run_digital_twin import TwinState


class TrackingDriftTests(unittest.TestCase):
    """Valida reloj solar, pose fija, trayectoria y limite de historial."""

    def make_centered_state(self) -> TwinState:
        """Crea un caso diurno determinista inicialmente bien apuntado."""
        state = TwinState()
        state.use_live_time = False
        state.simulated_time = dt.datetime(2026, 6, 21, 12, 0, 0)
        state.advance_solar_time = False
        state.peralte = 0.0
        state.automatic = True
        state.free_mode = False
        state.tracking = True
        state.cdr = 0.0
        state.compute_geometry()
        state.az.angle_deg = state.target_acim
        state.el.angle_deg = state.target_elev
        state.az.target_deg = state.target_acim
        state.el.target_deg = state.target_elev
        state.compute_geometry()
        state.clear_history()
        return state

    def test_active_tracking_keeps_spot_near_center(self) -> None:
        state = self.make_centered_state()
        state.advance_solar_time = True
        state.solar_time_scale = 60.0

        for _ in range(10):
            state.update(1.0)

        self.assertTrue(state.spot_valid)
        self.assertLess(state.spot_error_radial, 0.005)

    def test_stopped_tracking_keeps_normal_fixed_and_spot_drifts(self) -> None:
        state = self.make_centered_state()
        initial_normal = state.actual_normal
        initial_error = state.spot_error_radial
        initial_time = state.simulated_time
        state.tracking = False
        state.advance_solar_time = True
        state.solar_time_scale = 60.0

        radial_errors = []
        for _ in range(10):
            state.update(1.0)
            radial_errors.append(state.spot_error_radial)

        self.assertEqual(state.actual_normal, initial_normal)
        self.assertEqual(state.simulated_time, initial_time + dt.timedelta(minutes=10))
        self.assertGreater(radial_errors[-1], initial_error + 0.005)
        self.assertGreater(radial_errors[-1], radial_errors[0])
        self.assertAlmostEqual(state.seconds_since_last_correction, 600.0)

    def test_history_respects_configurable_limit(self) -> None:
        state = self.make_centered_state()
        state.set_history_limit(5)
        state.tracking = False

        for _ in range(12):
            state.update(0.1)

        self.assertEqual(state.history_limit, 5)
        self.assertEqual(state.history.maxlen, 5)
        self.assertEqual(len(state.history), 5)

    def test_clear_history_removes_path(self) -> None:
        state = self.make_centered_state()
        for _ in range(4):
            state.update(0.1)
        self.assertGreater(len(state.history), 0)

        state.clear_history()

        self.assertEqual(len(state.history), 0)

    def test_simulated_clock_can_be_paused_independently(self) -> None:
        state = self.make_centered_state()
        initial_time = state.simulated_time
        state.tracking = False
        state.advance_solar_time = False

        state.update(15.0)

        self.assertEqual(state.simulated_time, initial_time)


if __name__ == "__main__":
    unittest.main()
