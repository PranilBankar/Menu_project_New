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
ROW_TOLERANCE        = 10   # px: max Y-gap to group tokens into the same row
                             # Tight on purpose — avoids merging adjacent rows
COLUMN_GAP_THRESHOLD = 80   # px: horizontal gap that signals a new column header
MIN_CONFIDENCE       = 0.60 # discard OCR tokens below this confidence
MIN_ITEM_LEN         = 2    # minimum chars for a valid item name
MAX_ITEM_NAME_LEN    = 60   # reject items with absurdly long names (it's a description)
MAX_WORDS_IN_NAME    = 8    # reject items with too many words (likely description text)

# Matches standalone price tokens: 150, ₹150, Rs.150, 150/-, 1,200 etc.
_PRICE_RE = re.compile(
    r'^₹?\s*(?:Rs\.?\s*)?(\d{1,5}(?:[.,]\d{1,3})?)(?:\s*/-)?$',
    re.IGNORECASE
)

# Strings that look like prices but are NOT (dates, phone fragments, etc.)
_NOISE_RE = re.compile(r'^\d{6,}$')   # 6+ digit numbers are not prices

# Words/characters to discard even if they pass confidence check
_GARBAGE_RE = re.compile(r'^[^\w\s₹]+$')   # purely punctuation/symbols

# OCR garbage words: contain digits mixed with letters in nonsensical ways
_GARBLED_WORD_RE = re.compile(r'\b(?:[a-zA-Z]{1,2}\d+|\d+[a-zA-Z]{1,2})\b')

# Phrases that indicate a description/note, not a menu header
_DESCRIPTION_CLUE_RE = re.compile(
    r'\b(served|with|includes|and|or|per|only|please|note|\(|\)$)\b',
    re.IGNORECASE
)


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


def _is_garbled(name: str) -> bool:
    """
    Return True if the item name looks like OCR garbage or a description.
    Heuristics:
      - Too long (likely a description/subtitle)
      - Too many words
      - Contains garbled OCR tokens (e.g. 'wh2', 'Rc', 'wtSad')
    """
    if len(name) > MAX_ITEM_NAME_LEN:
        return True
    words = name.split()
    if len(words) > MAX_WORDS_IN_NAME:
        return True
    # Count garbled OCR tokens — if more than 1, it's probably a description
    garbled_hits = len(_GARBLED_WORD_RE.findall(name))
    if garbled_hits > 1:
        return True
    return False


def _is_valid_header(text: str) -> bool:
    """
    Heuristic: a real section header is short, doesn't start with lowercase
    conjunctions, and doesn't look like a continuation of a description.
    """
    if len(text) > 50:
        return False
    if bool(_DESCRIPTION_CLUE_RE.search(text)):
        return False
    # Must start with an uppercase letter or digit
    stripped = text.strip()
    if stripped and not (stripped[0].isupper() or stripped[0].isdigit()):
        return False
    return True


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
    Garbled / overly long item names are discarded.
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
            if len(name) >= MIN_ITEM_LEN and not _is_garbled(name):
                pairs.append((name, price))
            item_fragments = []
        else:
            # Text token → accumulate into item name buffer
            if not _is_noise(text):
                item_fragments.append(text)

    return pairs


def _split_header_row(row: List[Dict]) -> List[Tuple[str, float]]:
    """
    Within a header row (no prices), detect multiple column headers by
    looking for large horizontal X-gaps between consecutive tokens.

    Returns a list of (header_text, mid_x) tuples — one per detected column.
    mid_x is the horizontal centre of the column header, used later to match
    with items that fall under the same column.
    """
    groups: List[List[Dict]] = []
    current_group: List[Dict] = []

    for i, tok in enumerate(row):       # row is already sorted left→right
        if not current_group:
            current_group.append(tok)
        else:
            gap = tok['left_x'] - current_group[-1]['left_x']
            if gap > COLUMN_GAP_THRESHOLD:
                groups.append(current_group)
                current_group = [tok]
            else:
                current_group.append(tok)

    if current_group:
        groups.append(current_group)

    result = []
    for grp in groups:
        text = _clean_name(' '.join(t['text'] for t in grp if not _is_noise(t['text'])))
        if len(text) >= MIN_ITEM_LEN and not re.match(r'^\d+$', text):
            # mid_x = centre of this header group
            min_x = min(t['left_x'] for t in grp)
            max_x = max(t['left_x'] for t in grp)
            mid_x = (min_x + max_x) / 2.0
            result.append((text, mid_x))

    return result


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
            'right_x':  max(pt[0] for pt in bbox),
        })

    # ── Group into rows ───────────────────────────────────────────────────────
    rows = _group_rows(raw_tokens)

    # ── Parse each row ────────────────────────────────────────────────────────
    menu_items: List[Dict[str, Any]] = []

    # column_categories: list of (category_name, mid_x)
    # We keep one per discovered column; items are assigned the category
    # whose mid_x is closest to the item's left_x.
    column_categories: List[Tuple[str, float]] = [("General", 0.0)]

    def _category_for_x(x: float) -> str:
        """Return the category whose mid_x is closest to x."""
        return min(column_categories, key=lambda c: abs(c[1] - x))[0]

    for row in rows:
        pairs = _parse_row(row)

        if pairs:
            # Row produced item-price pairs — assign each to nearest column
            for name, price in pairs:
                # Use the left_x of the first token of the item (approx)
                # We approximate by finding the token whose text starts the name
                item_x = row[0]['left_x']  # simplification: leftmost token in row
                # Better: find the token matching the beginning of the item name
                for tok in row:
                    if tok['text'].strip() and name.startswith(tok['text'].strip()[:4]):
                        item_x = tok['left_x']
                        break

                menu_items.append({
                    "category": _category_for_x(item_x),
                    "item":     name,
                    "price":    price,
                })
        else:
            # No price found → detect column headers (may be multiple per row)
            headers = _split_header_row(row)
            if headers:
                # Merge into column_categories: update existing or add new columns
                # Strategy: for each detected header, find closest existing column
                # and update it, or add a new one if gap is large.
                for hdr_text, hdr_mid_x in headers:
                    # Reject description fragments like "and pickle)"
                    if not _is_valid_header(hdr_text):
                        continue
                    # Find closest existing column
                    closest = min(column_categories,
                                  key=lambda c: abs(c[1] - hdr_mid_x))
                    if abs(closest[1] - hdr_mid_x) < COLUMN_GAP_THRESHOLD:
                        idx = column_categories.index(closest)
                        column_categories[idx] = (hdr_text, hdr_mid_x)
                    else:
                        column_categories.append((hdr_text, hdr_mid_x))

    return menu_items
