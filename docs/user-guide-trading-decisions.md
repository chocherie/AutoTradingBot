# How the bot thinks about opening and closing trades

This guide is written for **you**, the human operator. It explains—in plain language—**how AutoTradingBot decides to put trades on and take them off**, and how that lines up with what you see in logs.

There are always **two voices** in the room:

1. **Claude (the “portfolio manager”)** — reads the daily briefing, forms a macro view, and outputs a JSON plan: what to buy, sell, short, cover, or close, and why.
2. **The software (risk and simulation)** — does **not** guess markets. It enforces **hard limits**, tracks **real positions**, and **refuses** orders that would break rules or contradict the book.

If Claude says “sell SPY” but the book shows **no SPY position**, the model’s instruction is ignored. The system is designed to be **boring and literal** about that.

---

## What happens each day (order matters)

Think of one daily cycle as a **conveyor belt**:

1. **Refresh prices** and update the portfolio’s view of the world.
2. **Stops and take-profits** — if a position hits its stop or target, the system **closes it first**, before any new ideas. This is automatic; Claude is not consulted for those exits.
3. **Severe drawdown (“circuit halt”)** — if the portfolio has fallen **very** far from its peak (see `circuit_breaker_halt` in `config/settings.yaml`), the system starts **force-closing** the largest positions to bring risk down. Again: automatic safety rail.
4. **Build the briefing** — portfolio snapshot, market stats (trend and volatility-style fields), economic indicators, and news sentiment go into the prompt Claude sees.
   **Operator note:** the same conveyor-belt story (steps **1–6** above) is repeated at the very top of that user message as `## DAILY PIPELINE`, built in `src/brain/prompt_builder.py`, so the model always sees what already ran and that `positions_to_close` executes before new `orders`.
5. **Claude responds** — one JSON object: regime, macro summary, `orders`, `positions_to_close`, and risk notes.
6. **`positions_to_close` runs first** — for each listed ticker, the simulator tries to **flatten** that exposure (sell longs / cover shorts) with the rationale `claude_positions_to_close`.
7. **`orders` run next** — each `BUY`, `SELL`, `SHORT`, or `COVER` is checked against limits and the **actual** open positions, then **paper-filled** with slippage and commissions if allowed.

So: **machines protect you first**, then **the model proposes**, then **the machine validates and executes**.

---

## Putting trades **on** (opening or adding risk)

### What Claude is trying to optimize

In its system instructions, Claude is cast as a **systematic macro manager** with a **$1M paper book**. The mandate (paraphrased) is:

- Favor **risk-adjusted** returns; **Sharpe** is called out as a primary lens.
- **Cash and doing nothing** are valid choices.
- Use **cross-asset** reasoning (equities, rates, commodities, etc.) and think about **regime** (`RISK_ON`, `RISK_OFF`, and so on in the JSON).
- Options are allowed when specified with strikes/expiry in the schema.

It **must** attach a **stop** and **take-profit** (as percentages) to new risk. The prompt universe is **G7 exchange-traded** names only—no random tickers outside the list it is given that day.

### Hard limits the model cannot override

These come from `config/settings.yaml` under `risk:` and are enforced in code before a trade “counts”:

| Idea | Typical setting | What it means in practice |
|------|-----------------|---------------------------|
| **Position cap** | `max_position_pct` (e.g. 20%) | No single line can dominate the whole book. |
| **Margin** | `max_margin_utilization` (e.g. 60%) | Total margin use cannot exceed this share of what the engine computes. |
| **“Heat”** | `max_portfolio_heat` (e.g. 10%) | The sum of stop-driven risk across positions is capped—prevents dozens of small bets from stacking into one giant drawdown. |
| **Circuit breaker — warning** | `circuit_breaker_warn` (e.g. 15%) | If drawdown from **peak NAV** is **at or above** this, **new longs (`BUY`) are blocked**. Reducing risk (sells/covers) can still be attempted if positions exist. |
| **Circuit breaker — halt** | `circuit_breaker_halt` (e.g. 20%) | Handled **earlier** in the day: the system **closes** chunks of the book automatically—before Claude runs—until risk is back under control. |

**Why you might see “Circuit breaker: drawdown ≥ … blocks new longs” in logs**  
Claude may still *recommend* buys when the book is already wounded. The executor says **no** until the portfolio climbs back enough that peak-to-trough pain is below the warn threshold. That can feel frustrating; it is intentional **capital preservation**.

---

## Taking trades **off** (exiting or reducing)

There are **four** conceptually different exit paths:

### 1. Stop-loss or take-profit (system)

Every open position carries the stop/TP the model (or past run) wired in. If price action **hits** those levels on the data the bot uses that day, the position closes **without** asking Claude again.

### 2. Drawdown halt (system)

If drawdown breaches **`circuit_breaker_halt`**, the program **picks the largest positions** and closes them (up to a small batch) to **stop the bleeding**. This is meant to mimic a **risk officer** pulling risk when the strategy is wrong in aggregate—not a discretionary “market call.”

### 3. `positions_to_close` (Claude’s explicit exit list)

Claude can name tickers in `positions_to_close` when it wants the book **flat in those names**—for example after a regime change or a thesis break. The code runs these **before** new `orders`, so you don’t accidentally add and subtract the same name in the wrong order.

### 4. `SELL` / `COVER` inside `orders`

Same economic outcome as closing, but expressed as an **order** with size and rationale. **Still** subject to the rule: you can only sell what you **own**, and cover what you **owe**.

**Typical log annoyance:**  
`No matching open position for SELL SPY` means the model **thought** it was long SPY (or memory from an older narrative), but SQLite says **no such open line**. The bot guards capital and drops the order.

---

## How to read “thinking” in the outputs

- **`macro_summary` and `market_regime`** — Claude’s **story** for the day. Good for your intuition; not every story becomes a trade.
- **`rationale` and `signal_source` per order** — **why** it wants a line and **what data** it leaned on. Useful when you disagree or want to audit behavior.
- **`risk_notes`** — worries about correlation, concentration, or macro—sometimes the model is **cautious** even while still proposing trades.
- **`order_rejected` in logs** — not moral judgment; usually **constraint** or **book mismatch**. Read the `reason` field.

---

## If you want different behavior

- **Looser or tighter drawdown rules** — edit `circuit_breaker_warn` and `circuit_breaker_halt` in `config/settings.yaml` *knowing you are changing survival vs aggression*.
- **When the job runs** — your Mac’s **LaunchAgent** time is local clock time; `settings.yaml` has a documented **ET after-close** *preference* for the product design, but your machine scheduler may differ—align them on purpose.
- **Deeper behavior** — `src/brain/claude_client.py` (`SYSTEM_PROMPT`) and `src/brain/prompt_builder.py` (user message: **DAILY PIPELINE** preamble + portfolio, market, econ, news, optional prior learnings) are the text-level “constitution” of the manager.

---

## Closing thought

The bot is built so **simple, repeatable rules** (stops, drawdown caps, position limits) **trump** a clever paragraph from the model. **Opening** is “macro brain + strict risk”; **closing** is often **machines first**, then **model discretion**, always checked against the **actual book**. That split is deliberate: it keeps paper trading **explainable** and leaves **you** in charge of tuning how protective you want the rails to be.
