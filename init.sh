#!/usr/bin/env bash
# One command: create .venv, install driftpatch with its dev tools, lint, and run every test offline.
set -euo pipefail
cd "$(dirname "$0")"
if command -v uv >/dev/null 2>&1; then
  [ -d .venv ] || uv venv -q --python ">=3.11" .venv
  uv pip install -q --python .venv/bin/python -e ".[dev]"
else
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/python -m pip install -q -e ".[dev]"
fi
# oasdiff is optional. If Go installed it, put it on PATH so its test runs.
if command -v go >/dev/null 2>&1; then export PATH="$(go env GOPATH)/bin:$PATH"; fi
command -v node >/dev/null 2>&1 || { echo "init.sh: Node 22 or newer is needed for the TypeScript client tests"; exit 1; }
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m pytest
echo "init.sh: all checks passed"
