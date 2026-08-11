# Spend Dashboard — Common Operations
PYTHON = python3
DIR = $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.PHONY: build check refresh serve clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build docs/data.json from transactions CSV
	$(PYTHON) $(DIR)/build.py

check: ## Validate build without writing output
	$(PYTHON) $(DIR)/build.py --check

refresh: ## Download latest transactions from Monarch + rebuild + push
	$(PYTHON) $(DIR)/monarch_download.py

serve: ## Serve the dashboard locally (http://localhost:8000)
	cd $(DIR)/docs && $(PYTHON) -m http.server 8000

clean: ## Remove generated files
	rm -f $(DIR)/docs/data.json $(DIR)/build_old.py $(DIR)/docs/data_old.json
	@echo "✓ Cleaned"
