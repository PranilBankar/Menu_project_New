"""
Auth API Endpoints

Provides a simple /auth/me endpoint so the frontend can check who is logged in
and whether they already have a restaurant linked to their account.
"""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.restaurant import Restaurant
from app.schemas.auth import UserInfo

router = APIRouter()


@router.get("/me", response_model=UserInfo)
def get_me(
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the current authenticated user's info.

    If they own a restaurant, includes the restaurant_id and name.
    The frontend uses this to decide whether to show "Create Restaurant"
    or "Go to Dashboard".
    """
    # Check if user already owns a restaurant
    restaurant = db.query(Restaurant).filter(
        Restaurant.owner_id == current_user
    ).first()

    return UserInfo(
        user_id=current_user,
        restaurant_id=restaurant.restaurant_id if restaurant else None,
        restaurant_name=restaurant.restaurant_name if restaurant else None,
    )
