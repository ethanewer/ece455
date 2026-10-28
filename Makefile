PYTHON ?= python3

.PHONY: test firmware sim breadboard docs verify clean

test:
	$(PYTHON) -m pytest

firmware:
	$(PYTHON) -m pytest util/tests/test_firmware.py

sim:
	$(PYTHON) -m util.simulate

breadboard:
	$(PYTHON) -m util.breadboard

docs: sim breadboard

verify: test docs

clean:
	rm -rf .pytest_cache build *.egg-info
	find local -depth -mindepth 1 ! -path local/.gitkeep -delete
