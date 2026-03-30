"""Dump raw OCR tokens to debug_tokens.txt — no emojis, no mixed output."""
import sys, os, cv2, logging
logging.disable(logging.CRITICAL)
os.environ["PPOCR_LOG_LEVEL"] = "ERROR"
sys.path.insert(0, os.path.dirname(__file__))

from app.services.ocr.ocr_engine import get_ocr_engine
from app.services.ocr.menu_layout_parser import parse_menu, _parse_price

image_path = sys.argv[1] if len(sys.argv) > 1 else "../dataset/Menu4.jpeg"

ocr = get_ocr_engine()
img = cv2.imread(image_path)
raw = ocr.ocr.ocr(img)
page = raw[0] if raw and raw[0] else []

tokens = []
for line in page:
    bbox, (text, conf) = line[0], line[1]
    cy = (bbox[0][1] + bbox[2][1]) / 2.0
    lx = min(pt[0] for pt in bbox)
    rx = max(pt[0] for pt in bbox)
    tokens.append((cy, lx, rx, text, conf))

tokens.sort(key=lambda t: (t[0], t[1]))

out = []
out.append(f"Total tokens: {len(tokens)}")
out.append("")
out.append(f"{'#':<4} {'Y':>6} {'X-L':>6} {'X-R':>6} {'Gap':>5} {'Conf':>5}  {'Price?':>6}  Text")
out.append("-" * 85)

prev_rx = 0
prev_cy = 0
for i, (cy, lx, rx, text, conf) in enumerate(tokens, 1):
    is_price = _parse_price(text.strip()) is not None
    gap = lx - prev_rx if i > 1 and abs(cy - prev_cy) < 12 else 0
    row_break = "--- new row ---" if i > 1 and abs(cy - prev_cy) >= 12 else ""
    if row_break:
        out.append(row_break)
    price_flag = "PRICE" if is_price else ""
    gap_flag = f"  <<GAP {gap:.0f}px>>" if gap > 30 else ""
    out.append(f"{i:<4} {cy:>6.0f} {lx:>6.0f} {rx:>6.0f} {gap:>5.0f} {conf:>5.2f}  {price_flag:>6}  {text}{gap_flag}")
    prev_rx = rx
    prev_cy = cy

out.append("")
out.append("=" * 85)
out.append("PARSED ITEMS:")
out.append("=" * 85)

items = parse_menu(raw)
for i, it in enumerate(items, 1):
    out.append(f"{i:<4} {it['item']:<45} {it['price']:>8.2f}")
out.append(f"\nTotal: {len(items)}")

text = "\n".join(out)
with open("debug_tokens.txt", "w", encoding="utf-8") as f:
    f.write(text)
print(text)
