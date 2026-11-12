PYTHON ?= .venv/bin/python
RELEASE ?= release-20261112
TESTBED ?=

.PHONY: reproduce verify assets h6-assets seal
reproduce:
	$(PYTHON) experiments/reproduce.py --release $(RELEASE) $(if $(TESTBED),--testbed $(TESTBED),)
verify:
	$(PYTHON) experiments/verify_run.py results/$(RELEASE)/data
	HCADSE_RESULTS=results/$(RELEASE)/data $(PYTHON) experiments/verify_manuscript_numbers.py
assets:
	HCADSE_RESULTS=results/$(RELEASE)/data $(PYTHON) experiments/make_paper_assets.py
	HCADSE_RESULTS=results/$(RELEASE)/data $(PYTHON) experiments/make_claims.py
h6-assets:
	$(PYTHON) experiments/make_h6_claims.py

seal:
	$(PYTHON) experiments/seal_release.py --audit $(AUDIT) --name $(RELEASE)
