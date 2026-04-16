# Menu Upload Pipeline Optimization & OCR Improvement

This plan addresses the two major goals: minimizing the waiting time for the restaurant owner when they upload a menu, and improving the accuracy of how the system groups item names with their prices.

## User Review Required

> [!IMPORTANT]  
> Please review the optimizations below. The biggest change is that we will return a "Success" response to the frontend **before** the semantic embeddings are fully generated. The items will instantly appear in the dashboard, but the AI Search might take an extra 5 seconds in the background to index them. Let me know if this is acceptable!

---

## 1. Pipeline Speed Improvements (Latency Reduction)

Currently, the upload pipeline is completely synchronous. It waits for OCR -> Layout -> LLM (Synchronous network calls) -> DB Insert -> CPU AI Embeddings -> then finally responds. We can cut this time by **60-80%** using the following strategies:

### Proposed Changes

#### [MODIFY] `app/services/nlp/menu_structurer.py`
- **Parallel LLM Enrichment**: Right now, if a menu has 100 items, we chop it into 4 batches of 25 and send them to the Groq/OpenAI one by one. We will implement `asyncio.gather` so all 4 batches are processed concurrently. This will cut the LLM structurer time from ~6 seconds down to ~1.5 seconds.
- Switch the Groq client from synchronous to `AsyncGroq`.

#### [MODIFY] `app/api/v1/endpoints/admin.py`
- **Background Task for Embeddings**: Generating embeddings on the CPU (`sentence-transformers/all-MiniLM-L6-v2`) takes about 2-4 seconds for a large menu. 
- We will import `BackgroundTasks` from FastAPI. Once the DB inserts the items, we will return the `200 OK` JSON response immediately to the frontend.
- We will queue the `embedding_service.embed_and_store` function to run silently in the background.

---

## 2. Improving OCR Menu Extraction 

Currently, `menu_layout_parser.py` works well for simple lists, but struggles with **multi-line descriptions** or when prices are grouped weirdly.

### Proposed Changes

#### [MODIFY] `app/services/ocr/menu_layout_parser.py`
- **Multi-line Orphan Merging**: If an item name spans two lines (e.g. Line 1: `Paneer Butter`, Line 2: `Masala`), the current system might treat the second line as an orphan if it has no price. We will refine `ORPHAN_Y_TOLERANCE` and logic to merge floating text directly beneath a valid item into its description/name buffer.
- **Dynamic Price Gap Thresholding**: Currently `PRICE_GAP` is hardcoded to `20px`. The space between columns on different images can vary. I will add logic to estimate the average gap width dynamically based on the image's overall structure, preventing cross-column merging.
- **Dot Leader Filtering**: Enhance the `_clean_name` regex to aggressively scrub out menus that use heavy dot leaders (`Pizza ..................... $5`), preventing OCR noise.

---

## Verification Plan

### Automated Tests
- Upload a complex, multi-column Indian menu.
- Verify the total processing time drops significantly.
- Verify that `menu_embeddings` table continues to populate correctly after the HTTP request is closed.

### Manual Verification
- You will upload a menu from your dashboard and visually confirm how fast it responds compared to the previous version, and verify that item prices match perfectly.
