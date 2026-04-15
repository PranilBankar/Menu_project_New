"""
Pydantic schemas for request/response validation.
Each module mirrors its corresponding SQLAlchemy model in app/models/.
"""
from app.schemas.area import AreaCreate, AreaResponse
from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate, RestaurantResponse
from app.schemas.menu import UploadResponse, UploadStatusResponse
from app.schemas.chat import ChatRequest, ChatItemResponse, ChatResponse
from app.schemas.admin import DashboardStats, MenuItemSummary, MenuItemUpdate
