# Human steps

Steps that only Shreyas can do, in order. While Shreyas was away, Claude was allowed to open and merge the pull request, create the pre-release and set the About box and topics. Check each of those on GitHub before you redo it.

Release commit: this commit.

The commits after the release commit only record this SHA and the hand-off notes. Tag the release commit.

## 1. Create main on GitHub, if it is missing

The GitHub repo was empty when the build started, and the build was told never to create `main`. So `claude/build-driftpatch` starts from a fresh first commit, `6d779fe0e90217e0713fd650bbae409ad45b41d6`. If `main` is still missing, create it from that commit before you open the pull request:

```bash
git fetch origin
git push origin 6d779fe0e90217e0713fd650bbae409ad45b41d6:refs/heads/main
```

Then set `main` as the default branch in Settings, General.

## 2. Check that CI runs

Open the Actions tab. The `CI` workflow should finish green on `claude/build-driftpatch` in under five minutes. The build session also ran every CI step locally and all passed.

## 3. Open and merge the pull request

1. Open a pull request from `claude/build-driftpatch` into `main`, unless one is already merged.
2. Read the diff.
3. Merge with a merge commit, not a squash, so the release commit stays in the history of `main`.

## 4. Tag the release candidate

```bash
git fetch origin
git tag -a v0.1.0-rc1 RELEASE_SHA -m "Release candidate 1"
git push origin v0.1.0-rc1
```

Or create a pre-release with that tag on GitHub.

## 5. Run the secret scan once more

```bash
gitleaks git -v .
```

The build ran it on the full history with no findings.

## 6. Record mode on a free provider

This is the step the build could not do. The proxy blocked every model host (`BLOCKERS.md`). Without it, the README has no LLM numbers.

1. Create a free key at Groq (https://console.groq.com/keys). Check the free limits first. Send only the synthetic Acme cases.
2. Run locally:

   ```bash
   ./init.sh
   export GROQ_API_KEY=your-key            # never commit it
   .venv/bin/driftpatch bench --proposer llm --llm-mode record
   .venv/bin/driftpatch bench --proposer llm
   .venv/bin/driftpatch readme
   ```

3. Commit `fixtures/llm/`, `results/bench-llm.json` and the README.

## 7. Make the repo public

All history becomes public at that moment. Read `docs/build/BUILD_PROMPT.md` first.

## 8. Turn on Pages

Settings, Pages, deploy from the `main` branch and the `/docs` folder. `docs/index.html` is the results page. Put the Pages URL in the About box.

## 9. Social preview, About box and topics

- Upload `docs/social-preview.png` in Settings, General, Social preview.
- The description is in `docs/GITHUB_ABOUT.md`. The topics are in `docs/topics.txt`, one per line.

## 10. Pin the repo

Pin it on your profile, or list it in your profile README.

## 11. Publish to PyPI (optional)

The name `driftpatch` answered 404 on PyPI on 2026-11-20. If you want the package, set up trusted publishing on PyPI for this repo and add a release workflow. The build did not do this.

## 12. Install oasdiff in CI (optional)

CI skips the real oasdiff test because oasdiff is not installed there. Adding `go install github.com/oasdiff/oasdiff@v1.39.0` to the workflow turns it on, at the cost of a slower run.

## 13. Decide whether the build prompt stays public

`docs/build/BUILD_PROMPT.md` holds the full prompt the agents followed. Keep it, trim it or remove it before the repo goes public.

## 14. Update the human checks in the README

The README lists three human checks as "not done yet". Change each one only after you do it.
