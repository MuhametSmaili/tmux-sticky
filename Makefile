PYTHON ?= python3
SHELLCHECK ?= shellcheck

.PHONY: test lint check smoke-hetki

test:
	$(PYTHON) -m unittest discover -s tests -p '*.py' -v

lint:
	sh -n sticky.tmux
	sh -n bin/tmux-sticky
	sh -n scripts/run.sh
	$(SHELLCHECK) -s sh sticky.tmux bin/tmux-sticky scripts/run.sh

smoke-hetki:
	$(PYTHON) tests/hetki_smoke.py

check: lint test
