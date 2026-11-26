import unittest
from dataclasses import replace

from ml.mobility_profile import MobilityProfile
from ml.mobility_rules import assess_transitability, evaluate_rule


class MobilityRulesTests(unittest.TestCase):
    def setUp(self):
        self.profile = MobilityProfile("adequate", "minor_problems", "minor", True)
        self.features = {"passage_width": "adequate", "obstruction": "none", "surface_condition": "regular",
                         "level_change": "none", "path_continuity": "continuous"}

    def test_compatible_features(self):
        result = assess_transitability(self.features, self.profile)
        self.assertEqual(result.classification, "transitable")
        self.assertEqual(result.reasons, ())
        self.assertFalse(result.requires_review)
        self.assertEqual(len(result.rule_results), 5)

    def test_individual_rules(self):
        cases = [
            ("passage_width", "narrow", "critical"), ("passage_width", "blocked", "critical"),
            ("passage_width", "very_narrow", "critical"), ("passage_width", "wide", "none"),
            ("obstruction", "partial", "moderate"), ("obstruction", "full", "critical"),
            ("surface_condition", "minor_problem", "moderate"), ("surface_condition", "major_problem", "critical"),
            ("level_change", "minor", "moderate"), ("level_change", "step", "critical"),
            ("path_continuity", "restricted", "moderate"), ("path_continuity", "interrupted", "critical"),
        ]
        for feature, observed, impact in cases:
            with self.subTest(feature=feature, observed=observed):
                result = evaluate_rule(feature, observed, self.profile)
                self.assertEqual(result.impact, impact)
                self.assertEqual(result.feature, feature)
                self.assertEqual(result.observed, observed)
                self.assertTrue(result.code)
                self.assertTrue(result.message)

    def test_profile_changes_tolerance(self):
        strict = replace(self.profile, surface_tolerance="regular_only", level_change_tolerance="none", accepts_partial_obstruction=False)
        for feature, value in (("surface_condition", "minor_problem"), ("level_change", "minor"), ("obstruction", "partial")):
            self.assertEqual(evaluate_rule(feature, value, strict).impact, "critical")
        tolerant = replace(self.profile, surface_tolerance="major_problems", level_change_tolerance="step")
        self.assertEqual(evaluate_rule("surface_condition", "major_problem", tolerant).impact, "moderate")
        self.assertEqual(evaluate_rule("level_change", "step", tolerant).impact, "moderate")

    def test_aggregation_and_critical_precedence(self):
        features = {**self.features, "obstruction": "partial", "level_change": "minor"}
        self.assertEqual(assess_transitability(features, self.profile).classification, "partially_transitable")
        features["surface_condition"] = "unknown"
        self.assertEqual(assess_transitability(features, self.profile).classification, "undetermined")
        features["passage_width"] = "narrow"
        self.assertEqual(assess_transitability(features, self.profile).classification, "non_transitable")

    def test_missing_unknown_and_conflicting_information(self):
        for value in (None, "unknown", ["adequate", "narrow"]):
            result = assess_transitability({**self.features, "passage_width": value}, self.profile)
            self.assertEqual(result.classification, "undetermined")
            self.assertTrue(result.requires_review)
            self.assertFalse(result.rule_results[0].evaluated)
        missing = dict(self.features)
        del missing["surface_condition"]
        self.assertEqual(assess_transitability(missing, self.profile).classification, "undetermined")
        result = assess_transitability({**self.features, "obstruction": "full"}, self.profile)
        self.assertEqual(result.classification, "non_transitable")
        self.assertTrue(result.requires_review)
        self.assertIn("continuity_conflicts_with_blockage", [r.code for r in result.reasons])

    def test_auxiliary_and_future_fields_never_change_classification(self):
        result = assess_transitability({**self.features, "obstacle_type": ["construction", "stairs"],
                                       "surface_obstacle": ["very_broken"], "slope": "steep",
                                       "ramp_condition": "missing_required", "curb_access": "blocked", "detour": "unavailable"},
                                      replace(self.profile, requires_ramp_for_transition=True, slope_tolerance="flat_gentle", accepts_detour=False))
        self.assertEqual(result.classification, "transitable")
        self.assertEqual(assess_transitability({"obstacle_type": ["construction"]}, self.profile).classification, "undetermined")

    def test_reasons_are_structured_and_enriched(self):
        result = assess_transitability({**self.features, "obstruction": "partial", "obstacle_type": ["pole", "tree"],
                                       "surface_condition": "minor_problem", "surface_obstacle": ["cracks"]}, self.profile)
        self.assertEqual(result.classification, "partially_transitable")
        self.assertEqual(len(result.reasons), 2)
        self.assertIn("poste, árvore", result.reasons[0].message)
        self.assertIn("rachaduras", result.reasons[1].message)
        self.assertEqual(result.reasons[0].requirement, True)
        self.assertEqual(result.reasons[0].code, "obstruction_partial_accepted")

    def test_invalid_inputs_fail_explicitly(self):
        with self.assertRaises(ValueError):
            replace(self.profile, minimum_passage_width="90cm")
        with self.assertRaises(ValueError):
            replace(self.profile, accepts_partial_obstruction="yes")
        with self.assertRaises(ValueError):
            assess_transitability({**self.features, "level_change": "invalid"}, self.profile)


if __name__ == "__main__":
    unittest.main()
