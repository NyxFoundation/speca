#!/usr/bin/env bash
set -euo pipefail

echo "Verifying and setting up MCP servers..."

SERVERS=("tree_sitter" "serena" "semgrep")
COMMANDS=(
  "uvx mcp-server-tree-sitter"
  "uvx --from git+https://github.com/oraios/serena serena start-mcp-server"
  "uvx semgrep-mcp"
)

for i in "${!SERVERS[@]}"; do
  SERVER_NAME="${SERVERS[$i]}"
  SERVER_COMMAND="${COMMANDS[$i]}"

  if claude mcp list | grep -q "${SERVER_NAME}"; then
    echo "MCP server '${SERVER_NAME}' already registered."
    continue
  fi

  # if [ -f ".mcp.json" ] && grep -q "\"${SERVER_NAME}\"" ".mcp.json"; then
  #   echo "MCP server '${SERVER_NAME}' already registered in .mcp.json."
  #   continue
  # fi

  echo "Registering MCP server '${SERVER_NAME}'..."
  if ! ADD_OUTPUT=$(claude mcp add --scope project --transport stdio "${SERVER_NAME}" -- ${SERVER_COMMAND} 2>&1); then
    if echo "${ADD_OUTPUT}" | grep -qi "already exists"; then
      echo "MCP server '${SERVER_NAME}' already exists; skipping."
    else
      echo "${ADD_OUTPUT}"
      exit 1
    fi
  fi
done

echo
echo "Final MCP server list:"
claude mcp list

if [ -f ".mcp.json" ]; then
  echo
  echo "Contents of .mcp.json:"
  cat .mcp.json
else
  echo
  echo ".mcp.json not found. MCP servers might be registered at user scope."
fi
