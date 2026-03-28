# Workflow: Implement and Verify

1. **Read spec** — Open the relevant spec in `specs/`. Understand inputs, outputs, constraints.
2. **Implement** — Write the code following the spec. Include type hints and docstrings for public methods.
3. **Write tests** — Create tests covering happy path + key error cases.
4. **Run tests** — `pytest tests/test_<module>.py -v`. All must pass.
5. **Self-review** — Check: Does code match spec? Are edge cases handled? Any security issues?
6. **Fix issues** — Address any problems found. Re-run tests. Max 3 iterations.
7. **Update docs** — Update `docs/quality.md` scorecard. Update spec if implementation required changes.
