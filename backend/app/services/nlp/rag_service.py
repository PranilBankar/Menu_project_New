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

    def __init__(self, top_k: int = 6):
        self.top_k      = top_k
        self.parser     = get_query_parser()
        self._hf_client = None   # lazy-init

    # ── Public API ─────────────────────────────────────────────────────────────

    def chat(self,
             query:         str,
             area_name:     str = "",
             restaurant_id: Optional[str] = None) -> Dict[str, Any]:
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

        # 2. Hybrid search
        restaurant_ids = [restaurant_id] if restaurant_id else None
        with EmbeddingService() as svc:
            items = svc.hybrid_search(
                query=query,
                filters=filters,
                top_k=self.top_k,
                restaurant_ids=restaurant_ids,
            )

        # 3. Generate response
        if not items:
            return {
                "answer":       "Sorry, I couldn't find any menu items matching your query. Try broadening your search!",
                "items":        [],
                "filters_used": filters,
            }

        answer = self._generate_answer(query, items, area_name)

        return {
            "answer":       answer,
            "items":        items,
            "filters_used": filters,
        }

    # ── LLM Response Generation ────────────────────────────────────────────────

    def _generate_answer(self,
                         query: str,
                         items: List[Dict[str, Any]],
                         area_name: str) -> str:
        """Call Qwen to produce a natural language answer given retrieved items."""

        # Format items into a readable context block
        item_lines = []
        for i, it in enumerate(items, 1):
            veg_tag = "Veg" if it.get("is_veg") else "Non-Veg"
            cal     = f"{it['calories']} kcal" if it.get("calories") else "cal unknown"
            hs      = f"health {it['health_score']}/10" if it.get("health_score") else ""
            item_lines.append(
                f"{i}. {it['item_name']} — {it.get('section_name','?')} — "
                f"₹{it['price']} — {veg_tag} — {cal} {hs}"
            )
        context = "\n".join(item_lines)

        area_str = f" in {area_name}" if area_name else ""

        prompt = f"""You are a friendly and knowledgeable restaurant food assistant{area_str}.

A customer asked: "{query}"

Here are the most relevant menu items found:
{context}

Write a helpful, conversational response (2-4 sentences):
- Mention 2-3 of the best matching items by name with their price
- Highlight why they match the customer's request (veg/non-veg, price, health)
- Be warm and encouraging
- Do NOT make up items not in the list above"""

        try:
            client = self._get_hf_client()
            if client is None:
                return self._fallback_answer(query, items)

            response = client.chat_completion(
                model="Qwen/Qwen2.5-7B-Instruct",
                messages=[
                    {"role": "system", "content": "You are a helpful restaurant food assistant. Be concise and friendly."},
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
