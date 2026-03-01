"""
Menu Layout Parser (Simplified)
--------------------------------
Extracts raw (item_name, price) pairs from PaddleOCR bounding-box output.

Deliberately does NOT attempt to detect categories/section names — that
semantic work is handed off to the LLM structurer (menu_structurer.py).

Algorithm:
  1. Cluster tokens into rows by fixed anchor Y proximity (±ROW_TOLERANCE px).
  2. Sort each row's tokens left-to-right by X position.
  3. Scan each row left→right:
       - Accumulate text tokens into a running item-name buffer.
       - When a price token is hit → emit (item_name, price) pair, reset buffer.
  4. Filter out garbled / overly long item names (OCR noise / description text).
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Tuple

# ── Tunables ──────────────────────────────────────────────────────────────────
ROW_TOLERANCE     = 10    # px: max Y-gap to group tokens into the same row
MIN_CONFIDENCE    = 0.60  # discard OCR tokens below this confidence
MIN_ITEM_LEN      = 2     # minimum chars for a valid item name
MAX_ITEM_NAME_LEN = 60    # reject overly long names (they're description text)
MAX_WORDS_IN_NAME = 8     # reject names with too many words

# Matches standalone price tokens: 150, ₹150, Rs.150, 150/-, 1,200 etc.
_PRICE_RE = re.compile(
    r'^₹?\s*(?:Rs\.?\s*)?(\d{1,5}(?:[.,]\d{1,3})?)(?:\s*/-)?$',
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
    if _LONG_NUM_RE.match(token):
        return None
    m = _PRICE_RE.match(token)
    if m:
        try:
            return float(m.group(1).replace(',', ''))
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


# ── Row parser ────────────────────────────────────────────────────────────────

def _parse_row(row: List[Dict]) -> List[Tuple[str, float]]:
    """
    Scan one row left→right.  Each price token closes the preceding text
    buffer into an (item_name, price) pair.
    """
    pairs: List[Tuple[str, float]] = []
    fragments: List[str] = []

    for tok in row:
        text = tok['text'].strip()
        if not text:
            continue
        price = _parse_price(text)
        if price is not None:
            name = _clean_name(' '.join(fragments))
            if len(name) >= MIN_ITEM_LEN and not _is_garbled(name):
                pairs.append((name, price))
            fragments = []
        else:
            if not _is_noise(text):
                fragments.append(text)

    return pairs


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

    # Group into rows and parse each row
    menu_items: List[Dict[str, Any]] = []
    for row in _group_rows(tokens):
        for name, price in _parse_row(row):
            menu_items.append({"item": name, "price": price})

    return menu_items
