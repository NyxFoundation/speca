# Configuration variables
TARGET_REPO ?= ethereum/go-ethereum
TARGET_REF ?= master
KEYWORDS ?= "geth,ethereum client,execution specs,EIP"
SPEC_URLS ?= "https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"
WORKDIR ?= target_workspace
OUTPUT_DIR ?= outputs
LOG_DIR ?= outputs/logs

# MCP configuration
# Directories accessible to the filesystem MCP server (space-separated)
FILESYSTEM_DIRS ?= . $(WORKDIR)

# Claude environment
export CLAUDE_CODE_PERMISSIONS := bypassPermissions
export CLAUDE_CODE_MAX_OUTPUT_TOKENS := 100000

# Claude configuration
CLAUDE_FLAGS ?= --dangerously-skip-permissions --output-format stream-json
PYTHON_RUNNER ?= uv run python3

# Parallel execution configuration
WORKERS ?= 4
MAX_CONCURRENT ?= 64
FORCE_EXECUTE ?=

.PHONY: all preparation audit init init-prep \
        01a 01b-parallel 01c-parallel 01d-parallel 01e-parallel \
        02-parallel \
        03-parallel 04-parallel \
        benchmark-all benchmark-setup benchmark-run benchmark-evaluate benchmark-report \
        clean help mcp-setup mcp-verify

# Default target: run full pipeline
all: preparation audit

# Phase targets
# preparation: 01a → 01b-parallel → 01c → 01d → 01e → 02-parallel
preparation: 02-parallel
	@echo "🎉 Preparation phase completed! Check $(OUTPUT_DIR)/"

audit: 04-parallel
	@echo "🎉 Audit phase completed! Check $(OUTPUT_DIR)/04_REVIEW_PARTIAL_*.json"

# ------------------------------------------------------
# Utilities
# ------------------------------------------------------

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Phase Targets:"
	@echo "  all          - Run full pipeline (preparation + audit)"
	@echo "  preparation  - Run preparation phase (all parallel)"
	@echo "  audit        - Run audit phase (all parallel)"
	@echo ""
	@echo "Specification Steps (01a-01e) - All Parallel:"
	@echo "  init-prep    - Setup output directories"
	@echo "  01a          - Discovery & Queuing"
	@echo "  01b-parallel - Extraction (subgraphs)"
	@echo "  01c-parallel - Verification (validate subgraphs)"
	@echo "  01d-parallel - Trust Model (partials)"
	@echo "  01e-parallel - Properties (partials)"
	@echo ""
	@echo "Checklist Steps (02) - All Parallel:"
	@echo "  02-parallel  - Unified Checklist Generation (partials)"
	@echo ""
	@echo "Audit Steps - All Parallel:"
	@echo "  init         - Setup target workspace"
	@echo "  03-parallel  - Audit Map (partials)"
	@echo "  04-parallel  - Audit Review (partials)"
	@echo ""
	@echo "Utilities:"
	@echo "  clean      - Remove generated outputs"
	@echo "  mcp-setup  - Register MCP servers for Claude"
	@echo "  mcp-verify - Check MCP server registration status"
	@echo ""
	@echo "Configuration:"
	@echo "  WORKERS        - Parallel workers (default: 4)"
	@echo "  MAX_CONCURRENT - Max concurrent Claude calls (default: 64)"
	@echo "  FORCE_EXECUTE  - Set to 1 to bypass skip conditions"
	@echo "  FILESYSTEM_DIRS - Directories for filesystem MCP (default: '. $(WORKDIR)')"
	@echo ""
	@echo "Examples:"
	@echo "  make mcp-setup FILESYSTEM_DIRS='. target_workspace /tmp/audit'"
	@echo "  make 01b-parallel WORKERS=8"
	@echo "  make preparation WORKERS=4 MAX_CONCURRENT=16"
	@echo ""
	@echo "Benchmark Targets:"
	@echo "  benchmark-all      - Run setup, tools, and evaluation"
	@echo "  benchmark-setup    - Download benchmark datasets"
	@echo "  benchmark-run      - Run benchmark tools in Docker"
	@echo "  benchmark-evaluate - Compute metrics from results"
	@echo "  benchmark-report   - Generate Markdown report (if available)"

# Init for audit phase (requires git repo)
init:
	@echo "Initializing workspace..."
	mkdir -p $(LOG_DIR)
	mkdir -p $(WORKDIR)/outputs
	@if [ ! -d "$(WORKDIR)/.git" ]; then \
		echo "Error: $(WORKDIR) is not a git repo. Please clone target repo:"; \
		echo "  git clone https://github.com/$(TARGET_REPO) $(WORKDIR)"; \
		exit 1; \
	fi
	@echo "Workspace ready at $(WORKDIR)"

