"""
POST /api/v1/chat  — RAG-powered food discovery chatbot endpoint
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.nlp.rag_service import get_rag_service
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


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

    rest_id = req.restaurant_id if req.restaurant_id and req.restaurant_id != "string" else None

    result = rag.chat(
        query=req.query,
        area_name=req.area_name or "",
        restaurant_id=rest_id,
    )

    return ChatResponse(**result)
