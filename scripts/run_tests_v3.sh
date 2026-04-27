#!/usr/bin/env bash
# Run V3 test suite: paragraph chunking, Semantic Scholar, REST API, MCP end-to-end
set -euo pipefail
PYTHON=/home/hansz/scratch-data/tools/miniconda3/envs/academic-mcp/bin/python
$PYTHON -m pytest \
  tests/test_v3_chunking.py \
  tests/test_v3_semantic_scholar.py \
  tests/test_v3_rest_api.py \
  tests/test_v3_mcp_server.py \
  -v "$@"
