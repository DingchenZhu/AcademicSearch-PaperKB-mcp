#!/usr/bin/env bash
# V0 tests: arXiv search (unit + httpx-mocked integration)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${CONDA_PREFIX:-/home/hansz/scratch-data/tools/miniconda3/envs/academic-mcp}/bin/python"
"$PYTHON" -m pytest tests/test_paper_search.py tests/test_v0_search.py -v "$@"
