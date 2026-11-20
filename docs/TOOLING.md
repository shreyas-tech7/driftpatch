# Tooling

| Tool | Version | Used for | How it got here |
| --- | --- | --- | --- |
| uv | system | venv and installs | present |
| ruff | from `.[dev]` | lint and format | `./init.sh` |
| pytest | from `.[dev]` | tests | `./init.sh` |
| Node | 22 | TypeScript client tests | present |
| oasdiff | 1.39.0 | optional second differ | `go install github.com/oasdiff/oasdiff@v1.39.0` |
| gitleaks | v8.30.1 | secret scan, pre-commit hook | `go install` |
| actionlint | latest at build time | CI workflow lint | `go install` |
| pip-audit, pre-commit | latest at build time | release check | `uv tool install` |

## Skills

The build prompt asks for the ponytail, humanizer, security-audit and caveman skills. `npx skills add` was denied by the permission system on 2026-11-20 and not retried. The release check used the skills already present (superpowers, the built-in security review and simplify skills) and applied the humanizer and Ponytail rules by hand.
