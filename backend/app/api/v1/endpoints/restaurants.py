"""
Restaurants API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.core.database import get_db
from app.models.restaurant import Restaurant
from app.models.area import Area
from app.schemas.restaurant import RestaurantCreate, RestaurantUpdate, RestaurantResponse

router = APIRouter()


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

    # Attach area info for the response
    return _restaurant_with_area(db_restaurant, area)


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
    return [_restaurant_with_area(r, r.area) for r in restaurants]


@router.get("/{restaurant_id}", response_model=RestaurantResponse)
def get_restaurant(restaurant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific restaurant"""
    restaurant = db.query(Restaurant).filter(
        Restaurant.restaurant_id == restaurant_id
    ).first()
    
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    return _restaurant_with_area(restaurant, restaurant.area)


@router.put("/{restaurant_id}", response_model=RestaurantResponse)
def update_restaurant(
    restaurant_id: uuid.UUID,
    updates: RestaurantUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a restaurant's details (partial update — only provided fields are changed).
    
    The admin can update the restaurant name, switch area, change cuisine, etc.
    """
    restaurant = db.query(Restaurant).filter(
        Restaurant.restaurant_id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    # If area_id is being changed, verify the new area exists
    update_data = updates.dict(exclude_unset=True)
    if "area_id" in update_data:
        area = db.query(Area).filter(Area.area_id == update_data["area_id"]).first()
        if not area:
            raise HTTPException(status_code=404, detail="Area not found")

    # Apply only the fields that were actually sent
    for field, value in update_data.items():
        setattr(restaurant, field, value)

    db.commit()
    db.refresh(restaurant)
    return _restaurant_with_area(restaurant, restaurant.area)


@router.delete("/{restaurant_id}")
def delete_restaurant(restaurant_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Soft-delete a restaurant (sets is_active = false).
    
    The restaurant and its menu data are preserved but hidden from public listings.
    """
    restaurant = db.query(Restaurant).filter(
        Restaurant.restaurant_id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    restaurant.is_active = False
    db.commit()

    return {"message": f"Restaurant '{restaurant.restaurant_name}' deactivated", "restaurant_id": str(restaurant_id)}


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


# ── Helper ──────────────────────────────────────────────────────────────────

def _restaurant_with_area(restaurant: Restaurant, area) -> dict:
    """Build a RestaurantResponse-compatible dict with joined area info."""
    return {
        "restaurant_id": restaurant.restaurant_id,
        "restaurant_name": restaurant.restaurant_name,
        "cuisine_type": restaurant.cuisine_type,
        "price_category": restaurant.price_category,
        "address": restaurant.address,
        "phone": restaurant.phone,
        "area_id": restaurant.area_id,
        "is_active": restaurant.is_active,
        "area_name": area.area_name if area else None,
        "city": area.city if area else None,
        "created_at": restaurant.created_at,
        "updated_at": restaurant.updated_at,
    }
