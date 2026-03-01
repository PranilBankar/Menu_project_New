"""
API Router - Combine all endpoint routers
"""
from fastapi import APIRouter

from app.api.v1.endpoints import areas, restaurants, menus, chat

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(areas.router,       prefix="/areas",       tags=["Areas"])
api_router.include_router(restaurants.router, prefix="/restaurants", tags=["Restaurants"])
api_router.include_router(menus.router,       prefix="/menus",       tags=["Menus"])
api_router.include_router(chat.router,        prefix="/chat",        tags=["Chat"])
