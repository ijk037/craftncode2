"""
Test Suite for Recommendation System — Sahayak AI / CraftNCode
===============================================================
Comprehensive unit and integration test suite using `pytest` and FastAPI's `TestClient`.

Test Scenarios:
1. Persona 1 (Marginal Farmer): Targeted agricultural schemes rank top with 'high' confidence.
2. Persona 2 (Student): Educational scholarship matching verified against income/education/gender/state criteria.
3. Persona 3 (Senior Citizen with Disability): Multi-attribute intersection matching across disability and age pensions.
4. Fallback Trigger Case: Persona eligible for 0 schemes receives top 2–3 closest schemes with descriptive `missing_criteria_reason`.
5. Edge Cases & Validation:
   - Missing optional profile fields.
   - Unrecognized / empty scheme catalog.
   - Invalid field types / schema rejections via API endpoint (HTTP 422).
"""

import json
import unittest
from typing import Any, Dict, List, Optional

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

try:
    import pytest
except ImportError:
    pytest = None  # type: ignore

# ── Imports from our modules ─────────────────────────────────────────────────
try:
    from app.services.ranker import UserProfile as RankerProfile
    from app.services.recommender import recommend_schemes
    from app.services.fallback_engine import find_closest_schemes
    from app.api.v1.endpoints.recommend_router import (
        DEFAULT_SCHEMES_CATALOG,
        RecommendationResponse,
        UserProfile,
        get_recommendations,
        get_schemes_datastore,
        router,
    )
except ImportError:
    from ranker import UserProfile as RankerProfile  # type: ignore[no-redef]
    from recommender import recommend_schemes  # type: ignore[no-redef]
    from fallback_engine import find_closest_schemes  # type: ignore[no-redef]
    from router import (  # type: ignore[no-redef]
        DEFAULT_SCHEMES_CATALOG,
        RecommendationResponse,
        UserProfile,
        get_recommendations,
        get_schemes_datastore,
        router,
    )

# ── FastAPI & TestClient Setup ───────────────────────────────────────────────
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


def create_test_app():
    """Create a FastAPI application instance mounted with recommendation router."""
    if not _FASTAPI_AVAILABLE:
        return None
    app = FastAPI(title="Sahayak AI Test App")
    app.include_router(router)
    return app


# Lightweight TestClient simulator if fastapi.testclient is not installed in the runner
class MockFastAPITestClient:
    """Simulates FastAPI TestClient request handling and Pydantic validation."""

    def post(self, url: str, json: Optional[Dict[str, Any]] = None, **kwargs) -> Any:
        payload = json or {}

        # 1. Validation checks for 422 Unprocessable Entity
        errors = []
        age = payload.get("age")
        if age is not None:
            if not isinstance(age, (int, float)) or isinstance(age, bool):
                errors.append({"loc": ["body", "age"], "msg": "value is not a valid integer", "type": "type_error.integer"})
            elif age < 0 or age > 150:
                errors.append({"loc": ["body", "age"], "msg": "ensure this value is within 0 to 150", "type": "value_error.number.not_in_range"})

        income = payload.get("income", payload.get("annual_income"))
        if income is not None:
            if not isinstance(income, (int, float)) or isinstance(income, bool):
                errors.append({"loc": ["body", "income"], "msg": "value is not a valid float", "type": "type_error.float"})
            elif income < 0:
                errors.append({"loc": ["body", "income"], "msg": "ensure this value is greater than or equal to 0", "type": "value_error.number.not_ge"})

        if errors:
            class Mock422Response:
                status_code = 422
                def json(self):
                    return {"detail": errors}
            return Mock422Response()

        # 2. Valid payload -> Execute get_recommendations
        try:
            profile = UserProfile(**payload)
            res_dict = get_recommendations(profile=profile, schemes_data=DEFAULT_SCHEMES_CATALOG)
            class Mock200Response:
                status_code = 200
                def json(self):
                    return res_dict
            return Mock200Response()
        except Exception as e:
            class Mock500Response:
                status_code = 500
                def json(self):
                    return {"detail": str(e)}
            return Mock500Response()


def get_client():
    """Return real TestClient if available, otherwise mock client."""
    if _FASTAPI_AVAILABLE:
        app = create_test_app()
        return TestClient(app)
    return MockFastAPITestClient()


