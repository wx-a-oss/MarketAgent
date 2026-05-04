# Roadmap

## Feature Backlog (Ranked by Execution Order)

Completed items are tracked in [implemented_features.md](./implemented_features.md). This backlog focuses on remaining work.

### 1) Price Intelligence
- `[partial]` Make Price Intelligence the primary downstream intelligence layer:
  - ensure subscribed companies automatically accumulate enough daily reports for strong inputs,
  - improve the price-intelligence prompt/output so it consistently explains price position, company state, active narratives, and what to watch next,
  - tighten the dependency flow from raw news -> daily report -> price intelligence,
  - verify output quality on cloud over multiple scheduled runs before expanding scope.

### 2) Iterative Reasoning Engine
- `[todo]` Move important LLM analysis flows away from one-shot prompts and toward staged iterative reasoning:
  - break complex analysis into multiple back-and-forth steps instead of asking for the whole answer in one request,
  - persist intermediate questions, answers, assumptions, and reasoning checkpoints so the system keeps a clear thinking line,
  - let later steps consume earlier outputs explicitly, rather than relying on one large undirected context blob,
  - make the reasoning path intentional and inspectable: what matters, why it matters, what it leads to, and what remains uncertain,
  - use this first in Price Intelligence, then expand to other deep-analysis modules where one-shot prompting is too shallow,
  - keep evolving prompts over time from rough draft logic toward stronger multi-step logic instead of treating prompts as static final forms.

### 3) Repeated Daily Run Gating
- `[todo]` Add incremental update gating for repeated daily runs:
  - allow multiple market/company runs per day without repeated LLM work when inputs did not change,
  - rerun raw fetch for today only, then skip daily report / clustering / story refresh if no new rows arrived,
  - define the safe duplicate policy before adding midday or pre-market worker runs.

### 4) Earnings Report Module
- `[done]` Comprehensive LLM-driven earnings analysis via web search:
  - extracts full financials, company-specific metrics, guidance, management quotes, keywords,
  - top-nav Earnings comparison page for multi-company side-by-side view,
  - quarter navigation with +/› buttons to fetch older/newer quarters,
  - incremental refresh that merges with existing data instead of overwriting,
  - decoupled from company subscription — works for any company.

### 5) Government Document and Macro Report Module
- `[partial]` Add a macro/government module:
  - ingest key releases such as CPI, PPI, payrolls, unemployment, GDP, Fed/FOMC decisions, and policy statements,
  - show recent and upcoming releases in a market calendar view,
  - keep macro/calendar refresh manual-only for now,
  - connect major releases to market relevance and later to market stories.

### 6) Trade System (Later Stage)
- `[todo]` Build a new **Trade** tab (major feature):
  - subscribe to a portfolio of company tickers for decision support,
  - evaluate current price position versus historical ranges and moving averages,
  - generate buy/hold/sell recommendations with confidence and rationale,
  - combine signals from company news, broader market news, and market regime,
  - include capital-flow/rotation signals (large capital moving across sectors and asset classes),
  - add a stock “personality profile” layer (stable/volatile behavior, narrative sensitivity, and typical reaction patterns driven by company fundamentals and investor mix).
- `[todo]` Add real-time signal pipeline for fast trading (late stage):
  - use low-cost cloud agents (for example OpenClaw + inexpensive LLMs) to ingest real-time news/social streams,
  - build a low-latency path for fetch -> summarize -> signal scoring -> trade decision support,
  - prioritize cost/performance validation before implementation.
- `[todo]` Solve real-time high-value news ingestion:
  - ingest valuable breaking news and viewpoints from X/Twitter and other fast-moving sources,
  - distinguish high-signal items from noise in real time,
  - make this feed reliable enough to support future fast-decision and trading workflows,
  - use story priority/manual story controls to decide what narratives deserve close tracking.

### 7) Strategy & Plan Board (User Workspace)
- `[todo]` Add a top-level **Plan Board** tab for users to write and track their own trading plans.
- `[todo]` Support flexible plan formats:
  - vague/idea-stage plans,
  - rule-based plans with specific price levels, triggers, and time windows,
  - short-term and long-term strategy plans.
- `[todo]` Add LLM evaluation workflow for each plan:
  - evaluate from multiple perspectives (thesis quality, risk, timing, scenario coverage, execution realism),
  - return confidence bands / estimated win-probability ranges with explicit assumptions.
- `[todo]` Add plan lifecycle tracking:
  - draft -> active -> closed/canceled,
  - version history and update notes,
  - user-friendly timeline view of plan changes and outcomes.
- `[todo]` Add post-trade review loop:
  - compare plan vs. actual outcome,
  - capture lessons learned and strategy adjustments.

### Technical Debt and Polish
- `[partial]` Stock history cache lifecycle polish:
  - daily catch-up/backfill,
  - stale-window refresh policy.
- `[partial]` Unified typography/style system across Market/Company/Person pages (including CJK font fallback).

### Deferred Modules (Low Priority)
- `[deferred]` **Notes Module** — personal notes and annotations. Hidden from top nav. Will revisit when core analysis modules are stable.
- `[deferred]` **Person Module** — user profile and preferences. Hidden from top nav. No current plan; will scope after higher-priority features ship.

## Cloud Migration (Separate Track)

### Remaining Cloud Follow-Up
1. `[todo]` Add stronger operational visibility:
   - worker result history,
   - easier cloud-side inspection of what updated on each run.
2. `[todo]` Add safer repeated-run policy:
   - explicit “no new input, skip expensive LLM stages” gates,
   - then consider midday or pre-market extra runs.
3. `[todo]` Update GitHub Actions workflow dependencies before Node 20 deprecation becomes blocking.

## Detailed Plans

- Company Story Warm-Up + Daily Pipeline: [company_story_warmup_daily_pipeline_plan.md](./company_story_warmup_daily_pipeline_plan.md)
