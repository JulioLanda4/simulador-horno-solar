"""Pruebas de las estrategias de correccion de deriva de la Etapa 7."""

from __future__ import annotations

import datetime as dt
import unittest

from digital_twin.correction_model import CorrectionConfig, CorrectionModel
from digital_twin.run_digital_twin import TwinState


class CorrectionModelTests(unittest.TestCase):
    """Valida correcciones absolutas, temporales y realimentadas."""

    def test_constant_correction_returns_configured_offset(self) -> None:
        config = CorrectionConfig(
            enabled=True,
            strategy="Offset constante",
            constant_az_deg=-0.7,
            constant_el_deg=0.4,
        )
        model = CorrectionModel(config)

        correction = model.update(0.0, 0.0, 0.0, 0.5)

        self.assertEqual(correction, (-0.7, 0.4))
        self.assertEqual(model.update_count, 1)

    def test_time_dependent_correction_uses_elapsed_hours(self) -> None:
        config = CorrectionConfig(
            enabled=True,
            strategy="Dependiente del tiempo",
            constant_az_deg=0.1,
            constant_el_deg=-0.2,
            time_az_rate_deg_per_hour=0.5,
            time_el_rate_deg_per_hour=-0.25,
        )
        model = CorrectionModel(config)

        correction = model.update(3600.0, 0.0, 0.0, 0.5)

        self.assertAlmostEqual(correction[0], 0.6)
        self.assertAlmostEqual(correction[1], -0.45)

    def test_polynomial_correction_follows_smooth_drift(self) -> None:
        config = CorrectionConfig(
            enabled=True,
            strategy="Polinomial",
            polynomial_az_c0=0.1,
            polynomial_az_c1=0.2,
            polynomial_az_c2=0.3,
            polynomial_el_c0=-0.1,
            polynomial_el_c1=0.4,
            polynomial_el_c2=-0.2,
        )
        model = CorrectionModel(config)

        at_half_hour = model.update(1800.0, 0.0, 0.0, 0.5)
        at_one_hour = model.update(1800.0, 0.0, 0.0, 0.5)

        self.assertAlmostEqual(at_half_hour[0], 0.275)
        self.assertAlmostEqual(at_half_hour[1], 0.05)
        self.assertAlmostEqual(at_one_hour[0], 0.6)
        self.assertAlmostEqual(at_one_hour[1], 0.1)

    def test_periodic_camera_waits_for_its_interval(self) -> None:
        config = CorrectionConfig(
            enabled=True,
            strategy="Camara periodica",
            camera_interval_s=60.0,
            image_max_step_deg=2.0,
        )
        model = CorrectionModel(config)

        before = model.update(59.0, 0.01, -0.01, 0.5)
        after = model.update(1.0, 0.01, -0.01, 0.5)

        self.assertEqual(before, (0.0, 0.0))
        self.assertNotEqual(after, (0.0, 0.0))
        self.assertEqual(model.update_count, 1)

    @staticmethod
    def configured_state() -> TwinState:
        state = TwinState()
        state.use_live_time = False
        state.set_simulated_start_time(dt.datetime(2026, 6, 21, 12, 0, 0))
        state.advance_solar_time = False
        state.peralte = 0.0
        state.compute_geometry()
        state.az.angle_deg = state.target_acim
        state.el.angle_deg = state.target_elev
        state.error_config.enable_azimuth_offset = True
        state.error_config.azimuth_offset_deg = 0.5
        state.error_config.enable_elevation_offset = True
        state.error_config.elevation_offset_deg = -0.35
        state.compute_geometry()
        return state

    def test_constant_correction_reduces_constant_offset(self) -> None:
        state = self.configured_state()
        uncorrected = state.error_spot_radial
        state.correction_config.enabled = True
        state.correction_config.strategy = "Offset constante"
        state.correction_config.constant_az_deg = -0.5
        state.correction_config.constant_el_deg = 0.35

        state._update_drift_correction(0.0)
        state.compute_geometry()

        self.assertLess(state.corrected_spot_radial, uncorrected)
        self.assertLess(state.corrected_spot_radial, 1e-9)

    def test_observed_impact_reduces_error_after_each_update(self) -> None:
        state = self.configured_state()
        state.target_tolerance_m = 0.001
        state.correction_config.enabled = True
        state.correction_config.strategy = "Impacto observado"
        state.correction_config.image_gain_az = 0.5
        state.correction_config.image_gain_el = 0.5
        state.correction_config.image_max_step_deg = 1.0
        errors = [state.corrected_spot_radial]
        self.assertGreater(errors[0], state.target_tolerance_m)

        # Con las dimensiones fisicas completas del perfil (target a 5.55 m),
        # la misma ganancia requiere mas actualizaciones que el antiguo modelo
        # reducido, pero debe conservar convergencia monotona.
        for _ in range(20):
            state.request_drift_correction()
            state._update_drift_correction(0.0)
            state.compute_geometry()
            errors.append(state.corrected_spot_radial)

        for previous, current in zip(errors, errors[1:]):
            self.assertLess(current, previous)
        self.assertLess(errors[-1], state.target_tolerance_m)

    def test_observed_impact_waits_for_manual_button_request(self) -> None:
        state = self.configured_state()
        state.correction_config.enabled = True
        state.correction_config.strategy = "Impacto observado"
        state.tracking_corrected_this_step = True

        state._update_drift_correction(1.0)

        self.assertEqual(state.correction_model.update_count, 0)
        self.assertEqual(state.drift_correction_az_deg, 0.0)
        self.assertEqual(state.drift_correction_el_deg, 0.0)

        state.request_drift_correction()
        state._update_drift_correction(0.0)

        self.assertEqual(state.correction_model.update_count, 1)

    def test_history_contains_without_and_with_correction_for_graph(self) -> None:
        state = self.configured_state()
        state.correction_config.enabled = True
        state.correction_config.strategy = "Offset constante"
        state.correction_config.constant_az_deg = -0.5
        state.correction_config.constant_el_deg = 0.35

        state.update(0.1)
        sample = state.history[-1]

        self.assertIn("error_spot_radial", sample)
        self.assertIn("corrected_spot_radial", sample)
        self.assertIn("drift_correction_az_deg", sample)
        self.assertLess(sample["corrected_spot_radial"], sample["error_spot_radial"])


if __name__ == "__main__":
    unittest.main()
