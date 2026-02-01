# Configuration variables
TARGET_REPO ?= ethereum/go-ethereum
TARGET_REF ?= master
KEYWORDS ?= "geth,ethereum client,execution specs,EIP"
SPEC_URLS ?= "https://ethereum.github.io/execution-specs/src/,https://geth.ethereum.org/docs"
WORKDIR ?= target_workspace
OUTPUT_DIR ?= outputs
LOG_DIR ?= outputs/logs

# Claude environment
export CLAUDE_CODE_PERMISSIONS := bypassPermissions
export CLAUDE_CODE_MAX_OUTPUT_TOKENS := 100000

# Claude configuration
CLAUDE_FLAGS ?= --dangerously-skip-permissions --agent serena --output-format json

# Max iteration counts (safety limit)
MAX_ITERATIONS ?= 100

# Parallel execution configuration
WORKERS ?= 4
BATCH_SIZE ?= 10
SKIP_SPLIT ?=
FORCE_EXECUTE ?=

.PHONY: all preparation audit init init-prep \
        01a 01b-parallel 01c-parallel 01d-parallel 01e-parallel \
        02a-parallel 02b-parallel 02c 02s \
        03-parallel 04-parallel \
        clean help

# Default target: run full pipeline
all: preparation audit

# Phase targets
# preparation: 01a → 01b-parallel → 01c → 01d → 01e → 02s → 02a → 02b-parallel
preparation: 02b-parallel
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
	@echo "Checklist Steps (02a-02s) - All Parallel:"
	@echo "  02a-parallel - Checklist Boundaries (partials)"
	@echo "  02b-parallel - Checklist Remaining (partials)"
	@echo "  02s          - Review & Validate"
	@echo "  02c          - Checklist Merge [OPTIONAL]"
	@echo ""
	@echo "Audit Steps - All Parallel:"
	@echo "  init         - Setup target workspace"
	@echo "  03-parallel  - Audit Map (partials)"
	@echo "  04-parallel  - Audit Review (partials)"
	@echo ""
	@echo "Utilities:"
	@echo "  clean  - Remove generated outputs"
	@echo ""
	@echo "Configuration:"
	@echo "  WORKERS        - Parallel workers (default: 4)"
	@echo "  MAX_ITERATIONS - Safety limit (default: 100)"
	@echo "  BATCH_SIZE     - Items per iteration (default: 10)"
	@echo ""
	@echo "Examples:"
	@echo "  make 01b-parallel WORKERS=8"
	@echo "  make preparation WORKERS=4"

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
	mkdir -p $(OUTPUT_DIR)/01b_SUBGRAPHS
	@echo "Output directories ready"

