"""
Comprehensive Test Suite for ranker.py — Sahayak AI / CraftNCode
==================================================================
Tests:
1. Scoring Weight System:
   - Specific attributes (occupation, farmer status, disability status, income threshold, category): 15-20 pts
   - General demographics (age, gender, state, district, education): 5-10 pts
   - Wildcards / 'any' / 'all' / None: 0 pts
2. Output Attributes per Scheme:
   - score: Total integer score (descending sort order)
   - confidence: 'high' (>=40), 'medium' (20-39), 'low' (<20)
   - match_reason: Single clear, plain-language sentence
3. Type Hinting & Robustness:
   - Pydantic models (v1 & v2)
   - Dataclasses
   - Dictionaries
   - Missing / None fields handled gracefully
   - Non-destructive operation
"""

import os
import sys
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

try:
    from app.services.ranker import (
        CONFIDENCE_HIGH_THRESHOLD,
        CONFIDENCE_MEDIUM_THRESHOLD,
        DEFAULT_WEIGHTS,
        ScoringWeights,
        UserProfile,
        calculate_confidence,
        format_indian_currency,
        rank_schemes,
        score_scheme,
    )
except ImportError:
    from ranker import (  # type: ignore[no-redef]
        CONFIDENCE_HIGH_THRESHOLD,
        CONFIDENCE_MEDIUM_THRESHOLD,
        DEFAULT_WEIGHTS,
        ScoringWeights,
        UserProfile,
        calculate_confidence,
        format_indian_currency,
        rank_schemes,
        score_scheme,
    )


class TestCurrencyFormatter(unittest.TestCase):
    def test_indian_currency_formatting(self):
        self.assertEqual(format_indian_currency(200000), "₹2,00,000")
        self.assertEqual(format_indian_currency(1500000), "₹15,00,000")
        self.assertEqual(format_indian_currency(50000), "₹50,000")
        self.assertEqual(format_indian_currency(500), "₹500")
        self.assertEqual(format_indian_currency("250000"), "₹2,50,000")
        self.assertEqual(format_indian_currency("10,00,000"), "₹10,00,000")


class TestConfidenceCalculation(unittest.TestCase):
    def test_confidence_thresholds(self):
        # High (>= 40)
        self.assertEqual(calculate_confidence(40), "high")
        self.assertEqual(calculate_confidence(41), "high")
        self.assertEqual(calculate_confidence(100), "high")

        # Medium (20-39)
        self.assertEqual(calculate_confidence(39), "medium")
        self.assertEqual(calculate_confidence(20), "medium")
        self.assertEqual(calculate_confidence(25), "medium")

        # Low (< 20)
        self.assertEqual(calculate_confidence(19), "low")
        self.assertEqual(calculate_confidence(5), "low")
        self.assertEqual(calculate_confidence(0), "low")


