"""
Quick OCR + Layout Parser test — no evaluation, no LLM.
Prints extracted (item, price) pairs from a menu image.

Usage:
    cd backend
    python test_ocr_parse.py ../dataset/Menu1.jpeg
    python test_ocr_parse.py ../dataset/Menu4.jpeg --debug    # show raw OCR tokens
"""
import sys
import os
import cv2

sys.path.insert(0, os.path.dirname(__file__))

from app.services.ocr.ocr_engine import get_ocr_engine
from app.services.ocr.menu_layout_parser import parse_menu


def main():
    debug = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--debug"]

    if not args:
        print("Usage: python test_ocr_parse.py <image_path> [--debug]")
        sys.exit(1)

    image_path = args[0]
    print(f"\n[IMAGE] {image_path}")

    # OCR
    print("Running PaddleOCR ...")
    ocr_engine = get_ocr_engine()
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: Cannot read image: {image_path}")
        sys.exit(1)

    raw = ocr_engine.ocr.ocr(img)
    page = raw[0] if raw and raw[0] else []
    print(f"OCR detected {len(page)} tokens\n")

    # Debug: show all raw OCR tokens
    if debug and page:
        print("═" * 80)
        print("  RAW OCR TOKENS (sorted by Y then X)")
        print("═" * 80)
        tokens = []
        for line in page:
            bbox, (text, conf) = line[0], line[1]
            cy = (bbox[0][1] + bbox[2][1]) / 2.0
            lx = min(pt[0] for pt in bbox)
            rx = max(pt[0] for pt in bbox)
            tokens.append((cy, lx, rx, text, conf))

        tokens.sort(key=lambda t: (t[0], t[1]))

        print(f"{'#':<4} {'Y':>6} {'X-left':>7} {'X-right':>8} {'Conf':>5}  {'Text'}")
        print("-" * 80)
        for i, (cy, lx, rx, text, conf) in enumerate(tokens, 1):
            marker = "$$" if any(c.isdigit() for c in text) and len(text) <= 5 else "  "
            print(f"{i:<4} {cy:>6.0f} {lx:>7.0f} {rx:>8.0f} {conf:>5.2f}  {marker} {text}")

        print(f"\n{'═' * 80}\n")

    # Layout Parser
    items = parse_menu(raw)
    print(f"{'#':<4} {'Item Name':<45} {'Price':>8}")
    print("-" * 60)
    for i, it in enumerate(items, 1):
        print(f"{i:<4} {it['item']:<45} ₹{it['price']:>7.2f}")

    print(f"\nTotal items extracted: {len(items)}")

    # Show what was missed
    if debug:
        print(f"\nHINT: If items are missing, check the raw tokens above:")
        print(f"   - Are prices being detected? (look for $$ markers)")
        print(f"   - Are item names and prices on the same Y-row?")
        print(f"   - Is there a large X-gap between name and price?\n")


if __name__ == "__main__":
    main()
