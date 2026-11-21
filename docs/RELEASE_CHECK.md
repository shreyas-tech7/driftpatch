# Release check

Run on 2026-11-20 before the v0.1.0-rc1 release commit. Each line says what ran and what it found.

| Check | Tool | Result |
| --- | --- | --- |
| Secret scan, full git history | gitleaks v8.30.1, `gitleaks git .` | No leaks found |
| Secret scan, working tree | gitleaks v8.30.1, `gitleaks dir .` | Findings only in `data/census-cache/`, which is ignored by git and never committed. They are the sample keys inside Stripe's public spec examples. |
| Dependency audit | pip-audit 2.10.1 on the 6 packages pinned by `uv pip freeze` from `.venv` | No known vulnerabilities. driftpatch itself is not on PyPI, so it was left out. |
| Security lint | ruff 0.17.6, `ruff check --select S src scripts` | 9 findings, each reviewed and marked with a reason (see below). 0 left open. |
| Workflow lint | actionlint v1.7.12 | No findings |
| Links | `scripts/check_links.py` | 0 errors. 4 external links listed, not fetched. |
| Writing rules | `tests/test_repo_quality.py::test_writing_rules` (humanizer rules by hand) | Pass on every doc |
| Code review | superpowers code review and the simplify pass (ponytail rules by hand) | See below |
| Security audit | the built-in security review, by hand | See below |
| Outside check | a separate subagent that read the repo cold | See below |

The ponytail, humanizer, security-audit and caveman skills could not be installed (`BLOCKERS.md`). Their checks were done with the tools above and by hand.

## ruff check --select S

- S603 and S607 (subprocess): `verifier.py`, `oasdiff.py` and `census.py` run fixed argument lists with no shell and a timeout.
- S310 (urlopen): `proposer_llm.py` only takes an https endpoint, `census.py` only builds raw.githubusercontent.com URLs.
- S311 (random): the case split and the bootstrap use seeded `random` for statistics, not for security.
- S314 (XML): `verifier.py` parses the JUnit file written by the test run it started. The client code in that run already runs as the user.

## Code review and security audit

- Patch paths: `safe_relpath` refuses absolute paths, `..`, backslashes, drive letters and NUL, and `write_files` checks the resolved target stays inside the client folder, so a symlink cannot lead out.
- Model answers: `parse_answer` accepts only the files that were sent and never a test file.
- Mock server: binds to 127.0.0.1 or localhost only.
- Secrets: the verifier strips `*_API_KEY`, `*_TOKEN` and `*_SECRET` variables before it runs client tests. Recorded fixtures hold the answer and token counts, not the key (tested).
- oasdiff runs with `--allow-external-refs=false`, so an untrusted spec cannot make it fetch a URL.
- Found and fixed during the check: the oasdiff adapter passed `--color never`, which oasdiff 1.39.0 refuses with JSON output. The real oasdiff test caught it.
- Found and documented: the audit hook guard covers the driftpatch process, not the client's test processes. The README Limits part says so.

## Outside check

A separate subagent read the repo cold, ran the tests and tried to break the claims. It reported these findings. Each was fixed with a test that failed first, or written into the docs.

| Finding | Level | What was done |
| --- | --- | --- |
| The guard missed `os.system`, `os.exec*`, `os.spawn*` and `os.posix_spawn*`, and a push hidden in an alias such as `git -c alias.p=push p` | High | Fixed in `guard.py`. Four new tests in `tests/test_guard.py` failed on the old guard and pass now. |
| The guard missed UDP sends and name lookups | High | `socket.sendto`, `socket.sendmsg` and `socket.getaddrinfo` are checked. Tested. |
| Only `run` was guarded, while `patch` and `bench` can call a model | High | `main` turns the guard on for every command except `census`. Tested. |
| `INTERVIEW_QA.md` said the guard blocks a push "in any form" and did not say child processes are outside it | Medium | Rewritten to say what is covered and what is not. |
| Python `ast` columns are byte offsets, so a non-ASCII line broke the rule patch | Medium | Fixed with `PyIndex`. The new test failed first. |
| `splitlines` split on form feed and other characters that are not line ends | Medium | Line splitting uses only `\n`, `\r\n` and `\r`. Tested. |
| A renamed path parameter showed up as a removed endpoint | Medium | Path parameters are matched by position. Tested. |
| Two tests with the same name (Node) counted as one | Medium | Duplicates are kept with a `#2` suffix. Tested. |
| The client's tests saw every variable in the caller's environment | Medium | The verifier passes an allow list only. A test proves a planted token does not reach the client. |
| Code under test could plant its own JUnit report | Medium | The report is written outside the client copy. Tested. |
| A patched run that crashed after writing results could still pass | Low | A nonzero exit code is now a failure reason. |
| A removed line that starts with `-- ` was read as a file header | Low | The diff parser reads hunks by their header counts. Tested. |
| The mock server allowed `::1` on an IPv4 socket | Low | Only 127.0.0.1 and localhost are allowed. |
| `run_case` stopped the bench on a record mode error | Low | It now marks the case "not run". |
| The README said tests run twice per case and did not say how declined cases count | Low | The README says up to three runs and that a declined case counts with its unpatched pass rate. |

While proving the guard tests against the old guard, one planted `git push origin main` really ran from the repo folder. It failed (there is no local main) and `git ls-remote origin` showed no change. Those tests now run from an empty temp folder.