class TestScoringAndRanking(unittest.TestCase):
    def test_farmer_maharashtra_income_matching(self):
        """Matches the example in user prompt: small/marginal farmer in Maharashtra with income under ₹2,00,000."""
        profile = UserProfile(
            state="Maharashtra",
            occupation="small_marginal_farmer",
            is_farmer=True,
            farmer_category="small/marginal",
            annual_income=80000,
            category="OBC",
            age=35,
            gender="male",
        )

        schemes = [
            {
                "scheme_id": "SCH-001",
                "name": "Maharashtra Shetkari Sanman Yojana",
                "require_farmer": True,
                "target_occupation": "farmer",
                "state": "Maharashtra",
                "maximum_income": 200000,
                "category": "any",
                "gender": "all",
            },
            {
                "scheme_id": "SCH-002",
                "name": "Universal Health Scheme",
                "state": "all",
                "occupation": "any",
                "gender": "all",
            },
            {
                "scheme_id": "SCH-003",
                "name": "State Artisan Welfare",
                "state": "Maharashtra",
                "target_occupation": "artisan",
                "maximum_income": 150000,
            },
        ]

        ranked = rank_schemes(profile, schemes)

        # Assertions on order and score
        self.assertEqual(len(ranked), 3)
        self.assertEqual(ranked[0]["scheme_id"], "SCH-001")
        # Farmer (20) + State (10) + Income (15) = 45
        self.assertEqual(ranked[0]["score"], 45)
        self.assertEqual(ranked[0]["confidence"], "high")
        self.assertEqual(
            ranked[0]["match_reason"],
            "Matched based on your status as a small/marginal farmer in Maharashtra with income under ₹2,00,000."
        )

        # SCH-003: State (10) + Income (15) = 25 (Occupation didn't match)
        self.assertEqual(ranked[1]["scheme_id"], "SCH-003")
        self.assertEqual(ranked[1]["score"], 25)
        self.assertEqual(ranked[1]["confidence"], "medium")

        # SCH-002: All wildcards = 0 points
        self.assertEqual(ranked[2]["scheme_id"], "SCH-002")
        self.assertEqual(ranked[2]["score"], 0)
        self.assertEqual(ranked[2]["confidence"], "low")
        self.assertEqual(ranked[2]["match_reason"], "Matched based on general eligibility criteria.")

    def test_female_student_karnataka(self):
        profile = UserProfile(
            state="Karnataka",
            occupation="student",
            gender="female",
            annual_income=120000,
            category="OBC",
            age=21,
        )

        scheme = {
            "name": "Pragathi Girl Student Scholarship",
            "state": "Karnataka",
            "target_occupation": "student",
            "gender": "female",
            "category": "OBC",
            "maximum_income": 300000,
            "min_age": 18,
            "max_age": 25,
        }

        score, confidence, reason = score_scheme(profile, scheme)
        # Occupation (20) + Category (15) + Income (15) + State (10) + Gender (10) + Age (10) = 80
        self.assertEqual(score, 80)
        self.assertEqual(confidence, "high")
        self.assertIn("your status as a female student in Karnataka", reason)
        self.assertIn("under the OBC category", reason)
        self.assertIn("with income under ₹3,00,000", reason)

    def test_disability_status_scoring(self):
        profile = UserProfile(
            is_disabled=True,
            state="Kerala",
        )

        scheme = {
            "name": "Divyangjan Special Pension",
            "require_disabled": True,
            "state": "Kerala",
        }

        score, confidence, reason = score_scheme(profile, scheme)
        # Disability (20) + State (10) = 30
        self.assertEqual(score, 30)
        self.assertEqual(confidence, "medium")
        self.assertEqual(reason, "Matched based on your disability status in Kerala.")

    def test_wildcard_criteria_get_zero_points(self):
        profile = UserProfile(
            age=30,
            gender="female",
            state="Tamil Nadu",
            occupation="tailor",
            annual_income=90000,
        )

        scheme = {
            "name": "Open National Welfare Fund",
            "state": "all",
            "gender": "any",
            "occupation": "*",
            "category": "N/A",
            "min_age": None,
            "max_age": None,
            "max_income": None,
        }

        score, confidence, reason = score_scheme(profile, scheme)
        self.assertEqual(score, 0)
        self.assertEqual(confidence, "low")
        self.assertEqual(reason, "Matched based on general eligibility criteria.")

    def test_missing_optional_profile_fields(self):
        """Profile with all None fields should not crash."""
        empty_profile = UserProfile()
        scheme = {
            "name": "Test Scheme",
            "state": "Gujarat",
            "maximum_income": 200000,
            "require_farmer": True,
        }

        score, confidence, reason = score_scheme(empty_profile, scheme)
        self.assertEqual(score, 0)
        self.assertEqual(confidence, "low")
        self.assertIsInstance(reason, str)

    def test_custom_dataclass_profile(self):
        """Should work seamlessly with standard dataclasses."""
        @dataclass
        class CustomProfile:
            state: str
            occupation: str
            annual_income: int
            is_farmer: bool = False
            is_disabled: bool = False
            age: int = 28
            gender: str = "male"
            category: str = "General"

        custom_profile = CustomProfile(
            state="Rajasthan",
            occupation="artisan",
            annual_income=150000,
        )

        scheme = {
            "name": "Hastkala Vikas Yojana",
            "target_occupation": "artisan",
            "state": "Rajasthan",
            "maximum_income": 200000,
        }

        score, confidence, reason = score_scheme(custom_profile, scheme)
        # Occupation (20) + State (10) + Income (15) = 45
        self.assertEqual(score, 45)
        self.assertEqual(confidence, "high")
        self.assertEqual(reason, "Matched based on your occupation as an artisan in Rajasthan with income under ₹2,00,000.")

    def test_dict_profile(self):
        """Should work with raw dictionary profile."""
        profile_dict = {
            "state": "Punjab",
            "is_farmer": True,
            "annual_income": 180000,
        }

        scheme = {
            "name": "Punjab Kisan Rahat",
            "require_farmer": True,
            "state": "Punjab",
            "max_income": 250000,
        }

        score, confidence, reason = score_scheme(profile_dict, scheme)
        # Farmer (20) + State (10) + Income (15) = 45
        self.assertEqual(score, 45)
        self.assertEqual(confidence, "high")

    def test_nested_criteria_scheme_dict(self):
        """Should extract criteria from nested 'criteria' or 'rules' dict."""
        profile = UserProfile(
            state="Bihar",
            occupation="weaver",
            annual_income=100000,
        )

        scheme = {
            "name": "Bunkar Sahayata",
            "criteria": {
                "state": "Bihar",
                "occupation": "weaver",
                "max_income": 150000,
            }
        }

        score, confidence, reason = score_scheme(profile, scheme)
        self.assertEqual(score, 45)
        self.assertEqual(confidence, "high")

    def test_sorting_descending_multiple_schemes(self):
        profile = UserProfile(
            state="Odisha",
            occupation="farmer",
            is_farmer=True,
            annual_income=70000,
            category="SC",
            age=40,
        )

        schemes = [
            {"id": 1, "name": "General Scheme", "state": "any"}, # score 0
            {"id": 2, "name": "Odisha State Scheme", "state": "Odisha"}, # score 10
            {"id": 3, "name": "Odisha SC Farmer Scheme", "state": "Odisha", "category": "SC", "require_farmer": True}, # 10 + 15 + 20 = 45
            {"id": 4, "name": "Odisha Farmer Low Income", "state": "Odisha", "require_farmer": True, "max_income": 100000}, # 10 + 20 + 15 = 45
            {"id": 5, "name": "Odisha SC Farmer Low Income", "state": "Odisha", "category": "SC", "require_farmer": True, "max_income": 100000}, # 10 + 15 + 20 + 15 = 60
        ]

        ranked = rank_schemes(profile, schemes)
        scores = [s["score"] for s in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(ranked[0]["id"], 5)
        self.assertEqual(ranked[0]["score"], 60)
        self.assertEqual(ranked[0]["confidence"], "high")

    def test_custom_weights(self):
        """Verify custom weights override defaults correctly."""
        custom_weights = ScoringWeights(
            OCCUPATION=18,
            STATE=8,
            INCOME_THRESHOLD=16,
        )
        profile = UserProfile(
            occupation="tailor",
            state="Assam",
            annual_income=50000,
        )
        scheme = {
            "target_occupation": "tailor",
            "state": "Assam",
            "maximum_income": 100000,
        }

        score, confidence, reason = score_scheme(profile, scheme, weights=custom_weights)
        # 18 + 8 + 16 = 42
        self.assertEqual(score, 42)
        self.assertEqual(confidence, "high")

    def test_non_destructive_ranking(self):
        """Input list and dictionaries should not be mutated."""
        profile = UserProfile(state="Goa")
        original_scheme = {"name": "Goa Scheme", "state": "Goa"}
        schemes_list = [original_scheme]

        ranked = rank_schemes(profile, schemes_list)

        self.assertNotIn("score", original_scheme)
        self.assertIn("score", ranked[0])
        self.assertEqual(len(schemes_list), 1)

    def test_empty_schemes_list(self):
        profile = UserProfile()
        self.assertEqual(rank_schemes(profile, []), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
