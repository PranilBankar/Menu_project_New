"""
Restaurant Model
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, ARRAY, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Restaurant(Base):
    __tablename__ = "restaurants"

    restaurant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id = Column(UUID(as_uuid=True), ForeignKey("areas.area_id", ondelete="CASCADE"), nullable=False)
    restaurant_name = Column(String(255), nullable=False, index=True)
    cuisine_type = Column(ARRAY(String(100)))
    price_category = Column(String(20))
    address = Column(Text)
    phone = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    area = relationship("Area", back_populates="restaurants")
    menu_sections = relationship("MenuSection", back_populates="restaurant", cascade="all, delete-orphan")
    menu_uploads = relationship("MenuUpload", back_populates="restaurant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Restaurant(name='{self.restaurant_name}')>"
