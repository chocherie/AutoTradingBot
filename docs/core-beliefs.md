# Core Beliefs

1. **Specs drive development** — Every module has a specification in `specs/`. The spec is the source of truth for behavior. Code implements the spec; divergence is a bug.

2. **Planning precedes execution** — Design decisions are made in specs and docs before code is written. This prevents architectural drift and ensures Claude's prompt strategy is deliberate.

3. **Verification over trust** — Every Claude response is validated (JSON schema, ticker existence, risk limits). Every trade is logged with full audit trail. Trust the data, not assumptions.

4. **Observable behavior defines success** — Performance is measured by concrete metrics (Sharpe ratio, returns, drawdown). Every trading decision has a recorded rationale that can be reviewed.

5. **Context is finite** — Claude has a token budget per prompt. Data must be summarized effectively. The prompt builder is the most critical code in the system.

6. **Build completely, not partially** — Each phase delivers a working, testable subsystem. No half-implemented modules.

7. **Simplicity is strategic** — SQLite over Postgres. Paper trading over broker integration. One daily cycle over continuous monitoring. Complexity is added only when justified by value.
