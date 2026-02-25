#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="${ROOT_DIR}/benchmarks/data/vul4j"
RAW_DIR="${DATA_DIR}/raw"
ZIP_NAME="vul4j.zip"
ZIP_PATH="${RAW_DIR}/${ZIP_NAME}"
EXPORT_JSONL="${DATA_DIR}/vul4j_export.jsonl"
CACHE_ROOT="${HOME}/.cache/security-agent/benchmarks"
CACHE_EXPORT="${CACHE_ROOT}/vul4j/vul4j_export.jsonl"

URL_DEFAULT="https://zenodo.org/record/6383527/files/${ZIP_NAME}?download=1"
URL="${1:-$URL_DEFAULT}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required." >&2
  exit 1
fi

mkdir -p "${RAW_DIR}"

if [ -f "${CACHE_EXPORT}" ]; then
  echo "Using cached export: ${CACHE_EXPORT}"
  cp -f "${CACHE_EXPORT}" "${EXPORT_JSONL}"
  echo "Wrote ${EXPORT_JSONL}"
  exit 0
fi

echo "Downloading Vul4J to ${ZIP_PATH}..."
curl -L -o "${ZIP_PATH}" "${URL}"

echo "Extracting ${ZIP_PATH}..."
unzip -q "${ZIP_PATH}" -d "${RAW_DIR}"

# Search for JSONL files
JSONL_FOUND="$(find "${RAW_DIR}" -maxdepth 8 -type f -iname "*.jsonl" 2>/dev/null | head -n 1 || true)"
if [ -n "${JSONL_FOUND}" ]; then
  echo "Found JSONL: ${JSONL_FOUND}"
  cp -f "${JSONL_FOUND}" "${EXPORT_JSONL}"
  mkdir -p "$(dirname "${CACHE_EXPORT}")"
  cp -f "${EXPORT_JSONL}" "${CACHE_EXPORT}"
  echo "Wrote ${EXPORT_JSONL}"
  exit 0
fi

# Try JSON files (Vul4J metadata)
JSON_FOUND="$(find "${RAW_DIR}" -maxdepth 8 -type f -iname "*.json" 2>/dev/null | head -n 1 || true)"
if [ -n "${JSON_FOUND}" ]; then
  echo "Found JSON (not JSONL): ${JSON_FOUND}"
  echo "Attempting to convert to JSONL..."
  # If it's a JSON array, convert each element to a line
  python3 - "${JSON_FOUND}" "${EXPORT_JSONL}" <<'PYEOF'
import json, sys
json_path = sys.argv[1]
export_path = sys.argv[2]
with open(json_path) as f:
    data = json.load(f)
if isinstance(data, list):
    with open(export_path, 'w') as out:
        for item in data:
            out.write(json.dumps(item) + '\n')
    print(f'Converted {len(data)} records to {export_path}')
else:
    print('JSON is not an array, cannot auto-convert.', file=sys.stderr)
    sys.exit(1)
PYEOF
  if [ -f "${EXPORT_JSONL}" ]; then
    mkdir -p "$(dirname "${CACHE_EXPORT}")"
    cp -f "${EXPORT_JSONL}" "${CACHE_EXPORT}"
    exit 0
  fi
fi

echo "=== DEBUG: Listing extracted files (top 50) ===" >&2
find "${RAW_DIR}" -maxdepth 4 -type f 2>/dev/null | head -50 >&2
echo "=== DEBUG: Largest files ===" >&2
find "${RAW_DIR}" -maxdepth 4 -type f -exec ls -lhS {} + 2>/dev/null | head -10 >&2
echo "" >&2
echo "No JSONL export found. Place a Vul4J JSONL export at ${EXPORT_JSONL}." >&2
echo "Then run: uv run python benchmarks/datasets/builders/setup_vul4j_from_jsonl.py" >&2
exit 2