# Utilities
clean:
	@echo "Cleaning outputs..."
	rm -rf $(OUTPUT_DIR)/*.json
	rm -rf $(OUTPUT_DIR)/01b_SUBGRAPHS
	rm -rf $(LOG_DIR)/*.json
	rm -rf $(WORKDIR)/outputs/*.json
	@echo "✅ Clean completed"

# ------------------------------------------------------
# Specification Steps (01a - 01e)
# ------------------------------------------------------

# Step 01a: Discovery & Queuing
01a:
	@mkdir -p $(LOG_DIR) $(OUTPUT_DIR)
	@if [ -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
		echo "⏭️  Skipping 01a: $(OUTPUT_DIR)/01a_STATE.json already exists"; \
	else \
		echo "⭐ Running 01a_crawl.md (Discovery & Queuing)..."; \
		START_TIME=$$(date +%s); \
		claude $(CLAUDE_FLAGS) -p "$$(cat prompts/01a_crawl.md) KEYWORDS=$(KEYWORDS) SPEC_URLS=$(SPEC_URLS)" > $(LOG_DIR)/01a_crawl.json; \
		END_TIME=$$(date +%s); \
		DURATION=$$((END_TIME - START_TIME)); \
		if [ -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
			COST=$$(grep -o '"total_cost_usd":[0-9.]*' $(LOG_DIR)/01a_crawl.json | head -1 | cut -d: -f2); \
			QUEUE_SIZE=$$(grep -o '"work_queue":\[[^]]*\]' $(OUTPUT_DIR)/01a_STATE.json | tr ',' '\n' | wc -l); \
			echo "✅ Finished 01a_crawl.md (Time: $${DURATION}s | URLs queued: ~$$QUEUE_SIZE | Cost: \$$$$COST)"; \
		else \
			echo "❌ Error: 01a_STATE.json not generated"; exit 1; \
		fi; \
	fi

# Step 01b-parallel: Parallel extraction using multiple workers
01b-parallel:
	@if [ ! -f "$(OUTPUT_DIR)/01a_STATE.json" ]; then \
		echo "❌ Error: $(OUTPUT_DIR)/01a_STATE.json not found. Run 01a first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/01b_SUBGRAPHS/spec_*.json >/dev/null 2>&1; then \
		SUBGRAPH_COUNT=$$(ls $(OUTPUT_DIR)/01b_SUBGRAPHS/spec_*.json 2>/dev/null | wc -l); \
		echo "⏭️  Skipping 01b-parallel: $$SUBGRAPH_COUNT subgraphs already exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01b extraction in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 01b --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(SKIP_SPLIT),--skip-split,); \
		SUBGRAPH_COUNT=$$(ls $(OUTPUT_DIR)/01b_SUBGRAPHS/*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel extraction complete. Total subgraphs: $$SUBGRAPH_COUNT"; \
	fi

# Step 01c-parallel: Parallel subgraph verification
01c-parallel:
	@if [ ! -d "$(OUTPUT_DIR)/01b_SUBGRAPHS" ] || [ -z "$$(ls $(OUTPUT_DIR)/01b_SUBGRAPHS/*.json 2>/dev/null)" ]; then \
		echo "❌ Error: No subgraphs found. Run 01b-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/01d_TRUSTMODEL_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 01c-parallel: trust model partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01c verification in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 01c --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(BATCH_SIZE),--batch-size $(BATCH_SIZE),) $(if $(SKIP_SPLIT),--skip-split,); \
		echo "✅ Parallel verification complete"; \
	fi

# Step 01d-parallel: Parallel trust model generation
01d-parallel:
	@if [ ! -d "$(OUTPUT_DIR)/01b_SUBGRAPHS" ] || [ -z "$$(ls $(OUTPUT_DIR)/01b_SUBGRAPHS/*.json 2>/dev/null)" ]; then \
		echo "❌ Error: No subgraphs found. Run 01b-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/01e_PROP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 01d-parallel: property partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01d trust model in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 01d --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(BATCH_SIZE),--batch-size $(BATCH_SIZE),) $(if $(SKIP_SPLIT),--skip-split,); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/01d_TRUSTMODEL_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel trust model complete. Partials: $$PARTIAL_COUNT"; \
	fi

# Step 01e-parallel: Parallel property generation
01e-parallel:
	@if ! ls $(OUTPUT_DIR)/01d_TRUSTMODEL_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No trust model partials found. Run 01d-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/02a_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 01e-parallel: checklist partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 01e properties in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 01e --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(BATCH_SIZE),--batch-size $(BATCH_SIZE),) $(if $(SKIP_SPLIT),--skip-split,); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/01e_PROP_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel property generation complete. Partials: $$PARTIAL_COUNT"; \
	fi

# ------------------------------------------------------
# Checklist Steps (02a - 02s)
# ------------------------------------------------------

# Step 02s: Review & Validate Preparation Outputs
02s:
	@if [ -f "$(OUTPUT_DIR)/02s_REVIEW_REPORT.json" ]; then \
		echo "⏭️  Skipping 02s: $(OUTPUT_DIR)/02s_REVIEW_REPORT.json already exists"; \
	else \
		if ! ls $(OUTPUT_DIR)/02b_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
			echo "❌ Error: No 02b_CHECKLIST_PARTIAL_*.json files found. Run 02b first."; exit 1; \
		fi; \
		echo "⭐ Running 02s_review.md (Preparation Review)..."; \
		START_TIME=$$(date +%s); \
		claude $(CLAUDE_FLAGS) -p "$$(cat prompts/02s_review.md)" > $(LOG_DIR)/02s_review.json; \
		END_TIME=$$(date +%s); \
		DURATION=$$((END_TIME - START_TIME)); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' $(LOG_DIR)/02s_review.json | head -1 | cut -d: -f2); \
		if [ -f "$(OUTPUT_DIR)/02s_REVIEW_REPORT.json" ]; then \
			echo "✅ Finished 02s_review.md (Time: $${DURATION}s | Cost: \$$$$COST)"; \
			VERDICT=$$(grep -o '"overall_verdict":"[^"]*"' $(OUTPUT_DIR)/02s_REVIEW_REPORT.json | cut -d'"' -f4); \
			ISSUES=$$(grep -o '"total_issues":[0-9]*' $(OUTPUT_DIR)/02s_REVIEW_REPORT.json | cut -d: -f2); \
			echo "📊 Review: $$VERDICT ($$ISSUES issues)"; \
		else \
			echo "⚠️  Review report not generated (Time: $${DURATION}s | Cost: \$$$$COST)"; \
		fi; \
	fi

# Step 02a-parallel: Parallel checklist boundary generation
02a-parallel:
	@if ! ls $(OUTPUT_DIR)/01e_PROP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No property partials found. Run 01e-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/02b_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 02a-parallel: 02b checklist partials exist (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 02a checklist boundaries in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 02a --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(BATCH_SIZE),--batch-size $(BATCH_SIZE),) $(if $(SKIP_SPLIT),--skip-split,); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/02a_CHECKLIST_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel boundary checklist complete. Partials: $$PARTIAL_COUNT"; \
	fi

# Step 02b-parallel: Parallel checklist generation for remaining properties
02b-parallel:
	@if ! ls $(OUTPUT_DIR)/02a_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No 02a checklist partials found. Run 02a-parallel first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/03_AUDITMAP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 02b-parallel: 03_AUDITMAP_PARTIAL_*.json exists (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 02b checklist remaining in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 02b --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(BATCH_SIZE),--batch-size $(BATCH_SIZE),) $(if $(SKIP_SPLIT),--skip-split,); \
		PARTIAL_COUNT=$$(ls $(OUTPUT_DIR)/02b_CHECKLIST_PARTIAL_*.json 2>/dev/null | wc -l); \
		echo "✅ Parallel checklist generation complete. Partials: $$PARTIAL_COUNT"; \
	fi

# Step 02c: Checklist Merge (Optional)
02c:
	@if [ -f "$(OUTPUT_DIR)/02_CHECKLIST.json" ]; then \
		echo "⏭️  Skipping 02c: $(OUTPUT_DIR)/02_CHECKLIST.json already exists"; \
	else \
		if [ ! -f "$(OUTPUT_DIR)/02a_CHECKLIST_BOUNDARIES.json" ]; then \
			echo "❌ Error: $(OUTPUT_DIR)/02a_CHECKLIST_BOUNDARIES.json not found. Run 02a first."; exit 1; \
		fi; \
		echo "⭐ Running 02c_checklistmerge.md (Checklist Merge)..."; \
		START_TIME=$$(date +%s); \
		claude $(CLAUDE_FLAGS) -p "$$(cat prompts/02c_checklistmerge.md)" > $(LOG_DIR)/02c_checklistmerge.json; \
		END_TIME=$$(date +%s); \
		DURATION=$$((END_TIME - START_TIME)); \
		if [ -f "$(OUTPUT_DIR)/02_CHECKLIST.json" ]; then \
			COST=$$(grep -o '"total_cost_usd":[0-9.]*' $(LOG_DIR)/02c_checklistmerge.json | head -1 | cut -d: -f2); \
			echo "✅ Finished 02c_checklistmerge.md (Time: $${DURATION}s | Cost: \$$$$COST)"; \
		else \
			echo "❌ Error: 02_CHECKLIST.json not generated"; exit 1; \
		fi; \
	fi

# ------------------------------------------------------
# Audit Steps
# ------------------------------------------------------

# Step 03-parallel: Parallel audit map using multiple workers
03-parallel:
	@if ! ls $(OUTPUT_DIR)/02*_CHECKLIST_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No checklist partials found. Run 02a-parallel and 02b-parallel first."; exit 1; \
	fi; \
	if [ ! -d "$(WORKDIR)/.git" ]; then \
		echo "❌ Error: $(WORKDIR) is not a git repo. Please clone target repo first."; exit 1; \
	fi; \
	if [ -z "$(FORCE_EXECUTE)" ] && ls $(OUTPUT_DIR)/04_REVIEW_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "⏭️  Skipping 03-parallel: 04_REVIEW_PARTIAL_*.json exists (use FORCE_EXECUTE=1 to override)"; \
	else \
		echo "🚀 Running 03_auditmap.md in parallel with $(WORKERS) workers..."; \
		python3 scripts/run_parallel.py --phase 03 --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(SKIP_SPLIT),--skip-split,); \
		echo "✅ Parallel audit map generation complete"; \
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
		python3 scripts/run_parallel.py --phase 04 --workers $(WORKERS) --max-iterations $(MAX_ITERATIONS) $(if $(SKIP_SPLIT),--skip-split,); \
		echo "✅ Parallel audit review complete"; \
	fi

