"""
Menu Models - Sections and Items
"""
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Integer, Numeric, ARRAY, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class MenuSection(Base):
    __tablename__ = "menu_sections"
    
    section_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    restaurant_id = Column(UUID(as_uuid=True), ForeignKey("restaurants.restaurant_id", ondelete="CASCADE"), nullable=False)
    section_name = Column(String(255), nullable=False)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    restaurant = relationship("Restaurant", back_populates="menu_sections")
    menu_items = relationship("MenuItem", back_populates="section", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MenuSection(name='{self.section_name}', restaurant='{self.restaurant.restaurant_name if self.restaurant else None}')>"


class MenuItem(Base):
    __tablename__ = "menu_items"
    
    item_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id = Column(UUID(as_uuid=True), ForeignKey("menu_sections.section_id", ondelete="CASCADE"), nullable=False)
    item_name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    price = Column(Numeric(10, 2), nullable=False, index=True)
    is_veg = Column(Boolean, default=True)
    is_available = Column(Boolean, default=True)
    calories = Column(Integer)
    health_score = Column(Integer)  # 0-100
    health_label = Column(String(20))  # healthy, moderate, unhealthy
    spice_level = Column(String(20))  # mild, medium, hot, extra-hot
    allergens = Column(ARRAY(String(100)))
    tags = Column(ARRAY(String(50)))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    section = relationship("MenuSection", back_populates="menu_items")
    embedding = relationship("MenuEmbedding", back_populates="menu_item", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<MenuItem(name='{self.item_name}', price={self.price})>"