# Init for preparation phase (no git repo required)
init-prep:
	@echo "Initializing for preparation phase..."
	mkdir -p $(LOG_DIR)
	mkdir -p $(OUTPUT_DIR)
	@echo "Output directories ready"
	@echo "Checking MCP servers..."
	@bash scripts/setup_mcp.sh --verify || echo "  Run 'make mcp-setup' to register MCP servers."

# Utilities
clean:
	@echo "Cleaning outputs..."
	rm -rf $(OUTPUT_DIR)/*.json
	rm -rf $(LOG_DIR)/*.json
	rm -rf $(WORKDIR)/outputs/*.json
	@echo "✅ Clean completed"

mcp-setup:
	@FILESYSTEM_DIRS="$(FILESYSTEM_DIRS)" bash scripts/setup_mcp.sh

mcp-verify:
	@bash scripts/setup_mcp.sh --verify

# ------------------------------------------------------
# Specification Steps (01a - 01e)
# All parallel phases use scripts/run_phase.py (unified orchestrator)
# Batching and iteration limits are configured in scripts/orchestrator/config.py
# ------------------------------------------------------

# Step 01a: Discovery & Queuing (single Claude invocation, not parallel)
01a:
	@mkdir -p $(LOG_DIR) $(OUTPUT_DIR)
	@if [ "$(APPEND_MODE)" = "true" ] && [ ! -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
		echo "❌ Error: APPEND_MODE=true but $(OUTPUT_DIR)/01a_STATE.json does not exist"; \
		exit 1; \
	fi; \
	if [ "$(APPEND_MODE)" != "true" ] && [ -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
		echo "⏭️  Skipping 01a: $(OUTPUT_DIR)/01a_STATE.json already exists (use APPEND_MODE=true to add URLs)"; \
	else \
		echo "⭐ Running 01a_crawl.md (Discovery & Queuing)..."; \
		if [ "$(APPEND_MODE)" = "true" ]; then \
			echo "   Mode: APPEND (merging with existing STATE)"; \
		fi; \
		TIMESTAMP=$$(date +'%Y%m%d-%H%M%S'); \
		LOG_FILE="$(LOG_DIR)/01a_crawl_$${TIMESTAMP}.jsonl"; \
		START_TIME=$$(date +%s); \
		claude --dangerously-skip-permissions --verbose --output-format stream-json -p "$$(cat prompts/01a_crawl.md) KEYWORDS=$(KEYWORDS) SPEC_URLS=$(SPEC_URLS) APPEND_MODE=$(APPEND_MODE) OUTPUT_FILE=$(OUTPUT_DIR)/01a_STATE.json" > "$${LOG_FILE}"; \
		END_TIME=$$(date +%s); \
		DURATION=$$((END_TIME - START_TIME)); \
		if [ -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
			COST=$$(grep -oE '"(total_cost_usd|costUSD)":[0-9.]*' "$${LOG_FILE}" | tail -1 | cut -d: -f2); \
			QUEUE_SIZE=$$(grep -o '"work_queue":\[[^]]*\]' $(OUTPUT_DIR)/01a_STATE.json | tr ',' '\n' | wc -l); \
			if [ "$(APPEND_MODE)" = "true" ]; then \
				echo "✅ Finished 01a_crawl.md - APPEND mode (Time: $${DURATION}s | Total URLs in queue: ~$$QUEUE_SIZE | Cost: \$$$$COST)"; \
			else \
				echo "✅ Finished 01a_crawl.md (Time: $${DURATION}s | URLs queued: ~$$QUEUE_SIZE | Cost: \$$$$COST)"; \
			fi; \
		else \
			echo "❌ Error: 01a_STATE.json not generated"; exit 1; \
		fi; \
	fi

# Step 01b-parallel: Parallel extraction using multiple workers
01b-parallel:
	@if [ ! -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
		echo "❌ Error: $(OUTPUT_DIR)/01a_STATE.json not found. Run 01a first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/01b_PARTIAL_*.json >/dev/null 2>&1; then \
		SUBGRAPH_COUNT=$$(ls $(OUTPUT_DIR)/01b_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "⏭️  Skipping 01b-parallel: $$SUBGRAPH_COUNT partials already exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01b extraction in parallel with $(WORKERS) workers..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 01b --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT); \
		SUBGRAPH_COUNT=$$(ls $(OUTPUT_DIR)/01b_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel extraction complete. Total partials: $$SUBGRAPH_COUNT"; \
	fi

# Step 01c-parallel: Parallel subgraph verification
01c-parallel:
	@if [ -z "$$(ls $(OUTPUT_DIR)/01b_PARTIAL_*.json 2>/dev/null)" ]; then \
		echo "❌ Error: No 01b partials found. Run 01b-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/01d_TRUSTMODEL_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 01c-parallel: trust model partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01c verification in parallel with $(WORKERS) workers..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 01c --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT); \
		echo "✅ Parallel verification complete"; \
	fi

# Step 01d-parallel: Parallel trust model generation
01d-parallel:
	@if [ -z "$$(ls $(OUTPUT_DIR)/01c_PARTIAL_*.json 2>/dev/null)" ]; then \
		echo "❌ Error: No 01c partials found. Run 01c-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/01e_PROP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 01d-parallel: property partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01d trust model in parallel with $(WORKERS) workers..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 01d --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/01d_TRUSTMODEL_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel trust model complete. Partials: $$PARTIAL_COUNT"; \
	fi

# Step 01e-parallel: Parallel property generation
01e-parallel:
	@if ! ls $(OUTPUT_DIR)/01d_TRUSTMODEL_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No trust model partials found. Run 01d-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/02_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 01e-parallel: checklist partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01e properties in parallel with $(WORKERS) workers..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 01e --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/01e_PROP_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel property generation complete. Partials: $$PARTIAL_COUNT"; \
	fi

# ------------------------------------------------------
# Checklist Steps (02)
# ------------------------------------------------------

# Step 02-parallel: Unified checklist generation
02-parallel:
	@if ! ls $(OUTPUT_DIR)/01e_PROP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No property partials found. Run 01e-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/03_AUDITMAP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 02-parallel: 03_AUDITMAP_PARTIAL_*.json exists (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running unified checklist generation in parallel with $(WORKERS) workers..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 02 --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/02_CHECKLIST_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel checklist generation complete. Partials: $$PARTIAL_COUNT"; \
	fi

# ------------------------------------------------------
# Audit Steps
# ------------------------------------------------------

# Step 03-parallel: Parallel audit map using multiple workers
03-parallel:
	@if ! ls $(OUTPUT_DIR)/02*_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No checklist partials found. Run 02-parallel first."; exit 1; \
	fi; \
	if [ ! -d "$(WORKDIR)/.git" ]; then \
		echo "❌ Error: $(WORKDIR) is not a git repo. Please clone target repo first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/04_REVIEW_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 03-parallel: 04_REVIEW_PARTIAL_*.json exists (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 03 Audit Map Async Orchestrator..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 03 --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT) && \
		echo "✅ Audit map generation complete."; \
	fi

# Step 04-parallel: Parallel audit review using multiple workers
04-parallel:
	@if [ ! -d "$(WORKDIR)/.git" ]; then \
		echo "❌ Error: $(WORKDIR) is not a git repo. Please clone target repo first."; exit 1; \
	fi; \
	if ! ls $(OUTPUT_DIR)/03_AUDITMAP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No 03_AUDITMAP_PARTIAL_*.json files found. Run 03-parallel first."; exit 1; \
	fi; \
	SHOULD_SKIP=false; \
	if [ -z "$(FORCE_EXECUTE)" ] && [ -f "$(OUTPUT_DIR)/04_STATE.json" ]; then \
		REMAINING=$$(python3 -c "import json; d=json.load(open('$(OUTPUT_DIR)/04_STATE.json')); print(len(d.get('unprocessed_audit_items', [])))" 2>/dev/null || echo "0"); \
		if [ "$$REMAINING" -eq 0 ] 2>/dev/null; then \
			PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/04_REVIEW_PARTIAL_*.json 2>/dev/null | wc -l); \
			echo "⏭️  Skipping 04-parallel: all audit items reviewed ($$PARTIAL_COUNT partial files exist, use FORCE_EXECUTE=1 to override)"; \
			SHOULD_SKIP=true; \
		fi; \
	fi; \
	if [ "$$SHOULD_SKIP" = "false" ]; then \
		echo "🚀 Running 04_review.md in parallel with $(WORKERS) workers..."; \
		$(PYTHON_RUNNER) scripts/run_phase.py --phase 04 --workers $(WORKERS) --max-concurrent $(MAX_CONCURRENT); \
		echo "✅ Parallel audit review complete"; \
	fi

# ------------------------------------------------------
# Benchmark Infrastructure
# ------------------------------------------------------

benchmark-all: benchmark-setup benchmark-run benchmark-evaluate
	@echo "Benchmark pipeline completed."

benchmark-setup:
	python3 benchmarks/datasets/builders/setup_benchmark.py

benchmark-run:
	docker build -t security-agent-benchmark -f benchmarks/Dockerfile .
	docker run --rm -v $(shell pwd):/app security-agent-benchmark \
	    python3 /app/benchmarks/runners/run_semgrep.py

benchmark-evaluate:
	docker run --rm -v $(shell pwd):/app security-agent-benchmark \
	    python3 /app/benchmarks/rq2/evaluate.py

benchmark-report:
	@echo "Benchmark report generation is not configured yet."
