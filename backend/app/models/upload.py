"""
Menu Upload Model - Track menu image uploads and OCR processing
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, func, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from app.core.database import Base


class MenuUpload(Base):
    __tablename__ = "menu_uploads"
    
    upload_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    restaurant_id = Column(UUID(as_uuid=True), ForeignKey("restaurants.restaurant_id", ondelete="SET NULL"))
    image_path = Column(String(500), nullable=False)
    ocr_status = Column(String(20), default='pending')  # pending, processing, completed, failed
    ocr_result = Column(JSONB)  # Store raw OCR output
    structured_data = Column(JSONB)  # Store LLM-structured menu data
    error_message = Column(Text)
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    
    # Relationships
    restaurant = relationship("Restaurant", back_populates="menu_uploads")
    
    def __repr__(self):
        return f"<MenuUpload(upload_id='{self.upload_id}', status='{self.ocr_status}')>"
