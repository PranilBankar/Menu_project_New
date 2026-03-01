"""
End-to-end RAG pipeline test.
Run from the backend/ directory with the venv active:
    python test_rag.py
"""
import os, sys
os.environ["GLOG_minloglevel"] = "3"
os.environ["FLAGS_use_mkldnn"]  = "0"
sys.path.insert(0, os.path.dirname(__file__))

# ── CONFIG ────────────────────────────────────────────────────────────────────
RESTAURANT_ID = "11986859-05ac-4e5e-846b-8ccbc7da0323"
AREA_NAME     = "Nagpur"
# ─────────────────────────────────────────────────────────────────────────────

from app.services.nlp.rag_service import RAGService

TEST_QUERIES = [
    ("healthy veg food under 200",           {"is_veg": True,  "max_price": 200}),
    ("spicy chicken biryani",                {"is_veg": False, "section_name": "Biryani"}),
    ("something sweet for dessert",          {"section_name": "Desserts"}),
    ("cold drink below 100 rupees",          {"max_price": 100}),
    ("cheap non-veg curry",                  {"is_veg": False}),
    ("low calorie light food",               {"max_calories": 400}),
]


def run():
    rag = RAGService(top_k=5)
    total, passed = 0, 0

    for query, expected_filters in TEST_QUERIES:
        print("\n" + "=" * 65)
        print(f"  QUERY: \"{query}\"")
        print("=" * 65)

        result = rag.chat(query, area_name=AREA_NAME, restaurant_id=RESTAURANT_ID)

        filters = result["filters_used"]
        items   = result["items"]
        answer  = result["answer"]

        print(f"\n  Filters extracted: {filters}")
        print(f"\n  Items found ({len(items)}):")
        for it in items:
            veg = "🟢" if it.get("is_veg") else "🔴"
            cal = f"{it.get('calories')} kcal" if it.get("calories") else "--"
            hs  = f"♥{it.get('health_score')}/10" if it.get("health_score") else ""
            print(f"    {veg} {it['item_name']:<40} ₹{str(it['price']):<6} {cal:<12} {hs}  sim={it['similarity']:.3f}")

        print(f"\n  LLM Answer:\n  {answer}")

        # ── Basic validation ─────────────────────────────────────────────────
        total += 1
        ok = True
        for key, val in expected_filters.items():
            actual = filters.get(key)
            if val is not None and actual != val:
                # Soft match on price (rule may set a different value)
                if key == "max_price" and actual is not None:
                    pass  # any price filter is acceptable
                else:
                    print(f"\n  [WARN] Expected {key}={val} but got {actual}")
                    ok = False
        if len(items) == 0:
            print("  [WARN] No items returned!")
            ok = False
        if ok:
            passed += 1
            print("  [PASS] ✅")
        else:
            print("  [FAIL] ❌")

    print("\n" + "=" * 65)
    print(f"  Results: {passed}/{total} passed")
    print("=" * 65)


if __name__ == "__main__":
    run()
