"""
Unit Tests for fallback_engine.py — Sahayak AI / CraftNCode
============================================================
Tests:
1. Fallback ranking by fewest violated criteria.
2. Numerical distance tie-breaking (closer age/income wins).
3. Plain-language missing_criteria_reason formatting.
4. is_fallback: True attribute presence.
5. top_k filtering (top 2–3 closest schemes).
6. Robustness with Pydantic models, dataclasses, dicts, and missing fields.
"""

import os
import sys
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

try:
    from app.services.fallback_engine import (
        CriterionViolation,
        SchemeMismatchEvaluator,
        find_closest_schemes,
        format_missing_criteria_reason,
    )
    from app.services.ranker import UserProfile
except ImportError:
    from fallback_engine import (  # type: ignore[no-redef]
        CriterionViolation,
        SchemeMismatchEvaluator,
        find_closest_schemes,
        format_missing_criteria_reason,
    )
    from ranker import UserProfile  # type: ignore[no-redef]


class TestFallbackEngine(unittest.TestCase):
    def test_single_age_violation_explanation(self):
        """Matches prompt example: Requires age over 60 (your age: 54)."""
        profile = UserProfile(
            age=54,
            gender="male",
            state="Maharashtra",
            annual_income=150000,
        )

        scheme = {
            "name": "Senior Citizen Pension",
            "min_age": 60,
            "state": "Maharashtra",
            "maximum_income": 200000,
        }

        evaluator = SchemeMismatchEvaluator(profile, scheme)
        violations, matched_count, distance = evaluator.evaluate()

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].criterion, "age")
        self.assertEqual(violations[0].reason, "Requires age over 60 (your age: 54)")
        self.assertEqual(matched_count, 2)  # state and income matched

    def test_single_gender_violation_explanation(self):
        """Matches prompt example: Targeted strictly for female applicants."""
        profile = UserProfile(
            age=30,
            gender="male",
            state="Karnataka",
        )

        scheme = {
            "name": "Mahila Samriddhi Yojana",
            "gender": "female",
            "state": "Karnataka",
        }

        evaluator = SchemeMismatchEvaluator(profile, scheme)
        violations, matched_count, distance = evaluator.evaluate()

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].criterion, "gender")
        self.assertEqual(violations[0].reason, "Targeted strictly for female applicants")

    def test_income_violation_explanation(self):
        """Matches income exceeding ceiling."""
        profile = UserProfile(
            annual_income=250000,
            state="Maharashtra",
        )

        scheme = {
            "name": "BPL Subsidy",
            "maximum_income": 200000,
            "state": "Maharashtra",
        }

        evaluator = SchemeMismatchEvaluator(profile, scheme)
        violations, matched_count, distance = evaluator.evaluate()

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].criterion, "income")
        self.assertEqual(
            violations[0].reason,
            "Requires annual income under ₹2,00,000 (your income: ₹2,50,000)"
        )

    def test_farmer_and_disability_violations(self):
        profile = UserProfile(
            is_farmer=False,
            is_disabled=False,
            state="Tamil Nadu",
        )

        scheme_farmer = {"name": "Kisan Credit Scheme", "require_farmer": True}
        scheme_disability = {"name": "Divyangjan Aid", "require_disabled": True}

        eval_farmer = SchemeMismatchEvaluator(profile, scheme_farmer)
        viol_f, _, _ = eval_farmer.evaluate()
        self.assertEqual(viol_f[0].reason, "Requires farmer status")

        eval_dis = SchemeMismatchEvaluator(profile, scheme_disability)
        viol_d, _, _ = eval_dis.evaluate()
        self.assertEqual(viol_d[0].reason, "Requires certified disability status (PwD)")

    def test_ranking_by_fewest_violations(self):
        """Scheme with 1 violation should rank higher than scheme with 2 or 3 violations."""
        profile = UserProfile(
            age=54,
            gender="male",
            state="Maharashtra",
            occupation="tailor",
            annual_income=250000,
            is_farmer=False,
        )

        schemes = [
            {
                "id": "SCH-3-VIOLATIONS",
                "name": "Gujarat Senior Female Pension",
                "state": "Gujarat",       # violation 1
                "gender": "female",       # violation 2
                "min_age": 60,            # violation 3
            },
            {
                "id": "SCH-1-VIOLATION-AGE-60",
                "name": "Maharashtra Senior Pension (Age 60)",
                "state": "Maharashtra",   # matches
                "gender": "all",          # wildcard (matches)
                "min_age": 60,            # violation 1 (age 54 vs 60, diff 6)
            },
            {
                "id": "SCH-2-VIOLATIONS",
                "name": "Maharashtra Women Farmer Aid",
                "state": "Maharashtra",   # matches
                "gender": "female",       # violation 1
                "require_farmer": True,   # violation 2
            },
            {
                "id": "SCH-1-VIOLATION-AGE-75",
                "name": "Maharashtra Super Senior Pension (Age 75)",
                "state": "Maharashtra",   # matches
                "gender": "all",          # matches
                "min_age": 75,            # violation 1 (age 54 vs 75, diff 21)
            },
        ]

        # Top 3 closest
        closest = find_closest_schemes(profile, schemes, top_k=3)

        self.assertEqual(len(closest), 3)

        # 1st place: SCH-1-VIOLATION-AGE-60 (1 violation, distance diff 6)
        self.assertEqual(closest[0]["id"], "SCH-1-VIOLATION-AGE-60")
        self.assertTrue(closest[0]["is_fallback"])
        self.assertEqual(closest[0]["mismatch_count"], 1)
        self.assertEqual(closest[0]["missing_criteria_reason"], "Requires age over 60 (your age: 54).")

        # 2nd place: SCH-1-VIOLATION-AGE-75 (1 violation, but larger distance diff 21)
        self.assertEqual(closest[1]["id"], "SCH-1-VIOLATION-AGE-75")
        self.assertEqual(closest[1]["mismatch_count"], 1)
        self.assertEqual(closest[1]["missing_criteria_reason"], "Requires age over 75 (your age: 54).")

        # 3rd place: SCH-2-VIOLATIONS (2 violations)
        self.assertEqual(closest[2]["id"], "SCH-2-VIOLATIONS")
        self.assertEqual(closest[2]["mismatch_count"], 2)
        self.assertIn("Targeted strictly for female applicants", closest[2]["missing_criteria_reason"])
        self.assertIn("Requires farmer status", closest[2]["missing_criteria_reason"])

    def test_top_k_parameter(self):
        profile = UserProfile(age=20, state="Delhi")
        schemes = [
            {"id": 1, "state": "Punjab"},
            {"id": 2, "state": "Haryana"},
            {"id": 3, "state": "Rajasthan"},
            {"id": 4, "state": "Kerala"},
        ]

        top_2 = find_closest_schemes(profile, schemes, top_k=2)
        self.assertEqual(len(top_2), 2)

        top_1 = find_closest_schemes(profile, schemes, top_k=1)
        self.assertEqual(len(top_1), 1)

        empty = find_closest_schemes(profile, [], top_k=3)
        self.assertEqual(empty, [])

    def test_dict_profile_and_nested_rules(self):
        profile_dict = {
            "age": 54,
            "gender": "male",
            "state": "Maharashtra",
        }

        scheme = {
            "name": "Nested Rule Scheme",
            "criteria": {
                "min_age": 60,
                "gender": "female",
            }
        }

        closest = find_closest_schemes(profile_dict, [scheme], top_k=1)
        self.assertEqual(len(closest), 1)
        self.assertTrue(closest[0]["is_fallback"])
        self.assertEqual(closest[0]["mismatch_count"], 2)
        self.assertIn("Requires age over 60 (your age: 54)", closest[0]["missing_criteria_reason"])
        self.assertIn("Targeted strictly for female applicants", closest[0]["missing_criteria_reason"])

    def test_non_destructive(self):
        profile = UserProfile(age=25)
        orig = {"id": "SCH-1", "min_age": 60}
        schemes = [orig]

        closest = find_closest_schemes(profile, schemes, top_k=1)
        self.assertNotIn("is_fallback", orig)
        self.assertIn("is_fallback", closest[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
