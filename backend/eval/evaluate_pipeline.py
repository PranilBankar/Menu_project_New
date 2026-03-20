"""
Pipeline Evaluation Script
===========================
Evaluates the full OCR → Layout Parser → LLM Enrichment pipeline
by comparing the extracted items against a ground truth JSON file.

Usage:
    cd backend
    python eval/evaluate_pipeline.py --image dataset/Menu1.jpeg --ground-truth eval/ground_truth_menu1.json

Ground-truth JSON format:
{
  "image_file": "dataset/Menu1.jpeg",
  "restaurant_name": "My Restaurant",
  "items": [
    { "item_name": "Chicken Biryani", "price": 320, "section_name": "Biryani", "is_veg": false },
    ...
  ]
}

Metrics produced:
  - Item Detection: Precision, Recall, F1 (fuzzy name matching)
  - Price Accuracy: MAE, exact-match %
  - Section Accuracy: % correctly classified
  - Veg/Non-Veg Accuracy: % correctly classified
  - Charts saved to eval/results/
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

# Add backend root to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Pipeline imports ─────────────────────────────────────────────────────────
from app.services.ocr.ocr_engine import get_ocr_engine
from app.services.ocr.menu_layout_parser import parse_menu
from app.services.nlp.menu_structurer import get_menu_structurer


# ── Fuzzy matching ───────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    import re
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return " ".join(name.split())


def _similarity(a: str, b: str) -> float:
    """Token-overlap Jaccard similarity between two names."""
    sa = set(_normalize(a).split())
    sb = set(_normalize(b).split())
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _best_match(pred_name: str, gt_items: List[Dict], threshold: float = 0.40
                ) -> Tuple[int, float]:
    """
    Returns (index_in_gt, similarity_score) for the best fuzzy match.
    Returns (-1, 0.0) if no match above threshold.
    """
    best_idx, best_sim = -1, 0.0
    for i, gt in enumerate(gt_items):
        sim = _similarity(pred_name, gt["item_name"])
        if sim > best_sim:
            best_idx, best_sim = i, sim
    return (best_idx, best_sim) if best_sim >= threshold else (-1, 0.0)


# ── Pipeline runner ──────────────────────────────────────────────────────────

def run_pipeline(image_path: str, restaurant_name: str = "") -> List[Dict]:
    """Run OCR → Layout Parser → LLM Enrichment and return enriched items."""
    import cv2

    print(f"\n{'='*60}")
    print(f"  Running pipeline on: {image_path}")
    print(f"{'='*60}")

    # Step 1: OCR
    print("\n[1/3] Running PaddleOCR ...")
    ocr_engine = get_ocr_engine()
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    raw_ocr = ocr_engine.ocr.ocr(img)
    n_tokens = len(raw_ocr[0]) if raw_ocr and raw_ocr[0] else 0
    print(f"       → {n_tokens} OCR tokens detected")

    # Step 2: Layout Parser
    print("[2/3] Running Layout Parser ...")
    parsed = parse_menu(raw_ocr)
    print(f"       → {len(parsed)} (item, price) pairs extracted")
    for p in parsed[:5]:
        print(f"         • {p['item']:40s} ₹{p['price']}")
    if len(parsed) > 5:
        print(f"         ... and {len(parsed)-5} more")

    # Step 3: LLM Enrichment
    print("[3/3] Running LLM Enrichment ...")
    structurer = get_menu_structurer()
    enriched = structurer.enrich(parsed_items=parsed, restaurant_name=restaurant_name)
    print(f"       → {len(enriched)} enriched items")

    return enriched


# ── Evaluation ───────────────────────────────────────────────────────────────

def evaluate(predicted: List[Dict], ground_truth: List[Dict]) -> Dict:
    """
    Compare predicted items against ground truth.
    Returns a dict of metrics.
    """
    gt_remaining = list(range(len(ground_truth)))  # indices not yet matched
    matches = []  # (pred_idx, gt_idx, similarity)
    unmatched_pred = []

    # Match each predicted item to best GT item
    for pi, pred in enumerate(predicted):
        pred_name = pred.get("item_name", pred.get("item", ""))
        gt_subset = [ground_truth[i] for i in gt_remaining]

        if not gt_subset:
            unmatched_pred.append(pi)
            continue

        best_local_idx, sim = _best_match(pred_name, gt_subset)
        if best_local_idx >= 0:
            gt_idx = gt_remaining[best_local_idx]
            matches.append((pi, gt_idx, sim))
            gt_remaining.remove(gt_idx)
        else:
            unmatched_pred.append(pi)

    # ── Detection metrics ────────────────────────────────────────────────
    tp = len(matches)
    fp = len(unmatched_pred)
    fn = len(gt_remaining)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # ── Per-match accuracy ───────────────────────────────────────────────
    name_similarities = []
    price_errors = []
    price_exact = 0
    section_correct = 0
    veg_correct = 0

    match_details = []

    for pi, gi, sim in matches:
        pred = predicted[pi]
        gt = ground_truth[gi]

        pred_name = pred.get("item_name", pred.get("item", ""))
        gt_name = gt["item_name"]
        name_similarities.append(sim)

        # Price
        pred_price = pred.get("price", 0) or 0
        gt_price = gt.get("price", 0) or 0
        try:
            pred_price = float(pred_price)
            gt_price = float(gt_price)
        except (TypeError, ValueError):
            pred_price, gt_price = 0, 0

        err = abs(pred_price - gt_price)
        price_errors.append(err)
        if err < 1:
            price_exact += 1

        # Section
        pred_sec = _normalize(pred.get("section_name", ""))
        gt_sec = _normalize(gt.get("section_name", ""))
        if pred_sec == gt_sec or _similarity(pred.get("section_name", ""), gt.get("section_name", "")) > 0.5:
            section_correct += 1

        # Veg
        pred_veg = pred.get("is_veg", True)
        gt_veg = gt.get("is_veg", True)
        if pred_veg == gt_veg:
            veg_correct += 1

        match_details.append({
            "pred_name": pred_name,
            "gt_name": gt_name,
            "name_sim": round(sim, 3),
            "pred_price": pred_price,
            "gt_price": gt_price,
            "price_error": round(err, 2),
            "section_match": pred_sec == gt_sec or _similarity(pred.get("section_name", ""), gt.get("section_name", "")) > 0.5,
            "veg_match": pred_veg == gt_veg,
        })

    n_matches = len(matches) or 1  # avoid division by zero

    metrics = {
        "detection": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
        },
        "name_similarity": {
            "mean": round(sum(name_similarities) / n_matches, 4) if name_similarities else 0,
            "min": round(min(name_similarities), 4) if name_similarities else 0,
            "max": round(max(name_similarities), 4) if name_similarities else 0,
        },
        "price_accuracy": {
            "mean_absolute_error": round(sum(price_errors) / n_matches, 2) if price_errors else 0,
            "exact_match_pct": round(price_exact / n_matches * 100, 1),
        },
        "section_accuracy_pct": round(section_correct / n_matches * 100, 1),
        "veg_accuracy_pct": round(veg_correct / n_matches * 100, 1),
        "counts": {
            "ground_truth_items": len(ground_truth),
            "predicted_items": len(predicted),
            "matched": tp,
        },
        "match_details": match_details,
        "unmatched_predictions": [
            predicted[i].get("item_name", predicted[i].get("item", "?")) for i in unmatched_pred
        ],
        "missed_ground_truth": [
            ground_truth[i]["item_name"] for i in gt_remaining
        ],
    }
    return metrics


# ── Plotting ─────────────────────────────────────────────────────────────────

def plot_results(metrics: Dict, output_dir: str):
    """Generate evaluation charts and save to output_dir."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  ⚠ matplotlib not installed — skipping charts. Run: pip install matplotlib")
        return

    os.makedirs(output_dir, exist_ok=True)

    # ── Chart 1: Detection Metrics Bar Chart ─────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Pipeline Evaluation Results", fontsize=14, fontweight="bold")

    det = metrics["detection"]
    bars = ["Precision", "Recall", "F1 Score"]
    vals = [det["precision"], det["recall"], det["f1_score"]]
    colors = ["#2196F3", "#4CAF50", "#FF9800"]
    axes[0].bar(bars, vals, color=colors, edgecolor="white", linewidth=1.5)
    axes[0].set_ylim(0, 1.1)
    axes[0].set_title("Item Detection")
    for i, v in enumerate(vals):
        axes[0].text(i, v + 0.03, f"{v:.2f}", ha="center", fontweight="bold")

    # ── Chart 2: Accuracy Breakdown ──────────────────────────────────────
    acc_labels = ["Price\nExact Match", "Section\nAccuracy", "Veg/Non-Veg\nAccuracy"]
    acc_vals = [
        metrics["price_accuracy"]["exact_match_pct"],
        metrics["section_accuracy_pct"],
        metrics["veg_accuracy_pct"],
    ]
    acc_colors = ["#9C27B0", "#00BCD4", "#8BC34A"]
    axes[1].bar(acc_labels, acc_vals, color=acc_colors, edgecolor="white", linewidth=1.5)
    axes[1].set_ylim(0, 110)
    axes[1].set_ylabel("Accuracy (%)")
    axes[1].set_title("Field-Level Accuracy")
    for i, v in enumerate(acc_vals):
        axes[1].text(i, v + 2, f"{v:.1f}%", ha="center", fontweight="bold")

    # ── Chart 3: Item Counts ─────────────────────────────────────────────
    cnt = metrics["counts"]
    count_labels = ["Ground\nTruth", "Predicted", "Matched"]
    count_vals = [cnt["ground_truth_items"], cnt["predicted_items"], cnt["matched"]]
    count_colors = ["#607D8B", "#FF5722", "#4CAF50"]
    axes[2].bar(count_labels, count_vals, color=count_colors, edgecolor="white", linewidth=1.5)
    axes[2].set_title("Item Counts")
    for i, v in enumerate(count_vals):
        axes[2].text(i, v + 0.5, str(v), ha="center", fontweight="bold")

    plt.tight_layout()
    chart_path = os.path.join(output_dir, "evaluation_summary.png")
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  📊 Chart saved: {chart_path}")

    # ── Chart 4: Per-Item Name Similarity ────────────────────────────────
    details = metrics.get("match_details", [])
    if details:
        fig2, ax2 = plt.subplots(figsize=(max(10, len(details) * 0.5), 6))
        names = [d["gt_name"][:25] for d in details]
        sims = [d["name_sim"] for d in details]
        bar_colors = ["#4CAF50" if s >= 0.6 else "#FF9800" if s >= 0.4 else "#F44336" for s in sims]
        ax2.barh(range(len(names)), sims, color=bar_colors, edgecolor="white")
        ax2.set_yticks(range(len(names)))
        ax2.set_yticklabels(names, fontsize=8)
        ax2.set_xlabel("Name Similarity (Jaccard)")
        ax2.set_title("Per-Item Name Match Quality")
        ax2.set_xlim(0, 1.1)
        ax2.axvline(x=0.4, color="red", linestyle="--", alpha=0.5, label="Match threshold")
        ax2.legend()
        ax2.invert_yaxis()
        plt.tight_layout()
        detail_path = os.path.join(output_dir, "per_item_similarity.png")
        plt.savefig(detail_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  📊 Chart saved: {detail_path}")


# ── Pretty print ─────────────────────────────────────────────────────────────

def print_report(metrics: Dict):
    """Print a formatted evaluation report to console."""
    det = metrics["detection"]
    print(f"\n{'='*60}")
    print(f"  PIPELINE EVALUATION REPORT")
    print(f"{'='*60}")

    print(f"\n  📦 Item Detection")
    print(f"     Ground truth items : {metrics['counts']['ground_truth_items']}")
    print(f"     Predicted items    : {metrics['counts']['predicted_items']}")
    print(f"     True positives     : {det['true_positives']}")
    print(f"     False positives    : {det['false_positives']}  (predicted but not in GT)")
    print(f"     False negatives    : {det['false_negatives']}  (in GT but not predicted)")
    print(f"     ─────────────────────")
    print(f"     Precision          : {det['precision']:.2%}")
    print(f"     Recall             : {det['recall']:.2%}")
    print(f"     F1 Score           : {det['f1_score']:.2%}")

    print(f"\n  📝 Name Similarity (Jaccard)")
    ns = metrics["name_similarity"]
    print(f"     Mean               : {ns['mean']:.2%}")
    print(f"     Min                : {ns['min']:.2%}")
    print(f"     Max                : {ns['max']:.2%}")

    print(f"\n  💰 Price Accuracy")
    pa = metrics["price_accuracy"]
    print(f"     Mean Abs Error     : ₹{pa['mean_absolute_error']:.2f}")
    print(f"     Exact Match        : {pa['exact_match_pct']:.1f}%")

    print(f"\n  📂 Section Accuracy  : {metrics['section_accuracy_pct']:.1f}%")
    print(f"  🥬 Veg/Non-Veg Acc   : {metrics['veg_accuracy_pct']:.1f}%")

    # Missed items
    if metrics["missed_ground_truth"]:
        print(f"\n  ❌ Missed Items (in GT, not detected):")
        for name in metrics["missed_ground_truth"]:
            print(f"     • {name}")

    # False positives
    if metrics["unmatched_predictions"]:
        print(f"\n  ⚠️  Extra Predictions (not in GT):")
        for name in metrics["unmatched_predictions"][:10]:
            print(f"     • {name}")

    print(f"\n{'='*60}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate the menu extraction pipeline")
    parser.add_argument("--image", required=True, help="Path to menu image")
    parser.add_argument("--ground-truth", required=True, help="Path to ground truth JSON")
    parser.add_argument("--output-dir", default="eval/results", help="Directory for charts")
    args = parser.parse_args()

    # Load ground truth
    with open(args.ground_truth, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    gt_items = gt_data["items"]
    restaurant_name = gt_data.get("restaurant_name", "")

    # Run pipeline
    predicted = run_pipeline(args.image, restaurant_name)

    # Evaluate
    metrics = evaluate(predicted, gt_items)

    # Print report
    print_report(metrics)

    # Save metrics JSON
    os.makedirs(args.output_dir, exist_ok=True)
    metrics_path = os.path.join(args.output_dir, "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print(f"  📄 Metrics saved: {metrics_path}")

    # Generate charts
    plot_results(metrics, args.output_dir)

    print(f"\n  ✅ Evaluation complete!\n")


if __name__ == "__main__":
    main()
