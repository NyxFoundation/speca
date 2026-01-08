# Configuration variables
TARGET_REPO ?= kbizikav/zERC20
TARGET_REF ?= dev
KEYWORDS ?= "zkSNARKs,zkWormhole,zERC20,"
SPEC_URLS ?= "https://raw.githubusercontent.com/kbizikav/zERC20/refs/heads/dev/docs/contract_spec.md"
WORKDIR ?= target_workspace
OUTPUT_DIR ?= outputs
LOG_DIR ?= outputs/logs

# Claude environment
export CLAUDE_CODE_PERMISSIONS := bypassPermissions
export CLAUDE_CODE_MAX_OUTPUT_TOKENS := 100000

# Claude configuration
CLAUDE_FLAGS ?= --dangerously-skip-permissions --agent serena --output-format json

.PHONY: all preparation audit init 01 01a 01b 01c 02a 02b 02c 03 04 clean help

# Default target: run full pipeline
all: preparation audit

# Phase targets (matching scripts)
preparation: 02a
	@echo "🎉 Preparation phase completed! Check $(OUTPUT_DIR)/"

audit: 04
	@echo "🎉 Audit phase completed! Check $(OUTPUT_DIR)/04_REVIEW_PARTIAL_*.json"

# ------------------------------------------------------
# Utilities
# ------------------------------------------------------

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Phase Targets:"
	@echo "  all         - Run full pipeline (preparation + audit)"
	@echo "  preparation - Run preparation phase (01 → 01a → 01b → 01c → 02a)"
	@echo "  audit       - Run audit phase (03 → 04)"
	@echo ""
	@echo "Preparation Steps:"
	@echo "  init  - Setup directories and check workspace"
	@echo "  01    - Specification Extraction (01_spec.md → 01_SPEC.json)"
	@echo "  01a   - Specification Retry (01a_specretry.md → 01_SPEC.json)"
	@echo "  01b   - Trust Model Generation (01b_trustmodel.md → 01b_TRUSTMODEL.json)"
	@echo "  01c   - Property Extraction (01c_prop.md → 01c_PROP.json)"
	@echo "  02a   - Checklist Boundaries (02a_checklist.md → 02a_CHECKLIST_BOUNDARIES.json)"
	@echo "  02b   - Checklist Remaining (02b_checklistrem.md) - Run iteratively, generates _<N>.json"
	@echo "  02c   - Checklist Merge (02c_checklistmerge.md → 02_CHECKLIST.json) [SKIPPED]"
	@echo ""
	@echo "Audit Steps:"
	@echo "  03    - Static Audit Map (03_auditmap.md) - Run iteratively, generates _PARTIAL_<N>.json"
	@echo "  04    - Audit Review (04_review.md) - Run iteratively, generates 04_REVIEW_PARTIAL_<N>.json"
	@echo ""
	@echo "Utilities:"
	@echo "  clean - Remove generated outputs"

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

