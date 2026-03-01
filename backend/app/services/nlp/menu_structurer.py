"""
Menu Structurer - Enrich parsed menu items using LLM
-----------------------------------------------------
Takes the flat (item_name, price) list from menu_layout_parser and asks
the LLM to assign:
  - section/category name (Biryani, Beverages, Desserts, etc.)
  - is_veg (true/false)
  - calories (estimate)
  - description (brief)
  - cleaned item name (fixes OCR typos where obvious)

Falls back to rule-based defaults when no LLM key is configured.
"""

import json
import re
import logging
from typing import Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class MenuStructurer:
    """Enrich raw (item, price) pairs with LLM-assigned metadata."""

    # HuggingFace Inference API endpoint template
    HF_API_URL = "https://api-inference.huggingface.co/models/{model}"

    def __init__(self):
        self.backend = None   # "huggingface" | "openai" | None (rules)
        self.client  = None   # only set for openai

        provider = getattr(settings, "LLM_PROVIDER", None)

        if provider == "huggingface" and settings.HUGGINGFACE_API_KEY:
            self.backend = "huggingface"
            self._hf_headers = {
                "Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}",
                "Content-Type":  "application/json",
            }
            self._hf_url = self.HF_API_URL.format(model=settings.LLM_MODEL)
            logger.info(f"MenuStructurer: using HuggingFace backend ({settings.LLM_MODEL}).")

        elif settings.OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.client  = OpenAI(api_key=settings.OPENAI_API_KEY)
                self.backend = "openai"
                logger.info("MenuStructurer: using OpenAI LLM backend.")
            except ImportError:
                logger.warning("openai package not installed.")

        else:
            logger.info("MenuStructurer: no LLM key found — using keyword rules.")

    # ── Public API ────────────────────────────────────────────────────────────

    def enrich(self,
               parsed_items: List[Dict],
               restaurant_name: str = "",
               raw_ocr_text: str = "") -> List[Dict]:
        """
        Enrich a flat list of { "item": str, "price": float } dicts.

        Args:
            parsed_items:    Output of menu_layout_parser.parse_menu()
            restaurant_name: Optional, used as context for the LLM prompt
            raw_ocr_text:    Optional full OCR text for extra context

        Returns:
            List of dicts:
              { item_name, price, section_name, is_veg, calories, description }
        """
        if not parsed_items:
            return []

        if self.backend == "huggingface":
            return self._enrich_with_huggingface(parsed_items, restaurant_name)
        elif self.backend == "openai":
            return self._enrich_with_llm(parsed_items, restaurant_name, raw_ocr_text)
        else:
            return self._enrich_with_rules(parsed_items)

    # ── LLM path ─────────────────────────────────────────────────────────────

    def _enrich_with_huggingface(self,
                                  items: List[Dict],
                                  restaurant_name: str) -> List[Dict]:
        """
        Call HuggingFace Inference API (Mistral-7B-Instruct or similar).
        Uses the [INST] prompt format expected by Mistral-family models.
        """
        import requests

        item_lines = "\n".join(
            f"{i+1}. {it['item']} — {it['price']}"
            for i, it in enumerate(items[:80])  # HF free tier has token limits
        )
        n = len(items[:80])

        prompt = f"""[INST] You are a restaurant menu expert. Enrich these {n} menu items from '{restaurant_name or 'a restaurant'}' with category, veg status, and calories.

Items:
{item_lines}

Return ONLY a valid JSON array with exactly {n} objects:
[
  {{"item_name": "cleaned name", "price": <number>, "section_name": "category", "is_veg": true/false, "calories": <int or null>, "description": "one line"}},
  ...
]

Rules: fix OCR typos in names, use Indian restaurant categories (Biryani/Starters/Veg Mains/Non-Veg Mains/Breads/Rice/Beverages/Desserts), is_veg=false for meat/egg/fish items. Return ONLY the JSON array. [/INST]"""

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature":  settings.LLM_TEMPERATURE,
                "max_new_tokens": 3000,
                "return_full_text": False,
            }
        }

        try:
            resp = requests.post(
                self._hf_url,
                headers=self._hf_headers,
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json()

            # HF returns [{"generated_text": "..."}]
            generated = raw[0]["generated_text"] if isinstance(raw, list) else raw.get("generated_text", "")

            # Extract JSON array from the response
            match = re.search(r'\[.*\]', generated, re.DOTALL)
            if not match:
                raise ValueError("No JSON array found in HF response")

            enriched = json.loads(match.group(0))

            # Handle remaining items beyond the 80-item limit with rules
            if len(items) > 80:
                enriched += self._enrich_with_rules(items[80:])

            return enriched

        except Exception as e:
            logger.warning(f"HuggingFace enrichment failed: {e}. Falling back to keyword rules.")
            return self._enrich_with_rules(items)

    def _enrich_with_llm(self,
                          items: List[Dict],
                          restaurant_name: str,
                          raw_ocr_text: str) -> List[Dict]:
        """Send items to OpenAI and get back enriched records."""
        # Build a compact item list for the prompt (max 120 items)
        item_lines = "\n".join(
            f"{i+1}. {it['item']} — ₹{it['price']}"
            for i, it in enumerate(items[:120])
        )

        prompt = f"""You are a restaurant menu expert. Below are menu items extracted via OCR from a restaurant menu.

Restaurant: {restaurant_name or "Unknown"}

Items (item name — price):
{item_lines}

For EACH item return a JSON array with exactly {len(items[:120])} objects in the same order:
[
  {{
    "item_name": "cleaned item name (fix obvious OCR typos, keep it concise)",
    "price": <number>,
    "section_name": "category like Biryani / Beverages / Starters / Main Course / Desserts / Breads / Rice / etc.",
    "is_veg": true or false,
    "calories": <estimated integer or null if uncertain>,
    "description": "one short line description"
  }},
  ...
]

Rules:
1. Fix obvious OCR noise in item names (e.g. "Grilled Chiken" → "Grilled Chicken")
2. Assign sensible Indian restaurant categories based on the item name
3. is_veg: true only if definitely vegetarian, false if meat/egg/fish
4. calories: rough estimate based on typical portion sizes, null if unsure
5. Return ONLY the JSON array, no extra text.
"""

        try:
            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "You are a menu digitization expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4000,
            )
            content = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            enriched = json.loads(content)

            # Merge any items beyond the 120-item LLM limit with rule-based defaults
            if len(items) > 120:
                enriched += self._enrich_with_rules(items[120:])

            return enriched

        except Exception as e:
            logger.warning(f"LLM enrichment failed ({e}). Falling back to rules.")
            return self._enrich_with_rules(items)

    # ── Rule-based fallback ───────────────────────────────────────────────────

    # Simple keyword → category map
    _CATEGORY_RULES = [
        (["biryani", "pulao", "dum"],                      "Biryani"),
        (["roti", "naan", "paratha", "kulcha", "bread"],   "Breads"),
        (["rice", "jeera", "khichdi"],                     "Rice"),
        (["lassi", "juice", "soda", "water", "coffee",
          "tea", "milk", "shake", "mojito", "mocktail",
          "cola", "pepsi", "energy", "bull"],              "Beverages"),
        (["ice cream", "kulfi", "halwa", "gulab",
          "brownie", "rasgulla", "kheer", "dessert"],      "Desserts"),
        (["soup", "salad", "tikka", "kebab", "kabab",
          "samosa", "roll", "starter"],                    "Starters"),
        (["chicken", "mutton", "fish", "prawn", "egg",
          "keema", "murg"],                                "Non-Veg Mains"),
        (["paneer", "dal", "veg", "sabzi", "curry",
          "masala", "makhani"],                            "Veg Mains"),
    ]

    _NON_VEG_KEYWORDS = {"chicken", "mutton", "fish", "prawn", "egg",
                         "keema", "meat", "beef", "pork", "lamb"}

    def _guess_category(self, item_name: str) -> str:
        lower = item_name.lower()
        for keywords, category in self._CATEGORY_RULES:
            if any(kw in lower for kw in keywords):
                return category
        return "Menu Items"

    def _guess_is_veg(self, item_name: str) -> bool:
        lower = item_name.lower()
        return not any(kw in lower for kw in self._NON_VEG_KEYWORDS)

    def _enrich_with_rules(self, items: List[Dict]) -> List[Dict]:
        """Fallback: assign categories and is_veg using keyword rules."""
        result = []
        for it in items:
            name = it.get("item", "")
            result.append({
                "item_name":    name,
                "price":        it.get("price"),
                "section_name": self._guess_category(name),
                "is_veg":       self._guess_is_veg(name),
                "calories":     None,
                "description":  "",
            })
        return result


# ── Singleton ─────────────────────────────────────────────────────────────────

_structurer: Optional[MenuStructurer] = None

def get_menu_structurer() -> MenuStructurer:
    global _structurer
    if _structurer is None:
        _structurer = MenuStructurer()
    return _structurer
