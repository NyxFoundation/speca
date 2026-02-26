#!/usr/bin/env bash
# run_rq2_local.sh — Run the full RQ2 benchmark pipeline locally.
#
# Usage:
#   bash benchmarks/scripts/run_rq2_local.sh [dataset] [tools] [limit]
#
# Arguments:
#   dataset  Dataset name: primevul (default), cvefixes, vul4j
#   tools    Comma-separated tool list or "all".
#            Supported: semgrep, codeql, llm, static, security_agent, all
#            Default: semgrep
#   limit    Max samples per tool (0 = all). Default: 0
#
# Examples:
#   bash benchmarks/scripts/run_rq2_local.sh                        # PrimeVul, Semgrep only
#   bash benchmarks/scripts/run_rq2_local.sh primevul all 100       # PrimeVul, all tools, 100 samples
#   bash benchmarks/scripts/run_rq2_local.sh primevul semgrep,codeql
set -euo pipefail

DATASET="${1:-primevul}"
TOOLS="${2:-semgrep}"
LIMIT="${3:-0}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${ROOT_DIR}"

case "${DATASET}" in
  primevul)  DATASET_PATH="benchmarks/data/primevul/primevul_test_paired.jsonl" ;;
  cvefixes)  DATASET_PATH="benchmarks/data/cvefixes/cvefixes_subset_paired.jsonl" ;;
  vul4j)     DATASET_PATH="benchmarks/data/vul4j/vul4j_paired.jsonl" ;;
  *)
    echo "Unsupported dataset: ${DATASET}" >&2
    exit 1
    ;;
esac

RESULTS_DIR="benchmarks/results/rq2/${DATASET}"
mkdir -p "${RESULTS_DIR}"

LIMIT_FLAG=""
if [ "${LIMIT}" -gt 0 ] 2>/dev/null; then
  LIMIT_FLAG="--limit ${LIMIT}"
fi

# ── Step 1: Dataset Setup ──────────────────────────────────────────────
echo "=== Step 1: Dataset Setup (${DATASET}) ==="
if [ -f "${DATASET_PATH}" ]; then
  echo "Dataset already exists at ${DATASET_PATH}; skipping download."
else
  case "${DATASET}" in
    primevul)  uv run python benchmarks/datasets/builders/setup_benchmark.py ;;
    cvefixes)
      bash benchmarks/datasets/fetch_cvefixes.sh
      uv run python benchmarks/datasets/builders/setup_cvefixes_subset.py
      ;;
    vul4j)
      bash benchmarks/datasets/fetch_vul4j.sh
      uv run python benchmarks/datasets/builders/setup_vul4j_from_jsonl.py
      ;;
  esac
fi
echo "Dataset: $(wc -l < "${DATASET_PATH}") lines"

# ── Step 2: Run Tools ──────────────────────────────────────────────────
echo "=== Step 2: Run Tools (${TOOLS}) ==="

run_semgrep() {
  echo "--- Semgrep ---"
  if [ -f "${RESULTS_DIR}/semgrep_results.json" ]; then
    echo "Semgrep results exist; skipping. Delete to re-run."
    return
  fi
  if command -v docker &>/dev/null; then
    docker build -t security-agent-benchmark -f benchmarks/Dockerfile . -q
    docker run --rm --user "$(id -u):$(id -g)" -v "${ROOT_DIR}":/app -e PYTHONPATH=/app security-agent-benchmark \
      python3 /app/benchmarks/runners/run_semgrep.py \
        --dataset "/app/${DATASET_PATH}" \
        --output "/app/${RESULTS_DIR}/semgrep_results.json" \
        --config auto \
        --timeout 60
  else
    echo "Docker not found; skipping Semgrep." >&2
  fi
}

run_codeql() {
  echo "--- CodeQL ---"
  if [ -f "${RESULTS_DIR}/codeql_results.jsonl" ]; then
    echo "CodeQL results exist; skipping."
    return
  fi
  uv run python benchmarks/runners/run_codeql.py \
    --dataset "${DATASET_PATH}" \
    --output "${RESULTS_DIR}/codeql_results.jsonl" \
    --tmp-dir benchmarks/tmp/codeql \
    --timeout 120 \
    --shell \
    ${LIMIT_FLAG}
}

