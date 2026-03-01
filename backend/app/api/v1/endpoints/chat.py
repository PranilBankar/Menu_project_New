"""
POST /api/v1/chat  — RAG-powered food discovery chatbot endpoint
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.nlp.rag_service import get_rag_service

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query:         str
    area_name:     Optional[str] = ""     # user's location — searches all nearby restaurants
    restaurant_id: Optional[str] = None   # optional: restrict to one restaurant


class MenuItem(BaseModel):
    item_name:    str
    section_name: Optional[str]
    price:        Optional[int]
    is_veg:       Optional[bool]
    calories:     Optional[int]
    health_score: Optional[int]
    similarity:   Optional[float]


class ChatResponse(BaseModel):
    answer:       str
    items:        List[Dict[str, Any]]
    filters_used: Dict[str, Any]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatResponse, summary="Ask the food discovery chatbot")
async def chat(req: ChatRequest):
    """
    Natural language food query → relevant menu items + conversational answer.

    Example request:
    ```json
    { "query": "healthy veg food under ₹200", "area_name": "Nagpur" }
    ```
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    rag = get_rag_service()

    result = rag.chat(
        query=req.query,
        area_name=req.area_name or "",
        restaurant_id=req.restaurant_id,
    )

    return ChatResponse(**result)
