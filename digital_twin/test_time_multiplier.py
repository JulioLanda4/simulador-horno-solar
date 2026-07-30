"""Pruebas del multiplicador y controles de tiempo de la Etapa 4."""

from __future__ import annotations

import datetime as dt
import unittest

from digital_twin.run_digital_twin import TwinState, wrap_deg


class TimeMultiplierTests(unittest.TestCase):
    """Valida el reloj simulado sin depender de la interfaz Tkinter."""

    START = dt.datetime(2026, 6, 21, 12, 0, 0)

    def make_state(self) -> TwinState:
        state = TwinState()
        state.use_live_time = False
        state.set_simulated_start_time(self.START)
        state.advance_solar_time = True
        return state

    def test_one_x_matches_real_elapsed_time(self) -> None:
        state = self.make_state()
        state.solar_time_scale = 1.0

        advanced = state.advance_simulation_clock(12.5)

        self.assertAlmostEqual(advanced, 12.5)
        self.assertEqual(state.simulated_time, self.START + dt.timedelta(seconds=12.5))

    def test_sixty_x_turns_one_real_minute_into_one_hour(self) -> None:
        state = self.make_state()
        state.solar_time_scale = 60.0

        advanced = state.advance_simulation_clock(60.0)

        self.assertEqual(advanced, 3600.0)
        self.assertEqual(state.simulated_time, self.START + dt.timedelta(hours=1))

    def test_pause_freezes_simulated_time(self) -> None:
        state = self.make_state()
        state.advance_solar_time = False

        advanced = state.advance_simulation_clock(300.0)

        self.assertEqual(advanced, 0.0)
        self.assertEqual(state.simulated_time, self.START)

    def test_manual_step_uses_configured_amount_while_paused(self) -> None:
        state = self.make_state()
        state.advance_solar_time = False
        state.simulation_step_s = 90.0

        advanced = state.step_simulated_time()

        self.assertEqual(advanced, 90.0)
        self.assertEqual(state.simulated_time, self.START + dt.timedelta(seconds=90))

    def test_reset_returns_to_configured_initial_datetime(self) -> None:
        state = self.make_state()
        new_start = dt.datetime(2026, 12, 5, 8, 30, 0)
        state.set_simulated_start_time(new_start)
        state.solar_time_scale = 120.0
        state.advance_simulation_clock(45.0)

        state.reset_simulated_time()

        self.assertEqual(state.initial_simulated_time, new_start)
        self.assertEqual(state.simulated_time, new_start)
        self.assertEqual(state.seconds_since_last_correction, 0.0)

    def test_solar_position_changes_coherently_after_one_hour_step(self) -> None:
        state = self.make_state()
        state.advance_solar_time = False
        state.compute_geometry()
        initial_azimuth = state.solar_azimuth
        initial_altitude = state.altitude

        state.step_simulated_time(3600.0)
        state.compute_geometry()

        self.assertGreater(abs(wrap_deg(state.solar_azimuth - initial_azimuth)), 1.0)
        self.assertGreater(abs(state.altitude - initial_altitude), 1.0)


if __name__ == "__main__":
    unittest.main()
