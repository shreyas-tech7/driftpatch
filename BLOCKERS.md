# Blockers

Each line: what is blocked, what was tried, and what unblocks it.

- 2026-11-20 LLM record mode: `api.groq.com` and `openrouter.ai` answer the proxy CONNECT with 403, and no provider key is set. Tried one probe each. The LLM row in the README is "not run". Unblock: a machine with network access and `GROQ_API_KEY` set, then `driftpatch bench --proposer llm --llm-mode record`.
- 2026-11-20 Skill installs: the permission system denied `npx skills add` for ponytail, humanizer, security-audit and caveman. Not retried. The review used the skills already present and the rules by hand. Unblock: install them on a machine that allows it and rerun the release check.
- 2026-11-20 GitHub REST API: `api.github.com` answers 403 for the census repos from this machine. The census uses `git ls-remote --tags` and raw file downloads instead, which work.
- 2026-11-20 GitHub repo steps: the `gh` CLI, PR creation and tag pushes do not work from this machine. The build branch is pushed. The PR, the tag, topics and the description are listed in docs/HUMAN_STEPS.md.
- 2026-11-20 Origin has no main. The coordinator brief says never to create main. The branch starts from a fresh first commit. Unblock: create main on GitHub from the first commit of `claude/build-driftpatch`, then open the PR.
