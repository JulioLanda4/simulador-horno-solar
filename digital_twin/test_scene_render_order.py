"""Pruebas de estabilidad para el orden de profundidad de la vista 3D."""

import unittest

from run_digital_twin import TwinState, choose_scene_front_group


class SceneRenderOrderTests(unittest.TestCase):
    def test_mechanical_guides_are_hidden_by_default(self) -> None:
        self.assertFalse(TwinState().show_mechanical_guides)

    def test_heliostat_is_front_when_its_depth_is_smaller(self) -> None:
        self.assertEqual(
            choose_scene_front_group(1.0, 2.0, "concentrator", 0.01),
            "heliostat",
        )

    def test_concentrator_is_front_when_its_depth_is_smaller(self) -> None:
        self.assertEqual(
            choose_scene_front_group(2.0, 1.0, "heliostat", 0.01),
            "concentrator",
        )

    def test_near_equal_depth_keeps_heliostat_previous_group(self) -> None:
        self.assertEqual(
            choose_scene_front_group(1.000, 1.004, "heliostat", 0.01),
            "heliostat",
        )

    def test_near_equal_depth_keeps_concentrator_previous_group(self) -> None:
        self.assertEqual(
            choose_scene_front_group(1.004, 1.000, "concentrator", 0.01),
            "concentrator",
        )


if __name__ == "__main__":
    unittest.main()
