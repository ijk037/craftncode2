"""
Filter Engine Module — Sahayak AI / CraftNCode
===============================================
Deterministic rule evaluation engine for filtering welfare schemes against
citizen demographic and socio-economic profiles.

Evaluation Philosophy:
- Criteria pass if the rule constraint is unconstrained (None or 'any').
- Criteria pass if the citizen profile field is missing/null (non-disqualifying / plausible eligibility).
- Criteria pass if the citizen's concrete profile value satisfies the rule requirement.
- A scheme is eligible if ALL specified criteria evaluate to true.
- Fully compatible with Pydantic SchemeRecord models and standard dictionary objects.
"""

from __future__ import annotations

import enum
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

logger = logging.getLogger(__name__)

# ── Optional Schema & Enum Imports ───────────────────────────────────────────
try:
    from schemas import (
        Education,
        FarmerStatus,
        Gender,
        MaritalStatus,
        Occupation,
        SchemeEligibilityRules,
        SchemeRecord,
        SocialCategory,
        UserProfile,
    )
    _HAS_SCHEMAS = True
except ImportError:
    _HAS_SCHEMAS = False
    Education = Any  # type: ignore
    FarmerStatus = Any  # type: ignore
    Gender = Any  # type: ignore
    MaritalStatus = Any  # type: ignore
    Occupation = Any  # type: ignore
    SchemeEligibilityRules = Any  # type: ignore
    SchemeRecord = Any  # type: ignore
    SocialCategory = Any  # type: ignore
    UserProfile = Any  # type: ignore


WILDCARD_TOKENS: Set[str] = {
    "any", "all", "*", "none", "n/a", "na", "", "null", "all-india",
    "pan-india", "pan india", "central", "national", "unrestricted"
}


# ============================================================================
# Helper Normalizers & Safegreppers
# ============================================================================

def _normalize_to_set(val: Any) -> Optional[Set[str]]:
    """
    Extracts a set of canonical lowercase string values from a scalar, list, or enum.
    Returns None if val is None, empty, or contains a wildcard token.
    """
    if val is None:
        return None

    if isinstance(val, str):
        cleaned = val.strip().lower()
        if cleaned in WILDCARD_TOKENS:
            return None
        return {cleaned}

    if isinstance(val, enum.Enum):
        name_val = val.value.lower() if isinstance(val.value, str) else str(val.value).lower()
        if name_val in WILDCARD_TOKENS:
            return None
        return {name_val}

    if isinstance(val, (list, tuple, set)):
        result: Set[str] = set()
        for item in val:
            if item is None:
                continue
            item_str = item.value.lower() if isinstance(item, enum.Enum) else str(item).strip().lower()
            if item_str in WILDCARD_TOKENS:
                return None  # Wildcard in list matches everything
            if item_str:
                result.add(item_str)
        return result if result else None

    s = str(val).strip().lower()
    return None if s in WILDCARD_TOKENS else {s}


def _get_enum_str(val: Any) -> Optional[str]:
    """Extracts lowercase string from enum, object, or string."""
    if val is None:
        return None
    if isinstance(val, enum.Enum):
        return val.value.lower() if isinstance(val.value, str) else str(val.value).lower()
    return str(val).strip().lower()


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """Safely extract field from dict or object."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    val = getattr(obj, key, default)
    if isinstance(val, enum.Enum):
        return val.value
    return val


def _extract_criterion(scheme: Any, *candidate_keys: str, default: Any = None) -> Any:
    """Extract criterion from object attributes or dictionary keys (flat or nested)."""
    # 1. Object attributes
    for k in candidate_keys:
        if hasattr(scheme, k) and getattr(scheme, k) is not None:
            return getattr(scheme, k)

    # 2. Top-level mapping
    if isinstance(scheme, Mapping):
        for k in candidate_keys:
            if k in scheme and scheme[k] is not None:
                return scheme[k]

    # 3. Nested rules containers
    for container_key in ("criteria", "rules", "eligibility_rules", "eligibility_rule", "requirements"):
        container = getattr(scheme, container_key, None) if not isinstance(scheme, Mapping) else scheme.get(container_key)
        if container is not None:
            if isinstance(container, Mapping):
                for k in candidate_keys:
                    if k in container and container[k] is not None:
                        return container[k]
            else:
                for k in candidate_keys:
                    if hasattr(container, k) and getattr(container, k) is not None:
                        return getattr(container, k)
    return default


def _parse_numeric(val: Any) -> Optional[float]:
    """Safely parse numeric value from float, int, Decimal, or string."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace(",", "").strip()
        if cleaned.lower() in WILDCARD_TOKENS:
            return None
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None


# ============================================================================
# Criterion Evaluators
# ============================================================================

