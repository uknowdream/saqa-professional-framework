SHELL := /bin/bash
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

.PHONY: install test test-serial compile target-smoke contract-test k6-test

install:
	$(PIP) install -e '.[test,ci,contract]'

test:
	$(PYTHON) -m pytest -n auto --dist loadfile --timeout=120 --cov=saqa --cov-report=term-missing

test-serial:
	$(PYTHON) -m pytest --cov=saqa --cov-report=term-missing

compile:
	$(PYTHON) -m compileall -q src tests

target-smoke:
	bash scripts/qa_target_smoke.sh

contract-test:
	$(PYTHON) scripts/contract_gate.py

k6-test:
	$(PYTHON) scripts/k6_gate.py
