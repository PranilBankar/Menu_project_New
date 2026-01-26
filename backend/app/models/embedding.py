"""
Embedding Model - Vector embeddings for semantic search
"""
from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import uuid

from app.core.database import Base


class MenuEmbedding(Base):
    __tablename__ = "menu_embeddings"
    
    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("menu_items.item_id", ondelete="CASCADE"), nullable=False, unique=True)
    embedding = Column(Vector(384))  # MiniLM dimension
    metadata = Column(JSONB)  # Store additional context
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    menu_item = relationship("MenuItem", back_populates="embedding")
    
    def __repr__(self):
        return f"<MenuEmbedding(item_id='{self.item_id}')>"
