"""
Query Parser — converts raw user text into structured search filters.

Two-stage approach:
  1. Rule-based pass (fast, no API call): regex + keyword matching
  2. LLM pass (Qwen via HuggingFace): fills in what rules miss for complex queries

Output schema:
  {
    "semantic_query":    str,   # cleaned text for embedding
    "is_veg":           bool | None,
    "max_price":        int  | None,
    "min_price":        int  | None,
    "max_calories":     int  | None,
    "min_health_score": int  | None,
    "section_name":     str  | None,   # e.g. "Biryani", "Desserts"
  }
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Category keyword map ───────────────────────────────────────────────────────
_SECTION_KEYWORDS: list[tuple[list[str], str]] = [
    (["biryani", "biriyani", "dum"],                      "Biryani"),
    (["starter", "appetiser", "appetizer", "snack",
      "tikka", "kebab", "kabab"],                         "Starters"),
    (["veg main", "veg curry", "sabzi", "paneer",
      "dal", "daal", "palak"],                            "Veg Mains"),
    (["chicken", "mutton", "fish", "prawn", "seafood",
      "keema", "non-veg", "nonveg", "meat"],              "Non-Veg Mains"),
    (["roti", "naan", "paratha", "bread", "kulcha",
      "tandoor"],                                         "Breads"),
    (["rice", "pulao", "fried rice", "jeera rice"],       "Rice"),
    (["drink", "juice", "lassi", "shake", "milkshake",
      "coffee", "tea", "soda", "mojito", "mocktail",
      "beverage", "cold", "water"],                       "Beverages"),
    (["dessert", "sweet", "ice cream", "halwa",
      "gulab", "kheer", "brownie", "cake", "mithai"],     "Desserts"),
]

# ── Healthy / diet keywords ────────────────────────────────────────────────────
_HEALTHY_WORDS    = {"healthy", "healthy", "light", "low calorie", "diet",
                     "nutritious", "nutritious", "fit", "clean"}
_LOW_CAL_WORDS    = {"low calorie", "low-calorie", "fewer calories",
                     "less calories", "diet", "light"}
_VEG_WORDS        = {"veg", "vegetarian", "veggie", "plant", "no meat",
                     "without meat"}
_NONVEG_WORDS     = {"non-veg", "nonveg", "chicken", "mutton", "fish",
                     "prawn", "seafood", "meat", "egg"}


def _rule_parse(query: str) -> Dict[str, Any]:
    """Fast, regex + keyword-based extraction. No API call."""
    q = query.lower().strip()
    result: Dict[str, Any] = {
        "semantic_query":    query,
        "is_veg":           None,
        "max_price":        None,
        "min_price":        None,
        "max_calories":     None,
        "min_health_score": None,
        "section_name":     None,
    }

    # ── Price filters ─────────────────────────────────────────────────────────
    # "under ₹200", "less than 300", "below 150", "upto 200", "cheap under 100"
    m = re.search(r'(?:under|below|less\s+than|upto|up\s+to|within|<)\s*[₹rs\.]*\s*(\d+)', q)
    if m:
        result["max_price"] = int(m.group(1))

    m = re.search(r'(?:above|over|more\s+than|minimum|min|>)\s*[₹rs\.]*\s*(\d+)', q)
    if m:
        result["min_price"] = int(m.group(1))

    # ── Calorie filters ───────────────────────────────────────────────────────
    m = re.search(r'(?:under|below|less\s+than|low[- ]?er\s+than)\s*(\d+)\s*(?:kcal|cal|calories)', q)
    if m:
        result["max_calories"] = int(m.group(1))

    if any(w in q for w in _LOW_CAL_WORDS):
        result["max_calories"] = result["max_calories"] or 400

    # ── Health score ──────────────────────────────────────────────────────────
    if any(w in q for w in _HEALTHY_WORDS):
        result["min_health_score"] = 6

    m = re.search(r'health\s*(?:score)?\s*(?:above|over|>=|>)\s*(\d+)', q)
    if m:
        result["min_health_score"] = int(m.group(1))

    # ── Veg / Non-veg ─────────────────────────────────────────────────────────
    if any(w in q for w in _NONVEG_WORDS):
        result["is_veg"] = False
    elif any(w in q for w in _VEG_WORDS):
        result["is_veg"] = True

    # ── Category / section ────────────────────────────────────────────────────
    for keywords, section in _SECTION_KEYWORDS:
        if any(kw in q for kw in keywords):
            result["section_name"] = section
            break

    # ── Clean semantic query (remove filter phrases for better embedding) ──────
    clean = re.sub(
        r'(under|below|less than|upto|above|over|more than|minimum|within)\s*[₹rs\.]*\s*\d+',
        '', q, flags=re.IGNORECASE
    )
    clean = re.sub(r'\b(healthy|veg(etarian)?|non.?veg|cheap|affordable|expensive)\b',
                   '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s{2,}', ' ', clean).strip()
    result["semantic_query"] = clean or query

    return result


def _llm_parse(query: str, rule_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Qwen to fill in filters that rules missed.
    Only called when at least one key filter is still None.
    Returns merged result (LLM overrides None-valued rule fields only).
    """
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        return rule_result

    if not getattr(settings, "HUGGINGFACE_API_KEY", None):
        return rule_result

    prompt = f"""You are a restaurant search query parser. Extract search filters from this query.

Query: "{query}"

Return ONLY a JSON object (no extra text):
{{
  "is_veg": true/false/null,
  "max_price": integer or null,
  "min_price": integer or null,
  "max_calories": integer or null,
  "min_health_score": integer 1-10 or null,
  "section_name": one of [Biryani, Starters, Veg Mains, Non-Veg Mains, Breads, Rice, Beverages, Desserts, Snacks] or null,
  "semantic_query": "cleaned query for semantic search"
}}

Rules:
- is_veg = true only if user says "veg", "vegetarian", or similar
- is_veg = false if user mentions chicken/mutton/fish/meat/egg
- is_veg = null if no preference stated
- max_price: the price ceiling in rupees (null if not mentioned)
- min_health_score: set to 6 if user says "healthy", 7 if "very healthy", null otherwise
- section_name: null if no specific category mentioned
- semantic_query: remove filter words from the query"""

    try:
        client   = InferenceClient(token=settings.HUGGINGFACE_API_KEY)
        response = client.chat_completion(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$',          '', raw, flags=re.MULTILINE)

        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return rule_result

        llm_result = json.loads(match.group(0))

        # Merge: LLM overrides only where rule_result has None
        merged = dict(rule_result)
        for key in ("is_veg", "max_price", "min_price", "max_calories",
                    "min_health_score", "section_name", "semantic_query"):
            if merged.get(key) is None and llm_result.get(key) is not None:
                merged[key] = llm_result[key]

        return merged

    except Exception as e:
        logger.warning(f"QueryParser LLM pass failed: {e}. Using rule-based result.")
        return rule_result


class QueryParser:
    """
    Parse a natural language query into structured search filters.
    Uses fast rules first, then optionally calls Qwen for complex queries.
    """

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm and bool(getattr(settings, "HUGGINGFACE_API_KEY", None))

    def parse(self, query: str) -> Dict[str, Any]:
        """
        Returns a filter dict:
          semantic_query, is_veg, max_price, min_price,
          max_calories, min_health_score, section_name
        """
        result = _rule_parse(query)

        # Only call LLM if at least most filter keys are still None
        # (avoids wasting an API call when rules already extracted everything)
        none_count = sum(1 for k in ("is_veg", "max_price", "section_name")
                         if result[k] is None)

        if self.use_llm and none_count >= 2:
            result = _llm_parse(query, result)

        logger.info(f"QueryParser: '{query}' → {result}")
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────
_parser: Optional[QueryParser] = None

def get_query_parser() -> QueryParser:
    global _parser
    if _parser is None:
        _parser = QueryParser()
    return _parser
