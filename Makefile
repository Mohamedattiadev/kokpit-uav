.PHONY: help install test demo sitl lint clean print-card

help:
	@echo "Kokpit UAV — make targets"
	@echo "  install      pip install -r requirements.txt"
	@echo "  test         pytest (all unit tests)"
	@echo "  demo         software demo (no hardware, no ArduPilot)"
	@echo "  sitl         ArduCopter SITL end-to-end mission"
	@echo "  lint         ruff check"
	@echo "  print-card   docs/SAHA_KART.md -> PDF (pandoc varsa)"
	@echo "  clean        remove caches"

print-card:
	@if command -v pandoc >/dev/null 2>&1; then \
	  pandoc docs/SAHA_KART.md -o docs/SAHA_KART.pdf -V geometry:margin=1cm; \
	  echo "OK: docs/SAHA_KART.pdf"; \
	else \
	  echo "pandoc yok — md görüntüle: cat docs/SAHA_KART.md"; \
	fi

# N1 — ardupilot/kokpit_baseline.param değişirse hash'i güncelle.
.PHONY: refresh-param-hash
refresh-param-hash:
	@H=$$(sha256sum ardupilot/kokpit_baseline.param | awk '{print $$1}'); \
	echo "Yeni hash: $$H"; \
	python3 -c "import re,sys; \
p='tools/preflight_check.py'; s=open(p).read(); \
s=re.sub(r'\"[a-f0-9]{64}\"', '\"$$H\"', s, count=1); \
open(p,'w').write(s); print('OK: preflight_check.py güncellendi')"

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
