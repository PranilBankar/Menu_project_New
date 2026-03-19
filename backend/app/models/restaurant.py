"""
Restaurant Model
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, ARRAY, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Restaurant(Base):
    __tablename__ = "restaurants"
    
    restaurant_id = Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id = Column("area_id", UUID(as_uuid=True), ForeignKey("areas.id", ondelete="CASCADE"), nullable=False)
    restaurant_name = Column("name", String(255), nullable=False, index=True)
    cuisine_type = Column(ARRAY(String(100)))  # Array of cuisines
    price_category = Column(String(20))  # budget, mid-range, premium
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    @property
    def address(self):
        return None

    @property
    def phone(self):
        return None

    @property
    def is_active(self):
        return True
    
    # Relationships
    area = relationship("Area", back_populates="restaurants")
    menu_sections = relationship("MenuSection", back_populates="restaurant", cascade="all, delete-orphan")
    menu_uploads = relationship("MenuUpload", back_populates="restaurant", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Restaurant(name='{self.restaurant_name}', area='{self.area.area_name if self.area else None}')>"
