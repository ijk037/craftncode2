"""
Production-grade Scheme Ranker Module — Sahayak AI / CraftNCode
=================================================================
Implements intelligent, multi-factor deterministic ranking for eligible
government schemes based on user profile demographic and socio-economic
specificity.

Key Features:
- Scoring Weight System:
  * Specific attributes (occupation, farmer status, disability status, income ceiling,
    vulnerable social category): 15–20 points each.
  * General demographics (age bracket, gender, state, district, education): 5–10 points each.
  * Wildcards / 'any' / 'all' / unrestricted criteria: 0 points.
- Output Attributes per Scheme:
  * `score`: Total integer score (sorted in descending order).
  * `confidence`: "high" (score >= 40), "medium" (20–39), or "low" (< 20).
  * `match_reason`: A single, clear, plain-language sentence highlighting primary matching attributes.
- Type Hinting & Extreme Robustness:
  * Supports Pydantic v1, Pydantic v2, standard dataclasses, dicts, or custom objects.
  * Gracefully handles missing optional fields, malformed types, and edge cases.
  * Pure & non-destructive: input scheme dicts are never mutated in-place.
"""

from __future__ import annotations

import copy
import dataclasses
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Set, Tuple, Union

# Set up module logger
logger = logging.getLogger(__name__)

# ── Optional Pydantic Support with Fallback ──────────────────────────────────
try:
    from pydantic import BaseModel, ConfigDict, Field
    _HAS_PYDANTIC = True
except ImportError:
    try:
        from pydantic import BaseModel, Field  # type: ignore[no-redef]
        ConfigDict = None  # type: ignore[assignment, misc]
        _HAS_PYDANTIC = True
    except ImportError:
        _HAS_PYDANTIC = False
        BaseModel = object  # type: ignore[assignment, misc]
        ConfigDict = None  # type: ignore[assignment, misc]
        Field = lambda default=None, **kwargs: default  # type: ignore[assignment]


# ── Confidence Types ─────────────────────────────────────────────────────────
ConfidenceLevel = Literal["high", "medium", "low"]


# ── Scoring Weights Configuration ────────────────────────────────────────────
@dataclass(frozen=True)
class ScoringWeights:
    """
    Scoring weights conforming to:
    - Specific attributes: 15–20 points each.
    - General demographics: 5–10 points each.
    - Wildcard / 'any': 0 points.
    """
    # Specific attributes (15–20 points)
    OCCUPATION: int = 20
    FARMER_STATUS: int = 20
    DISABILITY_STATUS: int = 20
    INCOME_THRESHOLD: int = 15
    TARGET_CATEGORY: int = 15
    BPL_STATUS: int = 15

    # General demographics (5–10 points)
    AGE_BRACKET: int = 10
    GENDER: int = 10
    STATE: int = 10
    DISTRICT: int = 5
    EDUCATION: int = 5


# Default global scoring weights
DEFAULT_WEIGHTS = ScoringWeights()

# Confidence score thresholds
CONFIDENCE_HIGH_THRESHOLD: int = 40
CONFIDENCE_MEDIUM_THRESHOLD: int = 20

# Standard Indian currency grouping regex / words
_WILDCARD_TOKENS: Set[str] = {
    "", "*", "all", "any", "na", "n/a", "none", "null", "all genders",
    "all categories", "pan-india", "pan india", "central", "national",
    "open", "not applicable", "irrelevant", "both", "general/all", "everyone",
    "unrestricted", "no limit", "any/all"
}


