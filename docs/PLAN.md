# Plan

Done means the six points in Part 2 of docs/build/BUILD_PROMPT.md.

1. Sample API and clients (Acme Orders v1, Python and TypeScript clients with tests).
2. Differ with six kinds, then the oasdiff adapter.
3. Call-site finder for Python, then TypeScript.
4. Mock server and verifier with the strict pass rule.
5. Rule proposer, answer key proposer, LLM proposer in replay mode.
6. State machine and guard.
7. Frozen suite of 36 cases and the benchmark with intervals.
8. Census of the Stripe and GitHub spec histories.
9. README written from results, CI, docs, study kit.
10. Release check, hand-off files, bundle and report.

Order matters for the interview point "why the baseline comes before the LLM": the rule proposer sets the bar the LLM has to beat, and the answer key proves every case is solvable.