def evaluate_age_criterion(
    profile_age: Optional[int],
    min_age: Optional[int],
    max_age: Optional[int],
) -> Tuple[bool, Optional[str]]:
    """Evaluates age boundary conditions."""
    if profile_age is None:
        return True, None

    if min_age is not None and profile_age < min_age:
        return False, f"Citizen age ({profile_age}) is below minimum required age ({min_age})."

    if max_age is not None and profile_age > max_age:
        return False, f"Citizen age ({profile_age}) exceeds maximum allowed age ({max_age})."

    return True, None


def evaluate_income_criterion(
    profile_income: Optional[float],
    max_annual_income: Optional[float],
) -> Tuple[bool, Optional[str]]:
    """Evaluates annual income ceiling."""
    if profile_income is None or max_annual_income is None:
        return True, None

    if profile_income > max_annual_income:
        return False, (
            f"Citizen annual income (INR {profile_income:,.0f}) exceeds "
            f"income ceiling of INR {max_annual_income:,.0f}."
        )

    return True, None


def evaluate_set_membership_criterion(
    profile_val: Any,
    rule_val: Any,
    criterion_name: str,
) -> Tuple[bool, Optional[str]]:
    """
    Generic set membership evaluation for categorical fields
    (occupation, farmer_status, social_category, gender, state, education, marital_status).
    """
    allowed_set = _normalize_to_set(rule_val)
    if allowed_set is None:
        return True, None  # Unconstrained rule

    if profile_val is None:
        return True, None  # Missing profile value is non-disqualifying

    user_val_str = _get_enum_str(profile_val)
    if not user_val_str or user_val_str in WILDCARD_TOKENS:
        return True, None

    # Handle partial / normalized match for synonyms
    user_val_normalized = user_val_str.replace("_", " ")
    matched = False
    if user_val_str in allowed_set or user_val_normalized in allowed_set:
        matched = True
    else:
        for item in allowed_set:
            item_norm = item.replace("_", " ")
            if item_norm == user_val_normalized or item_norm in user_val_normalized or user_val_normalized in item_norm:
                matched = True
                break

    if not matched:
        return False, (
            f"Citizen {criterion_name} '{user_val_str}' does not match "
            f"allowed criteria: {sorted(list(allowed_set))}."
        )

    return True, None


