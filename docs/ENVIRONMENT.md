# Environment

Probed once on 2026-11-20 from the build machine.

| Host | Result |
| --- | --- |
| pypi.org `driftpatch` | 404 (name free) |
| registry.npmjs.org `driftpatch` | 404 (name free) |
| api.github.com (stripe/openapi, github/rest-api-description) | 403 from the proxy |
| raw.githubusercontent.com (stripe spec3.json) | 200 |
| `git ls-remote --tags` on both census repos | works |
| proxy.golang.org | 200 (used to install oasdiff, gitleaks, actionlint) |
| api.groq.com, openrouter.ai, huggingface.co | CONNECT tunnel 403 |
| api.osv.dev, semgrep.dev | CONNECT tunnel 403 |

No model provider key is set.

## Machine

- Python 3.13 in `.venv` made by uv. CI uses Python 3.11.
- Node v22 (type stripping runs the TypeScript client with no npm packages).
- Go 1.24, which installed oasdiff 1.39.0, gitleaks v8.30.1 and actionlint into `$(go env GOPATH)/bin`.
- 4 cores visible. The 2-core timing uses `taskset -c 0,1`.

## What this means

- The census runs here, through tags and raw downloads.
- LLM record mode cannot run here. See BLOCKERS.md.
- pip-audit works here through the PyPI advisory service. api.osv.dev is blocked, so its OSV mode does not.
