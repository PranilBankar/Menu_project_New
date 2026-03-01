"""
Embedding Service
-----------------
Generates sentence embeddings for menu items and stores them in Supabase
via direct PostgreSQL connection (psycopg2 + pgvector).

Flow:
  parsed_menu_items (from menu_layout_parser)
      → build rich embedding text per item
      → sentence-transformers model → 384-dim vector
      → upsert into Supabase menu_items table
      → HNSW index enables fast similarity search at query time
"""

from __future__ import annotations

import os
import sys
import uuid
import logging
from typing import List, Dict, Any, Optional

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# Add backend root to path when running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_embedding_text(item: Dict[str, Any],
                           restaurant_name: str = "",
                           area_name: str = "") -> str:
    """
    Build a rich text string for embedding.
    Includes item name, category, restaurant, and area so the vector
    carries full geographic + semantic context.

    Example output:
        "Dal Tadka | section: Indian Combo Meals | restaurant: Gabbar da Dhaba | area: Pune"
    """
    parts = [item["item"]]
    if item.get("category") and item["category"] not in ("General", ""):
        parts.append(f"section: {item['category']}")
    if restaurant_name:
        parts.append(f"restaurant: {restaurant_name}")
    if area_name:
        parts.append(f"area: {area_name}")
    return " | ".join(parts)


# ── Main Service ──────────────────────────────────────────────────────────────

