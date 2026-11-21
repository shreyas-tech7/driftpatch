#!/usr/bin/env bash
# Write docs/DEMO.md from a real terminal session. Run from the repo root after ./init.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
DP=.venv/bin/driftpatch
V1=examples/acme/specs/acme-orders-v1.json
V2=examples/acme/specs/acme-orders-v2.json
run() {
  echo '```console'
  echo "\$ driftpatch ${*}"
  timeout 300 "$DP" "$@" 2>&1
  echo "(exit code $?)"
  echo '```'
  echo
}
rm -rf out/demo
{
  echo "# Demo"
  echo
  echo "A real terminal session, written by \`scripts/make_demo.sh\` on $(date -u +%Y-%m-%d). Each block shows the exit code."
  echo
  echo "## List the breaking changes between v1 and v2"
  echo
  run diff "$V1" "$V2"
  echo "## Find the call sites in the TypeScript client"
  echo
  run find "$V1" "$V2" examples/acme/clients/ts
  echo "## Run the whole pipeline on the Python client"
  echo
  run run "$V1" "$V2" examples/acme/clients/python --out out/demo
  echo "## The patch it wrote"
  echo
  echo '```diff'
  cat out/demo/patch.diff
  echo '```'
  echo
  echo "## A case the rule baseline declines"
  echo
  run run "$V1" bench/cases/C031/new.json examples/acme/clients/python --out out/demo-declined
  echo "## Confirm the README tables"
  echo
  run readme --check
} > docs/DEMO.md
echo "wrote docs/DEMO.md"