# ── User Profile Model ───────────────────────────────────────────────────────
if _HAS_PYDANTIC and BaseModel is not object:
    class UserProfile(BaseModel):
        """
        Pydantic contract for citizen demographic & socio-economic profile.
        All fields are optional to handle incomplete profiles gracefully.
        """
        if ConfigDict is not None:
            model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
        else:
            class Config:
                extra = "allow"
                arbitrary_types_allowed = True

        age: Optional[int] = Field(default=None, ge=0, le=150, description="Age in years")
        gender: Optional[str] = Field(default=None, description="Gender (e.g. 'male', 'female', 'transgender')")
        occupation: Optional[str] = Field(default=None, description="Primary occupation or student/artisan status")
        annual_income: Optional[Union[int, float]] = Field(default=None, ge=0, description="Annual household income in INR")
        income: Optional[Union[int, float]] = Field(default=None, ge=0, description="Alias for annual_income")
        state: Optional[str] = Field(default=None, description="State of residence (e.g. 'Maharashtra')")
        district: Optional[str] = Field(default=None, description="District of residence")
        category: Optional[str] = Field(default=None, description="Social category / caste (e.g. 'SC', 'ST', 'OBC', 'General')")
        education: Optional[str] = Field(default=None, description="Highest education level achieved")
        is_farmer: Optional[bool] = Field(default=None, description="Whether user is engaged in farming")
        farmer_category: Optional[str] = Field(default=None, description="Farmer classification (e.g. 'small', 'marginal', 'tenant')")
        is_disabled: Optional[bool] = Field(default=None, description="Whether user has a certified disability")
        disability_percentage: Optional[float] = Field(default=None, description="Percentage of disability if applicable")
        is_bpl: Optional[bool] = Field(default=None, description="Whether family is Below Poverty Line (BPL)")
        is_minority: Optional[bool] = Field(default=None, description="Whether user belongs to a notified minority")
else:
    @dataclass
    class UserProfile:  # type: ignore[no-redef]
        """Dataclass fallback if Pydantic is not installed."""
        age: Optional[int] = None
        gender: Optional[str] = None
        occupation: Optional[str] = None
        annual_income: Optional[Union[int, float]] = None
        income: Optional[Union[int, float]] = None
        state: Optional[str] = None
        district: Optional[str] = None
        category: Optional[str] = None
        education: Optional[str] = None
        is_farmer: Optional[bool] = None
        farmer_category: Optional[str] = None
        is_disabled: Optional[bool] = None
        disability_percentage: Optional[float] = None
        is_bpl: Optional[bool] = None
        is_minority: Optional[bool] = None


# ── Currency & String Formatting Utilities ───────────────────────────────────
def format_indian_currency(amount: Union[int, float, Decimal, str]) -> str:
    """
    Format a number into Indian Rupee notation with lakhs/crores commas.
    Example: 200000 -> ₹2,00,000; 1500000 -> ₹15,00,000.
    """
    try:
        clean_num = int(float(str(amount).replace(",", "").strip()))
    except (ValueError, TypeError):
        return f"₹{amount}"

    is_negative = clean_num < 0
    s = str(abs(clean_num))

    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        remaining = s[:-3]
        groups = []
        while len(remaining) > 2:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.append(remaining)
        groups.reverse()
        formatted = ",".join(groups) + "," + last3

    prefix = "-₹" if is_negative else "₹"
    return f"{prefix}{formatted}"


def _clean_str(val: Any) -> Optional[str]:
    """Clean and normalize string values, extracting enum .value if necessary."""
    if val is None:
        return None
    if isinstance(val, Enum):
        val = val.value
    if not isinstance(val, str):
        val = str(val)
    val = val.strip()
    return val if val else None


