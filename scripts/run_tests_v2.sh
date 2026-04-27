#!/usr/bin/env bash
# V2 tests: FaissRetriever + factory
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${CONDA_PREFIX:-/home/hansz/scratch-data/tools/miniconda3/envs/academic-mcp}/bin/python"
"$PYTHON" -m pytest tests/test_v2_faiss.py -v "$@"
