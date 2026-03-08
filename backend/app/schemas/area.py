"""
Pydantic schemas for Area entities.
"""
import uuid
from typing import Optional
from pydantic import BaseModel


class AreaBase(BaseModel):
    """Shared fields for all area schemas."""
    area_name: str
    city: str
    pincode: Optional[str] = None
    state: Optional[str] = None


class AreaCreate(AreaBase):
    """Schema for POST /areas — creating a new area."""
    pass


class AreaResponse(AreaBase):
    """Schema for GET /areas — reading area data."""
    area_id: uuid.UUID

    class Config:
        from_attributes = True
