.PHONY: setup data test eval eval-live smoke schema lint typecheck ci clean
PYTHON ?= python
setup:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e . --no-deps
data:
	PYTHONPATH=src:. $(PYTHON) scripts/generate_synthetic.py
schema:
	PYTHONPATH=src:. $(PYTHON) -m co_extract schema
lint:
	$(PYTHON) -m ruff check src tests eval scripts
typecheck:
	$(PYTHON) -m mypy src/co_extract --follow-imports=silent
TEST_ARGS ?=
test:
	PYTHONPATH=src:. $(PYTHON) -m pytest -q --cov=co_extract.normalize --cov=co_extract.validate --cov=co_extract.confidence --cov-report=term-missing $(TEST_ARGS)
eval:
	PYTHONPATH=src:. $(PYTHON) -m eval.run_eval
eval-live:
	PYTHONPATH=src:. $(PYTHON) -m co_extract eval --live
smoke:
	PYTHONPATH=src:. $(PYTHON) -m co_extract smoke
ci: lint typecheck test
clean:
	rm -rf .cache out .coverage .pytest_cache .mypy_cache .ruff_cache
