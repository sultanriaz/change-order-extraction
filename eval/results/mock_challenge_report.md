# Adversarial Challenge Evaluation Report: mock-regex-v1

**Model ID:** `mock-regex-v1`
**Cases:** 26 independently constructed adversarial scenarios with frozen ground truth.

## Overall Challenge Metrics

| Metric | Value |
|---|---:|
| Field Precision | 0.9053 |
| Field Recall | 0.7011 |
| Field F1 | 0.7902 |
| Correct Null Rate | 0.9455252918287937 |
| Hallucination Rate | 0.054474708171206226 |
| Line Item Matched F1 | 0.4286 |

## Breakdown by Adversarial Category

| Category | Rows | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Ambiguous Dates | 25 | 0.2222 | 0.0870 | 0.1250 |
| Complex PDF | 25 | 0.6923 | 0.4286 | 0.5294 |
| Distractors | 25 | 1.0000 | 0.8182 | 0.9000 |
| Empty Input | 0 | 0.0000 | 0.0000 | 0.0000 |
| Large Item Count | 25 | 0.0000 | 0.0000 | 0.0000 |
| Math Mismatch | 50 | 0.9200 | 0.8846 | 0.9020 |
| Multi-Currency | 25 | 0.8667 | 0.8667 | 0.8667 |
| Multi-Order | 50 | 0.7500 | 0.6429 | 0.6923 |
| Multi-page | 25 | 1.0000 | 0.5238 | 0.6875 |
| Negative & Credits | 25 | 0.9444 | 0.8947 | 0.9189 |
| Non-CO Document | 0 | 0.0000 | 0.0000 | 0.0000 |
| OCR Digits | 25 | 1.0000 | 0.8824 | 0.9375 |
| OCR Noise | 25 | 0.8000 | 0.5714 | 0.6667 |
| Parenthesized Numbers | 25 | 0.8824 | 0.8824 | 0.8824 |
| Party Roles | 25 | 1.0000 | 0.5455 | 0.7059 |
| Revisions | 25 | 1.0000 | 0.8333 | 0.9091 |
| Schedule Only | 25 | 1.0000 | 0.8824 | 0.9375 |
| Security Adversarial | 25 | 1.0000 | 0.8667 | 0.9286 |
| Sparse Incomplete | 25 | 1.0000 | 1.0000 | 1.0000 |
| Standard Clean | 25 | 1.0000 | 0.9130 | 0.9545 |
| Status Variations | 25 | 1.0000 | 0.8462 | 0.9167 |
| Unpriced TBD | 25 | 1.0000 | 0.8333 | 0.9091 |
| Unstructured Email | 25 | 0.8000 | 0.2500 | 0.3810 |
| Void / Conflicting Approval | 25 | 1.0000 | 0.8333 | 0.9091 |
| Zero Cost | 25 | 1.0000 | 0.8889 | 0.9412 |

## Case-by-Case Analysis

| Case ID | Category | Extracted/Expected | Confidence | Needs Review | Key Flags |
|---|---|:---:|---:|:---:|---|
| `case_01_clean_single_page` | Standard Clean | 1/1 | 0.93 | False | none |
| `case_02_complex_table` | Complex PDF | 1/1 | 0.00 | True | invalid_enum |
| `case_03_multipage_continued` | Multi-page | 1/1 | 0.00 | True | none |
| `case_04_multiple_cos` | Multi-Order | 2/2 | 0.00 | True | none |
| `case_05_scanned_ocr` | OCR Noise | 1/1 | 0.00 | True | none |
| `case_06_ocr_punct` | OCR Digits | 1/1 | 0.93 | False | none |
| `case_07_negative_credit` | Negative & Credits | 1/1 | 0.93 | False | none |
| `case_08_parenthesized_currency` | Parenthesized Numbers | 1/1 | 0.93 | False | none |
| `case_09_multiple_currencies` | Multi-Currency | 1/1 | 0.93 | False | none |
| `case_10_ambiguous_date` | Ambiguous Dates | 1/1 | 0.73 | True | ambiguous_date |
| `case_11_missing_fields` | Sparse Incomplete | 1/1 | 0.00 | True | none |
| `case_12_tbd_amount` | Unpriced TBD | 1/1 | 0.00 | True | unpriced_total_requires_review |
| `case_13_conflicting_totals` | Math Mismatch | 1/1 | 0.73 | True | arithmetic_mismatch |
| `case_14_bad_line_math` | Math Mismatch | 1/1 | 0.00 | True | line_item_mismatch |
| `case_15_revision_b` | Revisions | 1/1 | 0.93 | False | none |
| `case_16_rejected_status` | Status Variations | 1/1 | 0.93 | False | none |
| `case_17_prompt_injection` | Security Adversarial | 1/1 | 0.93 | True | possible_prompt_injection |
| `case_18_misleading_parties` | Party Roles | 1/1 | 0.00 | True | none |
| `case_19_distractor_numbers` | Distractors | 1/1 | 0.93 | False | none |
| `case_20_unrelated_doc` | Non-CO Document | 0/0 | 0.00 | True | pipeline_error:ModelError |
| `case_21_empty_input` | Empty Input | 0/0 | 0.00 | True | pipeline_error:EmptyDocument |
| `case_22_zero_cost` | Zero Cost | 1/1 | 0.93 | False | none |
| `case_23_schedule_only` | Schedule Only | 1/1 | 0.93 | False | none |
| `case_24_many_items` | Large Item Count | 1/1 | 0.00 | True | none |
| `case_25_void_status` | Void / Conflicting Approval | 1/1 | 0.93 | False | none |
| `case_26_email_thread` | Unstructured Email | 1/1 | 0.00 | True | invalid_enum |
