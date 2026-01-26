"""
Menu Structurer - Convert OCR text to structured menu data using LLM
"""
import json
import re
from typing import Dict, List, Optional
from openai import OpenAI

from app.core.config import settings


class MenuStructurer:
    """
    Structure raw OCR text into organized menu data using LLM
    """
    
    def __init__(self):
        """Initialize with OpenAI client if API key available"""
        self.client = None
        if settings.OPENAI_API_KEY:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    def structure_menu(self, ocr_text: str) -> Dict:
        """
        Convert OCR text to structured menu JSON
        
        Args:
            ocr_text: Raw OCR extracted text
            
        Returns:
            Structured menu dictionary
        """
        if self.client:
            return self._structure_with_llm(ocr_text)
        else:
            return self._structure_with_rules(ocr_text)
    
    def _structure_with_llm(self, ocr_text: str) -> Dict:
        """
        Use LLM (GPT-4) to structure menu
        
        Args:
            ocr_text: Raw OCR text
            
        Returns:
            Structured menu data
        """
        prompt = f"""
You are a menu digitization expert. Convert the following OCR-extracted menu text into a structured JSON format.

OCR Text:
{ocr_text}

Return ONLY a valid JSON object with this exact structure:
{{
    "restaurant_name": "Name of the restaurant (if found)",
    "sections": [
        {{
            "section_name": "Section name (e.g., Starters, Main Course)",
            "items": [
                {{
                    "item_name": "Dish name",
                    "description": "Description if available",
                    "price": 180.00,
                    "is_veg": true,
                    "keywords": ["keyword1", "keyword2"]
                }}
            ]
        }}
    ]
}}

Rules:
1. Extract ALL menu items with their prices
2. Group items into logical sections (Starters, Main Course, Desserts, etc.)
3. Mark is_veg as true for vegetarian items, false for non-veg
4. Extract keywords for each item (ingredients, cooking method, etc.)
5. If restaurant name is not found, use "Unknown Restaurant"
6. Prices should be numbers (e.g., 180.00, not "₹180")
7. Return ONLY the JSON, no additional text

JSON:
"""
        
        try:
            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": "You are a menu digitization expert. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=2000
            )
            
            # Extract JSON from response
            content = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks if present
            content = re.sub(r'```json\s*', '', content)
            content = re.sub(r'```\s*$', '', content)
            
            # Parse JSON
            structured_data = json.loads(content)
            
            return structured_data
            
        except Exception as e:
            print(f"LLM structuring failed: {e}. Falling back to rule-based.")
            return self._structure_with_rules(ocr_text)
    
    def _structure_with_rules(self, ocr_text: str) -> Dict:
        """
        Fallback: Use rule-based structuring
        
        Args:
            ocr_text: Raw OCR text
            
        Returns:
            Structured menu data
        """
        lines = ocr_text.split('\n')
        
        structured_data = {
            "restaurant_name": "Unknown Restaurant",
            "sections": []
        }
        
        current_section = None
        current_items = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if line is a section header (all caps, no price)
            if line.isupper() and not self._contains_price(line):
                # Save previous section
                if current_section and current_items:
                    structured_data["sections"].append({
                        "section_name": current_section,
                        "items": current_items
                    })
                
                # Start new section
                current_section = line.title()
                current_items = []
            
            # Check if line contains a price (likely a menu item)
            elif self._contains_price(line):
                item = self._parse_item(line)
                if item:
                    current_items.append(item)
        
        # Add last section
        if current_section and current_items:
            structured_data["sections"].append({
                "section_name": current_section,
                "items": current_items
            })
        
        # If no sections found, create a default one
        if not structured_data["sections"] and current_items:
            structured_data["sections"].append({
                "section_name": "Menu Items",
                "items": current_items
            })
        
        return structured_data
    
    def _contains_price(self, text: str) -> bool:
        """Check if text contains a price"""
        price_patterns = [
            r'₹\s*\d+',
            r'\d+\s*₹',
            r'\d+\s*/-',
        ]
        return any(re.search(pattern, text) for pattern in price_patterns)
    
    def _parse_item(self, line: str) -> Optional[Dict]:
        """
        Parse a single menu item line
        
        Args:
            line: Text line containing item and price
            
        Returns:
            Item dictionary or None
        """
        # Extract price
        price_match = re.search(r'₹\s*(\d+(?:,\d+)*(?:\.\d{2})?)', line)
        if not price_match:
            return None
        
        price_str = price_match.group(1).replace(',', '')
        try:
            price = float(price_str)
        except ValueError:
            return None
        
        # Extract item name (text before price)
        item_name = line[:price_match.start()].strip()
        
        # Check if vegetarian
        is_veg = 'veg' in line.lower() and 'non' not in line.lower()
        
        return {
            "item_name": item_name,
            "description": "",
            "price": price,
            "is_veg": is_veg,
            "keywords": []
        }


# Singleton instance
_menu_structurer = None

def get_menu_structurer() -> MenuStructurer:
    """Get or create menu structurer instance"""
    global _menu_structurer
    if _menu_structurer is None:
        _menu_structurer = MenuStructurer()
    return _menu_structurer
