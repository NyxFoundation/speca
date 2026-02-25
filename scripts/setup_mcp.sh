#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# MCP Server Setup Script
# =============================================================================
#
# Registers Model Context Protocol (MCP) servers for the security audit agent.
#
# Usage:
#   bash scripts/setup_mcp.sh                    # Register all servers
#   bash scripts/setup_mcp.sh --verify           # Verify registered servers
#   FILESYSTEM_DIRS=". target_workspace" bash scripts/setup_mcp.sh
#
# Environment Variables:
#   FILESYSTEM_DIRS  - Space-separated directories for filesystem MCP (default: ".")
#   GITHUB_TOKEN     - Required for github MCP server (GitHub API access)
#
# Phase-to-MCP-Server Mapping:
#   Phase 01a (spec-discovery)        -> fetch (primary), browser (fallback)
#   Phase 01b (subgraph-extractor)    -> filesystem, tree_sitter
#   Phase 01c (subgraph-verifier)     -> filesystem
#   Phase 01d (trust-model-analyst)   -> filesystem
#   Phase 01e (property-generator)    -> (none)
#   Phase 02  (checklist-specialist)  -> github
#   Phase 03  (formal-audit-phase*)   -> tree_sitter, filesystem
#   Phase 04  (inline review)          -> (none — uses Read/Grep/Glob)
#
# =============================================================================

FILESYSTEM_DIRS="${FILESYSTEM_DIRS:-.}"

# =============================================================================
# Prerequisite Checks
# =============================================================================

check_prerequisites() {
  local missing=()

  if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: 'claude' CLI is required but not found."
    echo "  Install: https://docs.anthropic.com/en/docs/claude-code"
    exit 1
  fi

  if ! command -v npx >/dev/null 2>&1; then
    missing+=("npx (install Node.js: https://nodejs.org/)")
  fi

  if ! command -v uvx >/dev/null 2>&1; then
    missing+=("uvx (install uv: https://docs.astral.sh/uv/)")
  fi

  if [ "${#missing[@]}" -gt 0 ]; then
    echo "ERROR: Missing required tools:"
    for tool in "${missing[@]}"; do
      echo "  - ${tool}"
    done
    exit 1
  fi

  # Resolve GitHub token from available env vars
  RESOLVED_GH_TOKEN="${GITHUB_PERSONAL_ACCESS_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"
  if [ -z "${RESOLVED_GH_TOKEN}" ]; then
    echo "WARNING: No GitHub token found."
    echo "  The 'github' MCP server requires GITHUB_PERSONAL_ACCESS_TOKEN for API access."
    echo "  Checked: GITHUB_PERSONAL_ACCESS_TOKEN, GH_TOKEN, GITHUB_TOKEN"
    echo "  Set one of them: export GH_TOKEN=ghp_..."
    echo
  else
    export GITHUB_PERSONAL_ACCESS_TOKEN="${RESOLVED_GH_TOKEN}"
    echo "GitHub token resolved (for github MCP server)."
  fi
}

# =============================================================================
# MCP Server Configuration
# =============================================================================

build_filesystem_args() {
  local args=""
  # shellcheck disable=SC2086 -- Intentional word splitting: FILESYSTEM_DIRS is a space-separated list
  for dir in ${FILESYSTEM_DIRS}; do
    # Resolve to absolute path
    local abs_dir
    abs_dir="$(cd "${dir}" 2>/dev/null && pwd)" || abs_dir="${dir}"
    args="${args} ${abs_dir}"
  done
  echo "${args}"
}

SERVERS=(
  "tree_sitter"
  "serena"
  "semgrep"
  "filesystem"
  "fetch"
  "github"
)

FS_ARGS=$(build_filesystem_args)

COMMANDS=(
  "uvx mcp-server-tree-sitter"
  "uvx --from git+https://github.com/oraios/serena serena start-mcp-server --open-web-dashboard False"
  "uvx semgrep-mcp"
  "npx -y @modelcontextprotocol/server-filesystem${FS_ARGS}"
  "uvx mcp-server-fetch"
  "npx -y @modelcontextprotocol/server-github"
)

DESCRIPTIONS=(
  "Code parsing and symbol extraction (Phase 01b, 03)"
  "Development workflow automation"
  "Static analysis for security vulnerabilities"
  "File system access for audit artifacts (Phase 01b-04)"
  "HTTP fetch for external specifications (Phase 01a)"
  "GitHub API for repository analysis (Phase 02)"
)

# =============================================================================
# Verify Mode
# =============================================================================

verify_servers() {
  echo "Verifying MCP server registration..."
  echo

  local registered
  registered=$(claude mcp list 2>/dev/null || echo "")
  local all_ok=true

  for i in "${!SERVERS[@]}"; do
    local name="${SERVERS[$i]}"
    local desc="${DESCRIPTIONS[$i]}"
    if echo "${registered}" | grep -q "${name}"; then
      echo "  [OK] ${name}: ${desc}"
    else
      echo "  [MISSING] ${name}: ${desc}"
      all_ok=false
    fi
  done

  echo
  if [ "${all_ok}" = true ]; then
    echo "All MCP servers are registered."
  else
    echo "Some MCP servers are missing. Run 'make mcp-setup' to register them."
    return 1
  fi
}

if [ "${1:-}" = "--verify" ]; then
  verify_servers
  exit $?
fi

# =============================================================================
# Registration
# =============================================================================

echo "Verifying and setting up MCP servers..."
echo

check_prerequisites

echo "Filesystem MCP scope: ${FILESYSTEM_DIRS}"
echo "Registering ${#SERVERS[@]} MCP servers..."
echo

for i in "${!SERVERS[@]}"; do
  SERVER_NAME="${SERVERS[$i]}"
  SERVER_COMMAND="${COMMANDS[$i]}"
  SERVER_DESC="${DESCRIPTIONS[$i]}"

  echo "[$((i+1))/${#SERVERS[@]}] ${SERVER_NAME}: ${SERVER_DESC}"

  if claude mcp list 2>/dev/null | grep -q "${SERVER_NAME}"; then
    echo "  ✓ Already registered."
    continue
  fi

  echo "  → Registering..."
  # Build env flags for servers that need tokens
  ENV_FLAGS=""
  if [ "${SERVER_NAME}" = "github" ] && [ -n "${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ]; then
    ENV_FLAGS="--env GITHUB_PERSONAL_ACCESS_TOKEN=${GITHUB_PERSONAL_ACCESS_TOKEN}"
  fi
  # shellcheck disable=SC2086 -- Intentional word splitting: ENV_FLAGS and SERVER_COMMAND contain multiple arguments
  if ! ADD_OUTPUT=$(claude mcp add --scope project --transport stdio ${ENV_FLAGS} "${SERVER_NAME}" -- ${SERVER_COMMAND} 2>&1); then
    if echo "${ADD_OUTPUT}" | grep -qi "already exists"; then
      echo "  ✓ Already exists; skipping."
    else
      echo "  ✗ Error: ${ADD_OUTPUT}"
      exit 1
    fi
  else
    echo "  ✓ Registered successfully."
  fi
done

echo
echo "=========================================="
echo "Final MCP server list:"
echo "=========================================="
claude mcp list

if [ -f ".mcp.json" ]; then
  echo
  echo "=========================================="
  echo "Contents of .mcp.json:"
  echo "=========================================="
  cat .mcp.json
else
  echo
  echo ".mcp.json not found. MCP servers might be registered at user scope."
fi

echo
echo "MCP setup complete."
