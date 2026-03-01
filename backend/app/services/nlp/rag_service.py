"""
RAG Service — orchestrates the full Retrieval-Augmented Generation pipeline.

Flow:
  1. QueryParser  → extract filters + clean semantic query
  2. EmbeddingService.hybrid_search() → top-k relevant items from Supabase
  3. Qwen (HuggingFace) → generate natural language response using items as context

Usage:
    svc = RAGService()
    result = svc.chat("healthy veg food under ₹200", area_name="Nagpur")
    print(result["answer"])
    print(result["items"])
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, Any, List, Optional

from app.core.config import settings
from app.services.nlp.query_parser import get_query_parser
from app.services.nlp.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class RAGService:
    """
    End-to-end RAG pipeline for menu-based food discovery chatbot.
    Thread-safe: EmbeddingService connection is created per-call (context manager).
    """

    def __init__(self, top_k: int = 15):
        self.top_k      = top_k
        self.parser     = get_query_parser()
        self._hf_client = None

    # ── Hard vs Soft filter split ──────────────────────────────────────────────
    HARD_FILTER_KEYS = {"is_veg", "max_price", "min_price"}   # applied in SQL
    SOFT_FILTER_KEYS = {"section_name", "min_health_score", "max_calories"}  # LLM hints

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(self,
             query:           str,
             area_name:       str = "",
             restaurant_id:   Optional[str] = None,
             restaurant_name: str = "") -> Dict[str, Any]:
        """
        Answer a natural language food query.

        Returns:
            {
              "answer":       str,         # LLM-generated response
              "items":        List[dict],  # top retrieved menu items
              "filters_used": dict,        # extracted filters for transparency
            }
        """
        # 1. Parse query → structured filters
        filters = self.parser.parse(query)
        logger.info(f"RAG: parsed filters = {filters}")

        # 2. Hybrid search — ONLY apply hard SQL filters for wide retrieval
        hard_filters = {k: v for k, v in filters.items()
                        if k in self.HARD_FILTER_KEYS and v is not None}
        hard_filters["semantic_query"] = filters.get("semantic_query", query)

        restaurant_ids = [restaurant_id] if restaurant_id else None
        with EmbeddingService() as svc:
            items = svc.hybrid_search(
                query=query,
                filters=hard_filters,
                top_k=self.top_k,     # retrieve more candidates
                restaurant_ids=restaurant_ids,
            )

        # 3. Generate response — LLM re-ranks and filters from all candidates
        if not items:
            return {
                "answer":       "Sorry, I couldn't find any menu items matching your query. Try broadening your search!",
                "items":        [],
                "filters_used": filters,
            }

        soft_hints = {k: filters.get(k) for k in self.SOFT_FILTER_KEYS}
        answer = self._generate_answer(query, items, area_name,
                                       soft_hints=soft_hints,
                                       restaurant_name=restaurant_name)

        return {
            "answer":       answer,
            "items":        items,
            "filters_used": filters,
        }

    # ── LLM Response Generation ────────────────────────────────────────────────

    def _generate_answer(self,
                         query: str,
                         items: List[Dict[str, Any]],
                         area_name: str,
                         soft_hints: Optional[Dict[str, Any]] = None,
                         restaurant_name: str = "") -> str:
        """Call Qwen to select best items and produce a natural language answer."""

        soft_hints = soft_hints or {}

        # Format all candidate items — include restaurant name on each line
        rest_label = f" @ {restaurant_name}" if restaurant_name else ""
        item_lines = []
        for i, it in enumerate(items, 1):
            veg_tag = "Veg" if it.get("is_veg") else "Non-Veg"
            cal     = f"{it['calories']} kcal" if it.get("calories") else "?"
            hs      = f"health {it['health_score']}/10" if it.get("health_score") else ""
            item_lines.append(
                f"{i}. {it['item_name']} — {it.get('section_name','?')} — "
                f"₹{it['price']} — {veg_tag} — {cal} {hs}"
            )
        context = "\n".join(item_lines)

        # Build context header with restaurant + area
        location_parts = []
        if restaurant_name:
            location_parts.append(restaurant_name)
        if area_name:
            location_parts.append(area_name)
        location_str = ", ".join(location_parts) or "this restaurant"

        # Build soft-hint guidance
        hint_lines = []
        if soft_hints.get("section_name"):
            hint_lines.append(f"- Prefer items from the '{soft_hints['section_name']}' category")
        if soft_hints.get("min_health_score"):
            hint_lines.append(f"- Prefer items with health score >= {soft_hints['min_health_score']}/10")
        if soft_hints.get("max_calories"):
            hint_lines.append(f"- Prefer items with calories <= {soft_hints['max_calories']} kcal")
        soft_guidance = ("\nAdditional preferences:\n" + "\n".join(hint_lines)) if hint_lines else ""

        system_msg = (
            "You are a warm, knowledgeable food guide who helps customers find the "
            "perfect dish at a restaurant. You speak like a helpful friend — naturally, "
            "enthusiastically, and conversationally. Never sound robotic or list-like."
        )

        prompt = f"""A customer is browsing the menu at **{location_str}** and asked:

"{query}"

Here are the available menu items to choose from:
{context}
{soft_guidance}

Your response guidelines:
- Start by mentioning **{location_str}** naturally (e.g. "At Mac D, ..." or "Mac D has some great options...")
- Pick the 3-4 items that BEST match what the customer wants — skip irrelevant ones entirely
- Mention each chosen item by name with its price, and say WHY it's a good fit for this customer
- Sound warm, genuine and helpful — like a knowledgeable friend recommending food
- 3-5 sentences max, no bullet points, no numbering, just natural flowing text
- Do NOT make up items or prices not in the list above"""

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
                max_tokens=300,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"RAG LLM response failed: {e}. Using fallback.")
            return self._fallback_answer(query, items)

    def _fallback_answer(self, query: str, items: List[Dict[str, Any]]) -> str:
        """Simple template-based answer when LLM is unavailable."""
        top3 = items[:3]
        names = ", ".join(
            f"{it['item_name']} (₹{it['price']})" for it in top3
        )
        return (
            f"Based on your query \"{query}\", here are some great options: {names}. "
            f"These were selected based on relevance, price, and nutritional profile."
        )

    def _get_hf_client(self):
        """Lazy-init HuggingFace InferenceClient."""
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
