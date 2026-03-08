"""
Pydantic schemas for the RAG Chat endpoint.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Schema for POST /chat — user's food query."""
    query: str
    area_name: Optional[str] = ""       # user's location — searches all nearby restaurants
    restaurant_id: Optional[str] = None  # optional: restrict to one restaurant


class ChatItemResponse(BaseModel):
    """A single menu item returned in the chat response."""
    item_name: str
    restaurant_name: Optional[str] = None
    section_name: Optional[str] = None
    price: Optional[int] = None
    is_veg: Optional[bool] = None
    calories: Optional[int] = None
    health_score: Optional[int] = None
    similarity: Optional[float] = None


class ChatResponse(BaseModel):
    """Schema for POST /chat response — LLM answer + matching items."""
    answer: str
    items: List[Dict[str, Any]]
    filters_used: Dict[str, Any]
