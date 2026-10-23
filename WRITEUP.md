# Change-order extraction — approach, evaluation and failure modes

**Assumptions.** An order is a document-stated proposal/authorization, not verified contractual truth. Every field is optional; missing values remain null. ISO dates are normalized only when unambiguous. Prices are amounts **as printed**, with separate arithmetic warnings. Synthetic documents are invented, not samples of actual AIA project data. A source can contain multiple COs, and a superseding revision must not be silently merged with a distinct CO number.

## Design and trade-offs

The pipeline combines PyMuPDF/pdfplumber text/table reading, optional Tesseract OCR for pages lacking text, 4-page overlapped windows, Google Gemini via `google-genai` (or a **non-LLM regex mock**), Pydantic v2 validation, merging by CO identifier, and field-by-field provenance checking. The [README](README.md#architecture) contains a flow diagram. The small Gemini-facing `LLMOutput` uses concrete wrappers to avoid generic schema complexity; the richer internal `DocumentResult` stores raw and normalized values separately, source quotes/pages, computed confidence and flags. Google supports a schema subset, so **Gemini-facing schema compatibility must be verified with a live smoke**. Provider JSON is Pydantic-revalidated; invalid results trigger a bounded feedback/JSON fallback. Input text is treated as untrusted data. No unverified number is automatically repaired.

**Confidence:** Inputs are page-quote fuzzy grounding, deterministic validation, cross-sample agreement (optional, temperature 0.5), text/OCR quality, and low-weight model self-rating. Logistic weights are fitted on the **20 DEV** fixtures only; a selective-review threshold is chosen on DEV for ≥95% observed critical-field correctness if attainable. Missing critical fields, contradictions, unsupported citations, and suspect instructions force review. Model IDs are bound to calibration parameters. These scores are **not calibrated clinical, legal or financial probabilities**.

## Measured results, 2026-10-23

All numbers below are from the seeded **40 held-out synthetic TEST documents**, with the rule-based `mock-regex-v1` (prompt `co-extract-2026-10-v1`). The **60 train** fixtures were not used to fit the logistic model; the **20 DEV** fixtures alone were used for calibration/threshold. This run has **no live Gemini requests**. Matching: exact IDs/enums, dates normalized, money within 0.02, free text ≥90 RapidFuzz; wrong non-null predictions count as both FP and FN. No LLM judge.

| Measure | Mock pipeline | Regex baseline |
|---|---:|---:|
| Field precision | 0.9971 | 0.9971 |
| Field recall | 0.9932 | 0.9932 |
| Field F1 | 0.9952 | 0.9952 |
| Correct-null rate | 1.0000 | 1.0000 |
| Hallucination rate (predicted non-null/truth null) | 0.0000 | 0.0000 |
| Matched line-item F1 | 0.9783 | 0.9783 |

Field-level ECE (10 bins, only predicted non-null): **0.1604**; see `eval/results/reliability.png`. DEV found no safe autoaccept threshold (chosen **1.01**, intentionally unreachable), so **40/40** TEST files require review. Pipeline latency p50/p95 **22.5/833 ms**; reported mock API usage/cost **0**. The mock and regex baseline are the **same heuristic**, so no LLM improvement or ablation gain can be inferred. Synthetic documents share the same generator skeleton; the nearly perfect F1 is not evidence of real-document readiness. Detailed sample IDs, slices and wrong fields: `eval/results/raw.json` and `report.md`.

## Failure-mode audit: observed evidence, mitigation and remaining risk

| Failure mode and TEST example | Mitigation | Residual risk |
|---|---|---|
| **OCR distortion:** `syn-088` scanned project number `P~2088` vs `P-2088`; `syn-116` misread contract number | OCR prior + grounding/review | Quote can faithfully match **wrong OCR text**; need image-grounded verification |
| **Multi-page/split line items:** `syn-087` split-page OCR-typo subtotal omitted; multi-page documents otherwise score strongly on templates | Window overlap + line-item dedup + page lookup | Cross-page header/value association may fail on unfamiliar layouts |
| **Two COs / revisions:** `syn-097` contains two distinct orders, non-summing case; separate superseding examples in tagged split | CO-ID separation, conflict flags | Unnumbered revisions may merge or split incorrectly |
| **Non-summing finances:** `syn-084`, `syn-097`, `syn-110` report a subtotal inconsistent with line items | `arithmetic_mismatch` errors; preserve printed values | Some accounting conventions require human context (tax, allowances) |
| **TBD, lump sum, T&M:** `syn-081` is tagged `tbd`; unknown amount stays null | Abstain, preserve original evidence if present | Unpriced T&M schedules may encode indirect amounts elsewhere |
| **Ambiguous dates:** `syn-082`, `syn-095`, `syn-108` (10/11/2026) | `normalized_value=null` and `ambiguous_date` issue | No contractual date locale inferred |
| **European money / multi-currency:** `syn-109` is EUR/OCR; project ID distorted while money normalizes | Conservative number parsing + ISO 4217 | Mixed-currency arithmetic must never add unlike units |
| **Absent-field hallucinations:** `syn-086` missing fields in generated sample family | Null defaults + evidence requirement + null-rate metric | Gemini could supply plausible text unsupported by document |
| **Instruction injection:** `syn-089`, `syn-102`, `syn-115` say to set total to 0; offline mock retains printed total | Treat as untrusted; heuristic detection + review | No general proof against model instruction following; live adversarial tests pending |
| **PII:** `syn-116` contains fake contact details | No raw document logging; email/phone redact helpers | Cache/output still contain evidence snippets and need access controls |
| **Confidently wrong model:** `syn-088` project number is wrong while evidence matches OCR | Source quality prior, strict acceptance gate | Dev logistic calibration overfits very small templated data |
| **Prompt schema limits / blocked output:** No live observation; cannot cite a failure ID | Pydantic revalidation, retry/fallback, typed review result | SDK schema rejection and safety blocks remain **untested** without key |
| **Provider model/version drift:** No live observation | Model+prompt version and cache key; model-ID rejection surfaced | New model can alter result semantics or structure |
| **Synthetic-to-real shift / handwriting:** No real document or handwritten scan was measured | Expose distribution caveat, 10 rough hand-authored memo text samples | Real AIA scans, handwriting and complex tables may fail substantially |

**Ablations:** In offline mode, the mock ignores temperature and PDF vision bytes and already returns schema-valid JSON. The variants were run on the same first 8 held-out TEST documents, but provide no independent **Gemini-specific** effect estimate: raw-field F1 was unchanged, as expected. Live provider ablations remain pending. Disabling grounding changes confidence/review, not extracted raw fields. For actual model comparisons, freeze the exact DEV calibrator, change one setting, run each variant on TEST and record token/latency differences. Do not interpret mock’s coincident agreement at temperature 0.5 as independent evidence.

## Provider and next steps

As of 2026-10-23 the configured current Flash default is `gemini-3.8-flash` (check Google AI Studio and [Google's model docs](https://ai.google.dev/gemini-api/docs/models)); exact account availability is unverified. API keys are environment-only. Default token-bucket limit is 20 RPM and concurrency 2; these are **local controls**, not claimed provider quotas. Cost table is an adjustable assumption and must be replaced with a tier-specific quote. Free-tier usage may contribute to model improvement; use synthetic documents only (see [Google pricing/privacy table](https://ai.google.dev/gemini-api/docs/pricing)).

Next: (1) run the smoke on a credentials-provisioned workstation; (2) pin/verify SDK and schema compatibility, execute all live ablations; (3) obtain permissioned, independently labeled real change orders; (4) create evidence-highlighting review UI and collect human corrections for active learning; (5) add layout-aware vision for scans, per-field reliability thresholds, provider/model drift monitors, dataset provenance and strict data retention policy. Do not enable financial auto-accept before independent validation.
