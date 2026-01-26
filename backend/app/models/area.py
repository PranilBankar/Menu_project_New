"""
Area Model - Geographic areas where restaurants are located
"""
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class Area(Base):
    __tablename__ = "areas"
    
    area_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_name = Column(String(255), nullable=False, index=True)
    pincode = Column(String(10))
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    restaurants = relationship("Restaurant", back_populates="area", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Area(area_name='{self.area_name}', city='{self.city}')>"
