"""
Pydantic schemas for Menu Upload entities.
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Schema for POST /menus/upload response."""
    upload_id: uuid.UUID
    status: str
    message: str
    restaurant_name: Optional[str] = None
    items_count: Optional[int] = None
    embedded_count: Optional[int] = None

    class Config:
        from_attributes = True


class UploadStatusResponse(BaseModel):
    """Schema for GET /menus/uploads/{id} response — full upload status."""
    upload_id: uuid.UUID
    status: str
    restaurant_id: Optional[uuid.UUID]
    image_path: str
    ocr_result: Optional[dict]
    structured_data: Optional[dict]
    error_message: Optional[str]
    uploaded_at: datetime
    processed_at: Optional[datetime]

    class Config:
        from_attributes = True