def _is_wildcard(val: Any) -> bool:
    """
    Return True if the criterion is a wildcard ('any', 'all', '*', None, empty).
    Criteria matching this receive 0 points.
    """
    if val is None:
        return True
    if isinstance(val, Enum):
        val = val.value
    if isinstance(val, str):
        cleaned = val.strip().lower()
        return cleaned in _WILDCARD_TOKENS
    if isinstance(val, (list, tuple, set)):
        if len(val) == 0:
            return True
        return all(_is_wildcard(item) for item in val)
    return False


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Safely extract attribute or dictionary key from a profile or scheme.
    Supports Pydantic models, dataclasses, dicts, and generic objects.
    """
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    # Check object attribute
    val = getattr(obj, key, default)
    if isinstance(val, Enum):
        return val.value
    return val


def _extract_criterion(scheme: Mapping[str, Any], *candidate_keys: str, default: Any = None) -> Any:
    """
    Look for a criterion in top-level scheme keys or common nested containers
    ('criteria', 'rules', 'eligibility_rules', 'eligibility_criteria', 'requirements').
    """
    # 1. Top-level
    for k in candidate_keys:
        if k in scheme and scheme[k] is not None:
            return scheme[k]

    # 2. Nested containers
    nested_keys = (
        "criteria", "rules", "eligibility_rules", "eligibility_rule",
        "eligibility_criteria", "requirements", "rule", "conditions"
    )
    for container_key in nested_keys:
        container = scheme.get(container_key)
        if isinstance(container, Mapping):
            for k in candidate_keys:
                if k in container and container[k] is not None:
                    return container[k]
        elif isinstance(container, Sequence) and not isinstance(container, (str, bytes)):
            for item in container:
                if isinstance(item, Mapping):
                    for k in candidate_keys:
                        if k in item and item[k] is not None:
                            return item[k]
    return default


def _parse_numeric(val: Any) -> Optional[float]:
    """Safely convert strings or numbers to float."""
    if val is None or _is_wildcard(val):
        return None
    if isinstance(val, (int, float, Decimal)):
        return float(val)
    if isinstance(val, str):
        # Remove currency symbols, commas, spaces
        cleaned = re.sub(r"[^\d.-]", "", val)
        if cleaned:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


# ── Match Reason Generator ───────────────────────────────────────────────────
class MatchReasonBuilder:
    """
    Constructs a single, clear, grammatically sound, plain-language sentence
    highlighting the primary matching attributes in order of specificity.
    """

    def __init__(self) -> None:
        self.persona: Optional[str] = None
        self.location: Optional[str] = None
        self.income_clause: Optional[str] = None
        self.category_clause: Optional[str] = None
        self.demographic_clause: Optional[str] = None
        self.other_clauses: List[str] = []

    def set_persona(self, text: str) -> None:
        self.persona = text

    def set_location(self, state: Optional[str], district: Optional[str] = None) -> None:
        if district and state:
            self.location = f"in {district}, {state}"
        elif state:
            self.location = f"in {state}"
        elif district:
            self.location = f"in {district}"

    def set_income(self, ceiling: Optional[float] = None) -> None:
        if ceiling is not None:
            self.income_clause = f"with income under {format_indian_currency(ceiling)}"

    def set_category(self, category: str) -> None:
        cat_clean = category.upper()
        if cat_clean in {"SC", "ST", "OBC", "EWS"}:
            self.category_clause = f"under the {cat_clean} category"
        else:
            self.category_clause = f"in the {category} category"

    def add_clause(self, clause: str) -> None:
        if clause and clause not in self.other_clauses:
            self.other_clauses.append(clause)

    def build(self) -> str:
        """Assemble all captured factors into a single fluent sentence."""
        # Case 1: Rich persona matched (e.g. small/marginal farmer, artisan, student, PwD)
        if self.persona:
            sentence = f"Matched based on {self.persona}"
            if self.location:
                sentence += f" {self.location}"
            if self.category_clause:
                sentence += f" {self.category_clause}"
            if self.income_clause:
                sentence += f" {self.income_clause}"
            if self.other_clauses:
                sentence += f" and {self.other_clauses[0]}"
            return sentence.strip() + "."

        # Case 2: Location + Income or Category (no specific occupation/disability persona)
        parts = []
        if self.location:
            parts.append(f"residence {self.location}")
        if self.category_clause:
            parts.append(self.category_clause.replace("under the ", "").replace("in the ", "") + " status")
        if self.income_clause:
            parts.append(self.income_clause.replace("with ", ""))
        for other in self.other_clauses:
            parts.append(other)

        if parts:
            if len(parts) == 1:
                return f"Matched based on your {parts[0]}."
            if len(parts) == 2:
                return f"Matched based on your {parts[0]} with {parts[1]}."
            joined_middle = ", ".join(parts[:-1])
            return f"Matched based on your {joined_middle} and {parts[-1]}."

        # Case 3: Universal / Open Central Scheme / Minimal specifics
        return "Matched based on general eligibility criteria."


# ── Individual Evaluators ────────────────────────────────────────────────────

def _evaluate_farmer_status(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate specific farmer requirement and status."""
    require_farmer = _extract_criterion(
        scheme, "require_farmer", "is_farmer", "farmer_only", "farmer_status", "farmer_required"
    )
    scheme_cat = _clean_str(_extract_criterion(scheme, "scheme_category", "category_name", "sector"))
    scheme_name = _clean_str(_extract_criterion(scheme, "name", "scheme_name", "title")) or ""

    user_is_farmer = bool(_safe_get(profile, "is_farmer", False))
    user_occupation = _clean_str(_safe_get(profile, "occupation", "")) or ""
    if "farmer" in user_occupation.lower() or "agriculture" in user_occupation.lower() or "kisan" in user_occupation.lower():
        user_is_farmer = True

    farmer_category = _clean_str(_safe_get(profile, "farmer_category", "")) or ""

    # Check if scheme explicitly targets farmers
    is_targeted_farmer_scheme = False
    if require_farmer is True:
        is_targeted_farmer_scheme = True
    elif isinstance(require_farmer, str) and require_farmer.lower() in {"true", "yes", "farmer", "farmers"}:
        is_targeted_farmer_scheme = True
    elif scheme_cat and scheme_cat.lower() in {"agriculture", "farming", "krishi", "kisan"}:
        is_targeted_farmer_scheme = True
    elif any(k in scheme_name.lower() for k in ["kisan", "farmer", "krishi", "crop insurance", "pm-kisan"]):
        is_targeted_farmer_scheme = True

    if is_targeted_farmer_scheme and user_is_farmer:
        # Determine exact persona description
        if farmer_category and any(w in farmer_category.lower() for w in ["small", "marginal"]):
            reason_builder.set_persona("your status as a small/marginal farmer")
        elif "small" in user_occupation.lower() or "marginal" in user_occupation.lower():
            reason_builder.set_persona("your status as a small/marginal farmer")
        else:
            reason_builder.set_persona("your status as a farmer")
        return weights.FARMER_STATUS

    return 0


