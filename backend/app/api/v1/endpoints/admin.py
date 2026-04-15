"""
Admin Dashboard API Endpoints

ALL endpoints in this router require authentication.
The logged-in user must be the owner of the restaurant they're managing.

Provides restaurant owners with endpoints to:
- View dashboard statistics for their restaurant
- Manage menu items (list, update, delete)
- Upload menu images with replace/append mode
- Clear all menu data for a fresh re-upload
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from typing import List, Optional
import uuid
import logging
from pathlib import Path
import shutil
from datetime import datetime

from app.core.database import get_db
from app.core.config import settings
from app.core.auth import get_current_user
from app.models.restaurant import Restaurant
from app.models.area import Area
from app.models.menu import MenuSection, MenuItem
from app.models.upload import MenuUpload
from app.models.embedding import MenuEmbedding
from app.schemas.admin import DashboardStats, MenuItemSummary, MenuItemUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/dashboard/{restaurant_id}", response_model=DashboardStats)
def get_dashboard(
    restaurant_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get dashboard statistics for a restaurant.

    Returns item counts, section counts, upload history, average price,
    veg/non-veg split, and restaurant metadata.
    """
    restaurant = _verify_ownership(restaurant_id, current_user, db)
    area = restaurant.area

    # Count sections
    total_sections = db.query(sql_func.count(MenuSection.section_id)).filter(
        MenuSection.restaurant_id == restaurant_id
    ).scalar() or 0

    # Count items & averages
    item_stats = db.query(
        sql_func.count(MenuItem.item_id),
        sql_func.avg(MenuItem.price),
        sql_func.count(MenuItem.item_id).filter(MenuItem.is_veg == True),
        sql_func.count(MenuItem.item_id).filter(MenuItem.is_veg == False),
    ).join(MenuSection).filter(
        MenuSection.restaurant_id == restaurant_id
    ).first()

    total_items = item_stats[0] or 0
    avg_price = round(float(item_stats[1]), 2) if item_stats[1] else None
    veg_items = item_stats[2] or 0
    non_veg_items = item_stats[3] or 0

    # Count uploads
    total_uploads = db.query(sql_func.count(MenuUpload.upload_id)).filter(
        MenuUpload.restaurant_id == restaurant_id
    ).scalar() or 0

    return DashboardStats(
        restaurant_id=restaurant.restaurant_id,
        restaurant_name=restaurant.restaurant_name,
        area_name=area.area_name if area else "Unknown",
        city=area.city if area else "Unknown",
        is_active=restaurant.is_active,
        total_sections=total_sections,
        total_items=total_items,
        total_uploads=total_uploads,
        avg_price=avg_price,
        veg_items=veg_items,
        non_veg_items=non_veg_items,
        created_at=restaurant.created_at,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# MENU ITEMS — LIST / UPDATE / DELETE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/restaurants/{restaurant_id}/items",
    response_model=List[MenuItemSummary],
)
def list_menu_items(
    restaurant_id: uuid.UUID,
    section_name: Optional[str] = None,
    is_veg: Optional[bool] = None,
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all menu items for a restaurant (admin view).

    Supports optional filters by section name and veg/non-veg.
    """
    _verify_ownership(restaurant_id, current_user, db)

    query = (
        db.query(MenuItem, MenuSection.section_name)
        .join(MenuSection)
        .filter(MenuSection.restaurant_id == restaurant_id)
    )

    if section_name:
        query = query.filter(MenuSection.section_name.ilike(f"%{section_name}%"))

    if is_veg is not None:
        query = query.filter(MenuItem.is_veg == is_veg)

    rows = query.order_by(MenuSection.display_order, MenuItem.item_name).all()

    return [
        MenuItemSummary(
            item_id=item.item_id,
            item_name=item.item_name,
            section_name=sec_name,
            price=float(item.price),
            is_veg=item.is_veg,
            is_available=item.is_available,
            description=item.description,
            calories=item.calories,
            health_score=item.health_score,
            health_label=item.health_label,
            tags=item.tags,
        )
        for item, sec_name in rows
    ]


@router.put(
    "/restaurants/{restaurant_id}/items/{item_id}",
    response_model=MenuItemSummary,
)
def update_menu_item(
    restaurant_id: uuid.UUID,
    item_id: uuid.UUID,
    updates: MenuItemUpdate,
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update a single menu item (partial update — only provided fields change).

    The admin can change the name, price, availability, veg status, etc.
    """
    _verify_ownership(restaurant_id, current_user, db)

    item = (
        db.query(MenuItem)
        .join(MenuSection)
        .filter(
            MenuItem.item_id == item_id,
            MenuSection.restaurant_id == restaurant_id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    update_data = updates.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)

    return MenuItemSummary(
        item_id=item.item_id,
        item_name=item.item_name,
        section_name=item.section.section_name,
        price=float(item.price),
        is_veg=item.is_veg,
        is_available=item.is_available,
        description=item.description,
        calories=item.calories,
        health_score=item.health_score,
        health_label=item.health_label,
        tags=item.tags,
    )


@router.delete("/restaurants/{restaurant_id}/items/{item_id}")
def delete_menu_item(
    restaurant_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Permanently delete a menu item and its embedding.
    """
    _verify_ownership(restaurant_id, current_user, db)

    item = (
        db.query(MenuItem)
        .join(MenuSection)
        .filter(
            MenuItem.item_id == item_id,
            MenuSection.restaurant_id == restaurant_id,
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    item_name = item.item_name
    db.delete(item)
    db.commit()

    return {"message": f"Item '{item_name}' deleted", "item_id": str(item_id)}


# ═══════════════════════════════════════════════════════════════════════════════
# MENU UPLOAD (with replace / append mode)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/restaurants/{restaurant_id}/menu/upload")
async def admin_upload_menu(
    restaurant_id: uuid.UUID,
    file: UploadFile = File(...),
    mode: str = Form("replace"),
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a menu image for processing (OCR → structuring → DB storage).

    **mode** (form field):
    - `"replace"` (default) — clears existing menu sections/items before saving new ones.
    - `"append"` — adds new items alongside the existing menu.

    This reuses the full OCR + LLM enrichment pipeline from the menus endpoint.
    """
    # Validate restaurant exists AND user owns it
    restaurant = _verify_ownership(restaurant_id, current_user, db)

    if mode not in ("replace", "append"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'replace' or 'append'",
        )

    area = restaurant.area

    # Validate file type
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file_ext} not allowed. Allowed: {settings.ALLOWED_EXTENSIONS}",
        )

    upload_id = uuid.uuid4()
    file_path = Path(settings.UPLOAD_DIR) / f"{upload_id}{file_ext}"
    upload = None

    try:
        # ── Save file ───────────────────────────────────────────────────────
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create upload record linked to this restaurant
        upload = MenuUpload(
            upload_id=upload_id,
            restaurant_id=restaurant_id,
            image_path=str(file_path),
            ocr_status="processing",
        )
        db.add(upload)
        db.commit()

        # ── Step 1: OCR ─────────────────────────────────────────────────────
        from app.services.ocr.ocr_engine import get_ocr_engine

        ocr_engine = get_ocr_engine()

        import cv2
        img = cv2.imread(str(file_path))
        if img is None:
            raise ValueError(f"Could not read image: {file_path}")

        raw_ocr_result = ocr_engine.ocr.ocr(img)
        upload.ocr_result = {"status": "ocr_completed"}
        db.commit()

        # ── Step 2: Layout parsing ──────────────────────────────────────────
        from app.services.ocr.menu_layout_parser import parse_menu

        parsed_items = parse_menu(raw_ocr_result)
        logger.info(f"[Admin Upload] Layout parser extracted {len(parsed_items)} items")

        if not parsed_items:
            upload.ocr_status = "completed"
            upload.error_message = "No menu items detected in the image"
            upload.processed_at = datetime.utcnow()
            db.commit()
            return {
                "upload_id": upload_id,
                "status": "completed",
                "message": "No menu items detected in image",
                "mode": mode,
                "restaurant_name": restaurant.restaurant_name,
                "items_count": 0,
                "embedded_count": 0,
            }

        # ── Step 3: LLM enrichment ──────────────────────────────────────────
        from app.services.nlp.menu_structurer import get_menu_structurer

        structurer = get_menu_structurer()
        enriched_items = structurer.enrich(
            parsed_items=parsed_items,
            restaurant_name=restaurant.restaurant_name,
        )
        logger.info(f"[Admin Upload] LLM enriched {len(enriched_items)} items")

        upload.structured_data = {"enriched_items": enriched_items}
        db.commit()

        # ── Step 4: Replace mode — clear old menu ───────────────────────────
        if mode == "replace":
            _clear_menu_data(restaurant_id, db)
            logger.info(f"[Admin Upload] Cleared old menu for '{restaurant.restaurant_name}'")

        # ── Step 5: Store in database ───────────────────────────────────────
        from app.services.health.health_scorer import get_health_scorer

        health_scorer = get_health_scorer()
        items_count = 0
        section_cache = {}

        for item_data in enriched_items:
            section_name = item_data.get("section_name", "Menu Items")

            if section_name not in section_cache:
                # In append mode, reuse existing sections with the same name
                existing_section = None
                if mode == "append":
                    existing_section = db.query(MenuSection).filter(
                        MenuSection.restaurant_id == restaurant_id,
                        MenuSection.section_name == section_name,
                    ).first()

                if existing_section:
                    section_cache[section_name] = existing_section
                else:
                    section = MenuSection(
                        restaurant_id=restaurant_id,
                        section_name=section_name,
                    )
                    db.add(section)
                    db.commit()
                    db.refresh(section)
                    section_cache[section_name] = section

            section = section_cache[section_name]

            # Health score
            h_score = item_data.get("health_score")
            if h_score is None:
                h_score = health_scorer.calculate_score(
                    item_name=item_data.get("item_name", ""),
                    description=item_data.get("description", ""),
                    is_veg=item_data.get("is_veg", True),
                )
            h_label = health_scorer.get_health_label(h_score) if h_score else None

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
        logger.info(f"[Admin Upload] Stored {items_count} menu items")

        # ── Step 6: Generate embeddings ─────────────────────────────────────
        created_items = (
            db.query(MenuItem)
            .join(MenuSection)
            .filter(MenuSection.restaurant_id == restaurant_id)
            .all()
        )

        embedded_count = 0
        if created_items:
            try:
                texts = []
                for mi in created_items:
                    text = f"{mi.item_name}"
                    if mi.description:
                        text += f" - {mi.description}"
                    if mi.section:
                        text += f" [{mi.section.section_name}]"
                    texts.append(text)

                from app.services.nlp.embedding_service import EmbeddingService

                svc = EmbeddingService()
                embeddings = svc.generate_embeddings(texts)

                for mi, emb in zip(created_items, embeddings):
                    # Skip if embedding already exists (append mode)
                    existing_emb = db.query(MenuEmbedding).filter(
                        MenuEmbedding.item_id == mi.item_id
                    ).first()
                    if existing_emb:
                        continue

                    menu_emb = MenuEmbedding(
                        item_id=mi.item_id,
                        embedding=emb.tolist(),
                        extra_metadata={
                            "item_name": mi.item_name,
                            "section_name": mi.section.section_name if mi.section else None,
                            "restaurant_name": restaurant.restaurant_name,
                            "area_name": area.area_name if area else None,
                            "price": float(mi.price) if mi.price else None,
                            "is_veg": mi.is_veg,
                            "calories": mi.calories,
                            "health_score": mi.health_score,
                        },
                    )
                    db.add(menu_emb)
                    embedded_count += 1

                db.commit()
                logger.info(f"[Admin Upload] Generated {embedded_count} embeddings")
            except Exception as embed_err:
                db.rollback()
                logger.warning(f"Embedding generation failed: {embed_err}")

        # Mark upload as completed
        upload.ocr_status = "completed"
        upload.processed_at = datetime.utcnow()
        db.commit()

        return {
            "upload_id": upload_id,
            "status": "completed",
            "message": f"Menu processed successfully (mode: {mode})",
            "mode": mode,
            "restaurant_name": restaurant.restaurant_name,
            "items_count": items_count,
            "embedded_count": embedded_count,
        }

    except Exception as e:
        db.rollback()

        if upload:
            try:
                upload.ocr_status = "failed"
                upload.error_message = str(e)
                db.commit()
            except Exception:
                db.rollback()

        logger.error(f"[Admin Upload] Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLEAR MENU
# ═══════════════════════════════════════════════════════════════════════════════

@router.delete("/restaurants/{restaurant_id}/menu/clear")
def clear_menu(
    restaurant_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Clear all menu sections, items, and embeddings for a restaurant.

    Use this before re-uploading a completely new menu, or when the admin
    wants to start fresh.
    """
    _verify_ownership(restaurant_id, current_user, db)
    deleted = _clear_menu_data(restaurant_id, db)
    return {
        "message": "Menu data cleared",
        "restaurant_id": str(restaurant_id),
        "sections_deleted": deleted["sections"],
        "items_deleted": deleted["items"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _verify_ownership(
    restaurant_id: uuid.UUID, current_user: uuid.UUID, db: Session
) -> Restaurant:
    """
    Check that the restaurant exists AND the current user is the owner.

    Returns the restaurant object if all checks pass.
    Raises 404 if restaurant doesn't exist, 403 if user is not the owner.
    """
    restaurant = db.query(Restaurant).filter(
        Restaurant.restaurant_id == restaurant_id
    ).first()

    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    if restaurant.owner_id != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this restaurant",
        )

    return restaurant


def _clear_menu_data(restaurant_id: uuid.UUID, db: Session) -> dict:
    """
    Delete all menu sections (cascades to items → embeddings) for a restaurant.
    Returns counts of deleted records.
    """
    # Count before deleting
    sections = db.query(MenuSection).filter(
        MenuSection.restaurant_id == restaurant_id
    ).all()

    items_count = 0
    for section in sections:
        items_count += len(section.menu_items)

    sections_count = len(sections)

    # Delete sections (cascade takes care of items and embeddings)
    db.query(MenuSection).filter(
        MenuSection.restaurant_id == restaurant_id
    ).delete(synchronize_session="fetch")
    db.commit()

    return {"sections": sections_count, "items": items_count}
