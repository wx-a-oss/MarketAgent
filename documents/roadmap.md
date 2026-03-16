# Roadmap

## Feature Backlog (Ranked by Execution Order)

Completed items are tracked in [implemented_features.md](./implemented_features.md). This backlog focuses on remaining work.

### 1) Price Intelligence
- `[partial]` Make Price Intelligence the primary downstream intelligence layer:
  - ensure subscribed companies automatically accumulate enough daily reports and weekly reports for strong inputs,
  - improve the price-intelligence prompt/output so it consistently explains price position, company state, active narratives, and what to watch next,
  - tighten the dependency flow from raw news -> daily report -> weekly report -> price intelligence,
  - verify output quality on cloud over multiple scheduled runs before expanding scope.

### 2) Repeated Daily Run Gating
- `[todo]` Add incremental update gating for repeated daily runs:
  - allow multiple market/company runs per day without repeated LLM work when inputs did not change,
  - rerun raw fetch for today only, then skip daily report / clustering / story refresh if no new rows arrived,
  - define the safe duplicate policy before adding midday or pre-market worker runs.

### 3) Earnings Report Module
- `[partial]` Build an earnings module:
  - show the last four earnings events for a subscribed company,
  - capture actual vs estimate, guidance/outlook where available, and short earnings impact analysis,
  - make earnings and post-earnings price reaction easy to review on a timeline.

### 4) Government Document and Macro Report Module
- `[partial]` Add a macro/government module:
  - ingest key releases such as CPI, PPI, payrolls, unemployment, GDP, Fed/FOMC decisions, and policy statements,
  - show recent and upcoming releases in a market calendar view,
  - keep macro/calendar refresh manual-only for now,
  - connect major releases to market relevance and later to market stories.

### 5) Trade System (Later Stage)
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

### 6) Strategy & Plan Board (User Workspace)
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