run_llm() {
  echo "--- LLM Baseline ---"
  if [ -f "${RESULTS_DIR}/llm_baseline_results.jsonl" ]; then
    echo "LLM baseline results exist; skipping."
    return
  fi
  # Unset CLAUDECODE to allow nested claude CLI invocation
  unset CLAUDECODE
  uv run python benchmarks/runners/run_llm_baseline.py \
    --dataset "${DATASET_PATH}" \
    --output "${RESULTS_DIR}/llm_baseline_results.jsonl" \
    --tmp-dir benchmarks/tmp/llm_baseline \
    --timeout 60 \
    --shell \
    ${LIMIT_FLAG}
}

run_static() {
  echo "--- Static Baseline ---"
  if [ -f "${RESULTS_DIR}/static_baseline_results.jsonl" ]; then
    echo "Static baseline results exist; skipping."
    return
  fi
  uv run python benchmarks/runners/run_static_baseline.py \
    --dataset "${DATASET_PATH}" \
    --output "${RESULTS_DIR}/static_baseline_results.jsonl" \
    --tmp-dir benchmarks/tmp/static_baseline \
    --timeout 120 \
    --shell \
    ${LIMIT_FLAG}
}

run_security_agent() {
  echo "--- Security Agent ---"
  if [ -f "${RESULTS_DIR}/security_agent_results.jsonl" ]; then
    echo "Security agent results exist; skipping."
    return
  fi
  SA_CMD="${SA_COMMAND:-bash benchmarks/runners/invoke_security_agent.sh {code_path} {output_path} {case_id}}"
  uv run python benchmarks/runners/run_security_agent.py \
    --dataset "${DATASET_PATH}" \
    --output "${RESULTS_DIR}/security_agent_results.jsonl" \
    --tmp-dir benchmarks/tmp/security_agent \
    --command "${SA_CMD}" \
    --shell \
    --timeout 300 \
    ${LIMIT_FLAG}
}

IFS=',' read -ra TOOL_LIST <<< "${TOOLS}"
for tool in "${TOOL_LIST[@]}"; do
  tool=$(echo "${tool}" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
  case "${tool}" in
    all)
      run_semgrep
      run_codeql
      run_llm
      run_static
      run_security_agent
      ;;
    semgrep)          run_semgrep ;;
    codeql)           run_codeql ;;
    llm)              run_llm ;;
    static)           run_static ;;
    security_agent)   run_security_agent ;;
    *)
      echo "Unknown tool: ${tool}" >&2
      ;;
  esac
done

# ── Step 3: Evaluate ──────────────────────────────────────────────────
echo "=== Step 3: Evaluate ==="
uv run python benchmarks/rq2/evaluate.py \
  --dataset "${DATASET}" \
  --dataset-path "${DATASET_PATH}"

# ── Step 4: Generate Report ───────────────────────────────────────────
echo "=== Step 4: Generate Report ==="
uv run python benchmarks/rq2/generate_report.py \
  --metrics benchmarks/results/rq2/metrics.json \
  --output benchmarks/results/rq2/report.md

# ── Step 5: Cache results ─────────────────────────────────────────────
CACHE_DIR="${HOME}/.cache/security-agent/benchmarks/results/${DATASET}"
mkdir -p "${CACHE_DIR}"
cp -rf "${RESULTS_DIR}/." "${CACHE_DIR}/" 2>/dev/null || true
for f in evaluation_summary.json metrics.json report.md; do
  [ -f "benchmarks/results/rq2/${f}" ] && cp "benchmarks/results/rq2/${f}" "${CACHE_DIR}/${f}"
done

echo ""
echo "=== Done ==="
echo "Report:  benchmarks/results/rq2/report.md"
echo "Metrics: benchmarks/results/rq2/metrics.json"
echo "Cache:   ${CACHE_DIR}/"