class EmbeddingService:
    """
    Handles embedding generation and Supabase storage for menu items.

    Usage:
        svc = EmbeddingService()
        svc.embed_and_store(
            parsed_items=parse_menu(ocr_result),
            restaurant_id="<uuid>",
            restaurant_name="Gabbar da Dhaba",
            area_name="Koramangala, Bangalore"
        )

    Similarity search:
        results = svc.search(query="spicy vegetarian biryani", top_k=5,
                             restaurant_ids=["<uuid>"])
    """

    def __init__(self):
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        self._conn: Optional[psycopg2.extensions.connection] = None

    # ── DB connection ─────────────────────────────────────────────────────────

    def _get_conn(self) -> psycopg2.extensions.connection:
        """
        Lazy-connect to Supabase PostgreSQL and register pgvector type.
        Uses urllib.parse to safely handle passwords that contain '@' characters,
        which break naive connection string parsing.
        """
        if self._conn is None or self._conn.closed:
            from urllib.parse import urlparse, unquote

            url = urlparse(settings.DATABASE_URL)
            self._conn = psycopg2.connect(
                host=url.hostname,
                port=url.port or 5432,
                dbname=url.path.lstrip("/"),
                user=url.username,
                password=unquote(url.password or ""),
                sslmode="require",
            )
            register_vector(self._conn)   # enables vector <-> numpy
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ── Embedding ─────────────────────────────────────────────────────────────

    def generate_embeddings(self,
                            texts: List[str]) -> np.ndarray:
        """
        Batch-generate normalized embeddings.
        Shape: (len(texts), 384)
        """
        vectors = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=len(texts) > 20,
            normalize_embeddings=True,   # cosine similarity → dot product
        )
        return vectors.astype(np.float32)

    # ── Store ─────────────────────────────────────────────────────────────────

    def embed_and_store(self,
                        parsed_items: List[Dict[str, Any]],
                        restaurant_id: str,
                        restaurant_name: str = "",
                        area_name: str = "") -> int:
        """
        Generate embeddings for all parsed menu items and upsert them
        into the Supabase menu_items table.

        Args:
            parsed_items:    Output of menu_layout_parser.parse_menu()
                             Each item: { "category": str, "item": str, "price": float }
            restaurant_id:   UUID of the restaurant row in Supabase
            restaurant_name: Used to enrich embedding text (not required)
            area_name:       Used to enrich embedding text (not required)

        Returns:
            Number of rows upserted.
        """
        if not parsed_items:
            logger.warning("embed_and_store called with empty item list.")
            return 0

        # Build rich embedding texts
        texts = [
            _build_embedding_text(item, restaurant_name, area_name)
            for item in parsed_items
        ]

        logger.info(f"Generating embeddings for {len(texts)} items ...")
        vectors = self.generate_embeddings(texts)

        # Upsert into Supabase
        conn = self._get_conn()
        inserted = 0
        with conn.cursor() as cur:
            for item, vector in zip(parsed_items, vectors):
                price = item.get("price")
                # Safely cast price to int (skip if not a clean number)
                try:
                    price_int = int(float(price)) if price is not None else None
                except (TypeError, ValueError):
                    price_int = None

                # Safely cast calories to int
                try:
                    cal = item.get("calories")
                    calories_int = int(cal) if cal is not None else None
                except (TypeError, ValueError):
                    calories_int = None

                # Safely cast health_score to int
                try:
                    hs = item.get("health_score")
                    health_score_int = int(hs) if hs is not None else None
                except (TypeError, ValueError):
                    health_score_int = None

                cur.execute(
                    """
                    INSERT INTO menu_items
                        (id, restaurant_id, section_name, item_name, price,
                         is_veg, calories, health_score, embedding)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        restaurant_id,
                        item.get("category", "General"),
                        item["item"],
                        price_int,
                        item.get("is_veg"),
                        calories_int,
                        health_score_int,
                        vector,
                    ),
                )
                inserted += 1



        conn.commit()
        logger.info(f"Upserted {inserted} menu items for restaurant {restaurant_id}.")
        return inserted

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self,
               query: str,
               top_k: int = 10,
               restaurant_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Embed a natural-language query and return the top-k most similar
        menu items using pgvector cosine similarity (<=>).

        Args:
            query:           e.g. "spicy vegetarian biryani under 300"
            top_k:           Number of results
            restaurant_ids:  Optional filter — only search within these restaurants

        Returns:
            List of dicts: { id, restaurant_id, section_name, item_name, price, similarity }
        """
        query_vector = self.generate_embeddings([query])[0]

        conn = self._get_conn()
        with conn.cursor() as cur:
            if restaurant_ids:
                cur.execute(
                    """
                    SELECT id, restaurant_id, section_name, item_name, price,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM   menu_items
                    WHERE  restaurant_id = ANY(%s::uuid[])
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  %s
                    """,
                    (query_vector, restaurant_ids, query_vector, top_k),
                )
            else:
                cur.execute(
                    """
                    SELECT id, restaurant_id, section_name, item_name, price,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM   menu_items
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  %s
                    """,
                    (query_vector, query_vector, top_k),
                )

            rows = cur.fetchall()

        return [
            {
                "id":            str(row[0]),
                "restaurant_id": str(row[1]),
                "section_name":  row[2],
                "item_name":     row[3],
                "price":         row[4],
                "similarity":    float(row[5]),
            }
            for row in rows
        ]

    def hybrid_search(self,
                      query: str,
                      filters: Dict[str, Any],
                      top_k: int = 8,
                      restaurant_ids: Optional[List[str]] = None,
                      area_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Semantic search combined with SQL column filters in one query.
        JOINs with restaurants + areas to support area-based multi-restaurant search.

        Args:
            query:          Natural language query (will be embedded)
            filters:        Dict from QueryParser.parse()
            top_k:          Max results to return
            restaurant_ids: Restrict to specific restaurants (optional)
            area_name:      Search across all restaurants in this area (optional)

        Returns:
            List of dicts with item details + restaurant_name + similarity score
        """
        semantic_q = filters.get("semantic_query") or query
        query_vector = self.generate_embeddings([semantic_q])[0]

        # ── Build WHERE clauses dynamically ──────────────────────────────────
        where_clauses = []
        params: list = [query_vector]   # first param: for <=> distance in SELECT

        # Area filter — searches ALL restaurants in the area
        if area_name:
            where_clauses.append("a.area_name ILIKE %s")
            params.append(area_name)

        # Specific restaurant filter (overrides area if both are given)
        if restaurant_ids:
            where_clauses.append("mi.restaurant_id = ANY(%s::uuid[])")
            params.append(restaurant_ids)

        # Hard column filters
        if filters.get("is_veg") is not None:
            where_clauses.append("mi.is_veg = %s")
            params.append(filters["is_veg"])

        if filters.get("max_price") is not None:
            where_clauses.append("mi.price <= %s")
            params.append(filters["max_price"])

        if filters.get("min_price") is not None:
            where_clauses.append("mi.price >= %s")
            params.append(filters["min_price"])

        if filters.get("max_calories") is not None:
            where_clauses.append("mi.calories <= %s")
            params.append(filters["max_calories"])

        if filters.get("min_health_score") is not None:
            where_clauses.append("mi.health_score >= %s")
            params.append(filters["min_health_score"])

        if filters.get("section_name"):
            where_clauses.append("mi.section_name = %s")
            params.append(filters["section_name"])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Second copy of vector for ORDER BY
        params.append(query_vector)
        params.append(top_k)

        sql = f"""
            SELECT mi.id, mi.restaurant_id, r.restaurant_name,
                   mi.section_name, mi.item_name, mi.price,
                   mi.is_veg, mi.calories, mi.health_score,
                   1 - (mi.embedding <=> %s::vector) AS similarity
            FROM   menu_items        mi
            JOIN   restaurants       r  ON mi.restaurant_id = r.restaurant_id
            LEFT JOIN areas          a  ON r.area_id        = a.area_id
            {where_sql}
            ORDER  BY mi.embedding <=> %s::vector
            LIMIT  %s
        """

        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        results = [
            {
                "id":              str(row[0]),
                "restaurant_id":   str(row[1]),
                "restaurant_name": row[2] or "Unknown",
                "section_name":    row[3],
                "item_name":       row[4],
                "price":           row[5],
                "is_veg":          row[6],
                "calories":        row[7],
                "health_score":    row[8],
                "similarity":      float(row[9]),
            }
            for row in rows
        ]

        logger.info(f"hybrid_search: '{query}' → {len(results)} results | area={area_name} | filters={filters}")
        return results



# ── Singleton ─────────────────────────────────────────────────────────────────

_service: Optional[EmbeddingService] = None

def get_embedding_service() -> EmbeddingService:
    """Get or create the shared EmbeddingService instance."""
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
