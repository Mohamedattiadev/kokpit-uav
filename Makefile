.PHONY: help install test demo sitl lint clean

help:
	@echo "Kokpit UAV — make targets"
	@echo "  install      pip install -r requirements.txt"
	@echo "  test         pytest (all unit tests)"
	@echo "  demo         software demo (no hardware, no ArduPilot)"
	@echo "  sitl         ArduCopter SITL end-to-end mission"
	@echo "  lint         ruff check"
	@echo "  clean        remove caches"

install:
	pip install -r requirements.txt

test:
	KOKPIT_SIM=1 pytest tests/ -q

demo:
	KOKPIT_SIM=1 python3 simulation/software_demo.py

sitl:
	bash simulation/run_sitl.sh

lint:
	ruff check onboard/ simulation/ tests/ tools/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache build dist
