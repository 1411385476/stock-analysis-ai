PYTHON ?= venv312/bin/python
SYMBOL ?= 600519
ARGS ?=
SMOKE_OUTPUT ?= /tmp/stock_skill_output.txt
SMOKE_STRICT ?= 0

.PHONY: analyze test sync screen dashboard smoke-skill pipeline-daily regression-snapshot preflight

analyze:
	$(PYTHON) stock_analyzer.py $(SYMBOL) $(ARGS)

test:
	$(PYTHON) -m unittest discover -s tests -v

sync:
	$(PYTHON) stock_analyzer.py --sync-a-share $(ARGS)

screen:
	$(PYTHON) stock_analyzer.py --keyword $(KEYWORD) $(ARGS)

dashboard:
	$(PYTHON) -m dashboard.app $(ARGS)

pipeline-daily:
	bash scripts/run_daily_pipeline.sh $(ARGS)

regression-snapshot:
	$(PYTHON) scripts/check_strategy_regression.py --baseline tests/fixtures/strategy_regression_baseline.json --output /tmp/strategy_regression_latest.json $(ARGS)

preflight:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) scripts/check_strategy_regression.py --baseline tests/fixtures/strategy_regression_baseline.json --output /tmp/strategy_regression_latest.json
	$(MAKE) smoke-skill SMOKE_OUTPUT=tests/fixtures/skill_output_ok.txt SMOKE_STRICT=1

smoke-skill:
	@if [ ! -f "$(SMOKE_OUTPUT)" ]; then \
		echo "missing output file: $(SMOKE_OUTPUT)"; \
		echo "usage: make smoke-skill SMOKE_OUTPUT=/path/to/skill_output.txt [SMOKE_STRICT=1]"; \
		exit 1; \
	fi
	@if [ "$(SMOKE_STRICT)" = "1" ]; then \
		bash scripts/smoke_skill_output.sh --strict "$(SMOKE_OUTPUT)"; \
	else \
		bash scripts/smoke_skill_output.sh "$(SMOKE_OUTPUT)"; \
	fi
