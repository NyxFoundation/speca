#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="${ROOT_DIR}/benchmarks/data/cvefixes"
RAW_DIR="${DATA_DIR}/raw"
ZIP_NAME="CVEfixes_v1.0.8.zip"
ZIP_PATH="${RAW_DIR}/${ZIP_NAME}"
DEST_DB="${DATA_DIR}/CVEfixes.db"
CACHE_ROOT="${HOME}/.cache/security-agent/benchmarks"
CACHE_DB="${CACHE_ROOT}/cvefixes/CVEfixes.db"

URL_DEFAULT="https://zenodo.org/records/13118970/files/${ZIP_NAME}?download=1"
URL="${1:-$URL_DEFAULT}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required." >&2
  exit 1
fi
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 is required to build ${DEST_DB}." >&2
  exit 1
fi

mkdir -p "${RAW_DIR}"

if [ -f "${CACHE_DB}" ]; then
  echo "Using cached DB: ${CACHE_DB}"
  cp -f "${CACHE_DB}" "${DEST_DB}"
  echo "Wrote ${DEST_DB}"
  exit 0
fi

echo "Downloading CVEfixes (v1.0.8) to ${ZIP_PATH}..."
curl -L -o "${ZIP_PATH}" "${URL}"

echo "Extracting ${ZIP_PATH}..."
unzip -q "${ZIP_PATH}" -d "${RAW_DIR}"

# Search broadly for database files (case-insensitive, deeper search)
DB_FOUND="$(find "${RAW_DIR}" -maxdepth 8 -type f \( -iname "*.db" -o -iname "*.sqlite" -o -iname "*.sqlite3" -o -iname "CVEfixes*" \) 2>/dev/null | head -n 1 || true)"
if [ -n "${DB_FOUND}" ]; then
  echo "Found DB: ${DB_FOUND}"
  cp -f "${DB_FOUND}" "${DEST_DB}"
  mkdir -p "$(dirname "${CACHE_DB}")"
  cp -f "${DEST_DB}" "${CACHE_DB}"
  echo "Wrote ${DEST_DB}"
  exit 0
fi

SQL_FOUND="$(find "${RAW_DIR}" -maxdepth 8 -type f -iname "*.sql" 2>/dev/null | head -n 1 || true)"
if [ -z "${SQL_FOUND}" ]; then
  echo "=== DEBUG: Listing extracted files (top 50) ===" >&2
  find "${RAW_DIR}" -maxdepth 4 -type f 2>/dev/null | head -50 >&2
  echo "=== DEBUG: Largest files ===" >&2
  find "${RAW_DIR}" -maxdepth 4 -type f -exec ls -lhS {} + 2>/dev/null | head -10 >&2
  echo "" >&2
  echo "No .db or .sql found after extraction." >&2
  echo "If the archive contains CSV files, place a pre-built CVEfixes.db at ${DEST_DB}." >&2
  exit 1
fi

echo "Building SQLite DB from ${SQL_FOUND}..."
rm -f "${DEST_DB}"
sqlite3 "${DEST_DB}" < "${SQL_FOUND}"
mkdir -p "$(dirname "${CACHE_DB}")"
cp -f "${DEST_DB}" "${CACHE_DB}"
echo "Wrote ${DEST_DB}"
