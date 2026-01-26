"""
Restaurants API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import uuid

from app.core.database import get_db
from app.models.restaurant import Restaurant
from app.models.area import Area

router = APIRouter()


# Pydantic schemas
class RestaurantCreate(BaseModel):
    area_id: uuid.UUID
    restaurant_name: str
    cuisine_type: List[str] | None = None
    price_category: str | None = None
    address: str | None = None
    phone: str | None = None


class RestaurantResponse(BaseModel):
    restaurant_id: uuid.UUID
    area_id: uuid.UUID
    restaurant_name: str
    cuisine_type: List[str] | None
    price_category: str | None
    address: str | None
    phone: str | None
    is_active: bool
    
    class Config:
        from_attributes = True


@router.post("/", response_model=RestaurantResponse)
def create_restaurant(restaurant: RestaurantCreate, db: Session = Depends(get_db)):
    """Create a new restaurant"""
    # Verify area exists
    area = db.query(Area).filter(Area.area_id == restaurant.area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")
    
    db_restaurant = Restaurant(**restaurant.dict())
    db.add(db_restaurant)
    db.commit()
    db.refresh(db_restaurant)
    return db_restaurant


@router.get("/", response_model=List[RestaurantResponse])
def list_restaurants(
    area_id: uuid.UUID | None = None,
    city: str | None = None,
    cuisine: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List restaurants with filters"""
    query = db.query(Restaurant).filter(Restaurant.is_active == True)
    
    if area_id:
        query = query.filter(Restaurant.area_id == area_id)
    
    if city:
        query = query.join(Area).filter(Area.city.ilike(f"%{city}%"))
    
    if cuisine:
        query = query.filter(Restaurant.cuisine_type.contains([cuisine]))
    
    restaurants = query.offset(skip).limit(limit).all()
    return restaurants


@router.get("/{restaurant_id}", response_model=RestaurantResponse)
def get_restaurant(restaurant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific restaurant"""
    restaurant = db.query(Restaurant).filter(
        Restaurant.restaurant_id == restaurant_id
    ).first()
    
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    return restaurant


@router.get("/{restaurant_id}/menu")
def get_restaurant_menu(restaurant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get full menu for a restaurant"""
    restaurant = db.query(Restaurant).filter(
        Restaurant.restaurant_id == restaurant_id
    ).first()
    
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    menu_data = {
        "restaurant": {
            "restaurant_id": restaurant.restaurant_id,
            "restaurant_name": restaurant.restaurant_name,
            "cuisine_type": restaurant.cuisine_type,
            "price_category": restaurant.price_category
        },
        "sections": []
    }
    
    for section in restaurant.menu_sections:
        section_data = {
            "section_id": section.section_id,
            "section_name": section.section_name,
            "items": [
                {
                    "item_id": item.item_id,
                    "item_name": item.item_name,
                    "description": item.description,
                    "price": float(item.price),
                    "is_veg": item.is_veg,
                    "health_score": item.health_score,
                    "health_label": item.health_label,
                    "tags": item.tags
                }
                for item in section.menu_items
                if item.is_available
            ]
        }
        menu_data["sections"].append(section_data)
    
    return menu_data
