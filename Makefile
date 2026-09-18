PYTHON ?= python3

.PHONY: test firmware eda verify clean

test:
	$(PYTHON) -m pytest

firmware:
	$(MAKE) -C frequency_estimator_firmware/core test PY=$(PYTHON)

eda:
	$(PYTHON) receiver_design/verify.py

verify: test firmware eda

clean:
	$(MAKE) -C frequency_estimator_firmware/core clean
	rm -rf .pytest_cache build *.egg-info
