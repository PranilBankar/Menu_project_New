"""
Menu Layout Parser
------------------
Converts raw PaddleOCR output (bounding-box + text tokens) into structured
(category, item, price) records using a price-as-boundary column strategy.

Works for 2, 3, or 4-column menu layouts without any hardcoded column count.

Algorithm:
  1. Cluster tokens into rows by centre-Y proximity (±ROW_TOLERANCE px).
  2. Sort each row's tokens left-to-right by X position.
  3. Scan each row left→right:
       - Accumulate text tokens into a running item-name buffer.
       - When a price token is hit  →  emit (item_name, price) pair, reset buffer.
  4. Rows that produce *no* price pairs are treated as category/section headers.
  5. Low-confidence or noisy tokens are discarded before parsing.
"""

from __future__ import annotations
import re
from typing import List, Dict, Any, Optional, Tuple

# ── Tunables ──────────────────────────────────────────────────────────────────
ROW_TOLERANCE   = 10    # px: max vertical gap to consider tokens on the same row
                        # Tight on purpose — avoids merging adjacent rows
MIN_CONFIDENCE  = 0.60  # discard OCR tokens below this confidence
MIN_ITEM_LEN    = 2     # minimum chars for a valid item name

# Matches standalone price tokens: 150, ₹150, Rs.150, 150/-, 1,200 etc.
_PRICE_RE = re.compile(
    r'^₹?\s*(?:Rs\.?\s*)?(\d{1,5}(?:[.,]\d{1,3})?)(?:\s*/-)?$',
    re.IGNORECASE
)

# Strings that look like prices but are NOT (dates, phone fragments, etc.)
_NOISE_RE = re.compile(r'^\d{6,}$')   # 6+ digit numbers are not prices

# Words/characters to discard even if they pass confidence check
_GARBAGE_RE = re.compile(r'^[^\w\s₹]+$')   # purely punctuation/symbols


# ── Helpers ───────────────────────────────────────────────────────────────────

def _centre_y(bbox: List) -> float:
    """Return vertical centre of an OCR bounding box."""
    # bbox: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
    return (bbox[0][1] + bbox[2][1]) / 2.0


def _left_x(bbox: List) -> float:
    return min(pt[0] for pt in bbox)


def _parse_price(token: str) -> Optional[float]:
    """
    Return numeric price if *token* is a price string, else None.
    """
    token = token.strip()
    if _NOISE_RE.match(token):
        return None
    m = _PRICE_RE.match(token)
    if m:
        raw = m.group(1).replace(',', '')
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _is_noise(text: str) -> bool:
    return bool(_GARBAGE_RE.match(text.strip())) or len(text.strip()) < 1


def _clean_name(name: str) -> str:
    """Strip filler characters (dots, dashes) from item name."""
    return re.sub(r'[\.\-]+$', '', name).strip(' .,:-')


# ── Core Parser ───────────────────────────────────────────────────────────────

def _group_rows(ocr_tokens: List[Dict]) -> List[List[Dict]]:
    """
    Partition tokens into rows by centre-Y proximity.

    Uses the FIRST token's Y as a fixed anchor for each row (no running average)
    so that adjacent rows never drift and merge into each other.
    Returns list of rows, each sorted left→right by X.
    """
    sorted_tokens = sorted(ocr_tokens, key=lambda t: t['centre_y'])

    rows: List[List[Dict]] = []
    current_row: List[Dict] = []
    anchor_y: Optional[float] = None   # fixed to first token in the row

    for tok in sorted_tokens:
        if anchor_y is None or abs(tok['centre_y'] - anchor_y) <= ROW_TOLERANCE:
            current_row.append(tok)
            # anchor_y is SET ONCE when the row starts and never updated
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda t: t['left_x']))
            current_row = [tok]
            anchor_y = tok['centre_y']   # new anchor for the new row

        if anchor_y is None:
            anchor_y = tok['centre_y']   # first token overall

    if current_row:
        rows.append(sorted(current_row, key=lambda t: t['left_x']))

    return rows


def _parse_row(row: List[Dict]) -> List[Tuple[str, float]]:
    """
    Scan one row left→right using price-as-boundary strategy.
    Returns a list of (item_name, price) pairs found in this row.
    """
    pairs: List[Tuple[str, float]] = []
    item_fragments: List[str] = []

    for tok in row:
        text = tok['text'].strip()
        if not text:
            continue

        price = _parse_price(text)
        if price is not None:
            # Price token → close current item segment
            name = _clean_name(' '.join(item_fragments))
            if len(name) >= MIN_ITEM_LEN:
                pairs.append((name, price))
            item_fragments = []
        else:
            # Text token → accumulate into item name buffer
            if not _is_noise(text):
                item_fragments.append(text)

    return pairs


# ── Public API ────────────────────────────────────────────────────────────────

def parse_menu(ocr_result: List) -> List[Dict[str, Any]]:
    """
    Parse raw PaddleOCR result into structured menu records.

    Args:
        ocr_result: The list returned by `paddleocr.ocr()`, i.e.
                    [ [ [bbox, (text, conf)], ... ] ]

    Returns:
        List of dicts:
          { "category": str, "item": str, "price": float }
    """
    # ── Flatten & filter tokens ───────────────────────────────────────────────
    raw_tokens: List[Dict] = []
    page = ocr_result[0] if ocr_result else []
    if page is None:
        return []

    for line in page:
        bbox, (text, conf) = line[0], line[1]
        if conf < MIN_CONFIDENCE:
            continue
        if _is_noise(text):
            continue
        raw_tokens.append({
            'bbox':     bbox,
            'text':     text,
            'conf':     conf,
            'centre_y': _centre_y(bbox),
            'left_x':   _left_x(bbox),
        })

    # ── Group into rows ───────────────────────────────────────────────────────
    rows = _group_rows(raw_tokens)

    # ── Parse each row ────────────────────────────────────────────────────────
    menu_items: List[Dict[str, Any]] = []
    current_category = "General"

    for row in rows:
        pairs = _parse_row(row)

        if pairs:
            # Row produced item-price pairs
            for name, price in pairs:
                menu_items.append({
                    "category": current_category,
                    "item":     name,
                    "price":    price,
                })
        else:
            # No price found → treat as a section/category header
            # Gather all non-noise text in the row as the category name
            header = ' '.join(t['text'] for t in row if not _is_noise(t['text']))
            header = _clean_name(header)
            if len(header) >= MIN_ITEM_LEN:
                # Only update category if the header looks like a real heading
                # (not a standalone letter or digit)
                if not re.match(r'^\d+$', header):
                    current_category = header

    return menu_items
