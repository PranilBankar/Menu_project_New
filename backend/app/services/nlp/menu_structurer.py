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
            print(f"[LLM] Backend: HuggingFace  |  model pool: Qwen2.5-7B → Zephyr → Phi-3.5 → Mistral-v0.3")

        elif settings.OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.client  = OpenAI(api_key=settings.OPENAI_API_KEY)
                self.backend = "openai"
                logger.info("MenuStructurer: using OpenAI LLM backend.")
            except ImportError:
                logger.warning("openai package not installed.")

        else:
            print("MenuStructurer: no LLM key found — using keyword rules.")

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
        Call HuggingFace Inference API via the official InferenceClient.
        Tries multiple models in order — first available wins.
        Falls back to keyword rules if all models fail.
        """
        try:
            from huggingface_hub import InferenceClient
        except ImportError:
            logger.warning("huggingface_hub not installed. Run: pip install huggingface_hub")
            return self._enrich_with_rules(items)

        item_lines = "\n".join(
            f"{i+1}. {it['item']} - {it['price']}"
            for i, it in enumerate(items[:60])   # keep within token limits
        )
        n = len(items[:60])

        system_msg = "You are a restaurant menu nutrition expert. Return only valid JSON arrays, no extra text."
        user_msg = f"""You are given {n} menu items from an Indian restaurant called '{restaurant_name or 'a restaurant'}'.

Items (number. name - price in rupees):
{item_lines}

For each item, return a JSON array with exactly {n} objects in the SAME ORDER:
[
  {{
    "item_name": "corrected item name (fix obvious OCR typos)",
    "price": <number>,
    "section_name": "one of: Biryani, Starters, Veg Mains, Non-Veg Mains, Breads, Rice, Beverages, Desserts, Snacks",
    "is_veg": true or false,
    "calories": <integer — MANDATORY estimate>,
    "health_score": <integer 1-10 — MANDATORY>,
    "description": "one-line description"
  }}
]

STRICT RULES:
1. Use the PRICE as a quality/quantity signal when estimating calories and health_score:
   - Low price (< ₹60): smaller portion or simpler ingredients → adjust calories down and health_score accordingly
   - High price (> ₹300): larger portion or premium ingredients → adjust calories up
2. "calories" MUST be an integer — never null. Typical Indian portions:
   - Roti/Naan ₹20-50: 120-160 kcal | Dal ₹100-200: 250-350 kcal
   - Veg curry ₹150-250: 280-400 kcal | Chicken/Mutton curry ₹250-400: 350-500 kcal
   - Biryani ₹250-500: 450-650 kcal | Mocktail/Juice ₹80-150: 80-180 kcal
   - Tea/Coffee ₹30-80: 30-100 kcal | Desserts ₹80-200: 200-400 kcal
3. "health_score" MUST be an integer 1-10 (10 = most healthy):
   - 8-10: Grilled/steamed items, plain rice/roti, dal, salads, coconut water
   - 6-7: Veg curries, plain biryani, lassi, fresh juices
   - 4-5: Paneer dishes, fried rice, naan, flavoured beverages
   - 2-3: Deep fried snacks, heavy curries, mithai, biryanis with cream
   - 1-2: Gulab jamun, jalebi, energy drinks, heavily processed items
   - Lower price sometimes = lower quality oil/ingredients → reduce health_score by 1-2
4. is_veg = false for: chicken, mutton, fish, prawn, egg, keema, meat, seafood
5. Return ONLY the JSON array, starting with '[' and ending with ']'"""


        # Try models in order — first available wins
        models_to_try = [
            "Qwen/Qwen2.5-7B-Instruct",
            "HuggingFaceH4/zephyr-7b-beta",
            "microsoft/Phi-3.5-mini-instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ]

        client = InferenceClient(token=settings.HUGGINGFACE_API_KEY)

        for model_id in models_to_try:
            try:
                print(f"[LLM] Trying model: {model_id} ...")
                response = client.chat_completion(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user",   "content": user_msg},
                    ],
                    max_tokens=5000,      # increased: more fields per item now
                    temperature=settings.LLM_TEMPERATURE,
                )
                generated = response.choices[0].message.content.strip()

                # Strip markdown code fences
                generated = re.sub(r'^```(?:json)?\s*', '', generated, flags=re.MULTILINE)
                generated = re.sub(r'```\s*$',          '', generated, flags=re.MULTILINE)

                # Extract JSON array
                match = re.search(r'(\[.*\])', generated, re.DOTALL)
                if not match:
                    raise ValueError(f"No JSON array in response from {model_id}")

                enriched = json.loads(match.group(1))

                # Normalise key names — different models use different conventions
                _KEY_MAP = {
                    "vegetarian":    "is_veg",
                    "is_vegetarian": "is_veg",
                    "veg":           "is_veg",
                    "calorie":       "calories",
                    "calorie_count": "calories",
                    "kcal":          "calories",
                    "score":         "health_score",
                    "healthscore":   "health_score",
                    "health":        "health_score",
                    "name":          "item_name",
                    "category":      "section_name",
                    "section":       "section_name",
                }
                enriched = [
                    {_KEY_MAP.get(k.lower().replace(" ", "_"), k): v for k, v in obj.items()}
                    for obj in enriched
                ]

                print(f"[LLM] SUCCESS: enriched {len(enriched)} items using {model_id}")
                for dbg in enriched[:3]:
                    print(f"  DEBUG → '{dbg.get('item_name')}' | cal={dbg.get('calories')} | health={dbg.get('health_score')} | veg={dbg.get('is_veg')} | section={dbg.get('section_name')}")

                if len(items) > 60:
                    enriched += self._enrich_with_rules(items[60:])

                return enriched

            except Exception as e:
                logger.warning(f"Model {model_id} failed: {e}. Trying next...")
                continue


        logger.warning("All HuggingFace models failed. Falling back to keyword rules.")
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
