#!/usr/bin/env bash
# Start the AcademicSearch MCP server (HTTP transport)
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python -m src.servers.academic_search_server "$@"
