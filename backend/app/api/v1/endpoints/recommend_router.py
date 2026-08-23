"""
FastAPI Recommendation API Router — Sahayak AI / CraftNCode
=============================================================
Exposes the recommendation endpoint `POST /api/v1/recommend`.
Integrates Pydantic v1/v2 user profile contracts with `recommender.py`.

Features:
- Validated `UserProfile` request body schema with sensible defaults and field constraints.
- Clean `RecommendationResponse` schema matching standard JSON API envelopes.
- Dependency-injected schemes dataset loader with rich default government scheme catalog.
- Robust HTTP 200 response for both direct and fallback recommendations.
- Standard HTTP 422 Unprocessable Entity responses for malformed payloads.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Union

# Set up module logger
logger = logging.getLogger(__name__)

# ── Optional FastAPI & Pydantic Imports with Resilient Fallbacks ─────────────
try:
    from fastapi import APIRouter, Depends, HTTPException, Query, status
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False
    class APIRouter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.routes: List[Any] = []
        def post(self, path: str, *args: Any, **kwargs: Any) -> Callable:
            def decorator(func: Callable) -> Callable:
                return func
            return decorator
        def get(self, path: str, *args: Any, **kwargs: Any) -> Callable:
            def decorator(func: Callable) -> Callable:
                return func
            return decorator

    def Depends(dependency: Any = None) -> Any:  # type: ignore[no-redef]
        return dependency

    class HTTPException(Exception):  # type: ignore[no-redef]
        def __init__(self, status_code: int, detail: Any = None) -> None:
            self.status_code = status_code
            self.detail = detail
            super().__init__(str(detail))

    class status:  # type: ignore[no-redef]
        HTTP_200_OK = 200
        HTTP_422_UNPROCESSABLE_ENTITY = 422
        HTTP_500_INTERNAL_SERVER_ERROR = 500

try:
    from pydantic import BaseModel, ConfigDict, Field, model_validator
    _HAS_PYDANTIC = True
except ImportError:
    try:
        from pydantic import BaseModel, Field, root_validator as model_validator  # type: ignore[no-redef]
        ConfigDict = None  # type: ignore[assignment, misc]
        _HAS_PYDANTIC = True
    except ImportError:
        _HAS_PYDANTIC = False
        BaseModel = object  # type: ignore[assignment, misc]
        ConfigDict = None  # type: ignore[assignment, misc]
        Field = lambda default=None, **kwargs: default  # type: ignore[assignment]
        model_validator = lambda *args, **kwargs: lambda func: func  # type: ignore[assignment]

# ── Recommender Engine Integration ──────────────────────────────────────────
try:
    from app.services.recommender import recommend_schemes
    from app.services.ranker import UserProfile as RankerUserProfile
except ImportError:
    try:
        from recommender import recommend_schemes  # type: ignore[no-redef]
        from ranker import UserProfile as RankerUserProfile  # type: ignore[no-redef]
    except ImportError:
        raise ImportError("Could not import 'recommend_schemes' from recommender.py")


# ── Pydantic Request & Response Schemas ──────────────────────────────────────
if _HAS_PYDANTIC and BaseModel is not object:

    class UserProfile(BaseModel):
        """
        Pydantic contract for citizen demographic & socio-economic profile.
        Includes robust constraints and sensible defaults.
        """
        if ConfigDict is not None:
            model_config = ConfigDict(extra="allow", populate_by_name=True)
        else:
            class Config:
                extra = "allow"
                allow_population_by_field_name = True

        age: Optional[int] = Field(
            default=None,
            ge=0,
            le=150,
            description="Age of the citizen in years (0–150)"
        )
        occupation: Optional[str] = Field(
            default=None,
            description="Primary occupation or profession (e.g. 'farmer', 'student', 'artisan', 'weaver')"
        )
        income: Optional[float] = Field(
            default=None,
            ge=0.0,
            description="Annual household income in INR"
        )
        annual_income: Optional[float] = Field(
            default=None,
            ge=0.0,
            description="Alias for annual income in INR"
        )
        gender: Optional[str] = Field(
            default=None,
            description="Gender of the applicant (e.g. 'male', 'female', 'transgender', 'other')"
        )
        state: Optional[str] = Field(
            default=None,
            description="State or Union Territory of residence (e.g. 'Maharashtra', 'Karnataka')"
        )
        district: Optional[str] = Field(
            default=None,
            description="District of residence (e.g. 'Pune', 'Bengaluru')"
        )
        category: Optional[str] = Field(
            default=None,
            description="Social / caste category (e.g. 'SC', 'ST', 'OBC', 'General', 'EWS')"
        )
        education: Optional[str] = Field(
            default=None,
            description="Highest education level achieved (e.g. 'secondary', 'graduate')"
        )
        is_farmer: bool = Field(
            default=False,
            description="Whether the applicant is an agricultural farmer"
        )
        farmer_category: Optional[str] = Field(
            default=None,
            description="Farmer classification (e.g. 'small', 'marginal', 'large')"
        )
        has_disability: bool = Field(
            default=False,
            description="Whether the applicant has a certified disability (PwD)"
        )
        is_disabled: Optional[bool] = Field(
            default=None,
            description="Alias for has_disability"
        )

        def sync_aliases(self) -> "UserProfile":
            """Synchronize field aliases (income vs annual_income, has_disability vs is_disabled)."""
            if self.income is None and self.annual_income is not None:
                object.__setattr__(self, "income", self.annual_income)
            elif self.annual_income is None and self.income is not None:
                object.__setattr__(self, "annual_income", self.income)

            if self.is_disabled is not None:
                if self.is_disabled and not self.has_disability:
                    object.__setattr__(self, "has_disability", True)
            else:
                object.__setattr__(self, "is_disabled", self.has_disability)
            return self

    class RecommendationMetadata(BaseModel):
        """Metadata summary for recommendation pipeline execution."""
        status: Literal["success", "fallback"]
        total_evaluated: int
        eligible_count: int
        fallback_count: int

    class RecommendationResponse(BaseModel):
        """
        Clean, JSON-serializable API envelope for scheme recommendations.
        """
        if ConfigDict is not None:
            model_config = ConfigDict(extra="allow")

        status: Literal["success", "fallback"] = Field(
            description="'success' if strictly eligible schemes were found, 'fallback' if closest alternatives are returned"
        )
        is_fallback: bool = Field(
            description="True when results represent closest fallback alternatives rather than strict matches"
        )
        total: int = Field(
            ge=0,
            description="Total number of schemes returned in the data array"
        )
        count: int = Field(
            ge=0,
            description="Alias for total"
        )
        message: str = Field(
            description="Human-readable summary explanation of the recommendation results"
        )
        data: List[Dict[str, Any]] = Field(
            default_factory=list,
            description="List of recommended or closest fallback scheme objects"
        )
        meta: Optional[RecommendationMetadata] = Field(
            default=None,
            description="Processing metrics and counts"
        )

else:
    # Dataclass fallbacks if Pydantic is not installed
    from dataclasses import dataclass

    @dataclass
    class UserProfile:  # type: ignore[no-redef]
        age: Optional[int] = None
        occupation: Optional[str] = None
        income: Optional[float] = None
        annual_income: Optional[float] = None
        gender: Optional[str] = None
        state: Optional[str] = None
        district: Optional[str] = None
        category: Optional[str] = None
        education: Optional[str] = None
        is_farmer: bool = False
        farmer_category: Optional[str] = None
        has_disability: bool = False
        is_disabled: Optional[bool] = None

        def sync_aliases(self) -> "UserProfile":
            if self.income is None and self.annual_income is not None:
                self.income = self.annual_income
            elif self.annual_income is None and self.income is not None:
                self.annual_income = self.income
            if self.is_disabled is not None:
                if self.is_disabled:
                    self.has_disability = True
            else:
                self.is_disabled = self.has_disability
            return self

    @dataclass
    class RecommendationMetadata:  # type: ignore[no-redef]
        status: str
        total_evaluated: int
        eligible_count: int
        fallback_count: int

    @dataclass
    class RecommendationResponse:  # type: ignore[no-redef]
        status: str
        is_fallback: bool
        total: int
        count: int
        message: str
        data: List[Dict[str, Any]]
        meta: Optional[RecommendationMetadata] = None


# ── Built-in Schemes Dataset Store ───────────────────────────────────────────
DEFAULT_SCHEMES_CATALOG: List[Dict[str, Any]] = [
    {
        "scheme_id": "PM-KISAN-001",
        "name": "Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)",
        "scheme_code": "PM-KISAN",
        "scheme_type": "Central",
        "category_name": "Agriculture",
        "state": "all",
        "require_farmer": True,
        "target_occupation": "farmer",
        "maximum_income": None,
        "benefits": "₹6,000 per year in three equal installments to eligible farmer families",
    },
    {
        "scheme_id": "MH-SHETKARI-002",
        "name": "Namo Shetkari Mahasanman Nidhi Yojana",
        "scheme_code": "MH-SHETKARI",
        "scheme_type": "State",
        "category_name": "Agriculture",
        "state": "Maharashtra",
        "require_farmer": True,
        "target_occupation": "farmer",
        "maximum_income": 200000,
        "benefits": "Additional ₹6,000 annual financial assistance for farmers in Maharashtra",
    },
    {
        "scheme_id": "KA-PRAGATHI-003",
        "name": "Pragathi Girl Student Higher Education Scholarship",
        "scheme_code": "KA-PRAGATHI",
        "scheme_type": "State",
        "category_name": "Education",
        "state": "Karnataka",
        "gender": "female",
        "target_occupation": "student",
        "min_age": 17,
        "max_age": 25,
        "maximum_income": 300000,
        "benefits": "₹50,000 per annum towards technical degree tuition assistance",
    },
    {
        "scheme_id": "NAT-DIVYANG-004",
        "name": "National Scheme for Persons with Disabilities (Divyangjan Sahayata)",
        "scheme_code": "NAT-DIVYANG",
        "scheme_type": "Central",
        "category_name": "Social Welfare",
        "state": "all",
        "require_disabled": True,
        "maximum_income": 250000,
        "benefits": "Financial aid, assistive aids, and skill development support",
    },
    {
        "scheme_id": "MH-ARTISAN-005",
        "name": "Maharashtra Hastkala & Bunkar Vikas Yojana",
        "scheme_code": "MH-ARTISAN",
        "scheme_type": "State",
        "category_name": "Handicrafts & Handlooms",
        "state": "Maharashtra",
        "target_occupation": "artisan",
        "maximum_income": 180000,
        "benefits": "Working capital subsidy up to ₹50,000 and subsidized toolkits",
    },
    {
        "scheme_id": "NAT-SENIOR-006",
        "name": "Indira Gandhi National Old Age Pension Scheme (IGNOAPS)",
        "scheme_code": "IGNOAPS",
        "scheme_type": "Central",
        "category_name": "Pension",
        "state": "all",
        "min_age": 60,
        "maximum_income": 100000,
        "benefits": "Monthly pension for senior citizens living below poverty line",
    }
]


def get_schemes_datastore() -> List[Dict[str, Any]]:
    """
    Dependency provider for government schemes catalog.
    Can be overridden in FastAPI dependency injection for DB or external service integration.
    """
    return copy.deepcopy(DEFAULT_SCHEMES_CATALOG)


# ── FastAPI Router Definition ────────────────────────────────────────────────
router = APIRouter(tags=["Recommendations"])


@router.post(
    "/api/v1/recommend",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Scheme Recommendations",
    description=(
        "Evaluates a user profile against all available government schemes. "
        "Returns strictly eligible schemes ranked by demographic specificity (status='success'). "
        "If zero schemes match strictly, returns closest fallback schemes with missing criteria explanations (status='fallback')."
    ),
)
@router.post(
    "/recommend",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_recommendations(
    profile: UserProfile,
    schemes_data: List[Dict[str, Any]] = Depends(get_schemes_datastore)
) -> Dict[str, Any]:
    """
    HTTP POST endpoint handler for `/api/v1/recommend`.
    """
    try:
        # Synchronize alias fields on profile
        if hasattr(profile, "sync_aliases"):
            profile.sync_aliases()

        # Map to ranker UserProfile if needed
        profile_dict = (
            profile.model_dump() if hasattr(profile, "model_dump") else (
                profile.dict() if hasattr(profile, "dict") else profile.__dict__
            )
        )

        ranker_profile = RankerUserProfile(
            age=profile_dict.get("age"),
            gender=profile_dict.get("gender"),
            occupation=profile_dict.get("occupation"),
            annual_income=profile_dict.get("annual_income") or profile_dict.get("income"),
            income=profile_dict.get("income") or profile_dict.get("annual_income"),
            state=profile_dict.get("state"),
            district=profile_dict.get("district"),
            category=profile_dict.get("category"),
            education=profile_dict.get("education"),
            is_farmer=bool(profile_dict.get("is_farmer", False)),
            farmer_category=profile_dict.get("farmer_category"),
            is_disabled=bool(profile_dict.get("has_disability", False) or profile_dict.get("is_disabled", False)),
        )

        result = recommend_schemes(ranker_profile, schemes_data)
        return result

    except Exception as exc:
        logger.error("Failed to generate recommendations: %s", str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while evaluating recommendations: {str(exc)}"
        )


__all__ = [
    "UserProfile",
    "RecommendationMetadata",
    "RecommendationResponse",
    "DEFAULT_SCHEMES_CATALOG",
    "get_schemes_datastore",
    "get_recommendations",
    "router",
]
