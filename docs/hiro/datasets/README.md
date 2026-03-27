# DeFi Audit Datasets & Analysis Results

Scraped audit findings from 3 public platforms + pattern matching & analysis results from the Chainlink Payment Abstraction V2 audit.

## Scraped CSV Datasets (Git LFS)

Located in `benchmarks/data/defi_audit_reports/`:

| File | Source | Size | Records | Last Updated |
|------|--------|------|---------|-------------|
| `code4rena_all_issues.csv` | Code4rena | 156 MB | ~3.3M | 2026-03-26 |
| `code4rena_all_issues_rq1.csv` | Code4rena (RQ1 format) | 155 MB | ~3.3M | 2026-03-26 |
| `sherlock_all_issues.csv` | Sherlock | 20 MB | ~406K | 2026-03-26 |
| `sherlock_all_issues_rq1.csv` | Sherlock (RQ1 format) | 20 MB | ~406K | 2026-03-26 |
| `codehawks_all_issues.csv` | CodeHawks | 3.6 MB | ~80K | 2026-03-26 |
| `codehawks_all_issues_rq1.csv` | CodeHawks (RQ1 format) | 3.6 MB | ~80K | 2026-03-26 |

**Total: ~360 MB, covering 232+ Sherlock contests, 3000+ Code4rena repos, and CodeHawks competitions.**

### CSV Schema

Standard columns: `source`, `severity`, `title`, `description`, `contest`, `issue_id`

### Scrapers

Located in `scripts/`:
- `scrape_code4rena.py` - Uses `gh` CLI to fetch from code-423n4 GitHub org
- `scrape_sherlock.py` - Paginates `mainnet-contest.sherlock.xyz` API + GitHub fallback
- `scrape_codehawks.py` - Fetches from `codehawks.cyfrin.io` tRPC API

## Pattern Matching Results (`precedents/`)

4 rounds of keyword-based pattern matching across all 3 CSV datasets:

| Round | Script | Patterns | Focus |
|-------|--------|----------|-------|
| 1 | `find_precedents_and_bugs.py` | 8 | M-02/M-07/M-14 calibration + 5 new bug patterns |
| 2 | `find_precedents_round2.py` | 12 | Fee-on-transfer, negative oracle, dutch frontrun, etc. |
| 3 | `find_precedents_round3.py` | 12 | Creative/compound: callback mismatch, pause bypass, etc. |
| 4 | `find_precedents_round4.py` | 12 | Order validation, partial fills, approval desync, etc. |

**Total: 44 unique search patterns, ~150K+ matches analyzed.**

JSON results:
- `precedent_search_results.json` - Round 1
- `precedent_round3_results.json` - Round 3
- `precedent_round4_results.json` - Round 4

CSV intermediate data:
- `past_defi_patterns*.csv` - Extracted patterns per round
- `similar_audit_findings.csv` - Cross-platform matching results

## Analysis Reports (`analysis/`)

### Audit Sessions
| File | Description |
|------|-------------|
| `fresh_audit_findings.md` | Fresh audit session 1 (independent) |
| `fresh_audit_round2.md` | Fresh audit session 2 (focus areas) |
| `fresh_audit_round3.md` | Fresh audit session 3 (under-audited areas) |

### Deep Contract Reviews
| File | Description |
|------|-------------|
| `gpv2_deep_review.md` | Line-by-line GPV2CompatibleAuction.sol review |
| `baseauction_deep_review.md` | BaseAuction.sol edge case analysis |
| `pricemanager_deep_review.md` | PriceManager.sol oracle logic review |

### Specialized Analyses
| File | Description |
|------|-------------|
| `compound_attack_analysis.md` | 12 compound attack scenarios (round 1) |
| `compound_attack_round2.md` | 10 compound attack scenarios (round 2) |
| `assumption_breaking_audit.md` | 10 implicit assumptions tested |
| `math_edge_cases.md` | Arithmetic edge case analysis |
| `creative_attack_final.md` | 20+ creative attack vectors |
| `spec_gap_analysis.md` | Spec vs implementation gap analysis |
| `test_reverse_analysis.md` | Test file reverse engineering |
| `config_deployment_audit.md` | Constructor/config audit |
| `csv_llm_match_round4.md` | LLM bulk matching on round 4 CSV hits |
| `round3_timeout_reanalysis.md` | Re-analysis of 4 timed-out patterns |

### Severity Calibration
| File | Description |
|------|-------------|
| `severity_calibration_M-02_shared_staleness.md` | M-02 precedent analysis |
| `severity_calibration_M-07_future_timestamp.md` | M-07 precedent analysis |
| `severity_calibration_M-14_stale_approval.md` | M-14 precedent analysis |
| `precedent_analysis_*.md` | 5 new bug pattern analyses |

### Status
| File | Description |
|------|-------------|
| `FINAL_AUDIT_STATUS.md` | Final audit status and finding inventory |
