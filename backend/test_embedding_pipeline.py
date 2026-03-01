"""
End-to-end pipeline: OCR → Parse → LLM Enrich → Embed → Store in Supabase → Search
Usage (from project root): python backend/test_embedding_pipeline.py
"""
import sys, io
# Force UTF-8 output on Windows (fixes rupee ₹ symbol encoding)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

"""
Prerequisites:
  - Supabase menu_items table with embedding vector(384) column
  - DATABASE_URL set in backend/.env (@ in password encoded as %40)
  - pgvector extension enabled in Supabase
  - A restaurant row already exists (set RESTAURANT_ID below)
  - Optional: OPENAI_API_KEY in .env for LLM enrichment (falls back to keyword rules)
"""

import os
import sys

os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_use_mkldnn"]  = "0"

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# ── CONFIG ────────────────────────────────────────────────────────────────────
IMAGE_PATH      = r"D:\Users\Pranil\Github Repos\Menu_project_New\dataset\Menu1.jpeg"
RESTAURANT_ID   = "11986859-05ac-4e5e-846b-8ccbc7da0323"
RESTAURANT_NAME = "Mac D"
AREA_NAME       = "Nagpur"
# ─────────────────────────────────────────────────────────────────────────────

from paddleocr import PaddleOCR
from app.services.ocr.menu_layout_parser import parse_menu
from app.services.nlp.menu_structurer import get_menu_structurer
from app.services.nlp.embedding_service import EmbeddingService


def run_pipeline():

    # ── PHASE 1: OCR ─────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  PHASE 1 — OCR")
    print("=" * 65)

    if not os.path.exists(IMAGE_PATH):
        print(f"[ERROR] Image not found: {IMAGE_PATH}")
        return

    print(f"[INFO] Running OCR on: {IMAGE_PATH} ...")
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
    result = ocr.ocr(IMAGE_PATH, cls=True)
    raw_count = len(result[0]) if result and result[0] else 0
    print(f"[INFO] Raw tokens detected: {raw_count}")

    # ── PHASE 2: Layout Parse ────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  PHASE 2 — LAYOUT PARSE (item + price pairs)")
    print("=" * 65)

    parsed = parse_menu(result)
    print(f"[INFO] Pairs extracted: {len(parsed)}")
    print("\n  Sample (first 8):")
    for p in parsed[:8]:
        print(f"    {p['item']:<45}  ₹{p['price']:.0f}")

    # ── PHASE 3: LLM Enrichment ──────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  PHASE 3 — ENRICHMENT (category / is_veg / calories)")
    print("=" * 65)

    structurer = get_menu_structurer()
    # Build raw OCR text as extra context for LLM
    raw_text = "\n".join(line[1][0] for line in result[0]) if result and result[0] else ""
    enriched = structurer.enrich(parsed, RESTAURANT_NAME, raw_text)

    print(f"[INFO] Enriched items: {len(enriched)}")
    current_cat = None
    for e in enriched[:20]:
        cat = e.get("section_name", "Unknown")
        if cat != current_cat:
            current_cat = cat
            print(f"\n  ── {current_cat} ──")
        veg = "🟢" if e.get("is_veg", True) else "🔴"
        cal = f"~{e['calories']} kcal" if e.get("calories") else ""
        hs  = f"| ♥ {e['health_score']}/10" if e.get("health_score") else ""
        print(f"  {veg} {e.get('item_name','?'):<44} ₹{e.get('price',0):<6}  {cal} {hs}")


    if len(enriched) > 20:
        print(f"\n  ... and {len(enriched) - 20} more items")

    # ── PHASE 4: Embed & Store ───────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  PHASE 4 — EMBED & STORE IN SUPABASE")
    print("=" * 65)

    # Convert enriched items to the format embedding_service expects
    for_embedding = [
        {
            "item":        e["item_name"],
            "category":   e["section_name"],
            "price":      e["price"],
            "is_veg":     e.get("is_veg"),
            "calories":   e.get("calories"),
            "health_score": e.get("health_score"),
            "description": e.get("description", ""),
        }
        for e in enriched
    ]

    with EmbeddingService() as svc:
        stored = svc.embed_and_store(
            parsed_items=for_embedding,
            restaurant_id=RESTAURANT_ID,
            restaurant_name=RESTAURANT_NAME,
            area_name=AREA_NAME,
        )
        print(f"[INFO] Items stored in Supabase: {stored}")

        # ── PHASE 5: Similarity Search Test ──────────────────────────────────
        print("\n" + "=" * 65)
        print("  PHASE 5 — SIMILARITY SEARCH TEST")
        print("=" * 65)

        queries = [
            "vegetarian biryani",
            "cold drinks and beverages",
            "spicy non-veg curry",
            "sweet dessert",
        ]
        for q in queries:
            print(f"\n  Query: '{q}'")
            hits = svc.search(q, top_k=3, restaurant_ids=[RESTAURANT_ID])
            for h in hits:
                print(f"    [{h['section_name']}] {h['item_name']:<35} ₹{h['price']}  sim={h['similarity']:.3f}")


if __name__ == "__main__":
    run_pipeline()
