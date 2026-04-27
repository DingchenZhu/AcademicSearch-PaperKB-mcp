#!/usr/bin/env bash
# V1 tests: PDF ingest pipeline + KB store + KBRetriever
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${CONDA_PREFIX:-/home/hansz/scratch-data/tools/miniconda3/envs/academic-mcp}/bin/python"
"$PYTHON" -m pytest tests/test_pdf_ingest.py tests/test_kb_store.py tests/test_v1_ingest.py -v "$@"
