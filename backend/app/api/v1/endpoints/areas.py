"""
Areas API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import uuid

from app.core.database import get_db
from app.models.area import Area

router = APIRouter()


# Pydantic schemas
class AreaCreate(BaseModel):
    area_name: str
    city: str
    pincode: str | None = None
    state: str | None = None


class AreaResponse(BaseModel):
    area_id: uuid.UUID
    area_name: str
    city: str
    pincode: str | None
    state: str | None
    
    class Config:
        from_attributes = True


@router.post("/", response_model=AreaResponse)
def create_area(area: AreaCreate, db: Session = Depends(get_db)):
    """Create a new area"""
    db_area = Area(**area.dict())
    db.add(db_area)
    db.commit()
    db.refresh(db_area)
    return db_area


@router.get("/", response_model=List[AreaResponse])
def list_areas(
    city: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all areas with optional city filter"""
    query = db.query(Area)
    
    if city:
        query = query.filter(Area.city.ilike(f"%{city}%"))
    
    areas = query.offset(skip).limit(limit).all()
    return areas


@router.get("/{area_id}", response_model=AreaResponse)
def get_area(area_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific area by ID"""
    area = db.query(Area).filter(Area.area_id == area_id).first()
    
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")
    
    return area


@router.get("/{area_id}/restaurants")
def get_area_restaurants(area_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get all restaurants in an area"""
    area = db.query(Area).filter(Area.area_id == area_id).first()
    
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")
    
    return {
        "area": {
            "area_id": area.area_id,
            "area_name": area.area_name,
            "city": area.city
        },
        "restaurants": [
            {
                "restaurant_id": r.restaurant_id,
                "restaurant_name": r.restaurant_name,
                "cuisine_type": r.cuisine_type,
                "price_category": r.price_category
            }
            for r in area.restaurants
        ]
    }
