# Self-review and Definition of Done (2026-10-23)

| Requirement | Result | Verification / gap |
|---|---|---|
| Pydantic v2 internal and model-facing schemas | ✅ Implemented | `docs/schema.json`, `tests/test_schema.py` |
| 120 seeded labeled train/dev/test fixtures and 10 manually authored rough samples | ✅ Implemented | Manifest shows 60/20/40; text samples are **not real handwriting scans** |
| PDFs, TXT/MD, PNG/JPG, PDF tables, OCR fallback | ✅ Implemented | Tesseract path verified on scanned synthetic PDF; no comprehensive malformed-document fuzzing |
| Gemini integration with Google SDK, Pydantic, fallback and typed errors | ⚠️ Implemented, **live unverified** | `google-genai` unavailable here, no API key; schema subset must be verified with `make smoke` |
| Bounded retries, token bucket, concurrency 2, disk cache and usage accounting | ✅ Implemented in code | Mock verifies integration; provider behavior not tested |
| Multiple orders, page overlap, conflict flags, self-consistency option | ✅ Implemented in code | Offline two-order test; self-consistency with mock is not independent evidence |
| Normalization, cross-field validation, no auto-correction | ✅ Passed | Parametrized tests incl locales, dates, currency, sign, line items |
| Computed provenance and DEV-fitted confidence | ✅ Offline verified | TEST ECE 0.1604. DEV threshold 1.01 accepts none; no safe autoaccept inferred |
| TEST F1/null/line-item metrics, per-case slices, baseline and reliability plot | ✅ Offline executed | `eval/results/` documents 40 TEST samples; same heuristic used as baseline/mock |
| Ablations: grounding, repair, temperature, vision/OCR | ⚠️ Offline 8-document variants executed; live pending | Mock effects are not evidence about Gemini accuracy; no credentials/provider SDK |
| Input injection detection, PII log redaction and failure isolation | ✅ Mock tested | Security heuristic, not a proof of comprehensive defense |
| CLI, Makefile, Dockerfile and CI | ✅ Added; partially verified | CLI tested, Docker image and GitHub CI not run; `ruff`/`mypy` unavailable locally |
| ≥85% coverage on normalize, validate, confidence | ✅ Passed | `make test`: 97%, 98%, 99%, respectively |
| Clean clone `make setup && make data && make test` | ⚠️ Partially verified | `make data` and `make test` passed; dependency install from PyPI failed due no network |
| `make smoke` ONE real validated Gemini call | ❌ Pending credentials/provider SDK | `GEMINI_API_KEY` absent; clearly fails rather than claiming success |
| `python -m co_extract extract examples/sample.pdf` works | ✅ Offline fallback verified | Explicit MockLLM warning without API key; live path untested |
| `make eval` regenerates report/plot and baseline | ✅ Verified offline | Real Gemini eval requires `make eval-live` with API key |
| Short writeup with observed failures | ✅ Complete | `WRITEUP.md`, observed IDs from `raw.json`; unobserved provider risks clearly labeled |
| Conventional commits, no secrets | ✅ Local commits | `.env` excluded; Git state and history included in ZIP |

**Release verdict:** **Candidate take-home repo with an explicit live-model verification blocker.** It is not an industry-certified extraction system and must not be marketed as such.