def _evaluate_occupation(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder,
    farmer_already_matched: bool
) -> int:
    """Evaluate targeted non-farmer occupation (e.g., student, artisan, weaver)."""
    target_occ = _extract_criterion(
        scheme, "target_occupation", "targeted_occupation", "occupation",
        "occupations", "eligible_occupations", "occupation_target"
    )

    if _is_wildcard(target_occ):
        return 0

    user_occ = _clean_str(_safe_get(profile, "occupation"))
    if not user_occ or _is_wildcard(user_occ):
        return 0

    user_occ_lower = user_occ.lower().replace("_", " ").strip()

    # Match against single string or list of targeted occupations
    matched = False
    if isinstance(target_occ, (list, tuple, set)):
        for item in target_occ:
            item_str = _clean_str(item)
            if item_str and not _is_wildcard(item_str):
                item_lower = item_str.lower().replace("_", " ")
                if item_lower == user_occ_lower or item_lower in user_occ_lower or user_occ_lower in item_lower:
                    matched = True
                    break
    elif isinstance(target_occ, (str, Enum)):
        target_str = _clean_str(target_occ)
        if target_str and not _is_wildcard(target_str):
            target_lower = target_str.lower().replace("_", " ")
            if target_lower == user_occ_lower or target_lower in user_occ_lower or user_occ_lower in target_lower:
                matched = True

    if matched:
        # If farmer status was already scored and this occupation is also farmer/agri, avoid double scoring
        if farmer_already_matched and any(f in user_occ_lower for f in ["farmer", "krishi", "kisan", "agriculture", "farming"]):
            return 0

        if not farmer_already_matched and not reason_builder.persona:
            if "student" in user_occ_lower:
                reason_builder.set_persona("your status as a student")
            elif "artisan" in user_occ_lower or "weaver" in user_occ_lower or "craft" in user_occ_lower:
                reason_builder.set_persona(f"your occupation as an {user_occ_lower}")
            elif "worker" in user_occ_lower or "labor" in user_occ_lower:
                reason_builder.set_persona(f"your status as a {user_occ_lower}")
            else:
                reason_builder.set_persona(f"your occupation as a {user_occ_lower}")
        return weights.OCCUPATION

    return 0


