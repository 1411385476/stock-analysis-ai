PYTHON ?= venv312/bin/python
SYMBOL ?= 600519
ARGS ?=

.PHONY: analyze test sync screen

analyze:
	$(PYTHON) stock_analyzer.py $(SYMBOL) $(ARGS)

test:
	$(PYTHON) -m unittest discover -s tests -v

sync:
	$(PYTHON) stock_analyzer.py --sync-a-share $(ARGS)

screen:
	$(PYTHON) stock_analyzer.py --keyword $(KEYWORD) $(ARGS)