def evaluate_disability_criterion(
    profile: Any,
    disability_required: Optional[bool],
    min_disability_percentage: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """Evaluates disability prerequisites and percentage thresholds."""
    if disability_required is None:
        return True, None

    is_disabled = _safe_get(profile, "is_disabled", _safe_get(profile, "has_disability", False))
    disability_type = _safe_get(profile, "disability_type", None)
    disability_pct = _safe_get(profile, "disability_percentage", None)

    if disability_required is True:
        # Scheme is exclusively for disabled citizens
        if not is_disabled and not disability_type:
            return False, "Scheme requires certified disability status."

        if min_disability_percentage is not None and disability_pct is not None:
            if disability_pct < min_disability_percentage:
                return False, (
                    f"Disability percentage ({disability_pct}%) is below "
                    f"minimum requirement of {min_disability_percentage}%."
                )

    elif disability_required is False:
        # Scheme is strictly for non-disabled applicants
        if is_disabled is True:
            return False, "Scheme is restricted to non-disabled applicants."

    return True, None


# ============================================================================
# Scheme & Rule Evaluation Functions
# ============================================================================

def is_scheme_eligible(
    profile: Any,
    rules: Any,
) -> Tuple[bool, List[str]]:
    """
    Evaluates a single profile against scheme eligibility rules.
    Returns:
        (is_eligible: bool, failure_reasons: list[str])
    """
    disqualifications: List[str] = []

    # 1. Age check
    age = _safe_get(profile, "age")
    min_age = _extract_criterion(rules, "min_age", "minimum_age")
    max_age = _extract_criterion(rules, "max_age", "maximum_age")
    passed, reason = evaluate_age_criterion(age, min_age, max_age)
    if not passed and reason:
        disqualifications.append(reason)

    # 2. Income check
    income = _safe_get(profile, "annual_income", _safe_get(profile, "income"))
    max_income = _extract_criterion(rules, "max_annual_income", "maximum_income", "max_income", "income_limit", "income_ceiling")
    passed, reason = evaluate_income_criterion(income, max_income)
    if not passed and reason:
        disqualifications.append(reason)

    # 3. Occupation check
    occupation = _safe_get(profile, "occupation")
    rule_occ = _extract_criterion(rules, "occupation", "target_occupation", "occupations", "eligible_occupations")
    passed, reason = evaluate_set_membership_criterion(occupation, rule_occ, "occupation")
    if not passed and reason:
        disqualifications.append(reason)

    # 4. Farmer Status check
    farmer_status = _safe_get(profile, "farmer_status", _safe_get(profile, "farmer_category"))
    is_farmer_val = _safe_get(profile, "is_farmer", None)
    rule_farmer = _extract_criterion(rules, "farmer_status", "require_farmer", "is_farmer", "farmer_only")
    if rule_farmer is True or (isinstance(rule_farmer, str) and rule_farmer.lower() in ("true", "yes", "farmer")):
        if is_farmer_val is False and not farmer_status and (not occupation or "farmer" not in str(occupation).lower()):
            disqualifications.append("Requires farmer status.")
    elif rule_farmer is not None:
        passed, reason = evaluate_set_membership_criterion(farmer_status or ("farmer" if is_farmer_val else None), rule_farmer, "farmer status")
        if not passed and reason:
            disqualifications.append(reason)

    # 5. Social Category check
    category = _safe_get(profile, "social_category", _safe_get(profile, "category"))
    rule_category = _extract_criterion(rules, "social_category", "category", "caste", "target_category")
    passed, reason = evaluate_set_membership_criterion(category, rule_category, "social category")
    if not passed and reason:
        disqualifications.append(reason)

    # 6. Gender check
    gender = _safe_get(profile, "gender")
    rule_gender = _extract_criterion(rules, "gender", "target_gender", "eligible_gender", "for_gender")
    passed, reason = evaluate_set_membership_criterion(gender, rule_gender, "gender")
    if not passed and reason:
        disqualifications.append(reason)

    # 7. State check
    state = _safe_get(profile, "state")
    rule_state = _extract_criterion(rules, "state", "applicable_state", "target_state", "states")
    passed, reason = evaluate_set_membership_criterion(state, rule_state, "state")
    if not passed and reason:
        disqualifications.append(reason)

    # 8. Education check
    education = _safe_get(profile, "education")
    rule_education = _extract_criterion(rules, "education", "min_education", "minimum_education")
    passed, reason = evaluate_set_membership_criterion(education, rule_education, "education")
    if not passed and reason:
        disqualifications.append(reason)

    # 9. Marital Status check
    marital = _safe_get(profile, "marital_status")
    rule_marital = _extract_criterion(rules, "marital_status")
    passed, reason = evaluate_set_membership_criterion(marital, rule_marital, "marital status")
    if not passed and reason:
        disqualifications.append(reason)

    # 10. Disability check
    disability_req = _extract_criterion(rules, "disability_required", "require_disabled", "is_disabled", "target_disability")
    min_dis_pct = _extract_criterion(rules, "min_disability_percentage")
    passed, reason = evaluate_disability_criterion(profile, disability_req, min_dis_pct)
    if not passed and reason:
        disqualifications.append(reason)

    return (len(disqualifications) == 0, disqualifications)


def is_eligible(profile: Any, scheme: Any) -> bool:
    """Evaluate whether a user profile strictly meets all non-wildcard criteria of a scheme."""
    rules = getattr(scheme, "eligibility_rules", scheme)
    is_match, _ = is_scheme_eligible(profile, rules)
    return is_match


def filter_eligible(
    profile: Any,
    schemes: Sequence[Any],
) -> List[Any]:
    """
    Filters a list of SchemeRecord or dict instances against the provided UserProfile.

    Rules:
    - Executes deterministic boolean comparisons across all rule keys.
    - An unconstrained rule (None or 'any') matches all citizens.
    - A missing/null field on the UserProfile is non-disqualifying.
    - Returns only the schemes where all specified constraints evaluate to true.
    """
    if not schemes:
        return []

    eligible_schemes: List[Any] = []

    for scheme in schemes:
        if hasattr(scheme, "is_active") and not scheme.is_active:
            continue

        rules = getattr(scheme, "eligibility_rules", scheme)
        is_match, _ = is_scheme_eligible(profile, rules)
        if is_match:
            eligible_schemes.append(scheme)

    return eligible_schemes


def filter_eligible_with_details(
    profile: Any,
    schemes: Sequence[Any],
) -> List[Dict[str, Any]]:
    """
    Evaluates schemes and returns structured audit details including pass/fail status
    and specific failure reasons for explainability.
    """
    results: List[Dict[str, Any]] = []

    for scheme in schemes:
        rules = getattr(scheme, "eligibility_rules", scheme)
        is_match, reasons = is_scheme_eligible(profile, rules)
        scheme_code = getattr(scheme, "scheme_code", _safe_get(scheme, "scheme_code", _safe_get(scheme, "id", "")))
        scheme_name = getattr(scheme, "name", _safe_get(scheme, "name", ""))
        is_active = getattr(scheme, "is_active", _safe_get(scheme, "is_active", True))

        results.append({
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "is_eligible": is_match,
            "is_active": is_active,
            "failure_reasons": reasons,
            "scheme": scheme,
        })

    return results


__all__ = [
    "WILDCARD_TOKENS",
    "evaluate_age_criterion",
    "evaluate_income_criterion",
    "evaluate_set_membership_criterion",
    "evaluate_disability_criterion",
    "is_scheme_eligible",
    "is_eligible",
    "filter_eligible",
    "filter_eligible_with_details",
]
