"""
Fallback Recommendation Engine — Sahayak AI / CraftNCode
==========================================================
Implements nearest-neighbor / mismatch distance analysis when no government
schemes pass strict eligibility criteria. Identifies the "closest" schemes
by calculating the fewest violated criteria and evaluating dimensional distance.

Key Features:
- Fallback & Distance Logic:
  * Computes exact criterion-level violations (age, gender, state, income, occupation, etc.).
  * Ranks schemes primarily by fewest violated criteria, secondarily by numerical distance,
    and tertiarily by highest number of satisfied criteria.
- Missing Criteria Explanations:
  * Injects `is_fallback: True` and plain-language explanations in `missing_criteria_reason`
    (e.g., "Requires age over 60 (your age: 54)", "Targeted strictly for female applicants").
- Robust & Extensible:
  * Works with Pydantic models, dataclasses, dicts, or generic profile objects.
  * Safely parses diverse scheme dictionary schemas (flat or nested rules).
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

# Set up logger
logger = logging.getLogger(__name__)

# ── Optional Import of UserProfile from ranker.py ───────────────────────────
try:
    from app.services.ranker import UserProfile, format_indian_currency, _is_wildcard, _safe_get, _extract_criterion, _parse_numeric, _clean_str
except ImportError:
    try:
        from ranker import UserProfile, format_indian_currency, _is_wildcard, _safe_get, _extract_criterion, _parse_numeric, _clean_str
    except ImportError:
        # Standalone fallbacks if ranker is in another path
        try:
            from pydantic import BaseModel, ConfigDict, Field
            _HAS_PYDANTIC = True
        except ImportError:
            _HAS_PYDANTIC = False
            BaseModel = object  # type: ignore[assignment, misc]
            ConfigDict = None  # type: ignore[assignment, misc]
            Field = lambda default=None, **kwargs: default  # type: ignore[assignment]

        if _HAS_PYDANTIC and BaseModel is not object:
            class UserProfile(BaseModel):  # type: ignore[no-redef]
                if ConfigDict is not None:
                    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
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
        else:
            @dataclass
            class UserProfile:  # type: ignore[no-redef]
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

        def format_indian_currency(amount: Union[int, float, Decimal, str]) -> str:
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

        _WILDCARD_TOKENS: Set[str] = {
            "", "*", "all", "any", "na", "n/a", "none", "null", "all genders",
            "all categories", "pan-india", "pan india", "central", "national",
            "open", "not applicable", "irrelevant", "both", "general/all", "everyone",
            "unrestricted", "no limit", "any/all"
        }

        def _clean_str(val: Any) -> Optional[str]:
            if val is None:
                return None
            if isinstance(val, Enum):
                val = val.value
            if not isinstance(val, str):
                val = str(val)
            val = val.strip()
            return val if val else None

        def _is_wildcard(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, Enum):
                val = val.value
            if isinstance(val, str):
                return val.strip().lower() in _WILDCARD_TOKENS
            if isinstance(val, (list, tuple, set)):
                return len(val) == 0 or all(_is_wildcard(item) for item in val)
            return False

        def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if isinstance(obj, Mapping):
                return obj.get(key, default)
            val = getattr(obj, key, default)
            if isinstance(val, Enum):
                return val.value
            return val

        def _extract_criterion(scheme: Mapping[str, Any], *candidate_keys: str, default: Any = None) -> Any:
            for k in candidate_keys:
                if k in scheme and scheme[k] is not None:
                    return scheme[k]
            nested_keys = ("criteria", "rules", "eligibility_rules", "eligibility_rule", "requirements")
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
            if val is None or _is_wildcard(val):
                return None
            if isinstance(val, (int, float, Decimal)):
                return float(val)
            if isinstance(val, str):
                cleaned = re.sub(r"[^\d.-]", "", val)
                if cleaned:
                    try:
                        return float(cleaned)
                    except ValueError:
                        return None
            return None


# ── Violation Representation ─────────────────────────────────────────────────
@dataclass
class CriterionViolation:
    """Represents a single unmet eligibility requirement."""
    criterion: str          # e.g. "age", "gender", "state", "income", "occupation"
    reason: str             # e.g. "Requires age over 60 (your age: 54)"
    distance: float = 1.0   # Normalized distance penalty
    is_missing_profile_field: bool = False


# ── Evaluation Engine ────────────────────────────────────────────────────────
class SchemeMismatchEvaluator:
    """Evaluates all criteria of a scheme against a profile to detect violations and matches."""

    def __init__(self, profile: Any, scheme: Mapping[str, Any]) -> None:
        self.profile = profile
        self.scheme = scheme
        self.violations: List[CriterionViolation] = []
        self.matched_criteria_count: int = 0

    def evaluate(self) -> Tuple[List[CriterionViolation], int, float]:
        """
        Evaluate all criteria.
        Returns:
            (violations_list, matched_criteria_count, total_distance)
        """
        self._check_age()
        self._check_gender()
        self._check_state()
        self._check_district()
        self._check_income()
        self._check_farmer_status()
        self._check_disability_status()
        self._check_occupation()
        self._check_social_category()
        self._check_education()

        total_distance = sum(v.distance for v in self.violations)
        return self.violations, self.matched_criteria_count, total_distance

    # ── Age Check ────────────────────────────────────────────────────────────
    def _check_age(self) -> None:
        min_age_val = _extract_criterion(self.scheme, "minimum_age", "min_age", "age_min")
        max_age_val = _extract_criterion(self.scheme, "maximum_age", "max_age", "age_max")

        has_min = not _is_wildcard(min_age_val)
        has_max = not _is_wildcard(max_age_val)

        if not has_min and not has_max:
            return

        min_age = _parse_numeric(min_age_val)
        max_age = _parse_numeric(max_age_val)

        user_age_raw = _safe_get(self.profile, "age")
        user_age = _parse_numeric(user_age_raw)

        if user_age is None:
            if min_age is not None and max_age is not None:
                self.violations.append(CriterionViolation(
                    criterion="age",
                    reason=f"Requires age between {int(min_age)} and {int(max_age)} (age not specified in profile)",
                    distance=1.0,
                    is_missing_profile_field=True
                ))
            elif min_age is not None:
                self.violations.append(CriterionViolation(
                    criterion="age",
                    reason=f"Requires age over {int(min_age)} (age not specified in profile)",
                    distance=1.0,
                    is_missing_profile_field=True
                ))
            elif max_age is not None:
                self.violations.append(CriterionViolation(
                    criterion="age",
                    reason=f"Requires age under {int(max_age)} (age not specified in profile)",
                    distance=1.0,
                    is_missing_profile_field=True
                ))
            return

        user_age_int = int(user_age)

        # Check bounds
        if min_age is not None and user_age < min_age:
            age_diff = min_age - user_age
            norm_dist = min(2.0, age_diff / 10.0)
            self.violations.append(CriterionViolation(
                criterion="age",
                reason=f"Requires age over {int(min_age)} (your age: {user_age_int})",
                distance=norm_dist
            ))
        elif max_age is not None and user_age > max_age:
            age_diff = user_age - max_age
            norm_dist = min(2.0, age_diff / 10.0)
            self.violations.append(CriterionViolation(
                criterion="age",
                reason=f"Requires age under {int(max_age)} (your age: {user_age_int})",
                distance=norm_dist
            ))
        else:
            self.matched_criteria_count += 1

    # ── Gender Check ─────────────────────────────────────────────────────────
    def _check_gender(self) -> None:
        target_gender = _extract_criterion(self.scheme, "gender", "target_gender", "eligible_gender", "for_gender")
        if _is_wildcard(target_gender):
            return

        user_gender = _clean_str(_safe_get(self.profile, "gender"))
        target_gender_str = str(target_gender).strip().lower()

        female_synonyms = {"female", "woman", "women", "girl", "girls"}
        male_synonyms = {"male", "man", "men", "boy", "boys"}

        is_target_female = target_gender_str in female_synonyms
        is_target_male = target_gender_str in male_synonyms

        if not user_gender or _is_wildcard(user_gender):
            if is_target_female:
                reason = "Targeted strictly for female applicants (gender not specified in profile)"
            elif is_target_male:
                reason = "Targeted for male applicants (gender not specified in profile)"
            else:
                reason = f"Targeted for {target_gender} applicants (gender not specified in profile)"
            self.violations.append(CriterionViolation(
                criterion="gender",
                reason=reason,
                distance=1.0,
                is_missing_profile_field=True
            ))
            return

        user_gender_lower = user_gender.lower()
        is_user_female = user_gender_lower in female_synonyms
        is_user_male = user_gender_lower in male_synonyms

        matched = False
        if is_target_female and is_user_female:
            matched = True
        elif is_target_male and is_user_male:
            matched = True
        elif target_gender_str == user_gender_lower:
            matched = True

        if not matched:
            if is_target_female:
                reason = "Targeted strictly for female applicants"
            elif is_target_male:
                reason = "Targeted strictly for male applicants"
            else:
                reason = f"Targeted strictly for {target_gender} applicants (your gender: {user_gender})"
            self.violations.append(CriterionViolation(
                criterion="gender",
                reason=reason,
                distance=1.0
            ))
        else:
            self.matched_criteria_count += 1

    # ── State Check ──────────────────────────────────────────────────────────
    def _check_state(self) -> None:
        target_state = _extract_criterion(self.scheme, "state", "applicable_state", "target_state", "states", "state_name")
        if _is_wildcard(target_state):
            return

        user_state = _clean_str(_safe_get(self.profile, "state"))
        if not user_state or _is_wildcard(user_state):
            state_desc = target_state if isinstance(target_state, str) else ", ".join(target_state)
            self.violations.append(CriterionViolation(
                criterion="state",
                reason=f"Restricted to residents of {state_desc} (state not specified in profile)",
                distance=1.0,
                is_missing_profile_field=True
            ))
            return

        user_state_clean = user_state.strip().lower()
        matched = False

        if isinstance(target_state, (list, tuple, set)):
            matched = any(str(s).strip().lower() == user_state_clean for s in target_state)
            state_desc = ", ".join(str(s) for s in target_state)
        else:
            matched = str(target_state).strip().lower() == user_state_clean
            state_desc = str(target_state)

        if not matched:
            self.violations.append(CriterionViolation(
                criterion="state",
                reason=f"Restricted to residents of {state_desc} (your state: {user_state})",
                distance=1.0
            ))
        else:
            self.matched_criteria_count += 1

    # ── District Check ───────────────────────────────────────────────────────
    def _check_district(self) -> None:
        target_district = _extract_criterion(self.scheme, "district", "target_district", "districts")
        if _is_wildcard(target_district):
            return

        user_district = _clean_str(_safe_get(self.profile, "district"))
        if not user_district or _is_wildcard(user_district):
            self.violations.append(CriterionViolation(
                criterion="district",
                reason=f"Restricted to {target_district} district (district not specified)",
                distance=0.5,
                is_missing_profile_field=True
            ))
            return

        if user_district.strip().lower() != str(target_district).strip().lower():
            self.violations.append(CriterionViolation(
                criterion="district",
                reason=f"Restricted to {target_district} district (your district: {user_district})",
                distance=0.5
            ))
        else:
            self.matched_criteria_count += 1

    # ── Income Check ─────────────────────────────────────────────────────────
    def _check_income(self) -> None:
        max_income_val = _extract_criterion(
            self.scheme, "maximum_income", "max_income", "income_limit",
            "income_ceiling", "income_threshold", "annual_income_limit"
        )
        if _is_wildcard(max_income_val):
            return

        max_income = _parse_numeric(max_income_val)
        if max_income is None or max_income <= 0:
            return

        user_income_raw = _safe_get(self.profile, "annual_income", _safe_get(self.profile, "income"))
        user_income = _parse_numeric(user_income_raw)

        if user_income is None:
            self.violations.append(CriterionViolation(
                criterion="income",
                reason=f"Requires annual income under {format_indian_currency(max_income)} (income not specified in profile)",
                distance=1.0,
                is_missing_profile_field=True
            ))
            return

        if user_income > max_income:
            diff = user_income - max_income
            norm_dist = min(2.0, diff / max_income)
            self.violations.append(CriterionViolation(
                criterion="income",
                reason=f"Requires annual income under {format_indian_currency(max_income)} (your income: {format_indian_currency(user_income)})",
                distance=norm_dist
            ))
        else:
            self.matched_criteria_count += 1

    # ── Farmer Status Check ──────────────────────────────────────────────────
    def _check_farmer_status(self) -> None:
        require_farmer = _extract_criterion(
            self.scheme, "require_farmer", "is_farmer", "farmer_only", "farmer_status", "farmer_required"
        )
        if _is_wildcard(require_farmer):
            return

        is_req = False
        if require_farmer is True:
            is_req = True
        elif isinstance(require_farmer, str) and require_farmer.lower() in {"true", "yes", "farmer", "farmers"}:
            is_req = True

        if not is_req:
            return

        user_is_farmer = bool(_safe_get(self.profile, "is_farmer", False))
        user_occ = _clean_str(_safe_get(self.profile, "occupation", "")) or ""
        if "farmer" in user_occ.lower() or "agriculture" in user_occ.lower() or "kisan" in user_occ.lower():
            user_is_farmer = True

        if not user_is_farmer:
            self.violations.append(CriterionViolation(
                criterion="farmer_status",
                reason="Requires farmer status",
                distance=1.0
            ))
        else:
            self.matched_criteria_count += 1

    # ── Disability Status Check ──────────────────────────────────────────────
    def _check_disability_status(self) -> None:
        require_disability = _extract_criterion(
            self.scheme, "require_disabled", "is_disabled", "disability_required",
            "target_disability", "pwd_only", "require_disability"
        )
        if _is_wildcard(require_disability):
            return

        is_req = False
        if require_disability is True:
            is_req = True
        elif isinstance(require_disability, str) and require_disability.lower() in {"true", "yes", "pwd", "disabled"}:
            is_req = True

        if not is_req:
            return

        user_is_disabled = bool(_safe_get(self.profile, "is_disabled", False))
        if not user_is_disabled:
            self.violations.append(CriterionViolation(
                criterion="disability",
                reason="Requires certified disability status (PwD)",
                distance=1.0
            ))
        else:
            self.matched_criteria_count += 1

    # ── Occupation Check ─────────────────────────────────────────────────────
    def _check_occupation(self) -> None:
        target_occ = _extract_criterion(
            self.scheme, "target_occupation", "targeted_occupation", "occupation",
            "occupations", "eligible_occupations"
        )
        if _is_wildcard(target_occ):
            return

        user_occ = _clean_str(_safe_get(self.profile, "occupation"))
        target_occ_desc = target_occ if isinstance(target_occ, str) else ", ".join(str(o) for o in target_occ)

        if not user_occ or _is_wildcard(user_occ):
            self.violations.append(CriterionViolation(
                criterion="occupation",
                reason=f"Targeted for {target_occ_desc}s (occupation not specified in profile)",
                distance=1.0,
                is_missing_profile_field=True
            ))
            return

        user_occ_clean = user_occ.lower().replace("_", " ").strip()
        matched = False

        if isinstance(target_occ, (list, tuple, set)):
            for item in target_occ:
                item_str = _clean_str(item)
                if item_str and not _is_wildcard(item_str):
                    item_lower = item_str.lower().replace("_", " ")
                    if item_lower == user_occ_clean or item_lower in user_occ_clean or user_occ_clean in item_lower:
                        matched = True
                        break
        else:
            target_str = _clean_str(target_occ)
            if target_str and not _is_wildcard(target_str):
                target_lower = target_str.lower().replace("_", " ")
                if target_lower == user_occ_clean or target_lower in user_occ_clean or user_occ_clean in target_lower:
                    matched = True

        if not matched:
            self.violations.append(CriterionViolation(
                criterion="occupation",
                reason=f"Targeted for {target_occ_desc}s (your occupation: {user_occ})",
                distance=1.0
            ))
        else:
            self.matched_criteria_count += 1

    # ── Social Category Check ────────────────────────────────────────────────
    def _check_social_category(self) -> None:
        target_cat = _extract_criterion(
            self.scheme, "category", "social_category", "caste", "target_category", "eligible_categories"
        )
        if _is_wildcard(target_cat):
            return

        user_cat = _clean_str(_safe_get(self.profile, "category"))
        cat_desc = target_cat if isinstance(target_cat, str) else "/".join(str(c) for c in target_cat)

        if not user_cat or _is_wildcard(user_cat):
            self.violations.append(CriterionViolation(
                criterion="category",
                reason=f"Targeted for {cat_desc.upper()} category applicants (category not specified in profile)",
                distance=1.0,
                is_missing_profile_field=True
            ))
            return

        user_cat_clean = user_cat.strip().upper()
        matched = False

        if isinstance(target_cat, (list, tuple, set)):
            matched = any(str(c).strip().upper() == user_cat_clean for c in target_cat)
        else:
            matched = str(target_cat).strip().upper() == user_cat_clean

        if not matched:
            self.violations.append(CriterionViolation(
                criterion="category",
                reason=f"Targeted for {cat_desc.upper()} category applicants (your category: {user_cat.upper()})",
                distance=1.0
            ))
        else:
            self.matched_criteria_count += 1

    # ── Education Check ──────────────────────────────────────────────────────
    def _check_education(self) -> None:
        req_edu = _extract_criterion(self.scheme, "education", "min_education", "minimum_education")
        if _is_wildcard(req_edu):
            return

        user_edu = _clean_str(_safe_get(self.profile, "education"))
        if not user_edu or _is_wildcard(user_edu):
            self.violations.append(CriterionViolation(
                criterion="education",
                reason=f"Requires minimum education: {req_edu} (education not specified)",
                distance=0.5,
                is_missing_profile_field=True
            ))
            return

        if user_edu.lower() != str(req_edu).lower():
            self.violations.append(CriterionViolation(
                criterion="education",
                reason=f"Requires education level of {req_edu} (your education: {user_edu})",
                distance=0.5
            ))
        else:
            self.matched_criteria_count += 1


# ── Plain-Language Reason Builder for Fallback ───────────────────────────────
def format_missing_criteria_reason(violations: Sequence[CriterionViolation]) -> str:
    """
    Format a list of criterion violations into a clean, plain-language explanation string.
    Single violation: "Requires age over 60 (your age: 54)"
    Multiple violations: "Requires age over 60 (your age: 54); Restricted to residents of Maharashtra (your state: Gujarat)."
    """
    if not violations:
        return "All eligibility criteria met."

    reasons = [v.reason.rstrip(".") for v in violations]

    if len(reasons) == 1:
        return reasons[0] + "."

    # Join multiple reasons cleanly with semicolons
    return "; ".join(reasons) + "."


# ── Core Fallback Scheme Search ──────────────────────────────────────────────
def find_closest_schemes(
    profile: Union[UserProfile, Any],
    all_schemes: Sequence[Mapping[str, Any]],
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Find and rank the closest fallback schemes when no schemes pass strict eligibility.

    Parameters:
        profile: The user profile (Pydantic model, dataclass, dict, or generic object).
        all_schemes: The full list of schemes to evaluate for closeness.
        top_k: Maximum number of closest schemes to return (defaults to 3, typically 2–3).

    Returns:
        A list of up to `top_k` scheme dictionaries sorted by closest match (fewest violations),
        each enriched with:
        - `is_fallback`: True
        - `missing_criteria_reason`: Plain-language explanation of unmet criteria.
        - `mismatch_count`: Integer count of violated criteria.
    """
    if not all_schemes or top_k <= 0:
        return []

    evaluated_candidates: List[Tuple[Tuple[int, float, int, str], Dict[str, Any]]] = []

    for item in all_schemes:
        if not isinstance(item, Mapping):
            logger.warning("Skipping invalid scheme item: %r", item)
            continue

        # Make non-destructive copy
        scheme_dict = copy.deepcopy(dict(item))
        scheme_name = str(scheme_dict.get("name", scheme_dict.get("scheme_name", "Unknown Scheme")))

        evaluator = SchemeMismatchEvaluator(profile, scheme_dict)
        violations, matched_count, total_distance = evaluator.evaluate()

        mismatch_count = len(violations)
        reason_str = format_missing_criteria_reason(violations)

        scheme_dict["is_fallback"] = True
        scheme_dict["missing_criteria_reason"] = reason_str
        scheme_dict["mismatch_count"] = mismatch_count
        scheme_dict["unmet_criteria"] = [v.criterion for v in violations]

        # Sorting key:
        # 1. Fewest violations (mismatch_count ascending)
        # 2. Smallest numerical distance (total_distance ascending)
        # 3. Highest satisfied criteria (matched_count descending -> -matched_count)
        # 4. Scheme name for deterministic tie-breaking
        sort_key = (mismatch_count, round(total_distance, 4), -matched_count, scheme_name)
        evaluated_candidates.append((sort_key, scheme_dict))

    # Sort all candidates by closeness
    evaluated_candidates.sort(key=lambda x: x[0])

    # Extract top_k closest
    closest_schemes = [candidate[1] for candidate in evaluated_candidates[:top_k]]
    return closest_schemes


__all__ = [
    "CriterionViolation",
    "SchemeMismatchEvaluator",
    "format_missing_criteria_reason",
    "find_closest_schemes",
]
