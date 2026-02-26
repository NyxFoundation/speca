# Benchmark Report

Generated: 2026-02-26T15:13:24.829977+00:00

## Dataset

- Path: benchmarks/data/primevul/primevul_test_paired.jsonl
- Ground-truth samples: 868
- Total samples: 868
- Pair groups: 412 (eligible: 386, skipped: 26)

## Tool Metrics

| Tool | Precision | Recall | F1 | Coverage | TP | FP | TN | FN | Errors |
| ---- | --------- | ------ | -- | -------- | -- | -- | -- | -- | ------ |
| semgrep | 0.000 | 0.000 | 0.000 | 1.000 | 0 | 0 | 433 | 435 | 0 |
| codeql | n/a | n/a | n/a | 0.000 | 0 | 0 | 0 | 0 | 0 |
| security_agent | n/a | n/a | n/a | 0.000 | 0 | 0 | 0 | 0 | 0 |
| llm_baseline | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0 | 0 | 0 | 20 |
| static_baseline | n/a | n/a | n/a | 0.000 | 0 | 0 | 0 | 0 | 0 |

## Tool Metadata

| Tool | Version | Timeout | Limit |
| ---- | ------- | ------- | ----- |
| semgrep | 1.152.0 | 300 | 0 |
| llm_baseline | n/a | 120 | 20 |

## Pairwise Correct

## Pairwise Statistics (Security Agent vs Baselines)

- n/a

| Tool | Accuracy | Correct | Scored | Total | Skipped |
| ---- | -------- | ------- | ------ | ----- | ------- |
| semgrep | 0.000 | 0 | 386 | 386 | 0 |
| codeql | n/a | 0 | 0 | 0 | 0 |
| security_agent | n/a | 0 | 0 | 0 | 0 |
| llm_baseline | 0.000 | 0 | 0 | 386 | 386 |
| static_baseline | n/a | 0 | 0 | 0 | 0 |

## Unique Detections (Security Agent)

- Count: 0

## CWE Coverage (Top 10 by vulnerable count)

| CWE | Total | Semgrep Recall | CodeQL Recall | Security Agent Recall |
| --- | ----- | -------------- | ------------- | --------------------- |
| CWE-787 | 72 | 0.000 | n/a | n/a |
| CWE-125 | 47 | 0.000 | n/a | n/a |
| CWE-703 | 47 | 0.000 | n/a | n/a |
| CWE-476 | 39 | 0.000 | n/a | n/a |
| CWE-416 | 29 | 0.000 | n/a | n/a |
| CWE-200 | 16 | 0.000 | n/a | n/a |
| CWE-369 | 14 | 0.000 | n/a | n/a |
| CWE-20 | 14 | 0.000 | n/a | n/a |
| CWE-119 | 14 | 0.000 | n/a | n/a |
| CWE-617 | 12 | 0.000 | n/a | n/a |

## Traditional Tool Weaknesses (Missed CWE)

- semgrep: CWE-787 (72), CWE-125 (47), CWE-703 (47), CWE-476 (39), CWE-416 (29)
- codeql: n/a

## Example Cases (Security Agent Only)

- n/a

## Notes

- codeql: results missing.
- security_agent: results missing.
- llm_baseline: no scored samples (check runner configuration).
- static_baseline: results missing.
