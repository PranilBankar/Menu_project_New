"""
End-to-end test: OCR → Layout Parse → Embed → Store in Supabase → Search
Usage (from project root): python backend/test_embedding_pipeline.py

Prerequisites:
  - Supabase menu_items table exists with embedding vector(384) column
  - DATABASE_URL set in backend/.env
  - pgvector extension enabled in Supabase
  - A restaurant row already exists in Supabase (set RESTAURANT_ID below)
"""

import os
import sys

# Suppress verbose paddle/paddleocr logs
os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_use_mkldnn"]  = "0"

# Backend path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# ── CONFIG — update these before running ─────────────────────────────────────
IMAGE_PATH      = r"D:\Users\Pranil\Github Repos\Menu_project_New\dataset\Menu1.jpeg"
RESTAURANT_ID   = "11986859-05ac-4e5e-846b-8ccbc7da0323"   # ← paste a real UUID from Supabase
RESTAURANT_NAME = "Mac D"
AREA_NAME       = "Nagpur"
# ─────────────────────────────────────────────────────────────────────────────

from paddleocr import PaddleOCR
from app.services.ocr.menu_layout_parser import parse_menu
from app.services.nlp.embedding_service import EmbeddingService


def run_pipeline():
    print("\n" + "=" * 65)
    print("  PHASE 1 — OCR")
    print("=" * 65)

    if not os.path.exists(IMAGE_PATH):
        print(f"[ERROR] Image not found: {IMAGE_PATH}")
        return

    print(f"[INFO] Running OCR on: {IMAGE_PATH} ...")
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
    result = ocr.ocr(IMAGE_PATH, cls=True)
    print(f"[INFO] Raw tokens detected: {len(result[0]) if result and result[0] else 0}")

    print("\n" + "=" * 65)
    print("  PHASE 2 — LAYOUT PARSE")
    print("=" * 65)

    menu_items = parse_menu(result)
    print(f"[INFO] Structured items extracted: {len(menu_items)}")
    print("\n  Sample (first 5):")
    for item in menu_items[:5]:
        print(f"    [{item['category']}]  {item['item']:<40}  ₹{item['price']:.0f}")

    print("\n" + "=" * 65)
    print("  PHASE 3 — EMBED & STORE IN SUPABASE")
    print("=" * 65)

    if RESTAURANT_ID == "YOUR-RESTAURANT-UUID-HERE":
        print("[SKIP] Set RESTAURANT_ID at the top of this script to enable Supabase storage.")
        print("       Running embedding generation only (no DB write) ...")
        svc = EmbeddingService()
        from app.services.nlp.embedding_service import _build_embedding_text
        texts = [_build_embedding_text(i, RESTAURANT_NAME, AREA_NAME) for i in menu_items[:3]]
        vectors = svc.generate_embeddings(texts)
        print(f"\n[INFO] Sample embedding shapes: {vectors.shape}")
        print(f"[INFO] Sample text → vector snippet:")
        for t, v in zip(texts, vectors):
            print(f"  '{t[:60]}'")
            print(f"   → [{v[0]:.4f}, {v[1]:.4f}, {v[2]:.4f}, ...] dim={len(v)}")
        return

    with EmbeddingService() as svc:
        stored = svc.embed_and_store(
            parsed_items=menu_items,
            restaurant_id=RESTAURANT_ID,
            restaurant_name=RESTAURANT_NAME,
            area_name=AREA_NAME,
        )
        print(f"[INFO] Items stored in Supabase: {stored}")

        print("\n" + "=" * 65)
        print("  PHASE 4 — SIMILARITY SEARCH TEST")
        print("=" * 65)
        queries = [
            "vegetarian biryani",
            "cold drinks",
            "spicy non-veg curry",
        ]
        for q in queries:
            print(f"\n  Query: '{q}'")
            hits = svc.search(q, top_k=3, restaurant_ids=[RESTAURANT_ID])
            for h in hits:
                print(f"    [{h['section_name']}] {h['item_name']:<35} ₹{h['price']}  sim={h['similarity']:.3f}")


if __name__ == "__main__":
    run_pipeline()
