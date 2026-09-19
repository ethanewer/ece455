PYTHON ?= python3

.PHONY: test firmware figures kicad pcb eda verify export clean

test:
	$(PYTHON) -m pytest

firmware:
	$(MAKE) -C frequency_estimator_firmware/core test PY=$(PYTHON)

figures:
	$(PYTHON) receiver_design/analyze.py

kicad:
	$(PYTHON) receiver_design/kicad/validate.py

pcb:
	$(PYTHON) receiver_design/kicad/validate.py --require-board

eda: figures kicad
	$(PYTHON) receiver_design/verify.py

verify: test firmware eda

export:
	$(PYTHON) receiver_design/export.py

clean:
	$(MAKE) -C frequency_estimator_firmware/core clean
	rm -rf .pytest_cache build *.egg-info
	find local -depth -mindepth 1 ! -path local/.gitkeep -delete
