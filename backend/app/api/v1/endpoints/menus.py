"""
Menu Upload API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import uuid
from pathlib import Path
import shutil
from datetime import datetime

from app.core.database import get_db
from app.core.config import settings
from app.models.upload import MenuUpload
from app.models.area import Area
from app.models.restaurant import Restaurant
from app.models.menu import MenuSection, MenuItem
from app.services.ocr.ocr_engine import get_ocr_engine
from app.services.nlp.menu_structurer import get_menu_structurer
from app.services.health.health_scorer import get_health_scorer
from app.schemas.menu import UploadResponse, UploadStatusResponse

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_menu(
    file: UploadFile = File(...),
    area_name: str = Form(...),
    city: str = Form(...),
    restaurant_name: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Upload and process a menu image
    
    Steps:
    1. Save uploaded file
    2. Run OCR
    3. Structure menu with LLM
    4. Calculate health scores
    5. Store in database
    """
    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not allowed. Allowed: {settings.ALLOWED_EXTENSIONS}"
        )
    
    # Create upload record
    upload_id = uuid.uuid4()
    file_path = Path(settings.UPLOAD_DIR) / f"{upload_id}{file_ext}"
    
    try:
        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Create upload record
        upload = MenuUpload(
            upload_id=upload_id,
            image_path=str(file_path),
            ocr_status='processing'
        )
        db.add(upload)
        db.commit()
        
        # Step 1: OCR Extraction
        ocr_engine = get_ocr_engine()
        ocr_results = ocr_engine.extract_text(str(file_path))
        cleaned_results = ocr_engine.clean_text(ocr_results)
        ocr_text = ocr_engine.get_text_blocks(cleaned_results)
        
        # Update upload with OCR results
        upload.ocr_result = {
            "raw_results": ocr_results,
            "cleaned_text": ocr_text
        }
        db.commit()
        
        # Step 2: Structure menu with LLM
        structurer = get_menu_structurer()
        structured_data = structurer.structure_menu(ocr_text)
        
        # Update upload with structured data
        upload.structured_data = structured_data
        db.commit()
        
        # Step 3: Store in database
        # Get or create area
        area = db.query(Area).filter(
            Area.area_name == area_name,
            Area.city == city
        ).first()
        
        if not area:
            area = Area(area_name=area_name, city=city)
            db.add(area)
            db.commit()
            db.refresh(area)
        
        # Get or create restaurant
        rest_name = restaurant_name or structured_data.get("restaurant_name", "Unknown Restaurant")
        restaurant = db.query(Restaurant).filter(
            Restaurant.restaurant_name == rest_name,
            Restaurant.area_id == area.area_id
        ).first()
        
        if not restaurant:
            restaurant = Restaurant(
                area_id=area.area_id,
                restaurant_name=rest_name
            )
            db.add(restaurant)
            db.commit()
            db.refresh(restaurant)
        
        # Update upload with restaurant
        upload.restaurant_id = restaurant.restaurant_id
        db.commit()
        
        # Step 4: Create menu sections and items
        health_scorer = get_health_scorer()
        items_count = 0
        
        for section_data in structured_data.get("sections", []):
            # Create section
            section = MenuSection(
                restaurant_id=restaurant.restaurant_id,
                section_name=section_data["section_name"]
            )
            db.add(section)
            db.commit()
            db.refresh(section)
            
            # Create items
            for item_data in section_data.get("items", []):
                # Calculate health score
                health_score = health_scorer.calculate_score(
                    item_name=item_data["item_name"],
                    description=item_data.get("description", ""),
                    is_veg=item_data.get("is_veg", True)
                )
                health_label = health_scorer.get_health_label(health_score)
                health_tags = health_scorer.get_health_tags(
                    item_data["item_name"],
                    item_data.get("description", "")
                )
                
                # Create menu item
                menu_item = MenuItem(
                    section_id=section.section_id,
                    item_name=item_data["item_name"],
                    description=item_data.get("description"),
                    price=item_data["price"],
                    is_veg=item_data.get("is_veg", True),
                    health_score=health_score,
                    health_label=health_label,
                    tags=item_data.get("keywords", []) + health_tags
                )
                db.add(menu_item)
                items_count += 1
            
            db.commit()
        
        # Mark upload as completed
        upload.ocr_status = 'completed'
        upload.processed_at = datetime.utcnow()
        db.commit()
        
        return {
            "upload_id": upload_id,
            "status": "completed",
            "message": "Menu processed successfully",
            "restaurant_name": rest_name,
            "items_count": items_count
        }
        
    except Exception as e:
        # Mark upload as failed
        if upload:
            upload.ocr_status = 'failed'
            upload.error_message = str(e)
            db.commit()
        
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.get("/uploads/{upload_id}", response_model=UploadStatusResponse)
def get_upload_status(upload_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get status of a menu upload"""
    upload = db.query(MenuUpload).filter(MenuUpload.upload_id == upload_id).first()
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    return upload


@router.get("/uploads", response_model=List[UploadStatusResponse])
def list_uploads(
    status: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all menu uploads"""
    query = db.query(MenuUpload)
    
    if status:
        query = query.filter(MenuUpload.ocr_status == status)
    
    uploads = query.order_by(MenuUpload.uploaded_at.desc()).offset(skip).limit(limit).all()
    return uploads
