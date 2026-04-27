#!/usr/bin/env bash
# Full test suite (all phases)
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${CONDA_PREFIX:-/home/hansz/scratch-data/tools/miniconda3/envs/academic-mcp}/bin/python"
"$PYTHON" -m pytest tests/ -v "$@"
