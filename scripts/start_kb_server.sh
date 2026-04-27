#!/usr/bin/env bash
# Start the PaperKB MCP server (HTTP transport)
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python -m src.servers.paper_kb_server "$@"
