"""
RAG Service — orchestrates the full Retrieval-Augmented Generation pipeline.

Flow:
  1. QueryParser  → extract filters + clean semantic query
  2. EmbeddingService.hybrid_search(area_name=...) → items from ALL restaurants in the area
  3. Qwen (HuggingFace) → generate natural language response comparing across restaurants

Usage:
    svc = RAGService()
    result = svc.chat("non-veg curry under ₹200 near me", area_name="Nagpur")
    print(result["answer"])
    print(result["items"])
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.services.nlp.query_parser import get_query_parser
from app.services.nlp.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class RAGService:
    """
    End-to-end RAG pipeline for location-aware multi-restaurant food discovery.
    """

    def __init__(self, top_k: int = 15):
        self.top_k      = top_k
        self.parser     = get_query_parser()
        self._hf_client = None

    # ── Hard vs Soft filter split ──────────────────────────────────────────────
    HARD_FILTER_KEYS = {"is_veg", "max_price", "min_price"}
    SOFT_FILTER_KEYS = {"section_name", "min_health_score", "max_calories"}

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(self,
             query:         str,
             area_name:     str = "",
             restaurant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Answer a natural language food query for a given area.
        Searches across ALL restaurants in the area unless restaurant_id is given.

        Returns:
            {
              "answer":       str,         # LLM-generated response
              "items":        List[dict],  # top retrieved menu items with restaurant_name
              "filters_used": dict,
            }
        """
        # 1. Parse query → structured filters
        filters = self.parser.parse(query)
        logger.info(f"RAG: parsed filters = {filters}")

        # 2. Hard SQL filters only (area + price + veg)
        hard_filters = {k: v for k, v in filters.items()
                        if k in self.HARD_FILTER_KEYS and v is not None}
        hard_filters["semantic_query"] = filters.get("semantic_query", query)

        restaurant_ids = [restaurant_id] if restaurant_id else None

        with EmbeddingService() as svc:
            items = svc.hybrid_search(
                query=query,
                filters=hard_filters,
                top_k=self.top_k,
                restaurant_ids=restaurant_ids,
                area_name=area_name or None,
            )

        if not items:
            return {
                "answer":       "Sorry, I couldn't find any matching items near you. Try broadening your search!",
                "items":        [],
                "filters_used": filters,
            }

        # 3. LLM re-ranks and generates human response (with soft hints)
        soft_hints = {k: filters.get(k) for k in self.SOFT_FILTER_KEYS}
        answer = self._generate_answer(query, items, area_name, soft_hints=soft_hints)

        return {
            "answer":       answer,
            "items":        items,
            "filters_used": filters,
        }

    # ── LLM Response Generation ────────────────────────────────────────────────

    def _generate_answer(self,
                         query:      str,
                         items:      List[Dict[str, Any]],
                         area_name:  str,
                         soft_hints: Optional[Dict[str, Any]] = None) -> str:
        """Qwen selects 3-4 best items from candidates and writes a human response."""

        soft_hints = soft_hints or {}

        # Format items: "ItemName @ RestaurantName — Category — ₹Price — Veg — Cal — Health"
        item_lines = []
        for i, it in enumerate(items, 1):
            veg_tag = "Veg" if it.get("is_veg") else "Non-Veg"
            cal     = f"{it['calories']} kcal" if it.get("calories") else "?"
            hs      = f"health {it['health_score']}/10" if it.get("health_score") else ""
            rest    = it.get("restaurant_name", "Unknown Restaurant")
            item_lines.append(
                f"{i}. {it['item_name']} @ {rest} — {it.get('section_name','?')} — "
                f"₹{it['price']} — {veg_tag} — {cal} {hs}"
            )
        context = "\n".join(item_lines)

        loc = area_name or "your area"

        # Soft preference hints for the LLM
        hint_lines = []
        if soft_hints.get("section_name"):
            hint_lines.append(f"- Prefer {soft_hints['section_name']} items")
        if soft_hints.get("min_health_score"):
            hint_lines.append(f"- Prefer health score >= {soft_hints['min_health_score']}/10")
        if soft_hints.get("max_calories"):
            hint_lines.append(f"- Prefer items <= {soft_hints['max_calories']} kcal")
        pref_block = ("\nUser preferences:\n" + "\n".join(hint_lines)) if hint_lines else ""

        system_msg = (
            "You are a friendly, local food guide. You help people discover great food "
            "at restaurants near them. Speak warmly and naturally, like a knowledgeable "
            "friend who knows all the best spots. Never sound robotic."
        )

        prompt = f"""Someone near {loc} is looking for food and asked:
"{query}"

Here are menu items from nearby restaurants:
{context}
{pref_block}

Write a warm, helpful 3-5 sentence recommendation:
- Mention {loc} to make it feel local and personal
- Pick the 3-4 BEST matching items — skip anything clearly irrelevant
- For each item, say its name, the restaurant it's from, and its price
- Explain briefly WHY it matches (taste, health, price value, diet type)
- Sound like a friend giving a genuine recommendation, not a search engine
- No bullet points, no numbering — just natural flowing conversation
- Do NOT invent items or prices not in the list above"""

        try:
            client = self._get_hf_client()
            if client is None:
                return self._fallback_answer(query, items)

            response = client.chat_completion(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=350,
                temperature=0.75,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"RAG LLM response failed: {e}. Using fallback.")
            return self._fallback_answer(query, items)

    def _fallback_answer(self, query: str, items: List[Dict[str, Any]]) -> str:
        top3 = items[:3]
        parts = [
            f"{it['item_name']} at {it.get('restaurant_name','?')} (₹{it['price']})"
            for it in top3
        ]
        return (
            f"Here are some great matches for \"{query}\" near you: "
            + ", ".join(parts) + ". All options were selected based on your query."
        )

    def _get_hf_client(self):
        if self._hf_client is not None:
            return self._hf_client
        hf_key = getattr(settings, "HUGGINGFACE_API_KEY", None)
        if not hf_key:
            return None
        try:
            from huggingface_hub import InferenceClient
            self._hf_client = InferenceClient(token=hf_key)
            return self._hf_client
        except ImportError:
            logger.warning("huggingface_hub not installed.")
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────
_rag_service: Optional[RAGService] = None

def get_rag_service() -> RAGService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


