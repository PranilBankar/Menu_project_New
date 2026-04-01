"""
Menu Layout Parser (Improved)
-------------------------------
Extracts raw (item_name, price) pairs from PaddleOCR bounding-box output.

Deliberately does NOT attempt to detect categories/section names — that
semantic work is handed off to the LLM structurer (menu_structurer.py).

Algorithm:
  1. Cluster tokens into rows by fixed anchor Y proximity (±ROW_TOLERANCE px).
  2. Split each row into columns using horizontal-gap detection + price breaks.
  3. Sort each column's tokens left-to-right by X position.
  4. Scan each column left→right:
       - Accumulate text tokens into a running item-name buffer.
       - When a price token is hit → emit (item_name, price) pair, reset buffer.
  5. Filter out garbled / overly long item names (OCR noise / description text).
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Tuple

# ── Tunables ──────────────────────────────────────────────────────────────────
ROW_TOLERANCE     = 10    # px: max Y-gap to group tokens into the same row
COLUMN_GAP        = 40    # px: min horizontal gap to split a row into columns
PRICE_GAP         = 20    # px: min gap after a price token to treat as column break
ORPHAN_Y_TOLERANCE = 15   # px: max Y-gap to match orphan items with nearby prices
MIN_CONFIDENCE    = 0.50  # discard OCR tokens below this confidence
MIN_ITEM_LEN      = 2     # minimum chars for a valid item name
MAX_ITEM_NAME_LEN = 60    # reject overly long names (they're description text)
MAX_WORDS_IN_NAME = 8     # reject names with too many words

# Matches standalone price tokens: 150, ₹150, Rs.150, 150/-, 1,200, ₹ 150, etc.
_PRICE_RE = re.compile(
    r'^[₹$]?\s*(?:Rs\.?\s*)?(\d{1,5}(?:[.,]\d{1,3})?)(?:\s*/-)?$',
    re.IGNORECASE
)
# Also match prices that OCR may garble slightly: "3Z0" → probably "320"
_PRICE_LOOSE_RE = re.compile(
    r'^[₹$]?\s*(?:Rs\.?\s*)?(\d{1,4}[0Oo]\d?)(?:\s*/-)?$',
    re.IGNORECASE
)
# 6+ digit numbers are NOT prices (phone numbers, dates)
_LONG_NUM_RE = re.compile(r'^\d{6,}$')
# Purely punctuation/symbol tokens
_GARBAGE_RE = re.compile(r'^[^\w\s₹]+$')
# OCR garbage: short letter+digit combos like 'wh2', 'Rc', 'wtSad'
_GARBLED_WORD_RE = re.compile(r'\b(?:[a-zA-Z]{1,2}\d+|\d+[a-zA-Z]{1,2})\b')


# ── Helpers ───────────────────────────────────────────────────────────────────

def _centre_y(bbox: List) -> float:
    return (bbox[0][1] + bbox[2][1]) / 2.0


def _left_x(bbox: List) -> float:
    return min(pt[0] for pt in bbox)


def _right_x(bbox: List) -> float:
    return max(pt[0] for pt in bbox)


def _parse_price(token: str) -> Optional[float]:
    token = token.strip()

    # Strip leading dots/periods (from OCR'd dot leaders: "item.........$6" → ".$6")
    token = token.lstrip('.')

    # Fix OCR misread: 'S' at start often means '$' (e.g., "S10" → "$10", ".S7" → "$7")
    if token and token[0] in ('S', 's') and len(token) <= 4:
        maybe = '$' + token[1:]
        if _PRICE_RE.match(maybe):
            token = maybe

    token = token.strip()
    if not token:
        return None

    if _LONG_NUM_RE.match(token):
        return None
    m = _PRICE_RE.match(token)
    if m:
        try:
            return float(m.group(1).replace(',', ''))
        except ValueError:
            return None
    # Loose match for OCR-garbled prices (e.g., "32O" → "320")
    m = _PRICE_LOOSE_RE.match(token)
    if m:
        try:
            cleaned = m.group(1).replace('O', '0').replace('o', '0')
            return float(cleaned)
        except ValueError:
            return None
    return None


def _is_noise(text: str) -> bool:
    return bool(_GARBAGE_RE.match(text.strip())) or len(text.strip()) < 1


def _is_garbled(name: str) -> bool:
    """True if the name is too long, too wordy, or full of OCR garbage tokens."""
    if len(name) > MAX_ITEM_NAME_LEN:
        return True
    if len(name.split()) > MAX_WORDS_IN_NAME:
        return True
    if len(_GARBLED_WORD_RE.findall(name)) > 1:
        return True
    return False


def _clean_name(name: str) -> str:
    return re.sub(r'[.\-]+$', '', name).strip(' .,:-')


# ── Row grouping ──────────────────────────────────────────────────────────────

def _group_rows(tokens: List[Dict]) -> List[List[Dict]]:
    """
    Cluster tokens into horizontal rows by centre-Y proximity.
    Uses a fixed anchor Y (first token in the row) — no drifting average.
    Each row is returned sorted left→right by X.
    """
    sorted_tokens = sorted(tokens, key=lambda t: t['centre_y'])
    rows: List[List[Dict]] = []
    current_row: List[Dict] = []
    anchor_y: Optional[float] = None

    for tok in sorted_tokens:
        if anchor_y is None or abs(tok['centre_y'] - anchor_y) <= ROW_TOLERANCE:
            if anchor_y is None:
                anchor_y = tok['centre_y']
            current_row.append(tok)
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda t: t['left_x']))
            current_row = [tok]
            anchor_y = tok['centre_y']

    if current_row:
        rows.append(sorted(current_row, key=lambda t: t['left_x']))

    return rows


# ── Column splitting ─────────────────────────────────────────────────────────

def _split_into_columns(row: List[Dict]) -> List[List[Dict]]:
    """
    Split a single row into sub-columns using two signals:
      1. Large horizontal gap (>COLUMN_GAP px) between consecutive tokens
      2. After a price token, if there's a gap (>PRICE_GAP px) to the next token,
         treat it as a column break — the price ends one item, next token starts another.

    This handles multi-column menus where items sit side-by-side on the same line.
    """
    if len(row) <= 1:
        return [row]

    columns: List[List[Dict]] = []
    current_col: List[Dict] = [row[0]]

    for i in range(1, len(row)):
        prev_tok = row[i - 1]
        curr_tok = row[i]

        # Calculate horizontal gap between end of previous token and start of current
        gap = curr_tok['left_x'] - prev_tok['right_x']

        # Is the current token a price?
        curr_is_price = _parse_price(curr_tok['text'].strip()) is not None
        # Was the previous token a price?
        prev_is_price = _parse_price(prev_tok['text'].strip()) is not None

        # Signal 1: Large gap means start of a new column
        # Normal columns split at COLUMN_GAP.
        # But if the current token is a price, we normally DON'T split so it pairs with text.
        # However, if the gap is massively large (> 90px), it's crossing over an empty column space
        # so we MUST split to prevent cross-column stealing (orphan recovery will pair it later).
        is_gap_break = (gap >= COLUMN_GAP and not curr_is_price) or (gap >= 90)

        # Signal 2: Previous token was a price AND there's a gap to next text
        is_price_break = prev_is_price and gap >= PRICE_GAP

        if is_gap_break or is_price_break:
            columns.append(current_col)
            current_col = [curr_tok]
        else:
            current_col.append(curr_tok)

    if current_col:
        columns.append(current_col)

    return columns


# ── Row parser ────────────────────────────────────────────────────────────────

def _parse_row(row: List[Dict]) -> Tuple[List[Tuple[str, float]],
                                          List[Dict],
                                          List[Dict]]:
    """
    Scan one row left→right.  Each price token closes the preceding text
    buffer into an (item_name, price) pair.

    Returns:
        (pairs, orphan_items, orphan_prices)
        - pairs:         matched (item_name, price) tuples
        - orphan_items:  tokens that formed text but had no following price
        - orphan_prices: price tokens with no preceding text
    """
    pairs: List[Tuple[str, float]] = []
    orphan_items: List[Dict] = []
    orphan_prices: List[Dict] = []
    fragments: List[str] = []
    fragment_tokens: List[Dict] = []

    for tok in row:
        text = tok['text'].strip()
        if not text:
            continue
        price = _parse_price(text)
        if price is not None:
            name = _clean_name(' '.join(fragments))
            if len(name) >= MIN_ITEM_LEN and not _is_garbled(name):
                pairs.append((name, price))
            elif not fragments:
                # Price with no preceding text → orphan price
                orphan_prices.append({
                    'price': price,
                    'centre_y': tok['centre_y'],
                    'left_x': tok['left_x'],
                })
            fragments = []
            fragment_tokens = []
        else:
            if not _is_noise(text):
                fragments.append(text)
                fragment_tokens.append(tok)

    # Leftover text with no price → orphan item
    if fragments:
        name = _clean_name(' '.join(fragments))
        if len(name) >= MIN_ITEM_LEN and not _is_garbled(name):
            avg_y = sum(t['centre_y'] for t in fragment_tokens) / len(fragment_tokens)
            avg_x = sum(t['right_x'] for t in fragment_tokens) / len(fragment_tokens)
            orphan_items.append({
                'name': name,
                'centre_y': avg_y,
                'right_x': avg_x,
            })

    return pairs, orphan_items, orphan_prices


# ── Public API ────────────────────────────────────────────────────────────────

def parse_menu(ocr_result: List) -> List[Dict[str, Any]]:
    """
    Parse raw PaddleOCR output into a flat list of menu item records.

    Args:
        ocr_result: Return value of paddleocr.ocr(), i.e.
                    [ [ [bbox, (text, conf)], ... ] ]

    Returns:
        List of dicts: { "item": str, "price": float }
        (No category — the LLM structurer assigns categories downstream.)
    """
    page = ocr_result[0] if ocr_result else []
    if not page:
        return []

    # Flatten & filter tokens
    tokens: List[Dict] = []
    for line in page:
        bbox, (text, conf) = line[0], line[1]
        if conf < MIN_CONFIDENCE or _is_noise(text):
            continue
        tokens.append({
            'text':     text,
            'conf':     conf,
            'centre_y': _centre_y(bbox),
            'left_x':   _left_x(bbox),
            'right_x':  _right_x(bbox),
        })

    # Group into rows → split into columns → parse each column
    menu_items: List[Dict[str, Any]] = []
    all_orphan_items: List[Dict] = []
    all_orphan_prices: List[Dict] = []

    for row in _group_rows(tokens):
        for column in _split_into_columns(row):
            pairs, orphan_items, orphan_prices = _parse_row(column)
            for name, price in pairs:
                menu_items.append({"item": name, "price": price})
            all_orphan_items.extend(orphan_items)
            all_orphan_prices.extend(orphan_prices)

    # ── Orphan recovery ───────────────────────────────────────────────────
    # Match items that had no price with nearby unclaimed prices.
    # This handles multi-column menus where a price token is slightly
    # offset in Y from its item (e.g., "Pineapple juice" Y=280, "$4" Y=287).
    claimed_prices = set()
    for orphan_item in all_orphan_items:
        best_price = None
        best_dist = float('inf')
        best_idx = -1

        for idx, orphan_price in enumerate(all_orphan_prices):
            if idx in claimed_prices:
                continue
            y_dist = abs(orphan_item['centre_y'] - orphan_price['centre_y'])
            if y_dist <= ORPHAN_Y_TOLERANCE:
                # Prefer prices to the RIGHT of the item (higher X)
                x_ok = orphan_price['left_x'] > orphan_item['right_x'] - 50
                if x_ok and y_dist < best_dist:
                    best_dist = y_dist
                    best_price = orphan_price['price']
                    best_idx = idx

        if best_price is not None:
            menu_items.append({"item": orphan_item['name'], "price": best_price})
            claimed_prices.add(best_idx)

    return menu_items


