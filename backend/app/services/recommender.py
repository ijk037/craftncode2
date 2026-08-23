"""
Scheme Recommendation Orchestrator — Sahayak AI / CraftNCode
==============================================================
Main recommendation orchestrator integrating:
1. Strict Eligibility Filtering (`filter_engine.py` by Person A)
2. Weighted Multi-Factor Ranking (`ranker.py`)
3. Nearest-Neighbor Fallback Engine (`fallback_engine.py`)

Workflow:
- Evaluates `schemes_data` against `profile` via `filter_eligible`.
- If eligible schemes exist (len > 0):
  * Ranks eligible schemes by demographic/socio-economic specificity.
  * Returns structured response with `status="success"`, `is_fallback=False`.
- If zero schemes meet strict eligibility (len == 0):
  * Computes nearest fallback schemes with distance scoring and unmet criteria reasons.
  * Returns structured response with `status="fallback"`, `is_fallback=True`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

# ── 1. Integrations ──────────────────────────────────────────────────────────
try:
    from app.services.filter_engine import filter_eligible
except ImportError:
    try:
        from filter_engine import filter_eligible  # type: ignore[no-redef]
    except ImportError:
        raise ImportError("Could not import 'filter_eligible' from filter_engine.py")

try:
    from app.services.ranker import UserProfile, rank_schemes
except ImportError:
    try:
        from ranker import UserProfile, rank_schemes  # type: ignore[no-redef]
    except ImportError:
        raise ImportError("Could not import 'rank_schemes' or 'UserProfile' from ranker.py")

try:
    from app.services.fallback_engine import find_closest_schemes
except ImportError:
    try:
        from fallback_engine import find_closest_schemes  # type: ignore[no-redef]
    except ImportError:
        raise ImportError("Could not import 'find_closest_schemes' from fallback_engine.py")

logger = logging.getLogger(__name__)


# ── Recommendation Pipeline ──────────────────────────────────────────────────
def recommend_schemes(
    profile: Union[UserProfile, Any],
    schemes_data: Sequence[Mapping[str, Any]],
    top_k_fallback: int = 3
) -> Dict[str, Any]:
    """
    Recommend government schemes for a user profile with automatic fallback.

    Parameters:
        profile: Citizen demographic & socio-economic profile (UserProfile, dataclass, or dict).
        schemes_data: List of all available government scheme dictionaries.
        top_k_fallback: Number of fallback schemes to return if zero schemes are strictly eligible.

    Returns:
        Clean JSON-serializable dictionary with standard API envelope:
        - `status` (str): "success" (eligible schemes found) or "fallback" (no strictly eligible schemes).
        - `is_fallback` (bool): False if eligible, True if fallback.
        - `total` (int): Number of returned schemes.
        - `count` (int): Alias for total.
        - `data` (list[dict]): Ranked schemes or closest fallback schemes with reasons.
        - `message` (str): Plain-language status message.
        - `meta` (dict): Processing metadata including counts and evaluation summary.
    """
    total_evaluated = len(schemes_data) if schemes_data else 0

    if not schemes_data:
        return {
            "status": "success",
            "is_fallback": False,
            "total": 0,
            "count": 0,
            "data": [],
            "message": "No schemes provided for evaluation.",
            "meta": {
                "status": "success",
                "total_evaluated": 0,
                "eligible_count": 0,
                "fallback_count": 0,
            }
        }

    # Step 1: Strict Eligibility Filtering (Person A's filter_engine)
    try:
        eligible_schemes = filter_eligible(profile, schemes_data)
    except Exception as e:
        logger.error("Error during filter_eligible execution: %s", str(e), exc_info=True)
        eligible_schemes = []

    # Step 2: Branch based on eligibility result
    if len(eligible_schemes) > 0:
        # ── SUCCESS PATH: Strict matches found ───────────────────────────────
        ranked_schemes = rank_schemes(profile, eligible_schemes)

        return {
            "status": "success",
            "is_fallback": False,
            "total": len(ranked_schemes),
            "count": len(ranked_schemes),
            "data": ranked_schemes,
            "message": f"Successfully found {len(ranked_schemes)} eligible scheme(s) matching your profile.",
            "meta": {
                "status": "success",
                "total_evaluated": total_evaluated,
                "eligible_count": len(ranked_schemes),
                "fallback_count": 0,
            }
        }
    else:
        # ── FALLBACK PATH: No strict matches ─────────────────────────────────
        fallback_schemes = find_closest_schemes(
            profile, schemes_data, top_k=top_k_fallback
        )

        return {
            "status": "fallback",
            "is_fallback": True,
            "total": len(fallback_schemes),
            "count": len(fallback_schemes),
            "data": fallback_schemes,
            "message": (
                f"No schemes met all strict eligibility criteria. "
                f"Showing top {len(fallback_schemes)} closest scheme(s) with missing criteria details."
            ),
            "meta": {
                "status": "fallback",
                "total_evaluated": total_evaluated,
                "eligible_count": 0,
                "fallback_count": len(fallback_schemes),
            }
        }


__all__ = [
    "UserProfile",
    "filter_eligible",
    "rank_schemes",
    "find_closest_schemes",
    "recommend_schemes",
]
