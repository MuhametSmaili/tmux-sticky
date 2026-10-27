PYTHON ?= python3
SHELLCHECK ?= shellcheck

.PHONY: test lint check smoke-hetki smoke-shared-hetki

test:
	$(PYTHON) -m unittest discover -s tests -p '*.py' -v

lint:
	sh -n sticky.tmux
	sh -n bin/tmux-sticky
	sh -n scripts/run.sh
	sh -n scripts/layout.sh
	sh -n scripts/layout-format.sh
	sh -n scripts/context.sh
	sh -n scripts/state.sh
	sh -n scripts/clients.sh
	sh -n scripts/shared.sh
	awk -f scripts/layout-remove.awk </dev/null
	$(SHELLCHECK) -x -s sh sticky.tmux bin/tmux-sticky scripts/run.sh

smoke-hetki:
	$(PYTHON) tests/hetki_smoke.py

smoke-shared-hetki:
	STICKY_SMOKE_SHARED=1 $(PYTHON) tests/hetki_smoke.py

check: lint test
