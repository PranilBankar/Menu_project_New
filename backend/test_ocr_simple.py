"""
OCR + Menu Layout Parser — test script
paddleocr 2.7.x compatible
Usage (from project root):  python backend/test_ocr_simple.py
"""
import os
import sys

# Must be set BEFORE importing paddle / paddleocr
os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_use_mkldnn"]  = "0"

import cv2
import numpy as np
from paddleocr import PaddleOCR

# Add backend/ to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from app.services.ocr.menu_layout_parser import parse_menu

# ── Config ────────────────────────────────────────────────────────────────────
REAL_IMAGE  = r"D:\Users\Pranil\Github Repos\Menu_project_New\dataset\Menu1.jpeg"
DUMMY_IMAGE = r"D:\Users\Pranil\Github Repos\Menu_project_New\dataset\dummy_menu.jpg"

# ── Dummy generator (fallback if real image missing) ─────────────────────────
def create_dummy_image(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = np.ones((600, 900, 3), dtype=np.uint8) * 255
    # Two-column layout
    rows = [
        # Col 1 — item text              Col 2 — price text
        ("Starters",       (30, 50),  1.1, None,             None,       None),
        ("Tomato Soup",    (30, 110), 0.8, "150",            (500, 110), 0.8),
        ("French Fries",   (30, 155), 0.8, "250",            (500, 155), 0.8),
        ("Main Course",    (30, 220), 1.1, None,             None,       None),
        ("Grilled Chicken",(30, 280), 0.8, "350",            (500, 280), 0.8),
        ("Veg Pasta",      (30, 325), 0.8, "300",            (500, 325), 0.8),
        # Second block (simulates 4-col layout)
        ("Beverages",      (480, 50), 1.1, None,             None,       None),
        ("Mango Lassi",    (480, 110),0.8, "120",            (800, 110), 0.8),
        ("Cold Coffee",    (480, 155),0.8, "100",            (800, 155), 0.8),
    ]
    for text, pos, scale, price_text, price_pos, _ in rows:
        cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (20, 20, 20), 2, cv2.LINE_AA)
        if price_text:
            cv2.putText(img, price_text, price_pos, cv2.FONT_HERSHEY_SIMPLEX,
                        scale, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.imwrite(path, img)
    print(f"[INFO] Dummy image created: {path}")
    return path


# ── OCR ───────────────────────────────────────────────────────────────────────
def run_ocr(img_path: str):
    print(f"\n[INFO] Image : {img_path}")
    print("[INFO] Initialising PaddleOCR ...")
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)

    print("[INFO] Running OCR ...\n")
    result = ocr.ocr(img_path, cls=True)

    if not result or not result[0]:
        print("[WARN] No text detected.")
        return

    # ── Section 1 : Raw OCR tokens ───────────────────────────────────────────
    print("=" * 70)
    print("  RAW OCR OUTPUT")
    print("=" * 70)
    print(f"  {'TEXT':<44} {'CONF':>8}")
    print("-" * 70)
    for line in result[0]:
        bbox, (text, conf) = line[0], line[1]
        print(f"  {text:<44} {conf:>8.3f}")
    print(f"\n  Total raw tokens: {len(result[0])}")

    # ── Section 2 : Structured menu items ────────────────────────────────────
    print("\n" + "=" * 70)
    print("  STRUCTURED MENU (after layout parsing)")
    print("=" * 70)
    menu = parse_menu(result)

    if not menu:
        print("  [WARN] No structured items could be extracted.")
    else:
        current_cat = None
        for entry in menu:
            if entry["category"] != current_cat:
                current_cat = entry["category"]
                print(f"\n  ── {current_cat} ──")
            price_str = f"₹{entry['price']:.0f}"
            print(f"  {entry['item']:<45} {price_str:>8}")
        print(f"\n  Total structured items: {len(menu)}")

    return menu


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    img = REAL_IMAGE if os.path.exists(REAL_IMAGE) else create_dummy_image(DUMMY_IMAGE)
    run_ocr(img)
