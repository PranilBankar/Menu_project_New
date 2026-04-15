"""
Pydantic schemas for authentication endpoints.
"""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserInfo(BaseModel):
    """Response for GET /auth/me — current user's profile."""
    user_id: uuid.UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    restaurant_id: Optional[uuid.UUID] = None
    restaurant_name: Optional[str] = None
