"""
Menu Upload API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import uuid
import logging
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
from app.services.ocr.menu_layout_parser import parse_menu
from app.services.nlp.menu_structurer import get_menu_structurer
from app.services.health.health_scorer import get_health_scorer
from app.services.nlp.embedding_service import EmbeddingService
from app.schemas.menu import UploadResponse, UploadStatusResponse

logger = logging.getLogger(__name__)

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
    Upload and process a menu image.

    Pipeline:
    1. Save uploaded file
    2. OCR → extract bounding boxes + text
    3. Layout Parser → extract (item, price) pairs
    4. LLM Enrichment → assign sections, calories, health scores
    5. Store in database (areas → restaurants → sections → items)
    6. Generate embeddings for AI search
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
    upload = None

    try:
        # Save file
        file_path.parent.mkdir(parents=True, exist_ok=True)
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

        # ── Step 1: OCR Extraction ──────────────────────────────────────────
        ocr_engine = get_ocr_engine()

        # Use original image (PaddleOCR handles its own preprocessing)
        import cv2
        img = cv2.imread(str(file_path))
        if img is None:
            raise ValueError(f"Could not read image: {file_path}")

        # Get RAW PaddleOCR output (parse_menu needs this format)
        raw_ocr_result = ocr_engine.ocr.ocr(img)

        # Store a summary in upload record (not the full raw output which can be huge)
        upload.ocr_result = {"status": "ocr_completed"}
        db.commit()

        # ── Step 2: Layout Parser → flat (item, price) list ─────────────────
        parsed_items = parse_menu(raw_ocr_result)
        logger.info(f"Layout parser extracted {len(parsed_items)} items")

        if not parsed_items:
            upload.ocr_status = 'completed'
            upload.error_message = 'No menu items detected in the image'
            upload.processed_at = datetime.utcnow()
            db.commit()
            return {
                "upload_id": upload_id,
                "status": "completed",
                "message": "No menu items detected in image",
                "restaurant_name": restaurant_name,
                "items_count": 0,
                "embedded_count": 0
            }

        # ── Step 3: LLM Enrichment → sections, calories, health scores ─────
        rest_name = restaurant_name or "Restaurant"
        structurer = get_menu_structurer()
        enriched_items = structurer.enrich(
            parsed_items=parsed_items,
            restaurant_name=rest_name
        )
        logger.info(f"LLM enriched {len(enriched_items)} items")

        # Save structured data to upload record
        upload.structured_data = {"enriched_items": enriched_items}
        db.commit()

        # ── Step 4: Store in database ───────────────────────────────────────
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

        # Link upload to restaurant
        upload.restaurant_id = restaurant.restaurant_id
        db.commit()

        # Create menu sections and items
        health_scorer = get_health_scorer()
        items_count = 0
        section_cache = {}  # section_name → MenuSection ORM object

        for item_data in enriched_items:
            section_name = item_data.get("section_name", "Menu Items")

            # Get or create section
            if section_name not in section_cache:
                section = MenuSection(
                    restaurant_id=restaurant.restaurant_id,
                    section_name=section_name
                )
                db.add(section)
                db.commit()
                db.refresh(section)
                section_cache[section_name] = section

            section = section_cache[section_name]

            # Calculate health score if not already provided by LLM
            h_score = item_data.get("health_score")
            if h_score is None:
                h_score = health_scorer.calculate_score(
                    item_name=item_data.get("item_name", ""),
                    description=item_data.get("description", ""),
                    is_veg=item_data.get("is_veg", True)
                )
            h_label = health_scorer.get_health_label(h_score) if h_score else None

            # Safely cast price
            try:
                price_val = float(item_data.get("price", 0))
            except (TypeError, ValueError):
                price_val = 0

            menu_item = MenuItem(
                section_id=section.section_id,
                item_name=item_data.get("item_name", item_data.get("item", "Unknown")),
                description=item_data.get("description"),
                price=price_val,
                is_veg=item_data.get("is_veg", True),
                calories=item_data.get("calories"),
                health_score=h_score,
                health_label=h_label,
            )
            db.add(menu_item)
            items_count += 1

        db.commit()
        logger.info(f"Stored {items_count} menu items for {rest_name}")

        # ── Step 5: Generate embeddings for already-created items ─────────
        # Collect the items we just created (they're in the session)
        created_items = db.query(MenuItem).join(MenuSection).filter(
            MenuSection.restaurant_id == restaurant.restaurant_id
        ).all()

        embedded_count = 0
        if created_items:
            try:
                # Build text strings for embedding
                texts = []
                for mi in created_items:
                    text = f"{mi.item_name}"
                    if mi.description:
                        text += f" - {mi.description}"
                    if mi.section:
                        text += f" [{mi.section.section_name}]"
                    texts.append(text)

                # Generate embedding vectors
                from app.services.nlp.embedding_service import EmbeddingService
                svc = EmbeddingService()
                embeddings = svc.generate_embeddings(texts)

                # Create MenuEmbedding records linked to existing items
                from app.models.embedding import MenuEmbedding
                for mi, emb in zip(created_items, embeddings):
                    menu_emb = MenuEmbedding(
                        item_id=mi.item_id,
                        embedding=emb.tolist(),
                        extra_metadata={
                            "item_name": mi.item_name,
                            "section_name": mi.section.section_name if mi.section else None,
                            "restaurant_name": rest_name,
                            "area_name": area_name,
                            "price": float(mi.price) if mi.price else None,
                            "is_veg": mi.is_veg,
                            "calories": mi.calories,
                            "health_score": mi.health_score,
                        }
                    )
                    db.add(menu_emb)
                    embedded_count += 1

                db.commit()
                logger.info(f"Generated {embedded_count} embeddings for {rest_name}")
            except Exception as embed_err:
                db.rollback()
                logger.warning(f"Embedding generation failed: {embed_err}")

        # Mark upload as completed
        upload.ocr_status = 'completed'
        upload.processed_at = datetime.utcnow()
        db.commit()

        return {
            "upload_id": upload_id,
            "status": "completed",
            "message": "Menu processed successfully",
            "restaurant_name": rest_name,
            "items_count": items_count,
            "embedded_count": embedded_count
        }

    except Exception as e:
        # Rollback any broken transaction first
        db.rollback()

        # Mark upload as failed
        if upload:
            try:
                upload.ocr_status = 'failed'
                upload.error_message = str(e)
                db.commit()
            except Exception:
                db.rollback()

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
