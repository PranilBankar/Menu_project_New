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
from app.services.nlp.category_classifier import get_category_classifier, CATEGORY_DESCRIPTIONS

logger = logging.getLogger(__name__)


class MenuStructurer:
    """Enrich raw (item, price) pairs with LLM-assigned metadata."""

    # HuggingFace Inference API endpoint template
    HF_API_URL = "https://api-inference.huggingface.co/models/{model}"

    def __init__(self):
        self.backend = None
        self.client  = None

        if getattr(settings, "GROQ_API_KEY", None):
            try:
                from groq import Groq
                self.client = Groq(api_key=settings.GROQ_API_KEY)
                self.backend = "groq"
                logger.info("MenuStructurer: using Groq LLM backend.")
            except ImportError:
                logger.warning("groq package not installed.")
        elif getattr(settings, "OPENAI_API_KEY", None):
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

        if self.backend in ("groq", "openai"):
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

        item_strings = []
        classifier = get_category_classifier()
        for j, it in enumerate(items[:60]):
            pred_cat = classifier.predict(it['item'])
            cat_hint = f"(Section: {pred_cat})" if pred_cat else "(Section: UNKNOWN)"
            item_strings.append(f"{j+1}. {it['item']} - {it['price']}  {cat_hint}")
            
        item_lines = "\n".join(item_strings)
        n = len(items[:60])
        
        allowed_cats = ", ".join(CATEGORY_DESCRIPTIONS.keys())

        system_msg = "You are a restaurant menu nutrition expert. Return only valid JSON arrays, no extra text."
        user_msg = f"""You are a strict food classification system.

Items (number. name - price - category status):
{item_lines}

For each item, return a JSON array with exactly {n} objects in the SAME ORDER:
[
  {{
    "item_name": "corrected item name (fix obvious OCR typos)",
    "price": <number>,
    "section_name": "Must be exactly the provided Section if given. If UNKNOWN, choose ONLY from: [{allowed_cats}]",
    "is_veg": true or false,
    "calories": <integer — MANDATORY estimate>,
    "health_score": <integer 1-10 — MANDATORY>,
    "description": "one-line description"
  }}
]

STRICT RULES:
1. "section_name" MUST be chosen from the allowed list if UNKNOWN. DO NOT invent categories.
2. If a Section is already provided in the input, you MUST use exactly that Section.
3. Use the PRICE to estimate calories (higher price = bigger portion). calories MUST be integer.
4. health_score MUST be an integer 1-10 (10 = healthiest).
5. is_veg = false for chicken, mutton, fish, prawn, egg.
6. Return ONLY the JSON array, starting with '[' and ending with ']'"""


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
        """Send items to Groq/OpenAI in batches to avoid rate limits."""
        enriched_all = []
        chunk_size = 25  # Down from 35 to prevent JSON output being cut off mid-response
        
        classifier = get_category_classifier()
        allowed_cats = ", ".join(CATEGORY_DESCRIPTIONS.keys())
        
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i + chunk_size]
            
            item_strings = []
            for j, it in enumerate(chunk):
                pred_cat = classifier.predict(it['item'])
                cat_hint = f"(Section: {pred_cat})" if pred_cat else "(Section: UNKNOWN)"
                item_strings.append(f"{j+1}. {it['item']} — ₹{it['price']}  {cat_hint}")
                
            item_lines = "\n".join(item_strings)
            n_items = len(chunk)

            prompt = f"""You are a strict food classification system. Below are {n_items} menu items extracted from a restaurant menu.
Restaurant: {restaurant_name or "Unknown"}

Items (item name — price — category status):
{item_lines}

For EACH item return a JSON array with exactly {n_items} objects in the same order:
[
  {{
    "item_name": "cleaned item name (fix obvious OCR typos)",
    "price": <number>,
    "section_name": "Must be exactly the provided Section if given. If UNKNOWN, choose ONLY from the Permitted Categories list below.",
    "is_veg": true or false,
    "calories": <integer — MANDATORY estimate, typically 100-600>,
    "health_score": <integer 1-10 — MANDATORY (10 = healthiest)>,
    "description": "one short line description"
  }}
]

Permitted Categories:
[{allowed_cats}]

Examples for UNKNOWN items:
- Honey Chilli Potato → Chinese
- Cheese Burger → Fast Food
- Paneer Butter Masala → North Indian

Rules:
1. Fix obvious OCR noise in item names
2. If a Section is already provided in the input, you MUST use exactly that Section.
3. You MUST choose ONLY from the Permitted Categories. DO NOT create new categories. Base classification on cuisine.
4. is_veg: true only if definitely vegetarian, false if meat/egg/fish
5. calories MUST be an integer. Keep typical Indian food in mind.
6. health_score MUST be an integer 1-10. Salads/steamed items are 8-10. Fried/Desserts are 1-4.
7. Return ONLY the JSON array, no extra text.
"""
            model_name = "llama-3.1-8b-instant" if self.backend == "groq" else settings.LLM_MODEL
            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a menu digitization expert. Return only valid JSON arrays."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=3500,  # increased to prevent unterminated JSON responses
                )
                content = response.choices[0].message.content.strip()
                content = re.sub(r'^```(?:json)?\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                
                _KEY_MAP = {
                    "vegetarian": "is_veg", "is_vegetarian": "is_veg", "veg": "is_veg",
                    "calorie": "calories", "score": "health_score", "name": "item_name",
                    "category": "section_name", "section": "section_name",
                }
                
                raw_enriched = json.loads(content)
                enriched_chunk = [
                    {_KEY_MAP.get(k.lower(), k): v for k, v in obj.items()}
                    for obj in raw_enriched
                ]
                enriched_all.extend(enriched_chunk)

            except Exception as e:
                logger.warning(f"Groq/Primary LLM chunk failed ({e}).")
                print(f"[ERROR] Groq LLM failed on chunk: {e}")
                
                # Fallback to HuggingFace if key exists
                if getattr(settings, "HUGGINGFACE_API_KEY", None):
                    print(f"  ---> Falling back to HuggingFace models for this chunk...")
                    hf_fallback = self._enrich_with_huggingface(chunk, restaurant_name)
                    # If HF fallback returned same length, we consider it successful, else rules.
                    if len(hf_fallback) == len(chunk):
                        enriched_all.extend(hf_fallback)
                    else:
                        enriched_all.extend(self._enrich_with_rules(chunk))
                else:
                    print(f"  ---> Falling back to keyword rules for this chunk.")
                    enriched_all.extend(self._enrich_with_rules(chunk))

        return enriched_all

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
