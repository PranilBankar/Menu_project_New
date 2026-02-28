"""
Standalone OCR test — paddleocr 2.7.x compatible
Usage (from backend/):  python test_ocr_simple.py
"""
import os
import sys

# Suppress verbose paddle/paddleocr logs
os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_use_mkldnn"] = "0"

import cv2
import numpy as np
from paddleocr import PaddleOCR

# ── Config ────────────────────────────────────────────────────────────────────
REAL_IMAGE  = r"D:\Users\Pranil\Github Repos\Menu_project_New\dataset\Menu1.jpeg"
DUMMY_IMAGE = r"D:\Users\Pranil\Github Repos\Menu_project_New\dataset\dummy_menu.jpg"

# ── Helpers ───────────────────────────────────────────────────────────────────
def create_dummy_image(path: str) -> str:
    """Generate a simple menu image for testing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = np.ones((500, 700, 3), dtype=np.uint8) * 255
    rows = [
        ("-- FOOD MENU --",         (160, 45),  1.2),
        ("Starters",                (40,  110), 1.0),
        ("Tomato Soup       Rs.150",(40,  160), 0.8),
        ("French Fries      250/-", (40,  200), 0.8),
        ("Main Course",             (40,  270), 1.0),
        ("Grilled Chicken   350/-", (40,  320), 0.8),
        ("Vegetable Pasta   Rs.300",(40,  360), 0.8),
        ("Beverages",               (40,  430), 1.0),
        ("Mango Lassi       Rs.120",(40,  475), 0.8),
    ]
    for text, pos, scale in rows:
        cv2.putText(img, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                    scale, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.imwrite(path, img)
    print(f"[INFO] Dummy image created: {path}")
    return path


def run_ocr(img_path: str):
    """Run OCR and print a clean results table."""
    print(f"\n[INFO] Image: {img_path}")
    print("[INFO] Initializing PaddleOCR (first run downloads models ~100 MB) ...")

    # paddleocr 2.7.x API — pass image path directly
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False,
                    show_log=False)

    print("[INFO] Running OCR ...\n")
    result = ocr.ocr(img_path, cls=True)

    if not result or not result[0]:
        print("[WARN] No text detected.")
        return

    print("=" * 65)
    print(f"  {'TEXT':<44} {'CONF':>8}")
    print("=" * 65)
    lines = []
    for line in result[0]:
        bbox, (text, conf) = line[0], line[1]
        print(f"  {text:<44} {conf:>8.3f}")
        lines.append(text)
    print("=" * 65)
    print(f"\n  Total lines detected: {len(lines)}")
    print("\n--- Full extracted text ---")
    print("\n".join(lines))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    img = REAL_IMAGE if os.path.exists(REAL_IMAGE) else create_dummy_image(DUMMY_IMAGE)
    run_ocr(img)
