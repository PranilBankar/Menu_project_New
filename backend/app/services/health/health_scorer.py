"""
Health Scoring System - Calculate health scores for menu items
"""
from typing import Dict, List


class HealthScorer:
    """
    Calculate health scores for menu items based on ingredients and preparation methods
    """
    
    # Health scoring rules
    HEALTH_RULES = {
        # Positive indicators (add points)
        'grilled': 10,
        'steamed': 10,
        'baked': 8,
        'roasted': 8,
        'boiled': 8,
        'salad': 15,
        'vegetarian': 5,
        'vegan': 10,
        'low-fat': 10,
        'fat-free': 12,
        'sugar-free': 10,
        'whole-grain': 10,
        'whole wheat': 10,
        'multigrain': 8,
        'quinoa': 12,
        'oats': 10,
        'fresh': 5,
        'organic': 8,
        'lean': 8,
        'light': 5,
        'healthy': 10,
        
        # Negative indicators (subtract points)
        'fried': -15,
        'deep-fried': -20,
        'deep fried': -20,
        'butter': -8,
        'cream': -10,
        'creamy': -10,
        'cheese': -5,
        'cheesy': -8,
        'sugar': -8,
        'sugary': -10,
        'processed': -10,
        'mayo': -8,
        'mayonnaise': -8,
        'oil': -5,
        'oily': -8,
        'rich': -5,
        'heavy': -8,
        'crispy': -5,
        'crunchy': -3,
    }
    
    def calculate_score(
        self,
        item_name: str,
        description: str = "",
        is_veg: bool = True,
        cuisine: str = None,
        calories: int = None
    ) -> int:
        """
        Calculate health score (0-100)
        
        Args:
            item_name: Name of the menu item
            description: Item description
            is_veg: Whether item is vegetarian
            cuisine: Cuisine type
            calories: Calorie count (if available)
            
        Returns:
            Health score between 0 and 100
        """
        # Start with base score
        score = 50
        
        # Combine text for analysis
        text = f"{item_name} {description}".lower()
        
        # Apply health rules
        for keyword, points in self.HEALTH_RULES.items():
            if keyword in text:
                score += points
        
        # Vegetarian bonus
        if is_veg:
            score += 5
        
        # Calorie-based adjustment
        if calories:
            if calories < 300:
                score += 10
            elif calories < 500:
                score += 5
            elif calories > 800:
                score -= 10
            elif calories > 1000:
                score -= 15
        
        # Clamp between 0-100
        return max(0, min(100, score))
    
    def get_health_label(self, score: int) -> str:
        """
        Convert score to health label
        
        Args:
            score: Health score (0-100)
            
        Returns:
            Health label: 'healthy', 'moderate', or 'unhealthy'
        """
        if score >= 70:
            return 'healthy'
        elif score >= 40:
            return 'moderate'
        else:
            return 'unhealthy'
    
    def get_health_tags(self, item_name: str, description: str) -> List[str]:
        """
        Extract health-related tags from item
        
        Args:
            item_name: Item name
            description: Item description
            
        Returns:
            List of health tags
        """
        tags = []
        text = f"{item_name} {description}".lower()
        
        # Check for specific tags
        tag_keywords = {
            'low-calorie': ['low-calorie', 'light', 'lite'],
            'high-protein': ['protein', 'high-protein'],
            'gluten-free': ['gluten-free', 'gluten free'],
            'dairy-free': ['dairy-free', 'dairy free', 'vegan'],
            'sugar-free': ['sugar-free', 'sugar free', 'no sugar'],
            'organic': ['organic'],
            'whole-grain': ['whole-grain', 'whole grain', 'multigrain'],
        }
        
        for tag, keywords in tag_keywords.items():
            if any(keyword in text for keyword in keywords):
                tags.append(tag)
        
        return tags


# Singleton instance
_health_scorer = None

def get_health_scorer() -> HealthScorer:
    """Get or create health scorer instance"""
    global _health_scorer
    if _health_scorer is None:
        _health_scorer = HealthScorer()
    return _health_scorer
