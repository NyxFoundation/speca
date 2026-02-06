Benchmark RQ1/RQ2 Overview

This repo defines two quantitative evaluation tracks:
- RQ1: How well the security agent finds real-world audit contest bugs, including bugs missed by humans.
- RQ2: How well the agent compares to traditional static tools / fuzzing baselines on labeled datasets.

RQ1: Sherlock Audit Contest (Audit Map vs Issues)

Method
- Inputs: audit findings JSON (03_PARTIAL_*.json / 03_AUDITMAP_PARTIAL_*.json) produced by the agent and the Sherlock contest issue CSV.
- Matching: 3-stage matching (text similarity, token overlap, keyword candidate selection + optional LLM adjudication).
- Output: overlap vs new findings, per-branch summaries, matching details.
- Optional: statistical comparison vs a baseline run, and human-label precision on sampled "new" findings.
- Code: see `benchmarks/rq1/` (matchers, stats, evaluate). `benchmarks/rq1/cli.py` is the CLI wrapper.

Core metrics
- overlap_rate: fraction of audit items matched to known issues.
- new_rate: fraction of audit items not matched (candidate novel findings).
- issue_recall: fraction of known issues matched by at least one audit item.
- stage_counts: how many matches came from each matching stage.
- llm_calls: number of LLM adjudications used.
- overlap_rate_ci / new_rate_ci: bootstrap confidence intervals.
- baseline_comparison: McNemar exact test + Cliff's delta effect size vs baseline results (if provided).
- human_eval: precision of sampled items judged true bugs (if labels provided).

How to run (local)
1) Evaluate branches (optionally with LLM)
   uv run python benchmarks/rq1/cli.py \
     --branches "branchA,branchB" \
     --use-llm

2) Compare against a baseline evaluation directory
   uv run python benchmarks/rq1/cli.py \
     --branches "branchA,branchB" \
     --use-llm \
     --baseline-results /path/to/baseline_results_dir

3) Generate human-eval sample (default: new_only)
   uv run python benchmarks/rq1/cli.py \
     --branches "branchA,branchB" \
     --use-llm \
     --human-scope new_only \
     --human-sample-size 100

4) Aggregate human labels (JSONL with branch, item_id, and label/is_bug/etc.)
   uv run python benchmarks/rq1/cli.py \
     --branches "branchA,branchB" \
     --use-llm \
     --human-scope new_only \
     --human-labels /path/to/labels.jsonl \
     --human-labels-report /path/to/labels_report.json

Human label format
- Input: JSONL, one JSON object per line.
- Required keys: "branch", "item_id".
- Label keys (any one): "label", "is_valid_bug", "is_bug", "is_true_positive", "valid", "bug", "verdict".
- Label values accepted: true/false, 1/0, yes/no, vulnerable/clean.

Example label row
{"branch":"branchA","item_id":"123","label":true,"notes":"confirmed bug"}

Template
- benchmarks/human_labels_template.jsonl

Labeling guidance (recommended)
- For new_only sampling: label "true" only if it is a real bug not already in the contest issues.
- Use the audit item text/snippet + file/line to locate code context.
- If unsure, mark false and add a note for adjudication.

Outputs
- benchmarks/results/rq1/sherlock_ethereum_audit_contest/evaluation_summary.json
- benchmarks/results/rq1/sherlock_ethereum_audit_contest/evaluation_<branch>.json
- benchmarks/results/rq1/sherlock_ethereum_audit_contest/human_eval_sample.jsonl (if requested)
- benchmarks/results/rq1/sherlock_ethereum_audit_contest/evaluation_summary.md

Workflow (GitHub Actions)
- .github/workflows/benchmark-rq1-sherlock-eval.yml

RQ2: PrimeVul Tool Comparison

Method
- Dataset: PrimeVul test paired JSONL (vulnerable vs clean pairs).
- Tools: Semgrep, CodeQL, Security Agent runner, optional LLM baseline, optional static baseline.
- Output: confusion metrics, pairwise correctness, CWE coverage, unique detections.
- Statistical comparison between Security Agent and baselines.

