PYTHON ?= python3
RELEASE ?= release-20261112
DATA = results/$(RELEASE)/data

.PHONY: verify assets test reproduce
verify:
	$(PYTHON) experiments/verify_run.py $(DATA)
	HCADSE_RESULTS=$(DATA) $(PYTHON) experiments/verify_manuscript_numbers.py
assets:
	mkdir -p manuscript/generated manuscript/tables manuscript/figures
	HCADSE_RESULTS=$(DATA) $(PYTHON) experiments/make_paper_assets.py
	HCADSE_RESULTS=$(DATA) $(PYTHON) experiments/make_claims.py
test:
	HCADSE_RESULTS=$(DATA) $(PYTHON) -m pytest -q tests
reproduce:
	$(PYTHON) experiments/reproduce.py --release $(RELEASE)-rerun