def _evaluate_disability(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate targeted disability / PwD criteria."""
    require_disability = _extract_criterion(
        scheme, "require_disabled", "is_disabled", "disability_required",
        "target_disability", "pwd_only", "require_disability"
    )

    if _is_wildcard(require_disability):
        return 0

    user_is_disabled = bool(_safe_get(profile, "is_disabled", False))

    is_targeted_pwd = False
    if require_disability is True:
        is_targeted_pwd = True
    elif isinstance(require_disability, str) and require_disability.lower() in {"true", "yes", "pwd", "disabled"}:
        is_targeted_pwd = True

    if is_targeted_pwd and user_is_disabled:
        if not reason_builder.persona:
            reason_builder.set_persona("your disability status")
        else:
            reason_builder.add_clause("certified disability status")
        return weights.DISABILITY_STATUS

    return 0


def _evaluate_income(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate specific income threshold / ceiling."""
    max_income_val = _extract_criterion(
        scheme, "maximum_income", "max_income", "income_limit",
        "income_ceiling", "income_threshold", "annual_income_limit"
    )

    if _is_wildcard(max_income_val):
        return 0

    max_income = _parse_numeric(max_income_val)
    if max_income is None or max_income <= 0:
        return 0

    user_income_raw = _safe_get(profile, "annual_income", _safe_get(profile, "income"))
    user_income = _parse_numeric(user_income_raw)

    if user_income is not None and user_income <= max_income:
        reason_builder.set_income(max_income)
        return weights.INCOME_THRESHOLD

    return 0


def _evaluate_social_category(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate targeted social categories (SC/ST/OBC/EWS/Minority)."""
    target_cat = _extract_criterion(
        scheme, "category", "social_category", "caste",
        "target_category", "eligible_categories", "caste_category"
    )

    if _is_wildcard(target_cat):
        return 0

    user_cat = _clean_str(_safe_get(profile, "category"))
    if not user_cat or _is_wildcard(user_cat):
        return 0

    user_cat_clean = user_cat.strip().upper()

    matched = False
    if isinstance(target_cat, (list, tuple, set)):
        for item in target_cat:
            item_clean = str(item).strip().upper()
            if item_clean == user_cat_clean:
                matched = True
                break
    elif isinstance(target_cat, (str, Enum)):
        target_str = _clean_str(target_cat)
        if target_str:
            matched = target_str.strip().upper() == user_cat_clean

    if matched:
        reason_builder.set_category(user_cat)
        return weights.TARGET_CATEGORY

    return 0


def _evaluate_state(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate specific state residence."""
    target_state = _extract_criterion(
        scheme, "state", "applicable_state", "target_state", "states", "state_name"
    )

    if _is_wildcard(target_state):
        return 0

    user_state = _clean_str(_safe_get(profile, "state"))
    if not user_state or _is_wildcard(user_state):
        return 0

    user_state_clean = user_state.strip().lower()

    matched = False
    if isinstance(target_state, (list, tuple, set)):
        for s in target_state:
            s_clean = str(s).strip().lower()
            if s_clean == user_state_clean:
                matched = True
                break
    elif isinstance(target_state, (str, Enum)):
        s_clean = str(target_state).strip().lower()
        matched = s_clean == user_state_clean

    if matched:
        user_district = _clean_str(_safe_get(profile, "district"))
        reason_builder.set_location(user_state, user_district)
        return weights.STATE

    return 0


def _evaluate_district(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights
) -> int:
    """Evaluate specific district requirement."""
    target_district = _extract_criterion(
        scheme, "district", "target_district", "districts", "applicable_district"
    )

    if _is_wildcard(target_district):
        return 0

    user_district = _clean_str(_safe_get(profile, "district"))
    if not user_district or _is_wildcard(user_district):
        return 0

    if user_district.strip().lower() == str(target_district).strip().lower():
        return weights.DISTRICT

    return 0


def _evaluate_gender(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate gender-specific requirements (e.g. female/women schemes)."""
    target_gender = _extract_criterion(
        scheme, "gender", "target_gender", "eligible_gender", "for_gender"
    )

    if _is_wildcard(target_gender):
        return 0

    user_gender = _clean_str(_safe_get(profile, "gender"))
    if not user_gender or _is_wildcard(user_gender):
        return 0

    user_gender_clean = user_gender.strip().lower()
    target_gender_clean = str(target_gender).strip().lower()

    # Map synonyms
    female_synonyms = {"female", "woman", "women", "girl", "girls"}
    male_synonyms = {"male", "man", "men", "boy", "boys"}

    matched = False
    if target_gender_clean in female_synonyms and user_gender_clean in female_synonyms:
        matched = True
    elif target_gender_clean in male_synonyms and user_gender_clean in male_synonyms:
        matched = True
    elif target_gender_clean == user_gender_clean:
        matched = True

    if matched:
        if user_gender_clean in female_synonyms:
            if reason_builder.persona:
                # Enhance e.g. "your status as a student" -> "your status as a female student"
                if "female" not in reason_builder.persona and "women" not in reason_builder.persona:
                    reason_builder.persona = reason_builder.persona.replace("as a ", "as a female ").replace("as an ", "as a female ")
            else:
                reason_builder.add_clause("female gender eligibility")
        return weights.GENDER

    return 0


def _evaluate_age(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate age bracket eligibility."""
    min_age_val = _extract_criterion(scheme, "minimum_age", "min_age", "age_min")
    max_age_val = _extract_criterion(scheme, "maximum_age", "max_age", "age_max")

    has_min = not _is_wildcard(min_age_val)
    has_max = not _is_wildcard(max_age_val)

    if not has_min and not has_max:
        return 0

    min_age = _parse_numeric(min_age_val)
    max_age = _parse_numeric(max_age_val)

    user_age_raw = _safe_get(profile, "age")
    user_age = _parse_numeric(user_age_raw)

    if user_age is None:
        return 0

    min_ok = min_age is None or user_age >= min_age
    max_ok = max_age is None or user_age <= max_age

    if min_ok and max_ok:
        # Construct human-friendly age clause if no persona exists
        if not reason_builder.persona:
            if min_age is not None and max_age is not None:
                reason_builder.add_clause(f"age bracket ({int(min_age)}–{int(max_age)} years)")
            elif min_age is not None:
                reason_builder.add_clause(f"age requirement (≥{int(min_age)} years)")
            elif max_age is not None:
                reason_builder.add_clause(f"age requirement (≤{int(max_age)} years)")
        return weights.AGE_BRACKET

    return 0


def _evaluate_education(
    profile: Any,
    scheme: Mapping[str, Any],
    weights: ScoringWeights,
    reason_builder: MatchReasonBuilder
) -> int:
    """Evaluate education qualification."""
    req_edu = _extract_criterion(scheme, "education", "min_education", "minimum_education")
    if _is_wildcard(req_edu):
        return 0

    user_edu = _clean_str(_safe_get(profile, "education"))
    if not user_edu or _is_wildcard(user_edu):
        return 0

    if user_edu.lower() == str(req_edu).lower():
        reason_builder.add_clause("education qualification")
        return weights.EDUCATION

    return 0


# ── Confidence Mapper ────────────────────────────────────────────────────────
def calculate_confidence(score: int) -> ConfidenceLevel:
    """
    Map score to confidence level:
    - score >= 40  -> "high"
    - 20 <= score < 40 (20–39) -> "medium"
    - score < 20   -> "low"
    """
    if score >= CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if score >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


# ── Core Scheme Scorer ───────────────────────────────────────────────────────
def score_scheme(
    profile: Union[UserProfile, Any],
    scheme: Mapping[str, Any],
    weights: ScoringWeights = DEFAULT_WEIGHTS
) -> Tuple[int, ConfidenceLevel, str]:
    """
    Score a single scheme against a user profile.

    Returns:
        (total_score, confidence, match_reason)
    """
    reason_builder = MatchReasonBuilder()
    total_score: int = 0

    # 1. Specific Attributes (15–20 points each)
    farmer_score = _evaluate_farmer_status(profile, scheme, weights, reason_builder)
    total_score += farmer_score

    occ_score = _evaluate_occupation(
        profile, scheme, weights, reason_builder, farmer_already_matched=(farmer_score > 0)
    )
    total_score += occ_score

    pwd_score = _evaluate_disability(profile, scheme, weights, reason_builder)
    total_score += pwd_score

    income_score = _evaluate_income(profile, scheme, weights, reason_builder)
    total_score += income_score

    category_score = _evaluate_social_category(profile, scheme, weights, reason_builder)
    total_score += category_score

    # 2. General Demographics (5–10 points each)
    state_score = _evaluate_state(profile, scheme, weights, reason_builder)
    total_score += state_score

    district_score = _evaluate_district(profile, scheme, weights)
    total_score += district_score

    gender_score = _evaluate_gender(profile, scheme, weights, reason_builder)
    total_score += gender_score

    age_score = _evaluate_age(profile, scheme, weights, reason_builder)
    total_score += age_score

    edu_score = _evaluate_education(profile, scheme, weights, reason_builder)
    total_score += edu_score

    # 3. Output Attributes
    confidence = calculate_confidence(total_score)
    match_reason = reason_builder.build()

    return total_score, confidence, match_reason


# ── Public API Function ──────────────────────────────────────────────────────
def rank_schemes(
    profile: Union[UserProfile, Any],
    eligible_schemes: Sequence[Mapping[str, Any]],
    weights: ScoringWeights = DEFAULT_WEIGHTS
) -> List[Dict[str, Any]]:
    """
    Rank a list of eligible schemes for a given user profile.

    Parameters:
        profile: The citizen profile (Pydantic model, dataclass, dict, or object).
        eligible_schemes: A list of scheme dictionaries already filtered for eligibility.
        weights: Optional custom ScoringWeights instance.

    Returns:
        A list of scheme dictionaries sorted descending by 'score', each enriched with:
        - `score` (int): Total integer score.
        - `confidence` (str): "high", "medium", or "low".
        - `match_reason` (str): A single clear, plain-language explanation sentence.
    """
    if not eligible_schemes:
        return []

    ranked_schemes: List[Dict[str, Any]] = []

    for item in eligible_schemes:
        if not isinstance(item, Mapping):
            logger.warning("Skipping non-mapping item in eligible_schemes: %r", item)
            continue

        # Non-destructive copy
        scheme_dict = copy.deepcopy(dict(item))

        try:
            score, confidence, match_reason = score_scheme(profile, scheme_dict, weights)
        except Exception as e:
            logger.error("Error scoring scheme %s: %s", scheme_dict.get("name", "unknown"), str(e), exc_info=True)
            score = 0
            confidence = "low"
            match_reason = "Matched based on general eligibility criteria."

        scheme_dict["score"] = score
        scheme_dict["confidence"] = confidence
        scheme_dict["match_reason"] = match_reason

        ranked_schemes.append(scheme_dict)

    # Sort descending by score. Python's timsort provides stable sorting.
    ranked_schemes.sort(key=lambda s: s.get("score", 0), reverse=True)

    return ranked_schemes


__all__ = [
    "UserProfile",
    "ScoringWeights",
    "DEFAULT_WEIGHTS",
    "ConfidenceLevel",
    "format_indian_currency",
    "calculate_confidence",
    "score_scheme",
    "rank_schemes",
]