# =============================================================================
# SCENARIO 1: Persona 1 (Marginal Farmer)
# =============================================================================
class TestPersonaMarginalFarmer(unittest.TestCase):
    """
    Scenario 1: Marginal Farmer
    - Profile: Farmer in Maharashtra, small/marginal landholding, income ₹80,000.
    - Expectation: Targeted agricultural schemes (Namo Shetkari Mahasanman / PM-KISAN)
      rank top with 'high' confidence (score >= 40) and specific match reasons.
    """

    def setUp(self):
        self.client = get_client()
        self.payload = {
            "age": 35,
            "gender": "male",
            "occupation": "small_marginal_farmer",
            "income": 80000.0,
            "state": "Maharashtra",
            "category": "OBC",
            "is_farmer": True,
            "farmer_category": "small/marginal",
            "has_disability": False,
        }

    def test_marginal_farmer_ranks_top_with_high_confidence(self):
        response = self.client.post("/api/v1/recommend", json=self.payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertFalse(data["is_fallback"])
        self.assertGreaterEqual(data["total"], 1)

        # Top ranked scheme must be Maharashtra Shetkari or PM-KISAN
        top_scheme = data["data"][0]
        self.assertIn("Namo Shetkari", top_scheme["name"])
        self.assertEqual(top_scheme["confidence"], "high")
        self.assertGreaterEqual(top_scheme["score"], 40)

        # Verify plain-language match reason mentions key attributes
        reason = top_scheme["match_reason"]
        self.assertIn("status as a small/marginal farmer", reason)
        self.assertIn("Maharashtra", reason)
        self.assertIn("₹2,00,000", reason)


# =============================================================================
# SCENARIO 2: Persona 2 (Student)
# =============================================================================
class TestPersonaStudent(unittest.TestCase):
    """
    Scenario 2: Student
    - Profile: 20-year-old female student in Karnataka, annual income ₹1,20,000.
    - Expectation: Pragathi Girl Student Scholarship matches against income,
      age (17–25), gender (female), state (Karnataka), and student occupation.
    """

    def setUp(self):
        self.client = get_client()
        self.payload = {
            "age": 20,
            "gender": "female",
            "occupation": "student",
            "income": 120000.0,
            "state": "Karnataka",
            "education": "secondary",
            "is_farmer": False,
            "has_disability": False,
        }

    def test_student_scholarship_matching(self):
        response = self.client.post("/api/v1/recommend", json=self.payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertFalse(data["is_fallback"])

        # Find the Karnataka Pragathi Scholarship in results
        pragathi_scheme = next(
            (s for s in data["data"] if "Pragathi" in s["name"]), None
        )
        self.assertIsNotNone(pragathi_scheme, "Pragathi scholarship should be in eligible recommendations")
        self.assertEqual(pragathi_scheme["confidence"], "high")
        self.assertGreaterEqual(pragathi_scheme["score"], 40)

        # Check match reason includes female student and Karnataka
        reason = pragathi_scheme["match_reason"]
        self.assertIn("female student", reason)
        self.assertIn("Karnataka", reason)
        self.assertIn("₹3,00,000", reason)


# =============================================================================
# SCENARIO 3: Persona 3 (Senior Citizen with Disability)
# =============================================================================
class TestPersonaSeniorCitizenWithDisability(unittest.TestCase):
    """
    Scenario 3: Senior Citizen with Disability
    - Profile: 65-year-old applicant with certified disability (has_disability=True),
      annual income ₹60,000.
    - Expectation: Multi-attribute intersection matching — Disability support and
      Senior Citizen pension schemes rank at the top.
    """

    def setUp(self):
        self.client = get_client()
        self.payload = {
            "age": 65,
            "gender": "male",
            "occupation": "unemployed",
            "income": 60000.0,
            "state": "all",
            "is_farmer": False,
            "has_disability": True,
        }

    def test_multi_attribute_intersection_matching(self):
        response = self.client.post("/api/v1/recommend", json=self.payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertFalse(data["is_fallback"])
        self.assertGreaterEqual(data["total"], 2)

        # Both Disability Aid and Senior Pension should be present
        scheme_names = [s["name"] for s in data["data"]]
        self.assertTrue(any("Divyang" in name or "Disabilities" in name for name in scheme_names))
        self.assertTrue(any("Old Age Pension" in name or "IGNOAPS" in name for name in scheme_names))

        # Check that top disability scheme matches disability status
        disability_scheme = next(s for s in data["data"] if "Divyang" in s["name"] or "Disabilities" in s["name"])
        self.assertIn("disability status", disability_scheme["match_reason"])


# =============================================================================
# SCENARIO 4: Fallback Trigger Case
# =============================================================================
class TestFallbackTrigger(unittest.TestCase):
    """
    Scenario 4: Fallback Trigger Case
    - Profile: 54-year-old male in Goa with high income (₹12,00,000), not a farmer, no disability.
    - Expectation: Strictly eligible for 0 schemes -> triggers fallback engine.
      Returns status="fallback", is_fallback=True, and top 2–3 closest schemes with
      descriptive missing_criteria_reason.
    """

    def setUp(self):
        self.client = get_client()
        self.payload = {
            "age": 54,
            "gender": "male",
            "occupation": "consultant",
            "income": 1200000.0,
            "state": "Goa",
            "is_farmer": False,
            "has_disability": False,
        }

    def test_fallback_triggered_when_zero_schemes_eligible(self):
        response = self.client.post("/api/v1/recommend", json=self.payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["status"], "fallback")
        self.assertTrue(data["is_fallback"])
        self.assertGreater(data["total"], 0)
        self.assertLessEqual(data["total"], 3)
        self.assertIn("No schemes met all strict eligibility criteria", data["message"])

        # Check that each fallback scheme has missing criteria metadata
        for scheme in data["data"]:
            self.assertTrue(scheme["is_fallback"])
            self.assertIn("missing_criteria_reason", scheme)
            self.assertIn("mismatch_count", scheme)
            self.assertGreater(scheme["mismatch_count"], 0)
            self.assertIsInstance(scheme["missing_criteria_reason"], str)

        # Check that closest schemes highlight specific unmet criteria
        all_reasons = " ".join(s["missing_criteria_reason"] for s in data["data"])
        # Should highlight age requirement for senior pensions and income limit
        self.assertTrue(
            "age" in all_reasons.lower() or "income" in all_reasons.lower() or "farmer" in all_reasons.lower()
        )


# =============================================================================
# SCENARIO 5: Edge Cases & Validation
# =============================================================================
class TestEdgeCasesAndValidation(unittest.TestCase):
    """
    Scenario 5: Edge Cases & Validation
    - Missing optional profile fields.
    - Unrecognized / empty scheme catalog.
    - Invalid field types / schema rejections via API endpoint (HTTP 422).
    """

    def setUp(self):
        self.client = get_client()

    def test_missing_optional_profile_fields(self):
        """Minimal profile with only state provided should not raise 500 error."""
        minimal_payload = {"state": "Maharashtra"}
        response = self.client.post("/api/v1/recommend", json=minimal_payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn(data["status"], ["success", "fallback"])
        self.assertIsInstance(data["data"], list)

    def test_empty_profile_payload(self):
        """Completely empty payload `{}` should be handled safely."""
        response = self.client.post("/api/v1/recommend", json={})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["status"], ["success", "fallback"])

    def test_empty_schemes_catalog(self):
        """Direct call to recommend_schemes with empty catalog returns clean response."""
        profile = RankerProfile(age=30, state="Delhi")
        result = recommend_schemes(profile, [])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["data"], [])
        self.assertFalse(result["is_fallback"])

    def test_schema_rejection_negative_age(self):
        """Negative age should return HTTP 422 Unprocessable Entity."""
        invalid_payload = {"age": -5, "state": "Maharashtra"}
        response = self.client.post("/api/v1/recommend", json=invalid_payload)
        self.assertEqual(response.status_code, 422)

    def test_schema_rejection_age_exceeding_maximum(self):
        """Age > 150 should return HTTP 422 Unprocessable Entity."""
        invalid_payload = {"age": 200, "state": "Maharashtra"}
        response = self.client.post("/api/v1/recommend", json=invalid_payload)
        self.assertEqual(response.status_code, 422)

    def test_schema_rejection_negative_income(self):
        """Negative income should return HTTP 422 Unprocessable Entity."""
        invalid_payload = {"income": -50000.0, "state": "Maharashtra"}
        response = self.client.post("/api/v1/recommend", json=invalid_payload)
        self.assertEqual(response.status_code, 422)

    def test_schema_rejection_invalid_type_age(self):
        """Non-numeric string for age should return HTTP 422 Unprocessable Entity."""
        invalid_payload = {"age": "thirty_five", "state": "Maharashtra"}
        response = self.client.post("/api/v1/recommend", json=invalid_payload)
        self.assertEqual(response.status_code, 422)


# =============================================================================
# Pytest execution entry point
# =============================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
