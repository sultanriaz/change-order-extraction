"""Evaluation of independent adversarial challenge dataset against frozen ground truth."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from co_extract.llm import GeminiClient, MockLLM
from co_extract.pipeline import Pipeline

try:
    from eval.metrics import align_orders, flatten, summarize, line_item_f1
except ImportError:
    from metrics import align_orders, flatten, summarize, line_item_f1

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
CHALLENGE_DIR = ROOT / "data" / "challenge"


def evaluate_challenge(*, mock: bool = True) -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    manifest_path = CHALLENGE_DIR / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Challenge manifest not found at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    client = MockLLM() if mock else GeminiClient()
    pipeline = Pipeline(client)

    all_rows = []
    all_pairs = []
    by_category = defaultdict(list)
    records = []

    for spec in manifest:
        source_path = ROOT / spec["source"]
        truth_path = ROOT / spec["truth"]
        truth = json.loads(truth_path.read_text(encoding="utf-8"))["orders"]

        result = pipeline.run(source_path)
        pairs = align_orders(result.orders, truth)
        doc_rows = flatten(pairs)

        all_rows.extend(doc_rows)
        all_pairs.extend(pairs)
        by_category[spec["category"]].extend(doc_rows)

        records.append({
            "id": spec["id"],
            "category": spec["category"],
            "tags": spec["tags"],
            "orders_extracted": len(result.orders),
            "orders_expected": len(truth),
            "document_confidence": result.document_confidence,
            "needs_review": result.needs_review,
            "validation_issues": [x.code for x in result.validation_report],
            "warnings": result.warnings,
            "summary": summarize(doc_rows)
        })

    overall_metrics = summarize(all_rows)
    line_f1 = line_item_f1(all_pairs)

    cat_summary = {cat: summarize(rows) for cat, rows in sorted(by_category.items())}

    output = {
        "model": client.model_id,
        "n_cases": len(manifest),
        "overall_metrics": overall_metrics,
        "line_item_f1": line_f1,
        "by_category": cat_summary,
        "records": records
    }

    prefix = "mock_" if mock else "gemini_"
    (RESULTS / f"{prefix}challenge_summary.json").write_text(json.dumps(output, indent=2), encoding="utf-8")

    lines = [
        f"# Adversarial Challenge Evaluation Report: {client.model_id}", "",
        f"**Model ID:** `{client.model_id}`",
        f"**Cases:** {len(manifest)} independently constructed adversarial scenarios with frozen ground truth.", "",
        "## Overall Challenge Metrics", "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Field Precision | {overall_metrics['precision']:.4f} |",
        f"| Field Recall | {overall_metrics['recall']:.4f} |",
        f"| Field F1 | {overall_metrics['f1']:.4f} |",
        f"| Correct Null Rate | {overall_metrics['correct_null_rate'] if overall_metrics['correct_null_rate'] is not None else 'N/A'} |",
        f"| Hallucination Rate | {overall_metrics['hallucination_rate'] if overall_metrics['hallucination_rate'] is not None else 'N/A'} |",
        f"| Line Item Matched F1 | {line_f1:.4f} |", "",
        "## Breakdown by Adversarial Category", "",
        "| Category | Rows | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|"
    ]
    for cat, data in cat_summary.items():
        lines.append(f"| {cat} | {data['n_rows']} | {data['precision']:.4f} | {data['recall']:.4f} | {data['f1']:.4f} |")

    lines += [
        "", "## Case-by-Case Analysis", "",
        "| Case ID | Category | Extracted/Expected | Confidence | Needs Review | Key Flags |",
        "|---|---|:---:|---:|:---:|---|"
    ]
    for rec in records:
        issues_str = ", ".join(rec["validation_issues"][:2] + rec["warnings"][:2]) or "none"
        lines.append(f"| `{rec['id']}` | {rec['category']} | {rec['orders_extracted']}/{rec['orders_expected']} | {rec['document_confidence']:.2f} | {rec['needs_review']} | {issues_str} |")

    (RESULTS / f"{prefix}challenge_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    is_live = "--live" in sys.argv
    print(json.dumps(evaluate_challenge(mock=not is_live), indent=2))
