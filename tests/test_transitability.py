from __future__ import annotations

import unittest

from ml.transitability import UnknownFeatureError, classify_transitability


class TransitabilityTests(unittest.TestCase):
    def test_no_features_is_transitable(self) -> None:
        result = classify_transitability([])

        self.assertEqual(result.classification, "Transitável")
        self.assertEqual(result.detected_features, ())
        self.assertEqual(
            result.justification,
            "Não foram identificadas barreiras consideradas pelo MVP0.",
        )

    def test_single_high_impact_feature_is_not_transitable(self) -> None:
        result = classify_transitability(["height-difference"])

        self.assertEqual(result.classification, "Não transitável")
        self.assertEqual(result.detected_features, ("height-difference",))
        self.assertIn("desnível", result.justification)

    def test_multiple_features_use_the_highest_impact(self) -> None:
        result = classify_transitability(
            ["vegetation", "parked-car", "construction"]
        )

        self.assertEqual(result.classification, "Não transitável")
        self.assertEqual(
            result.detected_features,
            ("vegetation", "parked-car", "construction"),
        )

    def test_justification_is_generated_from_all_friendly_names(self) -> None:
        result = classify_transitability(["pole", "trash-recycling-can", "tree"])

        self.assertEqual(result.classification, "Parcialmente transitável")
        self.assertEqual(
            result.justification,
            "Foram identificadas as seguintes características no trecho: "
            "poste, lixeira ou recipiente de reciclagem e árvore.",
        )

    def test_unknown_feature_raises_controlled_error(self) -> None:
        with self.assertRaisesRegex(
            UnknownFeatureError,
            "Características desconhecidas",
        ):
            classify_transitability(["unknown-label"])


if __name__ == "__main__":
    unittest.main()
