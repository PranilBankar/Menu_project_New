"""
Pydantic schemas for Restaurant entities.
"""
import uuid
from typing import List, Optional
from pydantic import BaseModel


class RestaurantBase(BaseModel):
    """Shared fields for all restaurant schemas."""
    restaurant_name: str
    cuisine_type: Optional[List[str]] = None
    price_category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


class RestaurantCreate(RestaurantBase):
    """Schema for POST /restaurants — creating a new restaurant."""
    area_id: uuid.UUID


class RestaurantResponse(RestaurantBase):
    """Schema for GET /restaurants — reading restaurant data."""
    restaurant_id: uuid.UUID
    area_id: uuid.UUID
    is_active: bool

    class Config:
        from_attributes = True
