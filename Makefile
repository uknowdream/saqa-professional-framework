SHELL := /bin/bash
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

.PHONY: install test test-serial compile target-smoke

install:
	$(PIP) install -e '.[test,ci]'

test:
	$(PYTHON) -m pytest -n auto --dist loadfile --timeout=120 --cov=saqa --cov-report=term-missing

test-serial:
	$(PYTHON) -m pytest --cov=saqa --cov-report=term-missing

compile:
	$(PYTHON) -m compileall -q src tests

target-smoke:
	bash scripts/qa_target_smoke.sh