Core metrics
- precision / recall / f1 / accuracy / coverage
- tp / fp / tn / fn, error_count
- pairwise accuracy on paired cases (vuln vs clean)
- CWE coverage and missed CWE counts
- unique detections by the security agent
- pairwise_stats: McNemar exact test + Cliff's delta effect size and bootstrap CIs for metric diffs

How to run (GitHub Actions)
1) Setup dataset:
   .github/workflows/benchmark-rq2-01-setup.yml
2) Run tools:
   .github/workflows/benchmark-rq2-02-tools.yml
   - tools: "all" or comma-separated (semgrep, codeql, security_agent, llm, static)
   - security_agent_command / llm_command / static_command required when selecting those tools
   - if tools=all, provide the command inputs for all non-automatic tools
3) Evaluate:
   .github/workflows/benchmark-rq2-03-evaluate.yml

How to run (local)
1) Ensure dataset exists at:
   benchmarks/data/primevul/primevul_test_paired.jsonl
2) Run tools (examples):
   uv run python benchmarks/runners/run_semgrep.py
   uv run python benchmarks/runners/run_codeql.py --dataset ... --output ...
   uv run python benchmarks/runners/run_security_agent.py --command "..."
   uv run python benchmarks/runners/run_llm_baseline.py --command "..."
   uv run python benchmarks/runners/run_static_baseline.py --tool-name infer --command "..."
3) Evaluate:
   uv run python benchmarks/rq2/evaluate.py --dataset primevul

Optional report:
   uv run python benchmarks/rq2/generate_report.py --rq1-summary benchmarks/results/rq1/sherlock_ethereum_audit_contest/evaluation_summary.json

Metadata capture
- RQ1: pass --metadata /path/to/metadata.json to rq1/cli.py
- RQ2: set BENCHMARK_METADATA_PATH=/path/to/metadata.json when running rq2/evaluate.py
- Tool runners: --version-command and --timeout are available for codeql/security_agent/llm/static runners

Additional datasets (distributed OSS + Java)
- CVEfixes subset (distributed systems OSS):
  - Requires a local CVEfixes SQLite DB.
  - Build subset:
    uv run python benchmarks/datasets/builders/setup_cvefixes_subset.py \
      --db /path/to/CVEfixes.db \
      --output benchmarks/data/cvefixes/cvefixes_subset_paired.jsonl
  - Optional: pass --repos to override the default distributed-OSS list.
- Vul4J (Java):
  - Export or prepare a JSONL with before/after code pairs.
  - Convert:
    uv run python benchmarks/datasets/builders/setup_vul4j_from_jsonl.py \
      --input /path/to/vul4j_export.jsonl \
      --output benchmarks/data/vul4j/vul4j_paired.jsonl
  - Evaluate:
    uv run python benchmarks/rq2/evaluate.py --dataset vul4j

Static baselines (paper-backed)
- C/C++: Infer (TACAS/SV-COMP)
  Example command template (per-sample):
    infer run --quiet -- clang -c {code_path} && \
      python benchmarks/runners/emit_prediction_from_infer.py \
        --infer-json infer-out/report.json \
        --output {output_path}
- Java: SpotBugs (FindBugs successor; FindBugs was published at OOPSLA)
  Example command template (per-sample):
    spotbugs -textui -xml:withMessages -output spotbugs.xml {code_path} && \
      python benchmarks/runners/emit_prediction_from_spotbugs.py \
        --spotbugs-xml spotbugs.xml \
        --output {output_path}

Note: the above templates are placeholders; adapt to your tool output by setting
predicted_vulnerable based on findings count.

Outputs
- benchmarks/results/rq2/metrics.json
- benchmarks/results/rq2/evaluation_summary.json

Notes
- Statistical outputs are intended for CCS/USENIX-style reporting.
- For fair comparisons, fix tool versions and resource limits, and record configs in the run metadata.
