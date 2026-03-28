# Rule: Update Docs After Changes

After modifying code that changes behavior, update:

1. The relevant spec in `specs/` if the interface or behavior changed
2. `docs/architecture.md` if the system structure changed
3. `docs/quality.md` scorecard if a domain's quality level changed
4. `AGENTS.md` if directory structure or key commands changed

Divergence between docs and code is treated as a bug.