# Utilities
clean:
	@echo "Cleaning outputs..."
	rm -rf $(OUTPUT_DIR)/*.json
	rm -rf $(LOG_DIR)/*.json
	rm -rf $(WORKDIR)/outputs/*.json
	@echo "✅ Clean completed"

# ------------------------------------------------------
# Preparation Steps
# ------------------------------------------------------

# Step 01: Specification Extraction
01: $(OUTPUT_DIR)/01_SPEC.json
$(OUTPUT_DIR)/01_SPEC.json: prompts/01_spec.md | init
	@echo "⭐ Running 01_spec.md..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/01_spec.md) KEYWORDS=$(KEYWORDS) SPEC_URLS=$(SPEC_URLS)" > ../$(LOG_DIR)/01_spec.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	if [ -f "outputs/01_SPEC.json" ]; then \
		cp outputs/01_SPEC.json ../$(OUTPUT_DIR)/; \
		INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/01_spec.json | head -1 | cut -d: -f2); \
		OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/01_spec.json | head -1 | cut -d: -f2); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/01_spec.json | head -1 | cut -d: -f2); \
		echo "✅ Finished 01_spec.md (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "❌ Error: 01_SPEC.json not generated"; exit 1; \
	fi

# Step 01a: Specification Retry (Optional/Refinement)
01a: | init
	@echo "⭐ Running 01a_specretry.md..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/01a_specretry.md)" > ../$(LOG_DIR)/01a_specretry.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	if [ -f "outputs/01_SPEC.json" ]; then \
		cp outputs/01_SPEC.json ../$(OUTPUT_DIR)/; \
		INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/01a_specretry.json | head -1 | cut -d: -f2); \
		OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/01a_specretry.json | head -1 | cut -d: -f2); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/01a_specretry.json | head -1 | cut -d: -f2); \
		echo "✅ Finished 01a_specretry.md (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	fi

# Step 01b: Trust Model
01b: $(OUTPUT_DIR)/01b_TRUSTMODEL.json
$(OUTPUT_DIR)/01b_TRUSTMODEL.json: prompts/01b_trustmodel.md | 01
	@echo "⭐ Running 01b_trustmodel.md..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/01b_trustmodel.md)" > ../$(LOG_DIR)/01b_trustmodel.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	if [ -f "outputs/01b_TRUSTMODEL.json" ]; then \
		cp outputs/01b_TRUSTMODEL.json ../$(OUTPUT_DIR)/; \
		INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/01b_trustmodel.json | head -1 | cut -d: -f2); \
		OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/01b_trustmodel.json | head -1 | cut -d: -f2); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/01b_trustmodel.json | head -1 | cut -d: -f2); \
		echo "✅ Finished 01b_trustmodel.md (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "❌ Error: 01b_TRUSTMODEL.json not generated"; exit 1; \
	fi

# Step 01c: Properties
01c: $(OUTPUT_DIR)/01c_PROP.json
$(OUTPUT_DIR)/01c_PROP.json: prompts/01c_prop.md | 01b
	@echo "⭐ Running 01c_prop.md..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/01c_prop.md)" > ../$(LOG_DIR)/01c_prop.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	if [ -f "outputs/01c_PROP.json" ]; then \
		cp outputs/01c_PROP.json ../$(OUTPUT_DIR)/; \
		INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/01c_prop.json | head -1 | cut -d: -f2); \
		OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/01c_prop.json | head -1 | cut -d: -f2); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/01c_prop.json | head -1 | cut -d: -f2); \
		echo "✅ Finished 01c_prop.md (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "❌ Error: 01c_PROP.json not generated"; exit 1; \
	fi

# Step 02a: Checklist Boundaries
02a: $(OUTPUT_DIR)/02a_CHECKLIST_BOUNDARIES.json
$(OUTPUT_DIR)/02a_CHECKLIST_BOUNDARIES.json: prompts/02a_checklist.md | 01c
	@echo "⭐ Running 02a_checklist.md..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/02a_checklist.md)" > ../$(LOG_DIR)/02a_checklist.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	if [ -f "outputs/02a_CHECKLIST_BOUNDARIES.json" ]; then \
		cp outputs/02a_CHECKLIST_BOUNDARIES.json ../$(OUTPUT_DIR)/; \
		INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/02a_checklist.json | head -1 | cut -d: -f2); \
		OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/02a_checklist.json | head -1 | cut -d: -f2); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/02a_checklist.json | head -1 | cut -d: -f2); \
		echo "✅ Finished 02a_checklist.md (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "❌ Error: 02a_CHECKLIST_BOUNDARIES.json not generated"; exit 1; \
	fi

# Step 02b: Checklist Remaining (Iterative)
# Each run generates 02b_CHECKLIST_PARTIAL_<N>.json and logs to 02b_checklistrem_<N>.json
02b: | 02a
	@N=$$(ls $(OUTPUT_DIR)/02b_CHECKLIST_PARTIAL_*.json 2>/dev/null | wc -l); \
	N=$$((N + 1)); \
	echo "⭐ Running 02b_checklistrem.md (iteration $$N)..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/02b_checklistrem.md)" > ../$(LOG_DIR)/02b_checklistrem_$$N.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/02b_checklistrem_$$N.json | head -1 | cut -d: -f2); \
	OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/02b_checklistrem_$$N.json | head -1 | cut -d: -f2); \
	COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/02b_checklistrem_$$N.json | head -1 | cut -d: -f2); \
	if [ -f "outputs/02b_CHECKLIST_PARTIAL_$$N.json" ]; then \
		cp outputs/02b_CHECKLIST_PARTIAL_$$N.json ../$(OUTPUT_DIR)/; \
		echo "✅ Finished 02b_checklistrem.md iter $$N (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "⚠️  No new partial checklist generated in iteration $$N (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	fi; \
	cp outputs/02b_STATE.json ../$(OUTPUT_DIR)/ 2>/dev/null || true; \
	if [ -f "../$(OUTPUT_DIR)/02b_STATE.json" ]; then \
		REMAINING=$$(grep -o '"remaining":[0-9]*' ../$(OUTPUT_DIR)/02b_STATE.json | cut -d: -f2); \
		if [ "$$REMAINING" -gt 0 ] 2>/dev/null; then \
			echo "📋 $$REMAINING items remaining. Run 'make 02b' again."; \
		else \
			echo "🎉 All items processed! Ready for 'make 03'."; \
		fi; \
	fi

# Step 02c: Checklist Merge
02c: $(OUTPUT_DIR)/02_CHECKLIST.json
$(OUTPUT_DIR)/02_CHECKLIST.json: prompts/02c_checklistmerge.md | 02a
	@echo "⭐ Running 02c_checklistmerge.md..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/02c_checklistmerge.md)" > ../$(LOG_DIR)/02c_checklistmerge.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	if [ -f "outputs/02_CHECKLIST.json" ]; then \
		cp outputs/02_CHECKLIST.json ../$(OUTPUT_DIR)/; \
		INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/02c_checklistmerge.json | head -1 | cut -d: -f2); \
		OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/02c_checklistmerge.json | head -1 | cut -d: -f2); \
		COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/02c_checklistmerge.json | head -1 | cut -d: -f2); \
		echo "✅ Finished 02c_checklistmerge.md (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "❌ Error: 02_CHECKLIST.json not generated"; exit 1; \
	fi

# ------------------------------------------------------
# Audit Steps
# ------------------------------------------------------

# Step 03: Audit Map (Iterative)
# Each run generates 03_AUDITMAP_PARTIAL_<N>.json and logs to 03_auditmap_<N>.json
03: | $(OUTPUT_DIR)/02a_CHECKLIST_BOUNDARIES.json
	@N=$$(ls $(OUTPUT_DIR)/03_AUDITMAP_PARTIAL_*.json 2>/dev/null | wc -l); \
	N=$$((N + 1)); \
	echo "⭐ Running 03_auditmap.md (iteration $$N)..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/03_auditmap.md)" > ../$(LOG_DIR)/03_auditmap_$$N.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/03_auditmap_$$N.json | head -1 | cut -d: -f2); \
	OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/03_auditmap_$$N.json | head -1 | cut -d: -f2); \
	COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/03_auditmap_$$N.json | head -1 | cut -d: -f2); \
	if [ -f "outputs/03_AUDITMAP_PARTIAL_$$N.json" ]; then \
		cp outputs/03_AUDITMAP_PARTIAL_$$N.json ../$(OUTPUT_DIR)/; \
		echo "✅ Finished 03_auditmap.md iter $$N (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "⚠️  No new partial auditmap generated in iteration $$N (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	fi; \
	cp outputs/03_STATE.json ../$(OUTPUT_DIR)/ 2>/dev/null || true; \
	if [ -f "../$(OUTPUT_DIR)/03_STATE.json" ]; then \
		REMAINING=$$(grep -o '"remaining":[0-9]*' ../$(OUTPUT_DIR)/03_STATE.json | cut -d: -f2); \
		if [ "$$REMAINING" -gt 0 ] 2>/dev/null; then \
			echo "📋 $$REMAINING items remaining. Run 'make 03' again."; \
		else \
			echo "🎉 All items processed! Ready for 'make 04'."; \
		fi; \
	fi

# Step 04: Review (Iterative)
# Each run generates 04_REVIEW_PARTIAL_<N>.json and logs to 04_review_<N>.json
04: | init
	@if ! ls $(OUTPUT_DIR)/03_AUDITMAP_PARTIAL_*.json >/dev/null 2>&1; then \
		echo "❌ Error: No 03_AUDITMAP_PARTIAL_*.json files found. Run 'make 03' first."; exit 1; \
	fi; \
	N=$$(ls $(OUTPUT_DIR)/04_REVIEW_PARTIAL_*.json 2>/dev/null | wc -l); \
	N=$$((N + 1)); \
	echo "⭐ Running 04_review.md (iteration $$N)..."; \
	START_TIME=$$(date +%s); \
	cd $(WORKDIR) && claude $(CLAUDE_FLAGS) -p "$$(cat ../prompts/04_review.md)" > ../$(LOG_DIR)/04_review_$$N.json; \
	END_TIME=$$(date +%s); \
	DURATION=$$((END_TIME - START_TIME)); \
	INPUT_TOKENS=$$(grep -o '"input_tokens":[0-9]*' ../$(LOG_DIR)/04_review_$$N.json | head -1 | cut -d: -f2); \
	OUTPUT_TOKENS=$$(grep -o '"output_tokens":[0-9]*' ../$(LOG_DIR)/04_review_$$N.json | head -1 | cut -d: -f2); \
	COST=$$(grep -o '"total_cost_usd":[0-9.]*' ../$(LOG_DIR)/04_review_$$N.json | head -1 | cut -d: -f2); \
	if [ -f "outputs/04_REVIEW_PARTIAL_$$N.json" ]; then \
		cp outputs/04_REVIEW_PARTIAL_$$N.json ../$(OUTPUT_DIR)/; \
		echo "✅ Finished 04_review.md iter $$N (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	else \
		echo "⚠️  No new partial review generated in iteration $$N (Time: $${DURATION}s | Tokens: In=$$INPUT_TOKENS, Out=$$OUTPUT_TOKENS | Cost: \$$$$COST)"; \
	fi; \
	cp outputs/04_STATE.json ../$(OUTPUT_DIR)/ 2>/dev/null || true; \
	if [ -f "../$(OUTPUT_DIR)/04_STATE.json" ]; then \
		REMAINING=$$(grep -o '"remaining":[0-9]*' ../$(OUTPUT_DIR)/04_STATE.json | cut -d: -f2); \
		if [ "$$REMAINING" -gt 0 ] 2>/dev/null; then \
			echo "📋 $$REMAINING items remaining. Run 'make 04' again."; \
		else \
			echo "🎉 All items reviewed! Audit complete."; \
		fi; \
	fi
