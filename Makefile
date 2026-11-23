PYTHON ?= python3

.PHONY: test test-live build

# The suite against a local siteverify; needs no network.
test:
	PYTHONPATH=src $(PYTHON) -m unittest discover --start-directory tests --top-level-directory .

# The test against CaptchaFox's siteverify; needs the network.
test-live:
	PYTHONPATH=src $(PYTHON) -m unittest tests.live_siteverify

# Writes the sdist and the wheel to dist/; needs the package build.
build:
	$(PYTHON) -m build
