"""
Category Classifier — Handles robust menu section assignment.
Uses Rules → Embeddings → LLM Fallback (handled in MenuStructurer).
"""

import numpy as np
import logging
from typing import Optional

from app.services.nlp.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)

# The specific ontology mapped to keyword descriptions for embeddings
CATEGORY_DESCRIPTIONS = {
    "Chinese": "noodles, manchurian, schezwan, chilli, fried rice, hakka, spring roll, momos, chop suey, dimsum",
    "North Indian": "paneer, dal, chole, rajma, kofta, bhindi, kadai, sabzi, butter masala, yellow dal, makhani",
    "South Indian": "dosa, idli, vada, sambhar, uttapam, rasam, upma, coconut chutney",
    "Fast Food": "pizza, burger, fries, sandwich, wrap, pasta, nuggets, garlic bread",
    "Street Food": "chaat, pav bhaji, bhel, pani puri, golgappa, tikki, vadapav, kachori",
    "Biryani": "biryani rice dishes with spices, pulao",
    "Rice ": "rice, jeera rice, steamed rice, fried rice",
    "Indian Breads": "roti, naan, paratha, kulcha, chapati, phulka, tandoori roti",
    "Curries & Gravies": "gravy, curry, masala, makhani, korma",
    "Snacks & Starters": "appetizers, finger food, cutlet, tikki, pakora, samosa, chaat, chilli, tikka",
    "Desserts": "sweet dishes, ice cream, gulab jamun, rasgulla, brownie, cake, halwa, kheer, pastry",
    "Beverages": "drinks, juices, shakes, tea, coffee, cold drink, lassi, mocktail, soda, water, mojito",
    "Salads & Healthy": "salad, green salad, sprouts, boiled vegetables, soup",
    "Thali & Combos": "thali, combo meal, mini meal, executive meal",
    "Tandoor & Grills": "tandoori, grilled meats, tikka, kebab, seekh, roast, tandoor",
    "Seafood": "fish, prawn, crab, surmai, pomfret, seafood",
    "Egg Dishes": "egg, anda, bhurji, omelette, boiled egg",
}

class CategoryClassifier:
    def __init__(self, confidence_threshold: float = 0.80):
        self.threshold = confidence_threshold
        self.categories = list(CATEGORY_DESCRIPTIONS.keys())
        self.category_texts = list(CATEGORY_DESCRIPTIONS.values())
        
        # Cache category embeddings
        self.embed_service = get_embedding_service()
        
        logger.info(f"CategoryClassifier: Generating vectors for {len(self.categories)} predefined categories...")
        # Shape: (N, 384)
        self.category_embeddings = self.embed_service.generate_embeddings(self.category_texts)

    def rule_based_category(self, item_name: str) -> Optional[str]:
        """Extremely fast heuristics for obvious culinary terms."""
        lower = item_name.lower()
        
        if any(x in lower for x in ["chilli", "manchurian", "hakka", "schezwan", "momos", "chop suey"]):
            return "Chinese"
        if any(x in lower for x in ["pizza", "burger", "sandwich", "fries", "pasta", "wrap"]):
            return "Fast Food"
        if any(x in lower for x in ["biryani"]):
            return "Biryani"
        if any(x in lower for x in ["roti", "naan", "paratha", "kulcha", "chapati", "phulka"]):
            return "Indian Breads"
        if any(x in lower for x in ["ice cream", "gulab jamun", "brownie", "kheer", "halwa", "pastry"]):
            return "Desserts"
        if any(x in lower for x in ["dosa", "idli", "vada", "sambhar", "uttapam"]):
            return "South Indian"
        if any(x in lower for x in ["shake", "juice", "coffee", "tea", "lassi", "mojito", "water", "soda"]):
            return "Beverages"
        if any(x in lower for x in ["paneer", "dal", "chole", "rajma"]):
            if any(y in lower for y in ["tikka", "chilli", "pakora"]):
                return "Snacks & Starters"
            return "North Indian"
        if any(x in lower for x in ["thali", "combo"]):
            return "Thali & Combos"
            
        return None

    def predict(self, item_name: str) -> Optional[str]:
        """
        Run the hybrid Rule -> Embedding pipeline to assign a category.
        Returns None if confidence is below threshold, letting LLM fallback handle it.
        """
        # 1. Rules
        cat = self.rule_based_category(item_name)
        if cat:
            return cat
            
        # 2. Embeddings
        # _get_conn() ensures the pgvector extension handles models, generate_embeddings normalizes arrays.
        item_emb = self.embed_service.generate_embeddings([item_name])
        
        # calculate dot product of item embedding with all cached category embeddings
        # Since normalize_embeddings=True, dot product equates to cosine similarity.
        similarities = np.dot(self.category_embeddings, item_emb[0])
        
        best_idx = np.argmax(similarities)
        confidence = similarities[best_idx]
        
        if confidence >= self.threshold:
            return self.categories[best_idx]
            
        return None

_classifier: Optional[CategoryClassifier] = None

def get_category_classifier() -> CategoryClassifier:
    global _classifier
    if _classifier is None:
        _classifier = CategoryClassifier()
    return _classifier
