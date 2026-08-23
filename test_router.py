"""
Unit Tests for router.py — Sahayak AI / CraftNCode
===================================================
Tests FastAPI Pydantic models, get_recommendations endpoint handler,
dependency-injected datastore, and error handling.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

try:
    from app.api.v1.endpoints.recommend_router import (
        DEFAULT_SCHEMES_CATALOG,
        RecommendationResponse,
        UserProfile,
        get_recommendations,
        get_schemes_datastore,
        router,
    )
except ImportError:
    from router import (  # type: ignore[no-redef]
        DEFAULT_SCHEMES_CATALOG,
        RecommendationResponse,
        UserProfile,
        get_recommendations,
        get_schemes_datastore,
        router,
    )


class TestRouter(unittest.TestCase):
    def test_user_profile_pydantic_schema_and_aliases(self):
        profile = UserProfile(
            age=35,
            occupation="farmer",
            income=80000.0,
            gender="male",
            state="Maharashtra",
            is_farmer=True,
            has_disability=False,
        )
        profile.sync_aliases()

        self.assertEqual(profile.age, 35)
        self.assertEqual(profile.occupation, "farmer")
        self.assertEqual(profile.income, 80000.0)
        self.assertEqual(profile.annual_income, 80000.0)
        self.assertTrue(profile.is_farmer)
        self.assertFalse(profile.has_disability)
        self.assertFalse(profile.is_disabled)

    def test_get_recommendations_endpoint_success(self):
        """User matches Maharashtra farmer scheme -> status='success', is_fallback=False."""
        profile = UserProfile(
            age=35,
            occupation="farmer",
            income=80000.0,
            gender="male",
            state="Maharashtra",
            is_farmer=True,
            farmer_category="small/marginal",
        )

        response = get_recommendations(profile=profile, schemes_data=DEFAULT_SCHEMES_CATALOG)

        self.assertEqual(response["status"], "success")
        self.assertFalse(response["is_fallback"])
        self.assertGreaterEqual(response["total"], 1)

        # Check top recommendation
        top_scheme = response["data"][0]
        self.assertIn("score", top_scheme)
        self.assertIn("confidence", top_scheme)
        self.assertIn("match_reason", top_scheme)

    def test_get_recommendations_endpoint_fallback(self):
        """User does not match any scheme strictly -> status='fallback', is_fallback=True."""
        profile = UserProfile(
            age=54,
            occupation="astronomer",
            income=950000.0,
            gender="male",
            state="Goa",
            is_farmer=False,
            has_disability=False,
        )

        response = get_recommendations(profile=profile, schemes_data=DEFAULT_SCHEMES_CATALOG)

        self.assertEqual(response["status"], "fallback")
        self.assertTrue(response["is_fallback"])
        self.assertGreater(response["total"], 0)

        # Check fallback metadata
        top_fallback = response["data"][0]
        self.assertTrue(top_fallback["is_fallback"])
        self.assertIn("missing_criteria_reason", top_fallback)
        self.assertIn("mismatch_count", top_fallback)

    def test_custom_schemes_dependency_injection(self):
        custom_schemes = [
            {
                "scheme_id": "CUSTOM-01",
                "name": "Custom Goa Youth Grant",
                "state": "Goa",
                "min_age": 18,
                "max_age": 30,
                "maximum_income": 500000,
            }
        ]

        profile = UserProfile(
            age=24,
            state="Goa",
            income=200000.0,
        )

        response = get_recommendations(profile=profile, schemes_data=custom_schemes)
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["data"][0]["scheme_id"], "CUSTOM-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
